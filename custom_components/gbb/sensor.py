import logging
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, Mapping, Set, cast

import aiohttp
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import ENTITY_MATCH_NONE, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing_extensions import override

from . import now, wildcard_filter

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "GBB Healthcheck"
CONF_NAME = "name"

CONF_HEALTHCHECK = "healthcheck"
CONF_HEALTHCHECK_ID = "id"
CONF_HEALTHCHECK_INTERVAL = "interval"
CONF_HEALTHCHECK_GRACE_PERIOD = "grace_period"
CONF_HEALTCHECK_IGNORE = "ignore"
CONF_HEALTHCHECK_REQUIRED = "required"
CONF_HEALTHCHECK_INCLUDE = "include"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): vol.All(str, vol.Length(min=1)),
        vol.Optional(CONF_HEALTHCHECK): {
            vol.Required(CONF_HEALTHCHECK_ID): vol.All(str, vol.Length(min=36, max=36)),
            vol.Optional(
                CONF_HEALTHCHECK_INTERVAL, default=timedelta(minutes=1)
            ): cv.positive_time_period,
            vol.Optional(
                CONF_HEALTHCHECK_GRACE_PERIOD, default=timedelta(hours=1)
            ): cv.positive_time_period,
            vol.Optional(CONF_HEALTCHECK_IGNORE, default=[]): vol.All(
                [str], vol.Length(min=0)
            ),
            vol.Optional(CONF_HEALTHCHECK_REQUIRED, default=[]): vol.All(
                [str], vol.Length(min=0)
            ),
            vol.Optional(CONF_HEALTHCHECK_INCLUDE, default=[]): vol.All(
                [str], vol.Length(min=0)
            ),
        },
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    _LOGGER.debug(f"Setup sensor: {config}")

    try:
        config = PLATFORM_SCHEMA(config)
    except vol.Error as e:
        _LOGGER.error(f"Setup failed: {e}")
        return

    name = cast(str, config.get(CONF_NAME))

    healthcheck = config.get(CONF_HEALTHCHECK)

    if healthcheck:
        id = cast(str, healthcheck.get(CONF_HEALTHCHECK_ID))
        interval = cast(timedelta, healthcheck.get(CONF_HEALTHCHECK_INTERVAL))
        grace_period = cast(timedelta, healthcheck.get(CONF_HEALTHCHECK_GRACE_PERIOD))
        ignore = set(healthcheck.get(CONF_HEALTCHECK_IGNORE) or [])
        required = set(healthcheck.get(CONF_HEALTHCHECK_REQUIRED) or [])
        include = set(healthcheck.get(CONF_HEALTHCHECK_INCLUDE) or [])

        async_add_entities(
            [
                HealthcheckSensor(
                    hass, id, name, interval, grace_period, ignore, required, include
                )
            ]
        )
    else:
        _LOGGER.error(f"You did not supply '{CONF_HEALTHCHECK}'")


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
            "filtered": 0,
        }

    @cached_property
    def name(self) -> str:
        return self._name

    @property  # type: ignore[misc]
    def state(self) -> int:  # type: ignore[reportIncompatibleVariableOverride]
        return self._state

    @override
    async def async_added_to_hass(self) -> None:
        async_track_time_interval(self._hass, self.check, self._interval)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:  # type: ignore[reportIncompatibleVariableOverride]
        return self._extra_attributes

    async def check(self, _: datetime | None = None) -> None:
        all = self._hass.states.async_all()
        all_count_before_filter = len(all)

        # filter out everything except those to include
        if self._include:
            _LOGGER.debug(f"Filtering entities to only match: {self._include}")
            m, _n = wildcard_filter([s.entity_id for s in all], self._include)
            all = [s for s in all if s.entity_id in m]

        # filter out those to ignore
        if self._ignore:
            _m, n = wildcard_filter([s.entity_id for s in all], self._ignore)
            all = [s for s in all if s.entity_id in n]

        self._extra_attributes.update(
            {
                "checked": len(all),
                "filtered": all_count_before_filter - len(all),
            }
        )

        # mark those that are failing
        failing = [
            s for s in all if s.state in [STATE_UNAVAILABLE, STATE_UNKNOWN, ENTITY_MATCH_NONE]
        ]

        # filter out those that are within the grace period
        failing = [s for s in failing if now() - s.last_updated > self._grace_period]

        # find missing
        missing = list(self._required - set([s.entity_id for s in all if s.entity_id]))
        _LOGGER.debug(f"Missing entities: {missing}")
        self._extra_attributes.update({"missing": missing})
        missing = [f"Entity ({s}): missing" for s in missing]

        _LOGGER.debug(f"Failing entities: {failing}")
        self._extra_attributes.update({"failing": [s.entity_id for s in failing]})
        failing = [
            f"{s.attributes.get('friendly_name', 'Entity')} ({s.entity_id}): {str(now() - s.last_updated)[:-7]}"  # type: ignore[misc]
            for s in failing
        ]

        total = missing + failing

        self._state = len(total)
        message = "\n".join(total)  # type: ignore[arg-type]
        if self._state == 0:
            message = f"checked: {len(all)}\nfiltered: {all_count_before_filter - len(all)}"

        await self.ping(message, len(total))

        if len(total) > 0:
            _LOGGER.debug(f"Create notification: {len(total)}")
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
                _LOGGER.warning(f"HC exception: {e}")
            finally:
                _LOGGER.debug(f"HC call: {url} [{status}]")

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
