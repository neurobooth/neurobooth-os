"""Snapshot a booth's security posture relevant to inter-machine plumbing.

Issue #764 / concern #2 of #759. Runs *on the booth* (not from CTR) and
captures the state items the runbook ``docs/inter_machine_setup.md``
Section 8 lists as expected, so a Win10 baseline can be diffed against a
Win11 pilot without anyone eyeballing each registry/firewall value.

Captured items:

* Per-NIC network profile (Section 2).
* Whether the three firewall rule groups (Section 3) have enabled rules.
* ``LocalAccountTokenFilterPolicy`` and ``LmCompatibilityLevel`` registry
  values (Sections 6 and 7).
* Credential Guard / VBS state (Section 7).
* ``RunAsPPL`` LSASS protection state (Section 7).
* SMB server protocol + signing config (Section 7).
* DCOM Launch/Activation permission *presence* (Section 5): the binary
  security descriptors are captured as base64 lengths and SHA-256 hashes
  so a change is detectable without the snapshot inspecting policy bytes.
* WMI CIMV2 ``__SystemSecurity.GetSD`` return code + descriptor hash
  (Section 4): same diff-friendly capture.

Emits the shared ``_baseline_common`` envelope under
``<log_dir>/booth_security_snapshot/<os>/<hostname>.json``. The
hash-only DCOM/WMI capture matches the runbook's "GUI verification"
acceptance criterion (Sections 4 and 5) -- the snapshot's job is to
detect drift, not interpret policy.

Usage::

    uv run python extras/perf/booth_security_snapshot.py
        [--role CTR|STM|ACQ|spare] [--out PATH] [--stdout]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from _baseline_common import (
    CollectionError,
    build_envelope,
    collect_os_identity,
    os_segment,
    ps_json,
    resolved_log_dir,
    run_powershell,
)

SCHEMA_VERSION = 1
SCHEMA_NAME = "booth_security_snapshot"

# Mirror the three groups from docs/inter_machine_setup.md Section 3.
FIREWALL_RULE_GROUPS = (
    "Windows Management Instrumentation (WMI)",
    "Remote Scheduled Tasks Management",
    "File and Printer Sharing",
)

# Expected state per Section 8. Drift from these flips the verdict to WARN.
EXPECTED_LATFP = 1
EXPECTED_LMCOMPAT_OK = (3, 5)
EXPECTED_RUNASPPL = (None, 0)


@dataclass
class Snapshot:
    network: dict = field(default_factory=dict)
    firewall: dict = field(default_factory=dict)
    registry: dict = field(default_factory=dict)
    credential_guard: dict = field(default_factory=dict)
    smb: dict = field(default_factory=dict)
    dcom: dict = field(default_factory=dict)
    wmi: dict = field(default_factory=dict)
    errors: List[CollectionError] = field(default_factory=list)

    def record(self, where: str, exc: BaseException) -> None:
        self.errors.append(CollectionError.from_exception(where, exc))


def _coerce_list(value: Any) -> list:
    """ConvertTo-Json emits a single object as a dict, not a 1-item list.

    Normalize to a list so downstream code does not branch on shape.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def collect_network_profiles(snap: Snapshot) -> None:
    """Per-NIC ``NetworkCategory`` (Private/Public/Domain).

    Section 8 expects ``Private`` on the booth's neurobooth-LAN NIC.
    PowerShell renders the ``[NetworkCategory]`` and
    ``[NetConnectivityLevel]`` enums as integers when piped through
    ``ConvertTo-Json``; we project them to their ``.ToString()`` form so
    the JSON carries the human-readable label.
    """
    try:
        info = ps_json(
            "Get-NetConnectionProfile | ForEach-Object { "
            "  [pscustomobject]@{ "
            "    Name = $_.Name; "
            "    InterfaceAlias = $_.InterfaceAlias; "
            "    InterfaceIndex = $_.InterfaceIndex; "
            "    NetworkCategory = $_.NetworkCategory.ToString(); "
            "    IPv4Connectivity = $_.IPv4Connectivity.ToString() "
            "  } "
            "} | ConvertTo-Json -Depth 3"
        )
        profiles = []
        for entry in _coerce_list(info):
            profiles.append(
                {
                    "name": entry.get("Name"),
                    "interface_alias": entry.get("InterfaceAlias"),
                    "interface_index": entry.get("InterfaceIndex"),
                    "network_category": entry.get("NetworkCategory"),
                    "ipv4_connectivity": entry.get("IPv4Connectivity"),
                }
            )
        snap.network["profiles"] = profiles
    except Exception as exc:  # noqa: BLE001
        snap.record("network.profiles", exc)


