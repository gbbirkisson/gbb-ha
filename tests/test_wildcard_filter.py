from custom_components.gbb import wildcard_filter


def test_normal_case() -> None:
    all_items = ["a.txt", "b.txt", "c.py", "d.md"]
    patterns = {"*.txt"}
    expected_match = {"a.txt", "b.txt"}
    expected_no_match = {"c.py", "d.md"}
    assert wildcard_filter(all_items, patterns) == (expected_match, expected_no_match)


def test_empty_lists() -> None:
    all_items: list[str] = []
    patterns: set[str] = set()
    expected_match: set[str] = set()
    expected_no_match: set[str] = set()
    assert wildcard_filter(all_items, patterns) == (expected_match, expected_no_match)


def test_no_matching_patterns() -> None:
    all_items = ["a.txt", "b.txt", "c.py", "d.md"]
    patterns = {"*.json"}
    expected_match: set[str] = set()
    expected_no_match = {"a.txt", "b.txt", "c.py", "d.md"}
    assert wildcard_filter(all_items, patterns) == (expected_match, expected_no_match)


def test_overlapping_patterns() -> None:
    all_items = ["a.txt", "b.txt", "c.py", "d.md"]
    patterns = {"*.txt", "*.md"}
    expected_match = {"a.txt", "b.txt", "d.md"}
    expected_no_match = {"c.py"}
    assert wildcard_filter(all_items, patterns) == (expected_match, expected_no_match)


def test_partial_matching_patterns() -> None:
    all_items = ["file1.py", "file2.py", "script.sh", "README.md"]
    patterns = {"*.py", "*.md"}
    expected_match = {"file1.py", "file2.py", "README.md"}
    expected_no_match = {"script.sh"}
    assert wildcard_filter(all_items, patterns) == (expected_match, expected_no_match)
