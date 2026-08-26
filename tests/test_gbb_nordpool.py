from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, State
from homeassistant.setup import async_setup_component

from custom_components.gbb.binary_sensor import NordPoolSensor

SENSOR = "sensor.nord_pool_no1_current_price"
AVERAGE = "sensor.nord_pool_no1_daily_average"
SWITCH = "input_boolean.nordpool_enable"
KNOB = "input_number.nordpool_knob"

NORDPOOL_CONFIG = {
    "sensor": SENSOR,
    "average": AVERAGE,
    "switch": SWITCH,
    "knob": KNOB,
}


async def test_setup_good(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": "gbb", "nordpool": NORDPOOL_CONFIG}},
    )
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.gbb_nordpool") is not None


async def test_setup_bad(hass: HomeAssistant) -> None:
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": "gbb", "bad": "key"}},
    )
    await hass.async_block_till_done()

    assert not hass.states.async_entity_ids("binary_sensor")


async def test_setup_missing_average(hass: HomeAssistant) -> None:
    config = {k: v for k, v in NORDPOOL_CONFIG.items() if k != "average"}
    assert await async_setup_component(
        hass,
        "binary_sensor",
        {"binary_sensor": {"platform": "gbb", "nordpool": config}},
    )
    await hass.async_block_till_done()

    assert not hass.states.async_entity_ids("binary_sensor")


def make_sensor(hass: HomeAssistant) -> NordPoolSensor:
    sensor = NordPoolSensor(
        name="test", sensor=SENSOR, average=AVERAGE, switch=SWITCH, knob=KNOB,
    )
    sensor.hass = hass
    return sensor


async def setup_sensor(
    hass: HomeAssistant, *, price: str, average: str, switch: str, knob: str,
) -> NordPoolSensor:
    hass.states.async_set(SENSOR, price)
    hass.states.async_set(AVERAGE, average)
    hass.states.async_set(SWITCH, switch)
    hass.states.async_set(KNOB, knob)
    await hass.async_block_till_done()

    sensor = make_sensor(hass)
    with patch.object(NordPoolSensor, "async_write_ha_state", MagicMock()):
        await sensor.async_added_to_hass()
    return sensor


def attributes(sensor: NordPoolSensor) -> dict[str, Any]:
    attrs = sensor.extra_state_attributes
    assert attrs
    return dict(attrs)


async def test_disabled_when_switch_off(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="1.0", average="2.0", switch=STATE_OFF, knob="1.0",
    )

    # Disabled means the sensor stays on so consumers keep running
    assert sensor.is_on
    assert attributes(sensor)["enabled"] is False
    assert attributes(sensor)["average"] == 2.0


async def test_enabled_price_below_threshold(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="1.0", average="2.0", switch=STATE_ON, knob="1.0",
    )

    assert sensor.is_on
    assert attributes(sensor)["enabled"] is True
    assert attributes(sensor)["threshold"] == 2.0


async def test_enabled_price_above_threshold(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="3.0", average="2.0", switch=STATE_ON, knob="1.0",
    )

    assert not sensor.is_on


async def test_knob_scales_threshold(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="3.0", average="2.0", switch=STATE_ON, knob="2.0",
    )

    assert attributes(sensor)["threshold"] == 4.0
    assert sensor.is_on


async def test_disabled_without_average(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="1.0", average=STATE_UNAVAILABLE, switch=STATE_ON, knob="1.0",
    )

    assert sensor.is_on
    assert attributes(sensor)["enabled"] is False
    assert attributes(sensor)["threshold"] == -1


async def test_disabled_on_unreadable_price(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price=STATE_UNAVAILABLE, average="2.0", switch=STATE_ON, knob="1.0",
    )

    assert sensor.is_on
    assert attributes(sensor)["enabled"] is False


async def test_state_change_triggers_update(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="3.0", average="2.0", switch=STATE_ON, knob="1.0",
    )
    assert not sensor.is_on

    with patch.object(NordPoolSensor, "async_write_ha_state", MagicMock()):
        sensor._async_state_changed(
            Event(
                "state_changed",
                {
                    "entity_id": KNOB,
                    "old_state": hass.states.get(KNOB),
                    "new_state": State(KNOB, "2.0"),
                },
            ),
        )

    # Threshold doubled, the current price is now below it
    assert sensor.is_on


async def test_average_change_recomputes_threshold(hass: HomeAssistant) -> None:
    sensor = await setup_sensor(
        hass, price="3.0", average="2.0", switch=STATE_ON, knob="1.0",
    )
    assert not sensor.is_on

    with patch.object(NordPoolSensor, "async_write_ha_state", MagicMock()):
        sensor._async_state_changed(
            Event(
                "state_changed",
                {
                    "entity_id": AVERAGE,
                    "old_state": hass.states.get(AVERAGE),
                    "new_state": State(AVERAGE, "4.0"),
                },
            ),
        )

    assert attributes(sensor)["threshold"] == 4.0
    assert sensor.is_on
