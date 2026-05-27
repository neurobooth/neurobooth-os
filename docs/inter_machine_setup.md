# Inter-machine setup runbook

Configures a fresh booth machine (or re-validates an existing one after a Windows upgrade) so that CTR can drive STM and ACQ over the inter-machine plumbing the booth code relies on.

Replaces the legacy `docs/enable_WMI_instuctions.txt` (typo preserved in the old filename); supersedes the deprecated `netsh firewall` flow with PowerShell equivalents and adds the Windows-11-specific surfaces (`Set-NetFirewallRule` rule groups, network-profile pinning, Credential Guard / NTLM / LSASS / SMB caveats). Concern #2 of #759; deliverable of the runbook portion of #764.

## What this configures

CTR launches the STM and ACQ servers using four remote primitives in `neurobooth_os/netcomm/client.py`:

| Primitive | Used by | Transport |
|---|---|---|
| `tasklist /S /U /P` | `get_python_pids` | RPC over named pipes (NTLM auth) |
| `Get-CimInstance -CimSession (Dcom)` | `get_all_python_processes_with_cmd` (replaced `WMIC` in PR #770) | DCOM |
| `SCHTASKS /S /U /P /Create /XML`, `/Run`, `/Query` | `start_server` | RPC + DCOM + SMB (XML pulled via `admin$`) |
| `taskkill /S /U /P /PID /F` | `kill_remote_pid` | RPC/DCOM |

All four share one underlying configuration: a WMI namespace ACL, DCOM Launch/Activation permissions, the `LocalAccountTokenFilterPolicy` registry tweak, three inbound firewall rule groups, NTLM auth between workgroup local accounts, and SMB access to `admin$`. The sections below configure each piece.

## Prerequisites

- Each booth machine is in the same workgroup (not domain-joined).
- An operator with local admin on every booth.
- All booths are on the same broadcast-reachable IP subnet (the booth README documents `192.168.100.1` as the canonical CTR address).

## 1. Local accounts

On each booth, create a local account whose username matches the booth's role and rename the computer to match:

| Computer name | Local account |
|---|---|
| `CTR` | `CTR` |
| `STM` | `STM` |
| `ACQ` | `ACQ` |

The exact password is set on each booth and stored on CTR in `secrets.yaml` (`machines.<name>.password`) — see `neurobooth_os/config.py` for the schema. CTR uses these credentials to authenticate the four primitives in the table above.

## 2. Pin the network profile to Private

Public network profile suppresses every inbound firewall rule in Section 3. Win11 in-place upgrades have been observed to flip workgroup NICs back to Public, even when the connection was Private pre-upgrade. Re-pin after any upgrade:

```powershell
Get-NetConnectionProfile
Set-NetConnectionProfile -InterfaceAlias "<NIC alias>" -NetworkCategory Private
```

After re-running, confirm `NetworkCategory` reads `Private` on the booth NIC.

## 3. Enable the three firewall rule groups

Replaces the deprecated `netsh firewall set service RemoteAdmin enable` from the old runbook. The three groups below cover all four primitives:

```powershell
Set-NetFirewallRule -DisplayGroup "Windows Management Instrumentation (WMI)" -Enabled True
Set-NetFirewallRule -DisplayGroup "Remote Scheduled Tasks Management" -Enabled True
Set-NetFirewallRule -DisplayGroup "File and Printer Sharing" -Enabled True
```

Coverage:

- `Windows Management Instrumentation (WMI)` — DCOM transport for `Get-CimInstance` (and the predecessor WMIC) plus `taskkill /S`.
- `Remote Scheduled Tasks Management` — SCHTASKS `/S`.
- `File and Printer Sharing` — `admin$` SMB read that SCHTASKS depends on when transferring the task XML, plus the named-pipe transport `tasklist /S` uses.

Verify:

```powershell
Get-NetFirewallRule -DisplayGroup "Windows Management Instrumentation (WMI)" |
    Select-Object DisplayName, Enabled, Profile
```

Repeat the `Get-NetFirewallRule` call for the other two display groups. Every rule in each group should show `Enabled = True` and `Profile` containing `Private` (or `Any`).

## 4. Grant WMI namespace ACL access

The CIMV2 namespace ACL is what gates remote WMI/DCOM queries against `Win32_Process`. There is no in-box PowerShell cmdlet that edits this ACL cleanly; the canonical path remains the GUI:

1. `Win+R` → `compmgmt.msc` → enter.
2. Expand `Services and Applications` → right-click `WMI Control` → `Properties`.
3. `Security` tab → expand `Root` → highlight `CIMV2` → click `Security…`.
4. `Add…` the remote user (the account that matches the *calling* booth — typically `CTR` on STM and ACQ).
5. Highlight the added user and tick `Remote Enable`.
6. `OK` twice and close Computer Management.

If a community module is preferred over the GUI, Microsoft's `Set-WmiNamespaceSecurity.ps1` (from the docs samples) is the long-standing reference; it is not in-box, so a fresh booth needs the GUI path or the script copied in.

## 5. Grant DCOM Launch/Activation permissions

Similar to Section 4, DCOM permissions remain GUI-driven for stock Windows:

1. `Win+R` → `dcomcnfg` → enter.
2. Expand `Component Services` → `Computers` → right-click `My Computer` → `Properties`.
3. `COM Security` tab.
4. Under `Launch and Activation Permissions`, click `Edit Limits…` (the second of the two Edit-Limits buttons).
5. `Add…` the remote user (same account as in Section 4).
6. Tick `Remote Activation`.
7. `OK` twice and close `Component Services`.

## 6. Enable LocalAccountTokenFilterPolicy

Allows NTLM-authenticated workgroup local accounts to receive a Remote UAC token (otherwise CTR's `/U CTR /P …` against STM/ACQ is filtered to a non-elevated token and every primitive fails with `Access denied`):

```powershell
$key = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
New-ItemProperty -Path $key -Name LocalAccountTokenFilterPolicy `
    -Value 1 -PropertyType DWord -Force | Out-Null
(Get-ItemProperty $key).LocalAccountTokenFilterPolicy   # should print 1
```

The value persists across reboots; no service restart required.

## 7. Windows 11 specific considerations

The five surfaces below shift behaviour on Win11 even when Sections 2–6 are correctly configured. Check each on every booth before declaring the inter-machine setup complete.

### Credential Guard

Win11 enables Virtualization-Based Security and Credential Guard by default on some SKUs (notably 24H2). Credential Guard restricts NTLM password-based auth flows from workgroup local accounts — which is exactly the auth path Sections 4–6 set up.

```powershell
Get-ComputerInfo | Select-Object DeviceGuardSmartStatus,
    DeviceGuardCodeIntegrityPolicyEnforcementStatus,
    DeviceGuardUserModeCodeIntegrityPolicyEnforcementStatus,
    DeviceGuardSecurityServicesConfigured,
    DeviceGuardSecurityServicesRunning
```

If `DeviceGuardSecurityServicesRunning` includes `CredentialGuard`, the booth's NTLM auth surface to CTR may be restricted. Options, none ideal:

- Leave Credential Guard enabled and accept any auth regressions surfaced by the harness portion of #764.
- Disable Credential Guard on the booth (group policy or registry; security tradeoff — booth machines hold no domain credentials but the system does cache local NTLM hashes).
- Move CTR-to-booth transport from NTLM-over-DCOM to WSMan/WinRM with explicit Kerberos / certificate auth — out of scope here, would invalidate the rest of this runbook.

Pick one explicitly per booth; record the choice in the operator log.

### LSASS protection (RunAsPPL)

Independent of Credential Guard, Win11 may set `RunAsPPL` to enforce LSASS as a Protected Process Light, which restricts the same NTLM password-auth surface:

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' -Name RunAsPPL `
    -ErrorAction SilentlyContinue).RunAsPPL
```

If the result is `1` or `2` and the harness portion of #764 surfaces a regression, evaluate the same trade-offs as the Credential Guard section before changing this.

### NTLM hardening (LmCompatibilityLevel)

Win11 raises the default `LmCompatibilityLevel` and tightens NTLMv2 requirements. Workgroup local-account NTLM is the precise scenario most affected:

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' -Name LmCompatibilityLevel `
    -ErrorAction SilentlyContinue).LmCompatibilityLevel
