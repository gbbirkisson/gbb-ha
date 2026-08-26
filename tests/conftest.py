"""Fixtures for testing."""

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import custom_components

# Home Assistant mounts `custom_components` from its config dir, which under
# pytest-homeassistant-custom-component is the packaged test config dir. Add this
# repo to the package path so the `gbb` integration is the one that gets found.
_REPO_COMPONENTS = str(Path(__file__).parent.parent / "custom_components")
if _REPO_COMPONENTS not in custom_components.__path__:
    custom_components.__path__.insert(0, _REPO_COMPONENTS)


# This fixture enables loading custom integrations in all tests. Remove to enable
# selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: Any,
) -> None:
    return


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss
# persistent notifications. These calls would fail without this fixture since the
# persistent_notification integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture() -> Generator[None]:
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield
