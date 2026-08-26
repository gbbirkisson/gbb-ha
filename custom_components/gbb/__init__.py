import fnmatch
from datetime import datetime


def now() -> datetime:
    return datetime.now().astimezone()


def wildcard_match(entity_ids: list[str], patterns: set[str]) -> set[str]:
    match: set[str] = set()
    for p in patterns:
        match.update(fnmatch.filter(entity_ids, p))
    return match
