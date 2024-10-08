import fnmatch
from datetime import datetime

from homeassistant.const import Platform

DOMAIN = "gbb"
PLATFORMS = [Platform.SENSOR, Platform.CLIMATE]


def now() -> datetime:
    return datetime.now().astimezone()


def wildcard_filter(all: list[str], patterns: set[str]) -> tuple[set[str], set[str]]:
    match = set([])
    for p in patterns:
        match.update(fnmatch.filter(all, p))
    no_match = set(all) - match
    return match, no_match
