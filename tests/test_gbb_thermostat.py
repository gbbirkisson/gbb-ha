from datetime import timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.climate.const import HVACMode
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.setup import async_setup_component
from pytest import fixture

from custom_components.gbb_thermostat import DOMAIN
from custom_components.gbb_thermostat.climate import Thermostat

DEFAULT_CONFIG = {
    DOMAIN: {
        "platform": "sensor",
        "id": "020166bc-5eb3-4a30-9f5a-356d15a3ee09",
        "name": "Test",
        "target_sensor": "sensor.temperature",
        "heater": "input_boolean.radiator",
        "min_temp": 16.0,
        "max_temp": 24.0,
        "ac_mode": False,
        "target_temp": 20.0,
        "hot_tolerance": 0.3,
        "min_cycle_duration": "00:00:00",
        "initial_hvac_mode": "heat",
        "precision": 1,
        "fallback_on_ratio": 0.2,
        "fallback_interval": "00:01:00",
        "fallback_force_switch": "input_boolean.force_fallback_mode",
    }
}


async def test_gbb_thermostat_setup(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, DEFAULT_CONFIG) is True
    await hass.async_block_till_done()


@fixture
async def mocked_entities(
    hass: HomeAssistant,
) -> AsyncGenerator[tuple[str, str, str], None]:
    mock_sensor_1 = "sensor.mock_sensor_1"
    mock_switch_1 = "sensor.mock_switch_1"
    mock_switch_2 = "sensor.mock_switch_2"

    hass.states.async_set(mock_sensor_1, "20.0")
    hass.states.async_set(mock_switch_1, STATE_OFF)
    hass.states.async_set(mock_switch_2, STATE_OFF)

    await hass.async_block_till_done()

    yield mock_sensor_1, mock_switch_1, mock_switch_2


@fixture
async def mocked_thermostat() -> AsyncGenerator[
    tuple[AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock, AsyncMock, MagicMock],
    None,
]:
    with patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_control_heating",
        new_callable=AsyncMock,
    ) as mock_control_heating, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_sensor_changed",
        new_callable=AsyncMock,
    ) as mock_sensor_changed, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._is_device_active",
        new_callable=MagicMock,
    ) as mock_device_active, patch(
        "homeassistant.components.generic_thermostat.climate.condition.state",
        new_callable=MagicMock,
    ) as mock_condition, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_heater_turn_off",
        new_callable=AsyncMock,
    ) as mock_off, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_heater_turn_on",
        new_callable=AsyncMock,
    ) as mock_on, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat.async_write_ha_state",
        new_callable=MagicMock,
    ) as mock_write_state:
        mock_control_heating.return_value = AsyncMock()
        mock_sensor_changed.return_value = AsyncMock()
        mock_device_active.return_value = True
        mock_condition.return_value = True
        mock_off.return_value = AsyncMock()
        mock_on.return_value = AsyncMock()
        mock_write_state.return_value = AsyncMock()

        yield (
            mock_control_heating,
            mock_sensor_changed,
            mock_device_active,
            mock_condition,
            mock_off,
            mock_on,
            mock_write_state,
        )


async def test_gbb_thermostat_no_fallback(
    hass: HomeAssistant,
    mocked_thermostat: tuple[
        AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock, AsyncMock, MagicMock
    ],
    mocked_entities: tuple[str, str, str],
) -> None:
    heating, _, _, _, _, _, _ = mocked_thermostat
    sensor, heater_switch, force_fallback = mocked_entities

    t = Thermostat(
        hass,
        "test",
        heater_switch,
        sensor,
        10.0,
        30.0,
        20.0,
        False,
        timedelta(minutes=1),
        0.3,
        0.3,
        timedelta(minutes=1),
        HVACMode.HEAT,
        {},
        0.1,
        0.1,
        UnitOfTemperature.CELSIUS,
        "test",
        0.4,
        timedelta(minutes=1),
        force_fallback,
    )

    await t._async_control_heating(time=None, force=False)
    heating.assert_called_with(time=None, force=False)


