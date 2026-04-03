"""Report full USB host controller topology.

Enumerates all USB host controllers and shows every device attached
to each, organized by hub. Useful for identifying bandwidth sharing
(devices on the same controller share ~5 Gbps for USB 3.0) and
diagnosing startup contention.

Usage:
    python extras/check_usb_topology.py
"""

import subprocess
import sys
from collections import defaultdict


def get_all_usb_devices():
    """Get all connected USB devices with their parent relationships in one call.

    Returns a list of dicts with keys: instance_id, name, class_name, parent_id.
    """
    # Single PowerShell call: get every connected PnP device under USB
    # controllers, along with its parent instance ID.
    ps_cmd = r"""
    $devices = Get-PnpDevice -Status OK -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -match '^USB|^BTHENUM|^HID\\VID' }

    # Also grab host controllers and root hubs (Class = USB)
    $usbClass = Get-PnpDevice -Class USB -Status OK -ErrorAction SilentlyContinue
    $all = @($devices) + @($usbClass) | Sort-Object InstanceId -Unique

    foreach ($dev in $all) {
        $parent = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId `
                   -KeyName 'DEVPKEY_Device_Parent' `
                   -ErrorAction SilentlyContinue).Data
        $busInfo = (Get-PnpDeviceProperty -InstanceId $dev.InstanceId `
                    -KeyName 'DEVPKEY_Device_BusReportedDeviceDesc' `
                    -ErrorAction SilentlyContinue).Data
        Write-Output "$($dev.InstanceId)|$($dev.FriendlyName)|$($dev.Class)|$parent|$busInfo"
    }
    """
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        print("Error: PowerShell timed out enumerating devices.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0 and result.stderr.strip():
        print(f"PowerShell warning: {result.stderr.strip()}", file=sys.stderr)

    devices = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        devices.append({
            "instance_id": parts[0].strip(),
            "name": parts[1].strip() or parts[0].strip(),
            "class_name": parts[2].strip(),
            "parent_id": parts[3].strip(),
            "bus_desc": parts[4].strip() if len(parts) > 4 else "",
        })
    return devices


def build_tree(devices):
    """Build a parent -> children tree and identify host controllers."""
    by_id = {d["instance_id"]: d for d in devices}
    children = defaultdict(list)
    controllers = []

    for d in devices:
        pid = d["parent_id"]
        children[pid].append(d["instance_id"])
        name_lower = d["name"].lower()
        if "host controller" in name_lower or "xhci" in name_lower:
            controllers.append(d["instance_id"])

    return by_id, children, controllers


def print_tree(node_id, by_id, children, prefix="", is_last=True):
    """Recursively print a device tree."""
    dev = by_id.get(node_id)
    if not dev:
        return

    connector = "└─ " if is_last else "├─ "
    name = dev["name"]
    bus = f"  ({dev['bus_desc']})" if dev["bus_desc"] and dev["bus_desc"] != dev["name"] else ""
    cls = dev["class_name"]
    cls_str = f"  [{cls}]" if cls and cls != "USB" else ""

    print(f"{prefix}{connector}{name}{bus}{cls_str}")

    child_prefix = prefix + ("   " if is_last else "│  ")
    child_ids = children.get(node_id, [])
    # Sort children: hubs first, then by name
    child_ids = sorted(child_ids, key=lambda c: (
        0 if "hub" in by_id.get(c, {}).get("name", "").lower() else 1,
        by_id.get(c, {}).get("name", ""),
    ))

    for i, child_id in enumerate(child_ids):
        print_tree(child_id, by_id, children, child_prefix, i == len(child_ids) - 1)


def main():
    print("=" * 70)
    print("USB Topology Report")
    print("=" * 70)

    print("\nEnumerating devices...", end="", flush=True)
    devices = get_all_usb_devices()
    print(f" found {len(devices)} USB-related devices.\n")

    if not devices:
        print("No USB devices found. Ensure you have permission to query PnP devices.")
        return

    by_id, children, controllers = build_tree(devices)

    if not controllers:
        # Fallback: look for root hubs if controller names don't match
        for d in devices:
            name_lower = d["name"].lower()
            if "root hub" in name_lower:
                controllers.append(d["instance_id"])

    if not controllers:
        print("No USB host controllers found.\n")
        print("All detected USB devices:")
        for d in devices:
            print(f"  {d['name']:50s}  [{d['class_name']}]  {d['instance_id']}")
        return

    # Print tree from each controller
    for i, ctrl_id in enumerate(sorted(controllers)):
        ctrl = by_id.get(ctrl_id, {})
        print(f"Controller {i + 1}: {ctrl.get('name', ctrl_id)}")
        print(f"  {ctrl_id}")

        child_ids = children.get(ctrl_id, [])
        child_ids = sorted(child_ids, key=lambda c: (
            0 if "hub" in by_id.get(c, {}).get("name", "").lower() else 1,
            by_id.get(c, {}).get("name", ""),
        ))
        for j, child_id in enumerate(child_ids):
            print_tree(child_id, by_id, children, "  ", j == len(child_ids) - 1)
        print()

    # Summary: count per controller
    print("--- Summary ---\n")

    def count_leaves(node_id):
        kids = children.get(node_id, [])
        if not kids:
            return [node_id]
        leaves = []
        for kid in kids:
            leaves.extend(count_leaves(kid))
        return leaves

    total_devices = 0
    for ctrl_id in sorted(controllers):
        ctrl = by_id.get(ctrl_id, {})
        leaves = [by_id[lid] for lid in count_leaves(ctrl_id) if lid in by_id and lid != ctrl_id]
        # Filter out hubs from leaf count
        endpoints = [l for l in leaves if "hub" not in l["name"].lower()]
        total_devices += len(endpoints)
        print(f"{ctrl.get('name', ctrl_id)}:")
        print(f"  {len(endpoints)} endpoint device(s)")
        for ep in sorted(endpoints, key=lambda e: e["name"]):
            print(f"    {ep['name']:50s}  [{ep['class_name']}]")
        print()

    print(f"Total: {total_devices} endpoint device(s) across {len(controllers)} controller(s)")


if __name__ == "__main__":
    main()
