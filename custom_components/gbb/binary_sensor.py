import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
from homeassistant.const import CONF_NAME, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import EventStateChangedData, async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "GBB Nordpool"

CONF_NORDPOOL = "nordpool"
CONF_NORDPOOL_SENSOR = "sensor"
CONF_NORDPOOL_AVERAGE = "average"
CONF_NORDPOOL_SWITCH = "switch"
CONF_NORDPOOL_KNOB = "knob"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): vol.All(str, vol.Length(min=1)),
        vol.Required(CONF_NORDPOOL): {
            vol.Required(CONF_NORDPOOL_SENSOR): cv.entity_id,
            vol.Required(CONF_NORDPOOL_AVERAGE): cv.entity_id,
            vol.Required(CONF_NORDPOOL_SWITCH): cv.entity_id,
            vol.Required(CONF_NORDPOOL_KNOB): cv.entity_id,
        },
    },
)


async def async_setup_platform(
    _hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    _LOGGER.debug("Setup binary sensor: %s", config)

    nordpool = config[CONF_NORDPOOL]
    async_add_entities(
        [
            NordPoolSensor(
                name=config[CONF_NAME],
                sensor=nordpool[CONF_NORDPOOL_SENSOR],
                average=nordpool[CONF_NORDPOOL_AVERAGE],
                switch=nordpool[CONF_NORDPOOL_SWITCH],
                knob=nordpool[CONF_NORDPOOL_KNOB],
            ),
        ],
    )


class NordPoolSensor(BinarySensorEntity):
    """Turns off while the nordpool price is above a share of the daily average."""

    def __init__(
        self, *, name: str, sensor: str, average: str, switch: str, knob: str,
    ) -> None:
        super().__init__()

        self._attr_name = name
        self._sensor = sensor
        self._average = average
        self._switch = switch
        self._knob = knob

        self._price: float | None = None
        self._average_state: float | None = None
        self._switch_state = STATE_UNAVAILABLE
        self._knob_state: float | None = None

        # Start out disabled, we know nothing about prices yet
        self._attr_is_on = True
        self._attr_extra_state_attributes = _disabled_attributes()

    @property
    def _watched(self) -> list[str]:
        return [self._sensor, self._average, self._switch, self._knob]

    @override
    async def async_added_to_hass(self) -> None:
        for entity in self._watched:
            state = self.hass.states.get(entity)
            if state:
                self._read_state(entity, state)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._watched, self._async_state_changed,
            ),
        )
        self._update_state()

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state:
            self._read_state(event.data["entity_id"], new_state)
            self._update_state()

    @callback
    def _read_state(self, entity_id: str, state: State) -> None:
        _LOGGER.debug("Got update for: %s -> %s", entity_id, state.state)

        if entity_id == self._sensor:
            self._price = _as_float(state.state)
        elif entity_id == self._average:
            self._average_state = _as_float(state.state)
        elif entity_id == self._switch:
            self._switch_state = state.state
        elif entity_id == self._knob:
            self._knob_state = _as_float(state.state)
        else:
            _LOGGER.error("Got bad entity_id: %s", entity_id)

    @callback
    def _update_state(self) -> None:
        if not self._price or not self._average_state or not self._knob_state:
            self._disable()
            return

        threshold = self._average_state * self._knob_state
        enabled = self._switch_state == STATE_ON

        _LOGGER.debug("Price: %s, Threshold: %s", self._price, threshold)
        # When disabled the sensor stays on, so consumers keep running as usual
        self._attr_is_on = self._price < threshold if enabled else True
        self._attr_extra_state_attributes = {
            "enabled": enabled,
            "average": self._average_state,
            "threshold": threshold,
        }
        self.async_write_ha_state()

    @callback
    def _disable(self) -> None:
        self._attr_is_on = True
        self._attr_extra_state_attributes = _disabled_attributes()
        self.async_write_ha_state()


def _disabled_attributes() -> dict[str, Any]:
    """Attributes for when nordpool control is off, or prices are unusable."""
    return {"enabled": False, "average": -1, "threshold": -1}


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
