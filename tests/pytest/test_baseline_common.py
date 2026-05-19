"""Unit tests for extras/perf/_baseline_common.py and the win11_readiness
refactor that now depends on it.

The win11_readiness test is the regression guard for the behaviour-preserving
extraction: its committed baseline JSONs must keep diffing cleanly, so the
envelope key set and order must not move.
"""

import _baseline_common as bc


def test_collection_error_from_exception():
    err = bc.CollectionError.from_exception("a.b", ValueError("boom"))
    assert err.field == "a.b"
    assert err.message == "ValueError: boom"


def test_build_envelope_shape_and_key_order():
    payload = bc.build_envelope(
        schema_name="demo",
        schema_version=3,
        machine={"hostname": "h"},
        blocks={"metrics": {"x": 1}, "extra": {"y": 2}},
        verdict={"category": "CAPTURED", "reasons": [], "remediation_hints": []},
        errors=[bc.CollectionError("f", "m")],
    )
    assert list(payload.keys()) == [
        "schema_version",
        "schema_name",
        "captured_at",
        "machine",
        "metrics",
        "extra",
        "verdict",
        "collection_errors",
    ]
    assert payload["schema_version"] == 3
    assert payload["schema_name"] == "demo"
    assert payload["collection_errors"] == [{"field": "f", "message": "m"}]
    # captured_at is an ISO-8601 UTC string.
    assert payload["captured_at"].endswith("+00:00")


def test_win11_readiness_envelope_unchanged_after_refactor():
    """Guard: the extraction must not change win11_readiness's JSON shape."""
    import win11_readiness as w

    payload = w.to_payload(w.Snapshot())
    assert list(payload.keys()) == [
        "schema_version",
        "schema_name",
        "captured_at",
        "machine",
        "win11_floor",
        "neurobooth_extras",
        "verdict",
        "collection_errors",
    ]
    assert payload["schema_name"] == "win11_readiness"
    assert payload["schema_version"] == 1


def test_parse_ps_date_passthrough_and_convert():
    assert bc.parse_ps_date("not-a-date") == "not-a-date"
    assert bc.parse_ps_date(None) is None
    out = bc.parse_ps_date("/Date(1600000000000)/")
    assert out.startswith("2020-")  # 2020-09-13T...