async def test_gbb_thermostat_fallback_off(
    hass: HomeAssistant,
    mocked_thermostat: tuple[
        AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock, AsyncMock, MagicMock
    ],
    mocked_entities: tuple[str, str, str],
) -> None:
    heating, _, _, condition, off, on, write_state = mocked_thermostat
    sensor, heater_switch, force_fallback = mocked_entities

    t = Thermostat(
        hass,
        "test",
        heater_switch,
        sensor,
        10.0,
        30.0,
        20.0,
        False,
        timedelta(minutes=1),
        0.3,
        0.3,
        timedelta(minutes=1),
        HVACMode.HEAT,
        {},
        0.1,
        0.1,
        UnitOfTemperature.CELSIUS,
        "test",
        0.4,
        timedelta(minutes=1),
        force_fallback,
    )
    t._is_device_active = True  # type: ignore

    hass.states.async_set(sensor, "unavailable")
    await hass.async_block_till_done()
    await t._async_sensor_changed(
        Event("test", {"new_state": State(sensor, STATE_UNAVAILABLE)})  # type: ignore
    )
    on.assert_not_called()
    off.assert_called_once()


async def test_gbb_thermostat_fallback_on(
    hass: HomeAssistant,
    mocked_thermostat: tuple[
        AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock, AsyncMock, MagicMock
    ],
    mocked_entities: tuple[str, str, str],
) -> None:
    heating, _, _, condition, off, on, write_state = mocked_thermostat
    sensor, heater_switch, force_fallback = mocked_entities

    t = Thermostat(
        hass,
        "test",
        heater_switch,
        sensor,
        10.0,
        30.0,
        20.0,
        False,
        timedelta(minutes=1),
        0.3,
        0.3,
        timedelta(minutes=1),
        HVACMode.HEAT,
        {},
        0.1,
        0.1,
        UnitOfTemperature.CELSIUS,
        "test",
        0.4,
        timedelta(minutes=1),
        force_fallback,
    )
    t._is_device_active = False  # type: ignore

    hass.states.async_set(sensor, "unavailable")
    await hass.async_block_till_done()
    await t._async_sensor_changed(
        Event("test", {"new_state": State(sensor, STATE_UNAVAILABLE)})  # type: ignore
    )
    on.assert_called_once()
    off.assert_not_called()


async def test_gbb_thermostat_override_on(
    hass: HomeAssistant,
    mocked_thermostat: tuple[
        AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock, AsyncMock, MagicMock
    ],
    mocked_entities: tuple[str, str, str],
) -> None:
    _, _, _, _, _, _, _ = mocked_thermostat
    sensor, heater_switch, force_fallback = mocked_entities

    t = Thermostat(
        hass,
        "test",
        heater_switch,
        sensor,
        10.0,
        30.0,
        20.0,
        False,
        timedelta(minutes=1),
        0.3,
        0.3,
        timedelta(minutes=1),
        HVACMode.HEAT,
        {},
        0.1,
        0.1,
        UnitOfTemperature.CELSIUS,
        "test",
        0.4,
        timedelta(minutes=1),
        force_fallback,
    )
    await t._async_override_changed(
        Event("test", {"new_state": State(sensor, STATE_ON)})  # type: ignore
    )
    assert t._fallback_forced


async def test_gbb_thermostat_override_off(
    hass: HomeAssistant,
    mocked_thermostat: tuple[
        AsyncMock, AsyncMock, MagicMock, MagicMock, AsyncMock, AsyncMock, MagicMock
    ],
    mocked_entities: tuple[str, str, str],
) -> None:
    _, _, _, _, _, _, _ = mocked_thermostat
    sensor, heater_switch, force_fallback = mocked_entities

    t = Thermostat(
        hass,
        "test",
        heater_switch,
        sensor,
        10.0,
        30.0,
        20.0,
        False,
        timedelta(minutes=1),
        0.3,
        0.3,
        timedelta(minutes=1),
        HVACMode.HEAT,
        {},
        0.1,
        0.1,
        UnitOfTemperature.CELSIUS,
        "test",
        0.4,
        timedelta(minutes=1),
        force_fallback,
    )
    await t._async_override_changed(
        Event("test", {"new_state": State(sensor, STATE_OFF)})  # type: ignore
    )
    assert not t._fallback_forced
