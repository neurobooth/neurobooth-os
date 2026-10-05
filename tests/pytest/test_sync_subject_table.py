"""Unit tests for extras/sync_subject_table.py (pure diff layer)."""

from sync_subject_table import find_rows_to_upsert


def test_source_only_row_is_new() -> None:
    source = {"100": ("100", "Ann")}
    new_rows, changed_rows = find_rows_to_upsert(source, {})
    assert new_rows == [("100", "Ann")]
    assert changed_rows == []


def test_differing_row_is_changed_with_source_values() -> None:
    source = {"100": ("100", "Ann")}
    target = {"100": ("100", "Anne")}
    new_rows, changed_rows = find_rows_to_upsert(source, target)
    assert new_rows == []
    assert changed_rows == [("100", "Ann")]


def test_identical_row_is_skipped() -> None:
    rows = {"100": ("100", "Ann")}
    assert find_rows_to_upsert(rows, dict(rows)) == ([], [])


def test_target_only_row_is_never_returned() -> None:
    target = {"200": ("200", "Bob")}
    assert find_rows_to_upsert({}, target) == ([], [])
