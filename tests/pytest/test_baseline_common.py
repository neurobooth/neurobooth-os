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


def test_resolved_log_dir_falls_back_to_nb_install(tmp_path, monkeypatch):
    """With no neurobooth config loaded and NB_CONFIG unset, the resolver
    must fall back to NB_INSTALL (the same fallback the crash logs use),
    and never raise."""
    import neurobooth_os.config as nb_config

    monkeypatch.setattr(nb_config, "neurobooth_config", None, raising=False)
    monkeypatch.delenv("NB_CONFIG", raising=False)
    monkeypatch.setenv("NB_INSTALL", str(tmp_path))

    assert bc.resolved_log_dir() == tmp_path
    assert bc.resolved_log_dir("timing") == tmp_path / "timing"


def test_resolved_log_dir_never_raises(monkeypatch):
    """Even with NB_INSTALL unset and no config, it returns a usable Path."""
    import neurobooth_os.config as nb_config

    monkeypatch.setattr(nb_config, "neurobooth_config", None, raising=False)
    monkeypatch.delenv("NB_CONFIG", raising=False)
    monkeypatch.delenv("NB_INSTALL", raising=False)

    result = bc.resolved_log_dir("timing")
    assert result.name == "timing"
    assert result.parent.is_absolute()
