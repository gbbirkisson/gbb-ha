import logging
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, List, Mapping

import aiohttp
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing_extensions import override

_LOGGER = logging.getLogger(__name__)

CONF_NAME = "name"
CONF_ID = "id"
CONF_INTERVAL = "interval"
CONF_GRACE_PERIOD = "grace_period"
CONF_IGNORE = "ignore"
CONF_REQUIRED = "required"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): vol.All(str, vol.Length(min=36, max=36)),
        vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
        vol.Optional(CONF_INTERVAL): cv.positive_time_period,
        vol.Optional(CONF_GRACE_PERIOD): cv.positive_time_period,
        vol.Optional(CONF_IGNORE): vol.All([str], vol.Length(min=0)),
        vol.Optional(CONF_REQUIRED): vol.All([str], vol.Length(min=0)),
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    if discovery_info is not None:
        return

    _LOGGER.debug(f"adding sensor with: {config}")

    id = config.get(CONF_ID) or "<FAIL>"
    name = config.get(CONF_NAME) or "<FAIL>"
    interval = config.get(CONF_INTERVAL) or timedelta(minutes=1)
    grace_period = config.get(CONF_GRACE_PERIOD) or timedelta(hours=1)
    ignore = config.get(CONF_IGNORE) or []
    required = config.get(CONF_REQUIRED) or []

    async_add_entities(
        [HealthcheckSensor(hass, id, name, interval, grace_period, ignore, required)]
    )


def _now() -> datetime:
    return datetime.now().astimezone()


class HealthcheckSensor(SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        id: str,
        name: str,
        interval: timedelta,
        grace_period: timedelta,
        ignore: List[str],
        required: List[str],
    ) -> None:
        self._hass = hass
        self._name = name
        self._url = f"https://hc-ping.com/{id}"
        self._interval = interval
        self._grace_period = grace_period
        self._ignore = ignore
        self._required = set(required)
        self._state = 0
        self._extra_attributes: dict[str, list[str]] = {"missing": [], "failing": []}

    @cached_property
    def name(self) -> str:
        return self._name

    @property  # type: ignore[misc]
    def state(self) -> int:
        return self._state

    @override
    async def async_added_to_hass(self) -> None:
        async_track_time_interval(self._hass, self._check, self._interval)

    @cached_property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return self._extra_attributes

    async def _check(self, _: datetime | None = None) -> None:
        all = self._hass.states.async_all()

        missing = list(self._required - set([s.entity_id for s in all if s.entity_id]))
        _LOGGER.debug(f"missing entities: {missing}")
        self._extra_attributes.update({"missing": missing})
        missing = [f"Entity ({s}): missing" for s in missing]

        failing = [s for s in all if s.state in ["unavailable", "unknown", "none"]]
        failing = [s for s in failing if s.entity_id not in self._ignore]
        failing = [s for s in failing if _now() - s.last_updated > self._grace_period]
        _LOGGER.debug(f"failing entities: {failing}")
        self._extra_attributes.update({"failing": [s.entity_id for s in failing]})
        failing = [
            f"{s.attributes.get('friendly_name', 'Entity')} ({s.entity_id}): {str(_now() - s.last_updated)[:-7]}"
            for s in failing
        ]

        total = missing + failing

        self._state = len(total)
        message = "\n".join(total)

        async with aiohttp.ClientSession() as session:
            url = f"{self._url}/{len(total)}"
            _LOGGER.debug(f"hc call: {url}")
            async with session.get(url, data=message) as res:
                _LOGGER.debug(f"hc response: {res.status}")

        if len(total) > 0:
            _LOGGER.debug(f"create notification: {len(total)}")
            await self._hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": self._name,
                    "title": f"{self._name} failed",
                    "message": message,
                },
            )

        self.async_write_ha_state()
