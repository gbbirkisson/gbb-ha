import datetime
import logging
from collections.abc import Mapping
from typing import Any, override

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.climate import PLATFORM_SCHEMA
from homeassistant.components.climate.const import HVACMode
from homeassistant.components.generic_thermostat.climate import (
    CONF_INITIAL_HVAC_MODE,
    CONF_PRECISION,
    CONF_TARGET_TEMP,
    CONF_TEMP_STEP,
    GenericThermostat,
)
from homeassistant.components.generic_thermostat.const import (
    CONF_AC_MODE,
    CONF_COLD_TOLERANCE,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_PRESETS,
    CONF_SENSOR,
    DEFAULT_TOLERANCE,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConditionError
from homeassistant.helpers import condition
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "GBB Thermostat"
CONF_KEEP_ALIVE = "keep_alive"
CONF_FALLBACK_ON_RATIO = "fallback_on_ratio"
CONF_FALLBACK_INTERVAL = "fallback_interval"
CONF_FALLBACK_FORCE_SWITCH = "fallback_force_switch"

# Fallback mode toggles the heater on a duty cycle, so it has to be polled far
# more often than the cycle itself lasts
FALLBACK_POLLS_PER_INTERVAL = 100

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HEATER): cv.entity_id,
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_AC_MODE): cv.boolean,
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MIN_DUR): cv.positive_time_period,
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
        vol.Optional(CONF_KEEP_ALIVE): cv.positive_time_period,
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF],
        ),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE],
        ),
        vol.Optional(CONF_TEMP_STEP): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE],
        ),
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Required(CONF_FALLBACK_ON_RATIO): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=1),
        ),
        vol.Optional(
            CONF_FALLBACK_INTERVAL, default=datetime.timedelta(minutes=60),
        ): cv.positive_time_period,
        vol.Optional(CONF_FALLBACK_FORCE_SWITCH): cv.entity_id,
    },
).extend({vol.Optional(v): vol.Coerce(float) for (_, v) in CONF_PRESETS.items()})


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    _LOGGER.debug("Setup climate: %s", config)

    async_add_entities(
        [
            Thermostat(
                name=config[CONF_NAME],
                heater_entity_id=config[CONF_HEATER],
                sensor_entity_id=config[CONF_SENSOR],
                min_temp=config.get(CONF_MIN_TEMP),
                max_temp=config.get(CONF_MAX_TEMP),
                target_temp=config.get(CONF_TARGET_TEMP),
                ac_mode=config.get(CONF_AC_MODE),
                min_cycle_duration=config.get(CONF_MIN_DUR),
                cold_tolerance=config[CONF_COLD_TOLERANCE],
                hot_tolerance=config[CONF_HOT_TOLERANCE],
                keep_alive=config.get(CONF_KEEP_ALIVE),
                initial_hvac_mode=config.get(CONF_INITIAL_HVAC_MODE),
                presets={
                    key: config[value]
                    for key, value in CONF_PRESETS.items()
                    if value in config
                },
                precision=config.get(CONF_PRECISION),
                target_temperature_step=config.get(CONF_TEMP_STEP),
                unit=hass.config.units.temperature_unit,
                unique_id=config.get(CONF_UNIQUE_ID),
                fallback_on_ratio=config[CONF_FALLBACK_ON_RATIO],
                fallback_interval=config[CONF_FALLBACK_INTERVAL],
                fallback_force_switch_entity_id=config.get(CONF_FALLBACK_FORCE_SWITCH),
            ),
        ],
    )


class Thermostat(GenericThermostat):
    """A GenericThermostat that keeps heating when its sensor goes away."""

    def __init__(
        self,
        *,
        fallback_on_ratio: float,
        fallback_interval: datetime.timedelta,
        fallback_force_switch_entity_id: str | None,
        # Everything else belongs to GenericThermostat, restating its 17 arguments
        # here just to forward them verbatim is worse than passing them through
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        # `max_cycle_duration` and `cycle_cooldown` are required, we do not use them
        super().__init__(max_cycle_duration=None, cycle_cooldown=None, **kwargs)

        self._sensor_available = True
        self._fallback_forced = False
        self._fallback_on_duration = fallback_interval * fallback_on_ratio
        self._fallback_off_duration = fallback_interval * (1 - fallback_on_ratio)
        self._fallback_interval = fallback_interval / FALLBACK_POLLS_PER_INTERVAL
        self._fallback_force_switch_entity_id = fallback_force_switch_entity_id
        self._static_attributes = {
            "fallback_on_duration": str(self._fallback_on_duration),
            "fallback_off_duration": str(self._fallback_off_duration),
            "fallback_interval": str(self._fallback_interval),
        }

        _LOGGER.info(
            (
                "Fallback mode configured. It will run '%s' ON for %s "
                "and OFF for %s in case '%s' becomes unavailable"
            ),
            self.heater_entity_id,
            self._fallback_on_duration,
            self._fallback_off_duration,
            self.sensor_entity_id,
        )

    @override
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_control_fallback,
                self._fallback_interval,
                cancel_on_shutdown=True,
            ),
        )

        if self._fallback_force_switch_entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._fallback_force_switch_entity_id],
                    self._async_override_changed,
                ),
            )

    @property
    def _is_fallback_mode_active(self) -> bool:
        return self._fallback_forced or not self._sensor_available

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return {
            **self._static_attributes,
            "fallback_mode": STATE_ON if self._is_fallback_mode_active else STATE_OFF,
            "fallback_forced": STATE_ON if self._fallback_forced else STATE_OFF,
        }

    @override
    async def _async_control_heating(
        self, _time: datetime.datetime | None = None, force: bool = False,
    ) -> None:
        if not self._is_fallback_mode_active:
            await super()._async_control_heating(_time, force=force)

    @override
    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state is not None and new_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            self._sensor_available = True
            _LOGGER.warning(
                "Sensor '%s' has become available, exiting fallback mode!",
                self.sensor_entity_id,
            )
        else:
            self._sensor_available = False
            _LOGGER.warning(
                "Sensor '%s' has become unavailable, entering fallback mode!",
                self.sensor_entity_id,
            )

        if self._is_fallback_mode_active:
            await self._async_control_fallback()
            self.async_write_ha_state()
        else:
            await super()._async_sensor_changed(event)

    async def _async_control_fallback(self, _time: datetime.datetime | None = None) -> None:
        if not self._is_fallback_mode_active:
            return

        async with self._temp_lock:
            device_active = self._is_device_active
            current_state = STATE_ON if device_active else STATE_OFF
            for_how_long = (
                self._fallback_on_duration if device_active else self._fallback_off_duration
            )

            try:
                long_enough = condition.state(
                    self.hass, self.heater_entity_id, current_state, for_how_long,
                )
            except ConditionError:
                long_enough = False

            if not long_enough:
                return

            _LOGGER.info(
                "Climate '%s' running in fallback mode, turning %s '%s'",
                self.name,
                "off" if device_active else "on",
                self.heater_entity_id,
            )
            if device_active:
                await self._async_heater_turn_off()
            else:
                await self._async_heater_turn_on()

    async def _async_override_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        self._fallback_forced = new_state is not None and new_state.state == STATE_ON
        _LOGGER.debug(
            "Fallback override %s!", "enabled" if self._fallback_forced else "disabled",
        )
        self.async_write_ha_state()