def collect_firewall_groups(snap: Snapshot) -> None:
    """For each of the three runbook rule groups, count enabled rules.

    Section 8 expects each group to have at least one ``Enabled = True``
    rule. The per-group count is enough for drift detection; we do not
    enumerate every rule by name (~hundreds; noisy diffs).
    """
    snap.firewall["groups"] = {}
    for group in FIREWALL_RULE_GROUPS:
        try:
            # Escape single quotes in the group name for the PS string literal.
            ps_group = group.replace("'", "''")
            info = ps_json(
                f"Get-NetFirewallRule -DisplayGroup '{ps_group}' "
                "-ErrorAction SilentlyContinue | "
                "Group-Object Enabled | "
                "Select-Object @{n='enabled';e={$_.Name}}, Count | "
                "ConvertTo-Json -Depth 3"
            )
            counts = {"True": 0, "False": 0}
            for entry in _coerce_list(info):
                # PowerShell may render Enabled as bool literal True/False
                # (newer) or the string 'True'/'False' (older); both land
                # as Python bool or str. Normalize.
                key = str(entry.get("enabled"))
                counts[key] = counts.get(key, 0) + int(entry.get("Count") or 0)
            snap.firewall["groups"][group] = {
                "enabled_count": counts.get("True", 0),
                "disabled_count": counts.get("False", 0),
            }
        except Exception as exc:  # noqa: BLE001
            snap.record(f"firewall.groups.{group}", exc)
            snap.firewall["groups"][group] = {"enabled_count": None, "disabled_count": None}


def _read_dword(path: str, name: str) -> Optional[int]:
    """Return the DWord value at ``path\\name``, or ``None`` if missing.

    Uses ``Get-ItemProperty -ErrorAction SilentlyContinue`` so a missing
    key returns ``None`` rather than raising.
    """
    raw = run_powershell(
        f"$v = (Get-ItemProperty '{path}' -Name '{name}' -ErrorAction SilentlyContinue)"
        f".'{name}'; if ($null -eq $v) {{ 'NULL' }} else {{ [string]$v }}"
    )
    if raw == "NULL" or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def collect_registry_state(snap: Snapshot) -> None:
    """Capture the three registry DWords the runbook Sections 6-7 set."""
    try:
        latfp = _read_dword(
            r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
            "LocalAccountTokenFilterPolicy",
        )
        snap.registry["local_account_token_filter_policy"] = latfp
    except Exception as exc:  # noqa: BLE001
        snap.record("registry.local_account_token_filter_policy", exc)

    try:
        lmc = _read_dword(r"HKLM:\SYSTEM\CurrentControlSet\Control\Lsa", "LmCompatibilityLevel")
        snap.registry["lm_compatibility_level"] = lmc
    except Exception as exc:  # noqa: BLE001
        snap.record("registry.lm_compatibility_level", exc)

    try:
        rap = _read_dword(r"HKLM:\SYSTEM\CurrentControlSet\Control\Lsa", "RunAsPPL")
        snap.registry["run_as_ppl"] = rap
    except Exception as exc:  # noqa: BLE001
        snap.record("registry.run_as_ppl", exc)


def collect_credential_guard(snap: Snapshot) -> None:
    """Capture VBS / Credential Guard configuration and running state."""
    try:
        info = ps_json(
            "Get-ComputerInfo -Property "
            "DeviceGuardSmartStatus, "
            "DeviceGuardSecurityServicesConfigured, "
            "DeviceGuardSecurityServicesRunning, "
            "DeviceGuardCodeIntegrityPolicyEnforcementStatus, "
            "DeviceGuardUserModeCodeIntegrityPolicyEnforcementStatus | "
            "ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            snap.credential_guard = {
                "smart_status": info.get("DeviceGuardSmartStatus"),
                "services_configured": info.get("DeviceGuardSecurityServicesConfigured"),
                "services_running": info.get("DeviceGuardSecurityServicesRunning"),
                "code_integrity_enforcement": info.get(
                    "DeviceGuardCodeIntegrityPolicyEnforcementStatus"
                ),
                "user_mode_ci_enforcement": info.get(
                    "DeviceGuardUserModeCodeIntegrityPolicyEnforcementStatus"
                ),
            }
    except Exception as exc:  # noqa: BLE001
        snap.record("credential_guard", exc)


