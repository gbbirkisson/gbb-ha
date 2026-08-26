from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers.event import EventStateChangedData
from homeassistant.setup import async_setup_component

from custom_components.gbb.climate import Thermostat

GENERIC_THERMOSTAT = "homeassistant.components.generic_thermostat.climate.GenericThermostat"

GOOD_CONFIG = {
    "platform": "gbb",
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
}


@dataclass
class Entities:
    sensor: str
    heater_switch: str
    fallback_switch: str


@dataclass
class Data:
    thermostat: Thermostat
    entities: Entities


def state_changed(entity_id: str, state: str) -> Event[EventStateChangedData]:
    return Event(
        "state_changed",
        {
            "entity_id": entity_id,
            "old_state": None,
            "new_state": State(entity_id, state),
        },
    )


@pytest.fixture
async def test_data(hass: HomeAssistant) -> Data:
    entities = Entities(
        sensor="sensor.mock_sensor_1",
        heater_switch="sensor.mock_switch_1",
        fallback_switch="sensor.mock_switch_2",
    )

    hass.states.async_set(entities.sensor, "20.0")
    hass.states.async_set(entities.heater_switch, STATE_OFF)
    hass.states.async_set(entities.fallback_switch, STATE_OFF)

    await hass.async_block_till_done()

    thermostat = Thermostat(
        name="test",
        heater_entity_id=entities.heater_switch,
        sensor_entity_id=entities.sensor,
        min_temp=10.0,
        max_temp=30.0,
        target_temp=20.0,
        ac_mode=False,
        min_cycle_duration=timedelta(minutes=1),
        cold_tolerance=0.3,
        hot_tolerance=0.3,
        keep_alive=timedelta(minutes=1),
        initial_hvac_mode=HVACMode.HEAT,
        presets={},
        precision=0.1,
        target_temperature_step=0.1,
        unit=UnitOfTemperature.CELSIUS,
        unique_id="test",
        fallback_on_ratio=0.4,
        fallback_interval=timedelta(minutes=1),
        fallback_force_switch_entity_id=entities.fallback_switch,
    )
    thermostat.hass = hass

    return Data(thermostat=thermostat, entities=entities)


async def test_setup_good(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "climate", {"climate": GOOD_CONFIG})
    await hass.async_block_till_done()

    assert hass.states.get("climate.test") is not None


async def test_setup_bad_fallback(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass, "climate", {"climate": {**GOOD_CONFIG, "fallback_on_ratio": 20.0}},
    )
    await hass.async_block_till_done()

    assert not hass.states.async_entity_ids("climate")


async def test_setup_bad(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass, "climate", {"climate": {"platform": "gbb", "bad": "key"}},
    )
    await hass.async_block_till_done()

    assert not hass.states.async_entity_ids("climate")


async def test_gbb_thermostat_no_fallback(test_data: Data) -> None:
    with patch(
        f"{GENERIC_THERMOSTAT}._async_control_heating", new_callable=AsyncMock,
    ) as mock_control_heating:
        assert not test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_heating()
        mock_control_heating.assert_called_with(None, force=False)


async def test_gbb_thermostat_fallback_switch(test_data: Data) -> None:
    with (
        patch(
            f"{GENERIC_THERMOSTAT}._async_control_heating", new_callable=AsyncMock,
        ) as mock_control_heating,
        patch(
            f"{GENERIC_THERMOSTAT}.async_write_ha_state", new_callable=MagicMock,
        ) as mock_write_state,
    ):
        # Enable override
        await test_data.thermostat._async_override_changed(
            state_changed(test_data.entities.fallback_switch, STATE_ON),
        )
        mock_write_state.assert_called()
        assert test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_heating()
        mock_control_heating.assert_not_called()

        mock_control_heating.reset_mock()
        mock_write_state.reset_mock()

        # Disable override
        await test_data.thermostat._async_override_changed(
            state_changed(test_data.entities.fallback_switch, STATE_OFF),
        )
        mock_write_state.assert_called()
        assert not test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_heating()
        mock_control_heating.assert_called()


async def test_gbb_thermostat_sensor_changed(test_data: Data) -> None:
    with (
        patch(
            "custom_components.gbb.climate.Thermostat._async_control_fallback",
            new_callable=AsyncMock,
        ) as mock_control_fallback,
        patch(
            f"{GENERIC_THERMOSTAT}._async_sensor_changed", new_callable=AsyncMock,
        ) as mock_sensor_changed,
        patch(
            f"{GENERIC_THERMOSTAT}.async_write_ha_state", new_callable=MagicMock,
        ) as mock_write_state,
    ):
        # Set sensor to unavailable
        await test_data.thermostat._async_sensor_changed(
            state_changed(test_data.entities.sensor, STATE_UNAVAILABLE),
        )
        assert test_data.thermostat._is_fallback_mode_active
        mock_control_fallback.assert_called()
        mock_write_state.assert_called()
        mock_sensor_changed.assert_not_called()

        mock_control_fallback.reset_mock()
        mock_write_state.reset_mock()

        # Set sensor to available
        await test_data.thermostat._async_sensor_changed(
            state_changed(test_data.entities.sensor, "20.0"),
        )
        assert not test_data.thermostat._is_fallback_mode_active
        mock_control_fallback.assert_not_called()
        mock_write_state.assert_not_called()
        mock_sensor_changed.assert_called()


async def test_gbb_thermostat_control_fallback(test_data: Data) -> None:
    with (
        patch(
            f"{GENERIC_THERMOSTAT}._is_device_active", new_callable=PropertyMock,
        ) as mock_device_active,
        patch(
            "custom_components.gbb.climate.condition.state", new_callable=MagicMock,
        ) as mock_long_enough,
        patch(
            f"{GENERIC_THERMOSTAT}._async_heater_turn_off", new_callable=AsyncMock,
        ) as mock_off,
        patch(
            f"{GENERIC_THERMOSTAT}._async_heater_turn_on", new_callable=AsyncMock,
        ) as mock_on,
    ):
        # Do nothing when fallback mode is off
        assert not test_data.thermostat._is_fallback_mode_active
        await test_data.thermostat._async_control_fallback()
        mock_device_active.assert_not_called()

        # Do nothing while long_enough has not elapsed
        mock_device_active.return_value = True
        mock_long_enough.return_value = False
        test_data.thermostat._fallback_forced = True
        await test_data.thermostat._async_control_fallback()
        mock_on.assert_not_called()
        mock_off.assert_not_called()

        # Turn off heater after elapsed time
        mock_long_enough.return_value = True
        await test_data.thermostat._async_control_fallback()
        mock_on.assert_not_called()
        mock_off.assert_called()

        # Turn on heater after elapsed time
        mock_off.reset_mock()
        mock_device_active.return_value = False
        await test_data.thermostat._async_control_fallback()
        mock_on.assert_called()
        mock_off.assert_not_called()


async def test_gbb_thermostat_attributes(test_data: Data) -> None:
    attrs = test_data.thermostat.extra_state_attributes
    assert attrs
    assert attrs.get("fallback_forced")
    assert attrs.get("fallback_interval")
    assert attrs.get("fallback_mode")
    assert attrs.get("fallback_off_duration")
    assert attrs.get("fallback_on_duration")
