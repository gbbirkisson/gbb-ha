from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.gbb_health import DOMAIN


async def test_gbb_health_setup(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {}) is True