```

Microsoft's recommended value is `5` (send NTLMv2 only, refuse LM and NTLMv1). The booth code authenticates with NTLMv2 by default — value `3` (the historical Win10 default) or `5` should both work; value `0`–`2` is too permissive and `4` may cause regressions if the calling side falls back to NTLMv1. If the booths' value is anything other than `3` or `5`, document why before proceeding.

### SMB server configuration

SCHTASKS `/Create /XML` writes the temporary task XML to the target's `admin$` share, so the SMB server has to accept inbound connections from CTR with the booth's local account.

```powershell
Get-SmbServerConfiguration | Select-Object EnableSMB1Protocol, EnableSMB2Protocol,
    EnableSecuritySignature, RequireSecuritySignature, EnableAuthenticateUserSharing,
    EnableInsecureGuestLogons
```

Expected:

- `EnableSMB1Protocol = False` (off by default on both Win10 and Win11 — leave it off; it is not needed and is a security hazard).
- `EnableSMB2Protocol = True`.
- `EnableInsecureGuestLogons = False` (default on Win11; SCHTASKS does not authenticate as guest).
- `RequireSecuritySignature` may be `True` on Win11; SCHTASKS' SMB client signs by default, so this should not regress.

### Network-profile flip after in-place upgrade

Section 2 covers this. Re-walk Section 2 after any Win10→Win11 in-place upgrade.

## 8. Expected state (harness checklist)

The harness portion of #764 (`extras/perf/booth_security_snapshot.py`, run on the booth) captures and validates the state below; Section 10 documents how to run it. Capture this as the booth-side acceptance criterion:

| Property | Expected value | How to check on booth |
|---|---|---|
| WMI rule group | Enabled True | `Get-NetFirewallRule -DisplayGroup "Windows Management Instrumentation (WMI)"` |
| Scheduled Tasks rule group | Enabled True | `Get-NetFirewallRule -DisplayGroup "Remote Scheduled Tasks Management"` |
| File and Printer Sharing | Enabled True | `Get-NetFirewallRule -DisplayGroup "File and Printer Sharing"` |
| NIC profile | Private | `Get-NetConnectionProfile` |
| `LocalAccountTokenFilterPolicy` | 1 | Section 6 command |
| DCOM Remote Activation grant | present for remote user | Section 5 GUI check |
| WMI CIMV2 Remote Enable | present for remote user | Section 4 GUI check |
| `LmCompatibilityLevel` | 3 or 5 | Section 7 |
| `RunAsPPL` | 0 (unset), or documented exception | Section 7 |
| `EnableSMB1Protocol` | False | Section 7 |
| Credential Guard | not running, or documented exception | Section 7 |

## 9. Smoke test from CTR

Once the booth is configured, validate from CTR before declaring it production-ready. Substitute `<booth>` (e.g. `STM`), `<user>` (e.g. `STM`), and `<password>`.

```powershell
# 1. DCOM / WMI: list python processes on the remote booth
$pw = ConvertTo-SecureString "<password>" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ("<booth>\<user>", $pw)
$opt = New-CimSessionOption -Protocol Dcom
$sess = New-CimSession -ComputerName <booth> -Credential $cred -SessionOption $opt
Get-CimInstance -CimSession $sess -ClassName Win32_Process -Filter "Name='python.exe'" |
    Select-Object ProcessId, CommandLine
