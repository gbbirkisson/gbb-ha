import fnmatch
import logging
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, Mapping, Set

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
CONF_INCLUDE = "include"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): vol.All(str, vol.Length(min=36, max=36)),
        vol.Required(CONF_NAME): vol.All(str, vol.Length(min=1)),
        vol.Optional(CONF_INTERVAL): cv.positive_time_period,
        vol.Optional(CONF_GRACE_PERIOD): cv.positive_time_period,
        vol.Optional(CONF_IGNORE): vol.All([str], vol.Length(min=0)),
        vol.Optional(CONF_REQUIRED): vol.All([str], vol.Length(min=0)),
        vol.Optional(CONF_INCLUDE): vol.All([str], vol.Length(min=0)),
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery: DiscoveryInfoType | None = None,
) -> None:
    if discovery and not config:
        config = discovery

    _LOGGER.debug(f"setup sensor: {config}")

    try:
        PLATFORM_SCHEMA(config)
    except vol.Error as e:
        _LOGGER.error(f"setup failed: {e}")
        return

    id = config.get(CONF_ID) or ""
    name = config.get(CONF_NAME) or ""
    interval = config.get(CONF_INTERVAL) or timedelta(minutes=1)
    grace_period = config.get(CONF_GRACE_PERIOD) or timedelta(hours=1)
    ignore = set(config.get(CONF_IGNORE) or [])
    required = set(config.get(CONF_REQUIRED) or [])
    include = set(config.get(CONF_INCLUDE) or [])

    async_add_entities(
        [
            HealthcheckSensor(
                hass, id, name, interval, grace_period, ignore, required, include
            )
        ]
    )


def wildcard_filter(all: list[str], patterns: set[str]) -> tuple[set[str], set[str]]:
    match = set([])
    for p in patterns:
        match.update(fnmatch.filter(all, p))
    no_match = set(all) - match
    return match, no_match


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
        ignore: Set[str],
        required: Set[str],
        include: Set[str],
    ) -> None:
        self._hass = hass
        self._name = name
        self._url = f"https://hc-ping.com/{id}"
        self._interval = interval
        self._grace_period = grace_period
        self._ignore = ignore
        self._required = required
        self._include = include
        self._state = 0
        self._extra_attributes: dict[str, Any] = {
            "missing": [],
            "failing": [],
            "checked": 0,
        }

    @cached_property
    def name(self) -> str:
        return self._name

    @property  # type: ignore[misc]
    def state(self) -> int:
        return self._state

    @override
    async def async_added_to_hass(self) -> None:
        async_track_time_interval(self._hass, self.check, self._interval)

    @cached_property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return self._extra_attributes

    async def check(self, _: datetime | None = None) -> None:
        all = self._hass.states.async_all()

        # filter out everything except those to include
        if self._include:
            _LOGGER.debug(f"filtering entities to only match: {self._include}")
            m, _n = wildcard_filter([s.entity_id for s in all], self._include)
            all = [s for s in all if s.entity_id in m]

        # filter out those to ignore
        if self._ignore:
            _m, n = wildcard_filter([s.entity_id for s in all], self._ignore)
            all = [s for s in all if s.entity_id in n]

        self._extra_attributes.update({"checked": len(all)})

        # mark those that are failing
        failing = [s for s in all if s.state in ["unavailable", "unknown", "none"]]

        # filter out those that are within the grace period
        failing = [s for s in failing if _now() - s.last_updated > self._grace_period]

        # find missing
        missing = list(self._required - set([s.entity_id for s in all if s.entity_id]))
        _LOGGER.debug(f"missing entities: {missing}")
        self._extra_attributes.update({"missing": missing})
        missing = [f"Entity ({s}): missing" for s in missing]

        _LOGGER.debug(f"failing entities: {failing}")
        self._extra_attributes.update({"failing": [s.entity_id for s in failing]})
        failing = [
            f"{s.attributes.get('friendly_name', 'Entity')} ({s.entity_id}): {str(_now() - s.last_updated)[:-7]}"
            for s in failing
        ]

        total = missing + failing

        self._state = len(total)
        message = "\n".join(total)
        if self._state == 0:
            message = f"checked {len(all)}"

        await self.ping(message, len(total))

        if len(total) > 0:
            _LOGGER.debug(f"create notification: {len(total)}")
            await self.notify(message)

        self.async_write_ha_state()

    async def ping(self, message: str, count: int) -> None:
        async with aiohttp.ClientSession() as session:
            url = f"{self._url}/{count}"
            status = -1
            try:
                async with session.get(url, data=message) as res:
                    status = res.status
            except aiohttp.ClientError as e:
                _LOGGER.warning(f"hc exception: {e}")
            finally:
                _LOGGER.debug(f"hc call: {url} [{status}]")

    async def notify(self, message: str) -> None:
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": self._name,
                "title": f"{self._name} failed",
                "message": message,
            },
        )
