from custom_components.gbb import wildcard_match


def test_normal_case() -> None:
    entity_ids = ["a.txt", "b.txt", "c.py", "d.md"]
    assert wildcard_match(entity_ids, {"*.txt"}) == {"a.txt", "b.txt"}


def test_empty_lists() -> None:
    assert wildcard_match([], set()) == set()


def test_no_matching_patterns() -> None:
    entity_ids = ["a.txt", "b.txt", "c.py", "d.md"]
    assert wildcard_match(entity_ids, {"*.json"}) == set()


def test_overlapping_patterns() -> None:
    entity_ids = ["a.txt", "b.txt", "c.py", "d.md"]
    assert wildcard_match(entity_ids, {"*.txt", "*.md"}) == {"a.txt", "b.txt", "d.md"}


def test_partial_matching_patterns() -> None:
    entity_ids = ["file1.py", "file2.py", "script.sh", "README.md"]
    assert wildcard_match(entity_ids, {"*.py", "*.md"}) == {
        "file1.py",
        "file2.py",
        "README.md",
    }
