from datetime import timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
from homeassistant.core import HomeAssistant
from pytest import fixture
from custom_components.gbb.notify import (
    CONF_WRAPS,
    WrappedNotificationService,
    get_service,
)


async def test_get_service_good(hass: HomeAssistant) -> None:
    assert get_service(hass, {"platform": "notify", CONF_WRAPS: "notify"}, None)


async def test_get_service_bad(hass: HomeAssistant) -> None:
    assert not get_service(hass, {}, None)


async def test_get_service_bad_delay(hass: HomeAssistant) -> None:
    assert not get_service(
        hass, {"platform": "notify", CONF_WRAPS: "notify", "delay": "00:01:00"}, None
    )


async def test_get_service_bad_rate_limit(hass: HomeAssistant) -> None:
    assert not get_service(
        hass,
        {
            "platform": "notify",
            CONF_WRAPS: "notify",
            "rate_limit": {"asdf": "00:00:01"},
        },
        None,
    )


@fixture
async def notify(
    hass: HomeAssistant,
) -> AsyncGenerator[WrappedNotificationService, None]:
    yield WrappedNotificationService(
        hass, "wrapped", False, timedelta(seconds=0), {}, timedelta(seconds=10)
    )


async def test_gbb_notify_minimal(notify: WrappedNotificationService) -> None:
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ) as mock_notify:
        await notify.async_send_message("some message")
        mock_notify.assert_called_once_with(
            "notify", "wrapped", service_data={"message": "some message"}
        )


async def test_gbb_notify_with_title(notify: WrappedNotificationService) -> None:
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ) as mock_notify:
        await notify.async_send_message("some message", title="some title")
        mock_notify.assert_called_once_with(
            "notify",
            "wrapped",
            service_data={"message": "some message", "title": "some title"},
        )


async def test_gbb_notify_with_data(notify: WrappedNotificationService) -> None:
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ) as mock_notify:
        await notify.async_send_message(
            "some message", title="some title", data={"some": "data"}
        )
        mock_notify.assert_called_once_with(
            "notify",
            "wrapped",
            service_data={
                "message": "some message",
                "title": "some title",
                "data": {"some": "data"},
            },
        )


async def test_gbb_notify_with_target(notify: WrappedNotificationService) -> None:
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ) as mock_notify:
        await notify.async_send_message(
            "some message", target=["target"], title="some title", data={"some": "data"}
        )
        mock_notify.assert_called_once_with(
            "notify",
            "wrapped",
            service_data={
                "message": "some message",
                "title": "some title",
                "data": {"some": "data"},
            },
        )
        mock_notify.reset_mock()

        await notify.async_send_message(
            "some message", target=["target"], title="some title", data={"some": "data"}
        )
        mock_notify.assert_not_called()


async def test_gbb_notify_with_target_forward(
    notify: WrappedNotificationService,
) -> None:
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        new_callable=AsyncMock,
    ) as mock_notify:
        notify._forward_target = True
        await notify.async_send_message(
            "some message", target=["target"], title="some title", data={"some": "data"}
        )
        mock_notify.assert_called_once_with(
            "notify",
            "wrapped",
            service_data={
                "message": "some message",
                "title": "some title",
                "target": ["target"],
                "data": {"some": "data"},
            },
        )
