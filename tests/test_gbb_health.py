from datetime import timedelta
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest import fixture

from custom_components.gbb_health import DOMAIN
from custom_components.gbb_health.sensor import HealthcheckSensor

DEFAULT_CONFIG = {
    DOMAIN: {
        "platform": "sensor",
        "id": "020166bc-5eb3-4a30-9f5a-356d15a3ee09",
        "name": "Test",
    }
}


async def test_gbb_health_setup(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.gbb_health.sensor.HealthcheckSensor.async_added_to_hass"
    ) as add_timer:
        assert await async_setup_component(hass, DOMAIN, DEFAULT_CONFIG) is True
        await hass.async_block_till_done()
        assert add_timer.called


@fixture
async def mocked_healthcheck() -> (
    AsyncGenerator[tuple[AsyncMock, AsyncMock, MagicMock], None]
):
    with patch(
        "custom_components.gbb_health.sensor.HealthcheckSensor.ping",
        new_callable=AsyncMock,
    ) as mock_ping, patch(
        "custom_components.gbb_health.sensor.HealthcheckSensor.notify",
        new_callable=AsyncMock,
    ) as mock_notify, patch(
        "custom_components.gbb_health.sensor.HealthcheckSensor.async_write_ha_state",
        new_callable=MagicMock,
    ) as mock_write_state:
        mock_ping.return_value = AsyncMock()
        mock_notify.return_value = AsyncMock()
        mock_write_state.return_value = AsyncMock()

        yield mock_ping, mock_notify, mock_write_state


@fixture
async def mocked_sensors(
    hass: HomeAssistant,
) -> AsyncGenerator[tuple[str, str, str], None]:
    mock_sensor_1 = "sensor.mock_sensor_1"
    mock_sensor_2 = "sensor.mock_sensor_2"
    mock_sensor_3 = "sensor.mock_sensor_3"

    hass.states.async_set(mock_sensor_1, STATE_ON)
    hass.states.async_set(mock_sensor_2, STATE_ON)
    hass.states.async_set(mock_sensor_3, STATE_ON)

    await hass.async_block_till_done()

    yield mock_sensor_1, mock_sensor_2, mock_sensor_3


async def test_gbb_health_all_good(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    _, _, _ = mocked_sensors

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
    notify.assert_not_called()
    ping.assert_called_with("checked: 3\nfiltered: 0", 0)


async def test_gbb_health_one_down(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    sen1, _, _ = mocked_sensors

    hass.states.async_set(sen1, "unavailable")
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
    notify.assert_called()
    ping.assert_called_with("Entity (sensor.mock_sensor_1): 0:00:00", 1)


async def test_gbb_health_all_down(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    sen1, sen2, sen3 = mocked_sensors

    hass.states.async_set(sen1, "unavailable")
    hass.states.async_set(sen2, "unknown")
    hass.states.async_set(sen3, "none")
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
    notify.assert_called()
    ping.assert_called_with(
        "Entity (sensor.mock_sensor_1): 0:00:00\nEntity (sensor.mock_sensor_2): 0:00:00\nEntity (sensor.mock_sensor_3): 0:00:00",
        3,
    )


async def test_gbb_health_ignored_down(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    sen1, _, _ = mocked_sensors

    hass.states.async_set(sen1, "unavailable")
    await hass.async_block_till_done()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set([sen1]),
        set(),
        set(),
    )

    await t.check(None)
    notify.assert_not_called()
    ping.assert_called_with("checked: 2\nfiltered: 1", 0)


async def test_gbb_health_required_present(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    sen1, _, _ = mocked_sensors

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set([sen1]),
        set(),
    )

    await t.check(None)
    notify.assert_not_called()
    ping.assert_called_with("checked: 3\nfiltered: 0", 0)


async def test_gbb_health_required_missing(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    _, _, _ = mocked_sensors

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
    notify.assert_called()
    ping.assert_called_with("Entity (sensor.not_present): missing", 1)


async def test_gbb_health_include_ok(
    hass: HomeAssistant,
    mocked_healthcheck: tuple[AsyncMock, AsyncMock, MagicMock],
    mocked_sensors: tuple[str, str, str],
) -> None:
    ping, notify, _ = mocked_healthcheck
    sen1, sen2, sen3 = mocked_sensors

    hass.states.async_set(sen1, "unavailable")
    await hass.async_block_till_done()

    t = HealthcheckSensor(
        hass,
        "test",
        "test",
        timedelta(minutes=1),
        timedelta(seconds=0),
        set(),
        set(),
        set([sen2, sen3]),
    )

    await t.check(None)
    notify.assert_not_called()
    ping.assert_called_with("checked: 2\nfiltered: 1", 0)


@patch("custom_components.gbb_health.sensor.HealthcheckSensor.notify")
@patch("custom_components.gbb_health.sensor.HealthcheckSensor.async_write_ha_state")
@patch("custom_components.gbb_health.sensor.aiohttp.ClientSession")
async def test_gbb_health_http_request(
    mock_client_session: MagicMock,
    mock_write_state: MagicMock,
    mock_notify: MagicMock,
    hass: HomeAssistant,
    mocked_sensors: tuple[str, str, str],
) -> None:
    sen1, sen2, sen3 = mocked_sensors

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
    hass.states.async_set(sen1, "unavailable")
    await hass.async_block_till_done()

    await t.check(None)
    session.get.assert_called_with(
        "https://hc-ping.com/test/1", data="Entity (sensor.mock_sensor_1): 0:00:00"
    )
    session.get.reset_mock()
    mock_notify.assert_called()
    mock_notify.reset_mock()
