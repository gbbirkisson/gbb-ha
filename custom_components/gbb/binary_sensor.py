import logging
from functools import cached_property
from typing import Any, Literal, Mapping, cast

import voluptuous as vol
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA, BinarySensorEntity
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing_extensions import override

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "GBB Nordpool"
CONF_NAME = "name"

CONF_NORDPOOL = "nordpool"
CONF_NORDPOOL_SENSOR = "sensor"
CONF_NORDPOOL_SWITCH = "switch"
CONF_NORDPOOL_KNOB = "knob"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): vol.All(str, vol.Length(min=1)),
        vol.Optional(CONF_NORDPOOL): {
            vol.Required(CONF_NORDPOOL_SENSOR): cv.entity_id,
            vol.Required(CONF_NORDPOOL_SWITCH): cv.entity_id,
            vol.Required(CONF_NORDPOOL_KNOB): cv.entity_id,
        },
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    _LOGGER.debug(f"Setup binary sensor: {config}")

    try:
        config = PLATFORM_SCHEMA(config)
    except vol.Error as e:
        _LOGGER.error(f"Setup failed: {e}")
        return

    name = cast(str, config.get(CONF_NAME))
    nordpool = config.get(CONF_NORDPOOL)

    if nordpool:
        async_add_entities(
            [
                NordPoolSensor(
                    hass,
                    name,
                    nordpool.get(CONF_NORDPOOL_SENSOR),
                    nordpool.get(CONF_NORDPOOL_SWITCH),
                    nordpool.get(CONF_NORDPOOL_KNOB),
                )
            ]
        )
    else:
        _LOGGER.error(f"You did not supply '{CONF_NORDPOOL}'")


class NordPoolSensor(BinarySensorEntity):
    def __init__(
        self, hass: HomeAssistant, name: str, sensor: str, switch: str, knob: str
    ) -> None:
        super().__init__()

        self.hass = hass
        self._name = name
        self._sensor = sensor
        self._switch = switch
        self._knob = knob

        self._state = STATE_ON
        self._extra_attributes: dict[str, Any] = {}

        self._nordpool_state: float | None = None
        self._nordpool_prices: list[dict[str, Any]] = []
        self._switch_state = STATE_UNAVAILABLE
        self._knob_state: float | None = None

        self._write_state(
            write=False,
            on=True,
            enabled=False,
            average=-1,
            threshold=-1,
            raw_plan=[],
        )

    def _write_state(
        self,
        write: bool = True,
        *,
        on: bool,
        enabled: bool,
        average: float,
        threshold: float,
        raw_plan: list[Any],
    ) -> None:
        is_on = on if enabled else True
        self._state = STATE_ON if is_on else STATE_OFF
        self._extra_attributes = {
            "enabled": enabled,
            "average": average,
            "threshold": threshold,
            "raw_plan": raw_plan,
        }
        if write:
            self.async_write_ha_state()

    @cached_property
    def name(self) -> str:
        return self._name

    @property  # type: ignore[misc]
    def state(self) -> Literal["on", "off"] | None:
        return self._state  # type: ignore[return-value]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return self._extra_attributes

    @override
    async def async_added_to_hass(self) -> None:
        for entity in [self._sensor, self._switch, self._knob]:
            state = self.hass.states.get(entity)
            if state:
                await self._trigger_update(entity, state)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._sensor, self._switch, self._knob],
                self._async_state_changed,
            )
        )

    async def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]

        if new_state:
            await self._trigger_update(entity_id, new_state)

    async def _trigger_update(self, entity_id: str, state: State) -> None:
        _LOGGER.debug(f"Got update for: {entity_id} -> {state.state}")
        if entity_id == self._sensor:
            try:
                self._nordpool_state = float(state.state)
            except ValueError:
                self._nordpool_state = None
            today: list[dict[str, Any]] = state.attributes.get("raw_today", [])
            tomorrow: list[dict[str, Any]] = state.attributes.get("raw_tomorrow", [])
            self._nordpool_prices = today
            if tomorrow:
                self._nordpool_prices.extend(tomorrow)

        elif entity_id == self._switch:
            self._switch_state = state.state

        elif entity_id == self._knob:
            try:
                self._knob_state = float(state.state)
            except ValueError:
                self._knob_state = None

        else:
            _LOGGER.error(f"Got bad entity_id: {entity_id}")

        await self._update_state()

    async def _update_state(self) -> None:
        enabled = self._switch_state == STATE_ON

        prices: list[float] = []
        if self._nordpool_prices:
            for p in self._nordpool_prices:
                v: float | None = p.get("value")
                if v:
                    prices.append(v)
                else:
                    # Disable if we see any problem
                    enabled = False
        else:
            # Disable if we dont have any prices
            enabled = False

        if not self._nordpool_state or not self._knob_state or not prices:
            self._write_state(
                on=True,
                enabled=False,
                average=-1,
                threshold=-1,
                raw_plan=[],
            )
            return

        average = sum(prices) / len(prices)
        threshold = average * self._knob_state
        for p in self._nordpool_prices:
            val = p.get("value")
            if val:
                p["state"] = 1 if self._calc_on(val, threshold) else 0

        _LOGGER.debug(f"Price: {self._nordpool_state}, Threshold: {threshold}")
        self._write_state(
            on=self._calc_on(self._nordpool_state, threshold),
            enabled=enabled,
            average=average,
            threshold=threshold,
            raw_plan=self._nordpool_prices,
        )

        self.async_write_ha_state()

    def _calc_on(self, val: str | float, threshold: float) -> bool:
        tmp = val
        if isinstance(tmp, str):
            tmp = float(tmp)
        return tmp < threshold