def collect_smb(snap: Snapshot) -> None:
    """Capture SMB server config relevant to ``admin$`` access."""
    try:
        info = ps_json(
            "Get-SmbServerConfiguration | Select-Object "
            "EnableSMB1Protocol, EnableSMB2Protocol, "
            "EnableSecuritySignature, RequireSecuritySignature, "
            "EnableInsecureGuestLogons, AutoShareServer, "
            "RestrictNamedPipeAccessViaQuic | "
            "ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            snap.smb = {
                "enable_smb1": info.get("EnableSMB1Protocol"),
                "enable_smb2": info.get("EnableSMB2Protocol"),
                "enable_security_signature": info.get("EnableSecuritySignature"),
                "require_security_signature": info.get("RequireSecuritySignature"),
                "enable_insecure_guest_logons": info.get("EnableInsecureGuestLogons"),
                "auto_share_server": info.get("AutoShareServer"),
                "restrict_named_pipe_access_via_quic": info.get(
                    "RestrictNamedPipeAccessViaQuic"
                ),
            }
    except Exception as exc:  # noqa: BLE001
        snap.record("smb", exc)


def collect_dcom_perms(snap: Snapshot) -> None:
    """Hash-fingerprint the four DCOM-permission registry values.

    Section 5 of the runbook configures DCOM Launch/Activation via the
    ``dcomcnfg`` GUI; the resulting ACLs live in HKLM\\SOFTWARE\\Microsoft\\Ole
    as REG_BINARY security descriptors. We capture each value's byte
    length and SHA-256 so a change to the policy surfaces as a hash
    diff between the Win10 baseline and the Win11 pilot artefact. The
    snapshot does not decode the descriptors -- diff-detection is the
    contract; full SDDL decoding is a follow-up.
    """
    properties = (
        "MachineLaunchRestriction",
        "MachineAccessRestriction",
        "DefaultLaunchPermission",
        "DefaultAccessPermission",
    )
    payload: dict[str, Any] = {}
    for prop in properties:
        try:
            raw = run_powershell(
                f"$v = (Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Ole' "
                f"-Name '{prop}' -ErrorAction SilentlyContinue).'{prop}'; "
                "if ($null -eq $v) { 'NULL' } else { "
                "  $sha = (New-Object System.Security.Cryptography.SHA256Managed)"
                ".ComputeHash($v); "
                "  ($v.Length).ToString() + ':' + "
                "  (($sha | ForEach-Object { $_.ToString('x2') }) -join '') }"
            )
            if raw == "NULL" or not raw:
                payload[prop] = {"present": False}
            else:
                length_str, _, sha_hex = raw.partition(":")
                payload[prop] = {
                    "present": True,
                    "length_bytes": int(length_str),
                    "sha256": sha_hex,
                }
        except Exception as exc:  # noqa: BLE001
            snap.record(f"dcom.{prop}", exc)
            payload[prop] = {"present": None, "error": str(exc)}
    snap.dcom["permissions"] = payload


def collect_wmi_acl(snap: Snapshot) -> None:
    """Capture the WMI CIMV2 namespace ACL via ``__SystemSecurity.GetSD``.

    Section 4 of the runbook adds a ``Remote Enable`` grant via
    ``compmgmt.msc``; the resulting ACL is reachable only through the
    legacy WMI `__SystemSecurity` interface. Pure CIM cmdlets cannot
    invoke ``GetSD``, so we drop to ``Get-WmiObject`` for this one
    query. Same diff-detection treatment as the DCOM block: length
    + SHA-256 of the returned bytes, no decoding.
    """
    try:
        raw = run_powershell(
            "$ns = Get-WmiObject -Namespace 'root\\cimv2' -List | "
            "Where-Object { $_.Name -eq '__SystemSecurity' }; "
            "$res = $ns.GetSD(); "
            "if ($res.ReturnValue -ne 0) { 'RC:' + $res.ReturnValue } "
            "else { "
            "  $sha = (New-Object System.Security.Cryptography.SHA256Managed)"
            ".ComputeHash($res.SD); "
            "  'OK:' + $res.SD.Length + ':' + "
            "  (($sha | ForEach-Object { $_.ToString('x2') }) -join '') }"
        )
        if raw.startswith("RC:"):
            snap.wmi["cimv2_acl"] = {
                "captured": False,
                "return_value": int(raw.split(":", 1)[1]),
            }
        elif raw.startswith("OK:"):
            _, length_str, sha_hex = raw.split(":", 2)
            snap.wmi["cimv2_acl"] = {
                "captured": True,
                "return_value": 0,
                "length_bytes": int(length_str),
                "sha256": sha_hex,
            }
        else:
            snap.wmi["cimv2_acl"] = {"captured": False, "raw": raw}
    except Exception as exc:  # noqa: BLE001
        snap.record("wmi.cimv2_acl", exc)