Remove-CimSession $sess

# 2. RPC / NTLM: tasklist round-trip
tasklist /S <booth> /U <user> /P <password>

# 3. SCHTASKS: query existing tasks (read-only round-trip)
SCHTASKS /Query /S <booth> /U <user> /P <password> /FO CSV /NH

# 4. SMB admin$: should list the share without error
net use \\<booth>\admin$ /USER:<user> <password>
net use \\<booth>\admin$ /DELETE
```

If all four return without an `Access denied` / RPC / SMB error, the booth is ready. If any one fails, work back through Sections 2–7; the failing primitive's transport identifies which.

## 10. Automated validation harness

The harness portion of #764 wraps Section 9's manual round-trips and Section 8's expected-state checklist into two scripts. Run both to capture a Win10 baseline before the Win11 pilot; the JSON artefacts both emit are diff-friendly for #768.

### From CTR — `extras/perf/intermachine_check.py`

Exercises each of the four remote primitives plus `admin$` SMB against every configured booth (`presentation` and each `acquisition_*` in `cfg.neurobooth_config`). Reads credentials from `secrets.yaml` so no passwords appear on the command line. Includes a SCHTASKS `/Create /XML /F` + `/Delete` round-trip with a disabled no-op task — exercises the SMB-via-`admin$` dependency the other primitives mask, and cleans up in a `finally` so nothing remains registered.

```powershell
uv run python extras/perf/intermachine_check.py
# or restrict to a single booth:
uv run python extras/perf/intermachine_check.py --targets presentation
```

Per-target verdict: `PASS` (all probes ok), `DEGRADED` (read primitives ok, write primitive failed — usually SMB), or `FAIL` (a read primitive failed — usually firewall or NTLM). Output: `<log_dir>/intermachine_check/<os>/<hostname>.json`.

### On each booth — `extras/perf/booth_security_snapshot.py`

Captures the Section 8 expected-state items into JSON for drift detection between Win10 baseline and Win11 candidate. The DCOM Launch/Activation and WMI CIMV2 ACL bytes are not decoded — captured as length + SHA-256 so any change is visible without the snapshot inspecting policy bytes. SDDL decoding is a follow-up; the contract here is "detect drift," not "interpret."

```powershell
uv run python extras/perf/booth_security_snapshot.py --role STM
```

Verdict: `PASS` if every Section 8 item matches; `WARN` with per-field reasons if any drift. The snapshot does not decide whether a drift is intentional — record any exception in the operator log alongside the JSON.

Output: `<log_dir>/booth_security_snapshot/<os>/<hostname>.json`. Re-run after any Windows servicing update so a silent default change does not regress the booth without anyone noticing.

## References

- `neurobooth_os/netcomm/client.py` — the four remote primitives and the SCHTASKS XML schema
- `extras/perf/intermachine_check.py` — CTR-side harness (Section 10)
- `extras/perf/booth_security_snapshot.py` — per-booth posture snapshot (Section 10)
- `docs/single_machine_testing.md` — how to skip this entire runbook for local dev
- #759 — Win11 upgrade evaluation umbrella (concern #2)
- #764 — parent issue
- #760 / PR #770 — the WMIC → `Get-CimInstance` code change this runbook backs
- #768 — Win10 baseline lockdown; this runbook's harness produces two of the per-booth artefacts it indexes
