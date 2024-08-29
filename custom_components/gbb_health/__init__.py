from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

DOMAIN = "gbb_health"
PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from yaml configuration."""

    if DOMAIN in config:
        hass.async_create_task(
            discovery.async_load_platform(
                hass, Platform.SENSOR, DOMAIN, config[DOMAIN], config
            )
        )

    return True