def derive_verdict(snap: Snapshot) -> dict:
    """PASS if every expected-state item from Section 8 matches; WARN if any
    drift; FAIL never -- the snapshot just captures, it does not decide
    whether a drift is intentional. WARN reasons name the field so the
    operator can record an exception in the runbook log."""
    reasons: List[str] = []
    hints: List[str] = []

    profiles = snap.network.get("profiles") or []
    non_private = [
        p for p in profiles
        if (p.get("network_category") or "").lower() not in ("private", "domainauthenticated")
    ]
    if non_private:
        aliases = ", ".join(p.get("interface_alias") or "?" for p in non_private)
        reasons.append(f"NIC profile not Private/Domain: {aliases}")
        hints.append("Re-pin NIC profile per Section 2 of the runbook")

    for group, counts in (snap.firewall.get("groups") or {}).items():
        enabled = counts.get("enabled_count")
        if enabled is None:
            reasons.append(f"firewall group not queryable: {group}")
        elif enabled == 0:
            reasons.append(f"firewall group has zero enabled rules: {group}")
            hints.append("Run Section 3 of the runbook")

    latfp = snap.registry.get("local_account_token_filter_policy")
    if latfp != EXPECTED_LATFP:
        reasons.append(f"LocalAccountTokenFilterPolicy={latfp} (expected {EXPECTED_LATFP})")
        hints.append("Run Section 6 of the runbook")

    lmc = snap.registry.get("lm_compatibility_level")
    if lmc not in EXPECTED_LMCOMPAT_OK and lmc is not None:
        reasons.append(
            f"LmCompatibilityLevel={lmc} (expected one of {EXPECTED_LMCOMPAT_OK})"
        )
        hints.append("Section 7 NTLM hardening")

    rap = snap.registry.get("run_as_ppl")
    if rap not in EXPECTED_RUNASPPL:
        reasons.append(f"RunAsPPL={rap} (expected 0 or unset)")
        hints.append("Section 7 LSASS protection -- document if intentional")

    services_running = snap.credential_guard.get("services_running") or []
    if any("CredentialGuard" in str(s) or s == 1 for s in _coerce_list(services_running)):
        reasons.append("Credential Guard running -- NTLM workgroup auth may be restricted")
        hints.append("Section 7 Credential Guard -- document if intentional")

    if snap.smb.get("enable_smb2") is False:
        reasons.append("EnableSMB2Protocol=False")
        hints.append("SCHTASKS /XML round-trip needs SMB2; re-enable")
    if snap.smb.get("enable_smb1") is True:
        reasons.append("EnableSMB1Protocol=True (security hazard, not needed)")
        hints.append("Disable SMB1 per Section 7")

    if not reasons:
        return {"category": "PASS", "reasons": [], "remediation_hints": []}
    return {"category": "WARN", "reasons": reasons, "remediation_hints": hints}


def to_payload(machine: dict, snap: Snapshot) -> dict:
    return build_envelope(
        schema_name=SCHEMA_NAME,
        schema_version=SCHEMA_VERSION,
        machine=machine,
        blocks={
            "network": snap.network,
            "firewall": snap.firewall,
            "registry": snap.registry,
            "credential_guard": snap.credential_guard,
            "smb": snap.smb,
            "dcom": snap.dcom,
            "wmi": snap.wmi,
        },
        verdict=derive_verdict(snap),
        errors=snap.errors,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--role",
        choices=["CTR", "STM", "ACQ", "spare"],
        help="Booth role for this machine; recorded in the JSON for triage.",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output JSON path. Defaults to "
        "<log_dir>/booth_security_snapshot/<os>/<hostname>.json.",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print the JSON envelope to stdout in addition to writing the file.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    snap = Snapshot()

    print("Collecting booth security posture snapshot...", file=sys.stderr)
    machine, machine_errors = collect_os_identity(args.role)
    snap.errors.extend(machine_errors)

    collect_network_profiles(snap)
    collect_firewall_groups(snap)
    collect_registry_state(snap)
    collect_credential_guard(snap)
    collect_smb(snap)
    collect_dcom_perms(snap)
    collect_wmi_acl(snap)

    payload = to_payload(machine, snap)
    out_path = args.out or (
        resolved_log_dir("booth_security_snapshot")
        / os_segment(machine)
        / f"{machine.get('hostname', 'unknown')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    verdict = payload["verdict"]["category"]
    print(f"Verdict: {verdict}", file=sys.stderr)
    if payload["verdict"]["reasons"]:
        for reason in payload["verdict"]["reasons"]:
            print(f"  - {reason}", file=sys.stderr)
    print(f"Wrote: {out_path}", file=sys.stderr)
    if snap.errors:
        print(
            f"Collection errors: {len(snap.errors)} (see JSON 'collection_errors')",
            file=sys.stderr,
        )

    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
