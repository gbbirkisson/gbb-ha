from datetime import timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from homeassistant.components.climate.const import HVACMode
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, State
from pydantic import BaseModel
from pytest import fixture

from custom_components.gbb.climate import Thermostat, async_setup_platform


class Entities(BaseModel):
    sensor: str
    heater_switch: str
    fallback_switch: str


class Data(BaseModel):
    thermostat: Thermostat
    entities: Entities

    class Config:
        arbitrary_types_allowed = True


@fixture
async def test_data(hass: HomeAssistant) -> AsyncGenerator[Data, None]:
    mock_sensor_1 = "sensor.mock_sensor_1"
    mock_switch_1 = "sensor.mock_switch_1"
    mock_switch_2 = "sensor.mock_switch_2"

    hass.states.async_set(mock_sensor_1, "20.0")
    hass.states.async_set(mock_switch_1, STATE_OFF)
    hass.states.async_set(mock_switch_2, STATE_OFF)

    await hass.async_block_till_done()

    entities = Entities(
        sensor=mock_sensor_1, heater_switch=mock_switch_1, fallback_switch=mock_switch_2
    )

    yield Data(
        thermostat=Thermostat(
            hass,
            "test",
            entities.heater_switch,
            entities.sensor,
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
            entities.fallback_switch,
        ),
        entities=entities,
    )


async def test_setup_good(hass: HomeAssistant) -> None:
    callback = MagicMock()
    await async_setup_platform(
        hass,
        {
            "platform": "climate",
            "name": "Test",
            "target_sensor": "sensor.temperature",
            "heater": "input_boolean.radiator",
            "min_temp": 16.0,
            "max_temp": 24.0,
            "ac_mode": False,
            "target_temp": 20.0,
            "hot_tolerance": 0.3,
            "min_cycle_duration": timedelta(minutes=1),
            "initial_hvac_mode": "heat",
            "precision": 1,
            "fallback_on_ratio": 0.2,
            "fallback_interval": timedelta(minutes=1),
            "fallback_force_switch": "input_boolean.force_fallback_mode",
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


async def test_gbb_thermostat_no_fallback(
    test_data: Data,
) -> None:
    with patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_control_heating",
        new_callable=AsyncMock,
    ) as mock_control_heating:
        assert not test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_heating(time=None, force=False)
        mock_control_heating.assert_called_with(time=None, force=False)


async def test_gbb_thermostat_fallback_switch(
    test_data: Data,
) -> None:
    with patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_control_heating",
        new_callable=AsyncMock,
    ) as mock_control_heating, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat.async_write_ha_state",
        new_callable=MagicMock,
    ) as mock_write_state:
        # Enable overwrite
        await test_data.thermostat._async_override_changed(
            Event("test", {"new_state": State(test_data.entities.fallback_switch, STATE_ON)})  # type: ignore
        )
        mock_write_state.assert_called()
        assert test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_heating(time=None, force=False)
        mock_control_heating.assert_not_called()

        # Reset mocks
        mock_control_heating.reset_mock()
        mock_write_state.reset_mock()

        # Disable overwrite
        await test_data.thermostat._async_override_changed(
            Event("test", {"new_state": State(test_data.entities.fallback_switch, STATE_OFF)})  # type: ignore
        )
        mock_write_state.assert_called()
        assert not test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_heating(time=None, force=False)
        mock_control_heating.assert_called()


async def test_gbb_thermostat_sensor_changed(
    test_data: Data,
) -> None:
    with patch(
        "custom_components.gbb.climate.Thermostat._async_control_fallback",
        new_callable=AsyncMock,
    ) as mock_control_fallback, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_sensor_changed",
        new_callable=AsyncMock,
    ) as mock_sensor_changed, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat.async_write_ha_state",
        new_callable=MagicMock,
    ) as mock_write_state:
        # Set sensor to unavailable
        await test_data.thermostat._async_sensor_changed(
            Event("test", {"new_state": State(test_data.entities.sensor, STATE_UNAVAILABLE)})  # type: ignore
        )
        assert test_data.thermostat._is_fallback_mode_active
        mock_control_fallback.assert_called()
        mock_write_state.assert_called()
        mock_sensor_changed.assert_not_called()

        # Reset mocks
        mock_control_fallback.reset_mock()
        mock_write_state.reset_mock()

        # Set sensor to available
        await test_data.thermostat._async_sensor_changed(
            Event("test", {"new_state": State(test_data.entities.sensor, 20.0)})  # type: ignore
        )
        assert not test_data.thermostat._is_fallback_mode_active
        mock_control_fallback.assert_not_called()
        mock_write_state.assert_not_called()
        mock_sensor_changed.assert_called()


async def test_gbb_thermostat_control_fallback(
    test_data: Data,
) -> None:
    with patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._is_device_active",
        new_callable=PropertyMock,
    ) as mock_device_active, patch(
        "homeassistant.components.generic_thermostat.climate.condition.state",
        new_callable=MagicMock,
    ) as mock_long_enough, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_heater_turn_off",
        new_callable=AsyncMock,
    ) as mock_off, patch(
        "homeassistant.components.generic_thermostat.climate.GenericThermostat._async_heater_turn_on",
        new_callable=AsyncMock,
    ) as mock_on:
        # Do nothing when fallback mode is off
        assert not test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_fallback(time=None)
        mock_device_active.assert_not_called()

        # Do nothing the long_enough has not elapsed
        mock_device_active.return_value = True
        mock_long_enough.return_value = False
        test_data.thermostat._fallback_forced = True
        await test_data.thermostat._async_control_fallback(time=None)
        mock_on.assert_not_called()
        mock_off.assert_not_called()

        # Turn off heater after elapsed time
        mock_long_enough.return_value = True
        await test_data.thermostat._async_control_fallback(time=None)
        mock_on.assert_not_called()
        mock_off.assert_called()

        # Turn on heater fter elapsed time
        mock_off.reset_mock()
        mock_device_active.return_value = False
        await test_data.thermostat._async_control_fallback(time=None)
        mock_on.assert_called()
        mock_off.assert_not_called()


async def test_gbb_thermostat_attributes(
    test_data: Data,
) -> None:
    attrs = test_data.thermostat.extra_state_attributes
    assert attrs
    assert attrs.get("fallback_forced")
    assert attrs.get("fallback_interval")
    assert attrs.get("fallback_mode")
    assert attrs.get("fallback_off_duration")
    assert attrs.get("fallback_on_duration")
