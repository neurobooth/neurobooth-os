"""Verify the SHA-256 of the vendored LabRecorder v1.17.1 binaries.

The vendor/labrecorder-v1.17.1/ tree exists to override liesl's bundled
v1.13-b4 binaries (see #812, #813). If those bytes ever drift -- accidental
modification, partial commit, corruption in transit -- the fix posted to
the booth machines is no longer the build we audited and signed off on.

This test catches that. Update the EXPECTED_HASHES dict only when
intentionally moving to a new LabRecorder version, in the same commit
that swaps the binaries (and updates the hashes baked into
extras/perf/upgrade_labrecorder_v1.17.1.ps1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = REPO_ROOT / "vendor" / "labrecorder-v1.17.1"

EXPECTED_HASHES = {
    "LabRecorderCLI.exe": "5a838787c938be19e90a8092c0da436ec7c01dff917b50285ee96b5a851820c5",
    "lsl.dll":            "6c97d5456d498ef6a062c74c54ff87cd39efd58dcf67d7bea4b01263d50df445",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("filename,expected", sorted(EXPECTED_HASHES.items()))
def test_vendored_binary_hash_matches(filename: str, expected: str) -> None:
    path = VENDOR_DIR / filename
    assert path.exists(), f"vendored file missing: {path}"
    actual = _sha256(path)
    assert actual == expected, (
        f"{filename} SHA-256 drift:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}\n"
        f"If this is intentional, update EXPECTED_HASHES here and the matching\n"
        f"hashes in extras/perf/upgrade_labrecorder_v1.17.1.ps1 in the same commit."
    )


def test_vendor_dir_has_license() -> None:
    license_path = VENDOR_DIR / "LICENSE"
    assert license_path.exists(), (
        "LICENSE missing from vendor dir; upstream LabRecorder is MIT-licensed and "
        "the license text must accompany the redistributed binaries."
    )
    text = license_path.read_text()
    assert "MIT License" in text, "vendored LICENSE does not look like the upstream MIT license"
