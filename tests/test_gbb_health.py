from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.gbb_health import DOMAIN

DEFAULT_CONFIG = {
    DOMAIN: {
        "platform": "sensor",
        "id": "020166bc-5eb3-4a30-9f5a-356d15a3ee09",
        "name": "Test",
    }
}


async def test_gbb_health_setup(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.gbb_health.sensor.HealthcheckSensor.async_added_to_hass"
    ) as add_timer:
        assert await async_setup_component(hass, DOMAIN, DEFAULT_CONFIG) is True
        await hass.async_block_till_done()
        assert add_timer.called
