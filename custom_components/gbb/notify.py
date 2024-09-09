import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, cast, override
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import voluptuous as vol
from homeassistant.components.notify import (
    PLATFORM_SCHEMA,
)
from homeassistant.components.notify.const import (
    DOMAIN as NOTIFY_DOMAIN,
    ATTR_MESSAGE,
    ATTR_TITLE,
    ATTR_DATA,
    ATTR_TARGET,
)
from homeassistant.components.notify.legacy import BaseNotificationService
from . import now
import logging

DEFAULT_NAME = "GBB Notify"
CONF_NAME = "name"
CONF_WRAPS = "wraps"
CONF_FORWARD_TARGET = "forward_target"
CONF_DELAY = "delay"
CONF_RATE_LIMIT = "rate_limit"
CONF_DEFAULT_RATE_LIMIT = "default_rate_limit"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_WRAPS): cv.string,
        vol.Optional(CONF_FORWARD_TARGET, default=False): cv.boolean,
        vol.Optional(
            CONF_DELAY, default=timedelta(seconds=10)
        ): cv.positive_time_period,
        vol.Optional(CONF_RATE_LIMIT, default={}): vol.Schema(
            {str: cv.positive_time_period}
        ),
        vol.Optional(
            CONF_DEFAULT_RATE_LIMIT, default=timedelta(seconds=10)
        ): cv.positive_time_period,
    }
)

_LOGGER = logging.getLogger(__name__)


def get_service(
    hass: HomeAssistant,
    config: ConfigType,
    _: DiscoveryInfoType | None = None,
) -> BaseNotificationService | None:
    _LOGGER.debug(f"Setup notify: {config}")

    try:
        config = PLATFORM_SCHEMA(config)
    except vol.Error as e:
        _LOGGER.error(f"Setup failed: {e}")
        return None

    wraps = cast(str, config.get(CONF_WRAPS))
    forward_target = cast(bool, config.get(CONF_FORWARD_TARGET))
    delay = cast(timedelta, config.get(CONF_DELAY))
    rate_limit = cast(Dict[str, timedelta], config.get(CONF_RATE_LIMIT))
    default_rate_limit = cast(timedelta, config.get(CONF_DEFAULT_RATE_LIMIT))

    bad_config = default_rate_limit < delay
    for k, r in rate_limit.items():
        if r < delay:
            bad_config = True
    if bad_config:
        _LOGGER.error("Setup failed: no rate limit value can be below delay")
        return None

    return WrappedNotificationService(
        hass, wraps, forward_target, delay, rate_limit, default_rate_limit
    )


class WrappedNotificationService(BaseNotificationService):
    def __init__(
        self,
        hass: HomeAssistant,
        wraps: str,
        forward_target: bool,
        delay: timedelta,
        rate_limit: dict[str, timedelta],
        rate_limit_default: timedelta,
    ) -> None:
        self._hass = hass
        self._wraps = wraps
        self._forward_target = forward_target
        self._delay = delay
        self._rate_limit = rate_limit
        self._rate_limit_default = rate_limit_default
        self._old: dict[str, datetime] = dict()

    @override
    async def async_send_message(  # type: ignore[override]
        self,
        message: str,
        title: str | None = None,
        target: list[str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        if target:
            for t in target:
                await self._handle(t, message, title=title, data=data)
        else:
            _LOGGER.warning(f"No target for message: {message}")
            await self._forward(message, title=title, target=target, data=data)

    async def _handle(
        self,
        target: str,
        message: str,
        title: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        rate_limit = self._rate_limit.get(target, self._rate_limit_default)
        ts_now = now()
        ts_before = self._old.get(target)
        if ts_before:
            if (ts_now - ts_before) < rate_limit:
                _LOGGER.debug(
                    f"Skipping '{target}' because of rate limiting: {ts_now -
                    ts_before} < {rate_limit}"
                )
                return

        _LOGGER.debug(f"Sending message: {target}")
        self._old[target] = ts_now
        await asyncio.sleep(self._delay.seconds)
        await self._forward(message, title=title, target=[target], data=data)

    async def _forward(
        self,
        message: str,
        title: str | None = None,
        target: list[str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {ATTR_MESSAGE: message}
        if title:
            payload[ATTR_TITLE] = title
        if target and self._forward_target:
            payload[ATTR_TARGET] = target
        if data:
            payload[ATTR_DATA] = data
        await self._hass.services.async_call(
            NOTIFY_DOMAIN,
            self._wraps,
            service_data=payload,
        )
