from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    ENTITY_MATCH_NONE,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.gbb.sensor import HealthcheckSensor

HEALTHCHECK_ID = "020166bc-5eb3-4a30-9f5a-356d15a3ee09"


@dataclass
class Mocks:
    ping: AsyncMock
    notify: AsyncMock
    write_state: MagicMock


def make_sensor(
    hass: HomeAssistant,
    *,
    ignore: set[str] | None = None,
    required: set[str] | None = None,
    include: set[str] | None = None,
) -> HealthcheckSensor:
    sensor = HealthcheckSensor(
        name="test",
        healthcheck_id="test",
        interval=timedelta(minutes=1),
        grace_period=timedelta(seconds=0),
        ignore=ignore or set(),
        required=required or set(),
        include=include or set(),
    )
    sensor.hass = hass
    return sensor


@pytest.fixture
async def test_data(hass: HomeAssistant) -> AsyncGenerator[Mocks]:
    with (
        patch(
            "custom_components.gbb.sensor.HealthcheckSensor.ping",
            new_callable=AsyncMock,
        ) as mock_ping,
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            new_callable=AsyncMock,
        ) as mock_notify,
        patch(
            "custom_components.gbb.sensor.HealthcheckSensor.async_write_ha_state",
            new_callable=MagicMock,
        ) as mock_write_state,
    ):
        yield Mocks(ping=mock_ping, notify=mock_notify, write_state=mock_write_state)


@pytest.fixture
async def test_sensors(hass: HomeAssistant) -> list[str]:
    sensors = [
        "sensor.mock_sensor_1",
        "sensor.mock_sensor_2",
        "sensor.mock_sensor_3",
    ]
    for sensor in sensors:
        hass.states.async_set(sensor, STATE_ON)

    await hass.async_block_till_done()

    return sensors


async def test_setup_good(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass,
        "sensor",
        {"sensor": {"platform": "gbb", "healthcheck": {"id": HEALTHCHECK_ID}}},
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.gbb_healthcheck") is not None


async def test_setup_bad(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass,
        "sensor",
        {"sensor": {"platform": "gbb", "bad": "key"}},
    )
    await hass.async_block_till_done()

    assert not hass.states.async_entity_ids("sensor")


async def test_setup_bad_healthcheck_id(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass,
        "sensor",
        {"sensor": {"platform": "gbb", "healthcheck": {"id": "too-short"}}},
    )
    await hass.async_block_till_done()

    assert not hass.states.async_entity_ids("sensor")


async def test_gbb_health_all_good(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    t = make_sensor(hass)
    assert t.name == "test"
    assert t.native_value == 0

    await t.check()
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 3\nfiltered: 0", 0)


async def test_gbb_health_one_down(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    t = make_sensor(hass)

    await t.check()
    test_data.notify.assert_called()
    test_data.ping.assert_called_with("Entity (sensor.mock_sensor_1): 0:00:00", 1)


async def test_gbb_health_all_down(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], STATE_UNAVAILABLE)
    hass.states.async_set(test_sensors[1], STATE_UNKNOWN)
    hass.states.async_set(test_sensors[2], ENTITY_MATCH_NONE)
    await hass.async_block_till_done()

    t = make_sensor(hass)

    await t.check()
    test_data.notify.assert_called()
    test_data.ping.assert_called_with(
        "Entity (sensor.mock_sensor_1): 0:00:00\n"
        "Entity (sensor.mock_sensor_2): 0:00:00\n"
        "Entity (sensor.mock_sensor_3): 0:00:00",
        3,
    )


async def test_gbb_health_ignored_down(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    t = make_sensor(hass, ignore={test_sensors[0]})

    await t.check()
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 2\nfiltered: 1", 0)


async def test_gbb_health_required_present(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    t = make_sensor(hass, required={test_sensors[0]})

    await t.check()
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 3\nfiltered: 0", 0)


async def test_gbb_health_required_missing(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    t = make_sensor(hass, required={"sensor.not_present"})

    await t.check()
    test_data.notify.assert_called()
    test_data.ping.assert_called_with("Entity (sensor.not_present): missing", 1)


async def test_gbb_health_include_ok(
    hass: HomeAssistant,
    test_data: Mocks,
    test_sensors: list[str],
) -> None:
    hass.states.async_set(test_sensors[0], STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    t = make_sensor(hass, include={test_sensors[1], test_sensors[2]})

    await t.check()
    test_data.notify.assert_not_called()
    test_data.ping.assert_called_with("checked: 2\nfiltered: 1", 0)


@patch("custom_components.gbb.sensor.HealthcheckSensor.notify")
@patch("custom_components.gbb.sensor.HealthcheckSensor.async_write_ha_state")
@patch("custom_components.gbb.sensor.async_get_clientsession")
async def test_gbb_health_http_request(
    mock_get_clientsession: MagicMock,
    mock_write_state: MagicMock,
    mock_notify: MagicMock,
    hass: HomeAssistant,
    test_sensors: list[str],
) -> None:
    session = MagicMock()
    session.get.return_value.__aenter__.return_value = SimpleNamespace(status=500)
    mock_get_clientsession.return_value = session

    t = make_sensor(hass)

    # All good
    await t.check()
    session.get.assert_called_with(
        "https://hc-ping.com/test/0", data="checked: 3\nfiltered: 0",
    )
    session.get.reset_mock()
    mock_notify.assert_not_called()

    # One sensor down
    hass.states.async_set(test_sensors[0], STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    await t.check()
    session.get.assert_called_with(
        "https://hc-ping.com/test/1", data="Entity (sensor.mock_sensor_1): 0:00:00",
    )
    mock_notify.assert_called()
