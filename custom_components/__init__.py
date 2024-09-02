import fnmatch


def wildcard_filter(all: list[str], patterns: set[str]) -> tuple[set[str], set[str]]:
    match = set([])
    for p in patterns:
        match.update(fnmatch.filter(all, p))
    no_match = set(all) - match
    return match, no_match
