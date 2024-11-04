from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.gbb.binary_sensor import async_setup_platform


async def test_setup_good(hass: HomeAssistant) -> None:
    callback = MagicMock()
    await async_setup_platform(
        hass,
        {
            "platform": "binary_sensor",
            "nordpool": {
                "sensor": "sensor.nordpool_kwh_no1_nok_3_10_025",
                "switch": "input_boolean.nordpool_enable",
                "knob": "input_number.nordpool_knob",
            },
        },
        callback,
        None,
    )
    callback.assert_called_once()


async def test_setup_bad(hass: HomeAssistant) -> None:
    callback = MagicMock()
    await async_setup_platform(
        hass,
        {
            "bad": "key",
        },
        callback,
        None,
    )
    callback.assert_not_called()
