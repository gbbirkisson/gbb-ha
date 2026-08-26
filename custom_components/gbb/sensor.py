import logging
from datetime import datetime, timedelta
from typing import Any, override

import aiohttp
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (
    CONF_NAME,
    ENTITY_MATCH_NONE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import now, wildcard_match

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "GBB Healthcheck"

CONF_HEALTHCHECK = "healthcheck"
CONF_HEALTHCHECK_ID = "id"
CONF_HEALTHCHECK_INTERVAL = "interval"
CONF_HEALTHCHECK_GRACE_PERIOD = "grace_period"
CONF_HEALTCHECK_IGNORE = "ignore"
CONF_HEALTHCHECK_REQUIRED = "required"
CONF_HEALTHCHECK_INCLUDE = "include"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): vol.All(str, vol.Length(min=1)),
        vol.Required(CONF_HEALTHCHECK): {
            vol.Required(CONF_HEALTHCHECK_ID): vol.All(str, vol.Length(min=36, max=36)),
            vol.Optional(
                CONF_HEALTHCHECK_INTERVAL, default=timedelta(minutes=1),
            ): cv.positive_time_period,
            vol.Optional(
                CONF_HEALTHCHECK_GRACE_PERIOD, default=timedelta(hours=1),
            ): cv.positive_time_period,
            vol.Optional(CONF_HEALTCHECK_IGNORE, default=[]): [str],
            vol.Optional(CONF_HEALTHCHECK_REQUIRED, default=[]): [str],
            vol.Optional(CONF_HEALTHCHECK_INCLUDE, default=[]): [str],
        },
    },
)


async def async_setup_platform(
    _hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    _LOGGER.debug("Setup sensor: %s", config)

    healthcheck = config[CONF_HEALTHCHECK]
    async_add_entities(
        [
            HealthcheckSensor(
                name=config[CONF_NAME],
                healthcheck_id=healthcheck[CONF_HEALTHCHECK_ID],
                interval=healthcheck[CONF_HEALTHCHECK_INTERVAL],
                grace_period=healthcheck[CONF_HEALTHCHECK_GRACE_PERIOD],
                ignore=set(healthcheck[CONF_HEALTCHECK_IGNORE]),
                required=set(healthcheck[CONF_HEALTHCHECK_REQUIRED]),
                include=set(healthcheck[CONF_HEALTHCHECK_INCLUDE]),
            ),
        ],
    )


class HealthcheckSensor(SensorEntity):
    def __init__(
        self,
        *,
        name: str,
        healthcheck_id: str,
        interval: timedelta,
        grace_period: timedelta,
        ignore: set[str],
        required: set[str],
        include: set[str],
    ) -> None:
        self._name = self._attr_name = name
        self._url = f"https://hc-ping.com/{healthcheck_id}"
        self._interval = interval
        self._grace_period = grace_period
        self._ignore = ignore
        self._required = required
        self._include = include
        self._attr_native_value = 0
        self._attr_extra_state_attributes: dict[str, Any] = {
            "missing": [],
            "failing": [],
            "checked": 0,
            "filtered": 0,
        }

    @override
    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self.check, self._interval, cancel_on_shutdown=True,
            ),
        )

    async def check(self, _: datetime | None = None) -> None:
        states = self.hass.states.async_all()
        total = len(states)

        # Keep only the entities we were told to include
        if self._include:
            _LOGGER.debug("Filtering entities to only match: %s", self._include)
            included = wildcard_match([s.entity_id for s in states], self._include)
            states = [s for s in states if s.entity_id in included]

        # Drop the entities we were told to ignore
        if self._ignore:
            ignored = wildcard_match([s.entity_id for s in states], self._ignore)
            states = [s for s in states if s.entity_id not in ignored]

        # Entities in a bad state for longer than the grace period
        failing = [
            s
            for s in states
            if s.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ENTITY_MATCH_NONE)
            and now() - s.last_updated > self._grace_period
        ]

        # Required entities that do not exist at all
        missing = sorted(self._required - {s.entity_id for s in states})

        _LOGGER.debug("Missing entities: %s", missing)
        _LOGGER.debug("Failing entities: %s", failing)

        checked = len(states)
        filtered = total - checked
        self._attr_extra_state_attributes = {
            "missing": missing,
            "failing": [s.entity_id for s in failing],
            "checked": checked,
            "filtered": filtered,
        }

        problems = [f"Entity ({e}): missing" for e in missing] + [
            f"{s.attributes.get('friendly_name', 'Entity')} ({s.entity_id}): "
            f"{str(now() - s.last_updated)[:-7]}"
            for s in failing
        ]

        self._attr_native_value = len(problems)
        message = "\n".join(problems) or f"checked: {checked}\nfiltered: {filtered}"

        await self.ping(message, len(problems))

        if problems:
            _LOGGER.debug("Create notification: %s", len(problems))
            await self.notify(message)

        self.async_write_ha_state()

    async def ping(self, message: str, count: int) -> None:
        url = f"{self._url}/{count}"
        status = -1
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, data=message) as res:
                status = res.status
        except aiohttp.ClientError as e:
            _LOGGER.warning("HC exception: %s", e)
        finally:
            _LOGGER.debug("HC call: %s [%s]", url, status)

    async def notify(self, message: str) -> None:
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": self._name,
                "title": f"{self._name} failed",
                "message": message,
            },
        )
