from datetime import timedelta
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from pydantic import BaseModel
from pytest import fixture

from custom_components.gbb.sensor import HealthcheckSensor, async_setup_platform


class Mocks(BaseModel):
    ping: AsyncMock
    notify: AsyncMock
    write_state: MagicMock

    class Config:
        arbitrary_types_allowed = True


@fixture
async def test_data(hass: HomeAssistant) -> AsyncGenerator[Mocks, None]:
    with patch(
        "custom_components.gbb.sensor.HealthcheckSensor.ping",
        new_callable=AsyncMock,
    ) as mock_ping, patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ) as mock_notify, patch(
        "custom_components.gbb.sensor.HealthcheckSensor.async_write_ha_state",
        new_callable=MagicMock,
    ) as mock_write_state:
        mock_ping.return_value = AsyncMock()
        mock_notify.return_value = AsyncMock()
        mock_write_state.return_value = AsyncMock()

        yield Mocks(
            ping=mock_ping,
            notify=mock_notify,
            write_state=mock_write_state,
        )


@fixture
async def test_sensors(
    hass: HomeAssistant,
) -> AsyncGenerator[list[str], None]:
    mock_sensor_1 = "sensor.mock_sensor_1"
    mock_sensor_2 = "sensor.mock_sensor_2"
    mock_sensor_3 = "sensor.mock_sensor_3"

    hass.states.async_set(mock_sensor_1, STATE_ON)
    hass.states.async_set(mock_sensor_2, STATE_ON)
    hass.states.async_set(mock_sensor_3, STATE_ON)

    await hass.async_block_till_done()

    yield [mock_sensor_1, mock_sensor_2, mock_sensor_3]


async def test_setup_good(hass: HomeAssistant) -> None:
    callback = MagicMock()
    await async_setup_platform(
        hass,
        {
            "platform": "sensor",
            "id": "020166bc-5eb3-4a30-9f5a-356d15a3ee09",
            "name": "Test",
        },
        callback,
        None,
    )
    callback.assert_called_once()


async def test_setup_bad(hass: HomeAssistant) -> None:
    callback = MagicMock()
    await async_setup_platform(
        hass,
        {
            "bad": "key",
        },
        callback,
        None,
    )
    callback.assert_not_called()


async def test_gbb_health_all_good(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(),
        set(),
    )
    assert t.name == "test"
    assert t.state == 0

    await t.check(None)
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 3\nfiltered: 0", 0)


async def test_gbb_health_one_down(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], "unavailable")
    await hass.async_block_till_done()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(),
        set(),
    )

    await t.check(None)
    test_data.notify.assert_called()
    test_data.ping.assert_called_with("Entity (sensor.mock_sensor_1): 0:00:00", 1)


async def test_gbb_health_all_down(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], "unavailable")
    hass.states.async_set(test_sensors[1], "unknown")
    hass.states.async_set(test_sensors[2], "none")
    await hass.async_block_till_done()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(),
        set(),
    )

    await t.check(None)
    test_data.notify.assert_called()
    test_data.ping.assert_called_with(
        "Entity (sensor.mock_sensor_1): 0:00:00\nEntity (sensor.mock_sensor_2): 0:00:00\nEntity (sensor.mock_sensor_3): 0:00:00",
        3,
    )


async def test_gbb_health_ignored_down(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], "unavailable")
    await hass.async_block_till_done()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set([test_sensors[0]]),
        set(),
        set(),
    )

    await t.check(None)
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 2\nfiltered: 1", 0)


async def test_gbb_health_required_present(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set([test_sensors[0]]),
        set(),
    )

    await t.check(None)
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 3\nfiltered: 0", 0)


async def test_gbb_health_required_missing(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(["sensor.not_present"]),
        set(),
    )

    await t.check(None)
    test_data.notify.assert_called()
    test_data.ping.assert_called_with("Entity (sensor.not_present): missing", 1)


async def test_gbb_health_include_ok(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], "unavailable")
    await hass.async_block_till_done()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(),
        set([test_sensors[1], test_sensors[2]]),
    )

    await t.check(None)
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 2\nfiltered: 1", 0)


@patch("custom_components.gbb.sensor.HealthcheckSensor.notify")
@patch("custom_components.gbb.sensor.HealthcheckSensor.async_write_ha_state")
@patch("custom_components.gbb.sensor.aiohttp.ClientSession")
async def test_gbb_health_http_request(
    mock_client_session: MagicMock,
    mock_write_state: MagicMock,
    mock_notify: MagicMock,
    hass: HomeAssistant,
    test_sensors: list[str],
) -> None:
    session = MagicMock()
    session.get.return_value.__aenter__.return_value = SimpleNamespace(status=500)
    mock_client_session.return_value.__aenter__.return_value = session

    mock_write_state.return_value = AsyncMock()
    mock_notify.return_value = AsyncMock()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(),
        set(),
    )

    # All good
    await t.check(None)
    session.get.assert_called_with(
        "https://hc-ping.com/test/0", data="checked: 3\nfiltered: 0"
    )
    session.get.reset_mock()
    mock_notify.assert_not_called()
    mock_notify.reset_mock()

    # One sensor down
    hass.states.async_set(test_sensors[0], "unavailable")
    await hass.async_block_till_done()

    await t.check(None)
    session.get.assert_called_with(
        "https://hc-ping.com/test/1", data="Entity (sensor.mock_sensor_1): 0:00:00"
    )
    session.get.reset_mock()
    mock_notify.assert_called()
    mock_notify.reset_mock()
