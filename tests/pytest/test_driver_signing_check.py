"""Unit tests for extras/perf/driver_signing_check.py (pure layer).

The PowerShell ``Get-AuthenticodeSignature`` collection is Windows/booth-
specific; only the pure summarize/verdict layer is unit-tested.
"""

import driver_signing_check as d


def test_summarize_counts_and_not_valid():
    files = [
        {"Path": "a.dll", "Status": "Valid", "Signer": "CN=Teledyne"},
        {"Path": "b.sys", "Status": "Valid", "Signer": "CN=Teledyne"},
        {"Path": "c.dll", "Status": "NotSigned", "Signer": None},
        {"Path": "d.sys", "Status": "HashMismatch", "Signer": "CN=Old"},
    ]
    m = d.summarize(files)
    assert m["n_files"] == 4
    assert m["by_status"] == {"Valid": 2, "NotSigned": 1, "HashMismatch": 1}
    assert m["n_not_valid"] == 2
    assert {x["status"] for x in m["not_valid"]} == {"NotSigned", "HashMismatch"}


def test_summarize_empty():
    m = d.summarize([])
    assert m["n_files"] == 0 and m["n_not_valid"] == 0


def test_verdict_no_files_ok_degraded():
    assert d.derive_verdict(d.summarize([]))["category"] == "NO_FILES"

    all_valid = [{"Path": "a", "Status": "Valid"}]
    assert d.derive_verdict(d.summarize(all_valid))["category"] == "OK"

    bad = [{"Path": "a", "Status": "Valid"}, {"Path": "b", "Status": "NotSigned"}]
    v = d.derive_verdict(d.summarize(bad))
    assert v["category"] == "DEGRADED"
    assert any("not 'Valid'" in r for r in v["reasons"])
