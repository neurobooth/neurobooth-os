"""Report USB host controller topology for all neurobooth devices.

Run on the ACQ machine to determine which USB host controller each
device is connected to. Devices sharing a controller share bandwidth
(~5 Gbps for USB 3.0), which can cause serialized startup and
reduced throughput.

Detects: Intel RealSense D455, FLIR Blackfly, Yeti Microphone,
Mbient sensors, iPhones, and any other connected USB devices.

Usage:
    python extras/check_usb_topology.py
"""

import subprocess
import re
import sys


def run_pnputil():
    """Get all connected USB devices via pnputil."""
    result = subprocess.run(
        ["pnputil", "/enum-devices", "/connected", "/class", "USB"],
        capture_output=True, text=True
    )
    return result.stdout


def run_wmic_usb():
    """Get USB device tree via PowerShell (fallback)."""
    ps_cmd = (
        "Get-PnpDevice -Class USB -Status OK | "
        "Select-Object FriendlyName, InstanceId, Status | "
        "Format-List"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True
    )
    return result.stdout


def parse_pnputil(output):
    """Parse pnputil output into device records."""
    devices = []
    current = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            if current:
                devices.append(current)
                current = {}
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.strip()
    if current:
        devices.append(current)
    return devices


def get_parent_controller(instance_id):
    """Trace a device's instance ID up to its root USB controller."""
    # Use PowerShell to walk the device tree
    ps_cmd = f"""
    $dev = Get-PnpDevice -InstanceId '{instance_id}' -ErrorAction SilentlyContinue
    if ($dev) {{
        $current = $dev.InstanceId
        $path = @($current)
        for ($i = 0; $i -lt 10; $i++) {{
            $parent = (Get-PnpDeviceProperty -InstanceId $current -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
            if (-not $parent -or $parent -eq $current) {{ break }}
            $path += $parent
            $current = $parent
        }}
        $path | ForEach-Object {{
            $name = (Get-PnpDevice -InstanceId $_ -ErrorAction SilentlyContinue).FriendlyName
            Write-Output "$_ | $name"
        }}
    }}
    """
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip()


def main():
    print("=" * 70)
    print("USB Host Controller Topology Report")
    print("=" * 70)

    # Step 1: Find host controllers
    print("\n--- USB Host Controllers ---\n")
    ps_controllers = (
        "Get-PnpDevice -Class USB -Status OK | "
        "Where-Object { $_.FriendlyName -match 'Host Controller|xHCI' } | "
        "Format-Table FriendlyName, InstanceId -AutoSize"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_controllers],
        capture_output=True, text=True
    )
    print(result.stdout if result.stdout.strip() else "(none found)")

    # Step 2: Find all neurobooth-relevant devices
    print("\n--- Neurobooth Devices ---\n")
    # Search patterns for all device types
    device_patterns = [
        "RealSense", "Intel.R..*D4",   # Intel D455 cameras
        "Blackfly", "FLIR",             # FLIR camera
        "Yeti",                          # Mic
        "Mbient", "MetaWear",           # Mbient sensors (BLE, may appear as USB dongle)
        "iPhone", "Apple",              # iPhone
        "EyeLink", "SR Research",       # Eyelink (if USB-connected)
    ]
    pattern = "|".join(device_patterns)
    ps_devices = (
        f"Get-PnpDevice -Status OK | "
        f"Where-Object {{ $_.FriendlyName -match '{pattern}' }} | "
        f"Format-Table FriendlyName, InstanceId, Class -AutoSize"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_devices],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        print(result.stdout)
    else:
        # Broader fallback: show all cameras and audio devices
        ps_broad = (
            "Get-PnpDevice -Status OK | "
            "Where-Object { $_.Class -match 'Camera|AudioEndpoint|Imaging|Media' } | "
            "Format-Table FriendlyName, InstanceId, Class -AutoSize"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_broad],
            capture_output=True, text=True
        )
        print(result.stdout if result.stdout.strip() else "(no relevant devices found)")

    # Step 3: Trace each device to its host controller
    print("\n--- Device → Host Controller Mapping ---\n")
    ps_find = (
        f"Get-PnpDevice -Status OK | "
        f"Where-Object {{ $_.FriendlyName -match '{pattern}' }} | "
        f"Select-Object -ExpandProperty InstanceId"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_find],
        capture_output=True, text=True
    )
    device_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    if not device_ids:
        # Fallback: cameras and audio
        ps_find = (
            "Get-PnpDevice -Status OK | "
            "Where-Object { $_.Class -match 'Camera|AudioEndpoint|Imaging' } | "
            "Select-Object -ExpandProperty InstanceId"
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_find],
            capture_output=True, text=True
        )
        device_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    if not device_ids:
        print("No neurobooth devices found. Run this script on the ACQ or STM machine.")
        return

    controller_map = {}  # controller_id -> [(device_name, device_id)]
    for dev_id in device_ids:
        tree = get_parent_controller(dev_id)
        if tree:
            lines = tree.splitlines()
            dev_name = lines[0].split(" | ")[1].strip() if " | " in lines[0] else dev_id
            print(f"Device: {dev_name}")
            print(f"  Device tree (device → root):")
            controller_id = None
            controller_name = None
            for line in lines:
                parts = line.split(" | ")
                iid = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                print(f"    {name:50s}  {iid}")
                if "host controller" in name.lower() or "xhci" in name.lower():
                    controller_id = iid
                    controller_name = name
            if controller_id:
                controller_map.setdefault(
                    (controller_id, controller_name or controller_id), []
                ).append(dev_name)
        else:
            print(f"Device: {dev_id}")
            print("  (unable to trace device tree)")
        print()

    # Step 4: Summary
    print("\n--- Summary ---\n")
    if controller_map:
        for (ctrl_id, ctrl_name), devices in sorted(controller_map.items()):
            print(f"Controller: {ctrl_name}")
            print(f"  ({ctrl_id})")
            for dev in devices:
                print(f"  └─ {dev}")
            print()

        n_controllers = len(controller_map)
        n_devices = sum(len(d) for d in controller_map.values())
        print(f"{n_devices} devices across {n_controllers} controller(s)")

        # Check for RealSense cameras sharing a controller
        for (ctrl_id, ctrl_name), devices in controller_map.items():
            realsense_count = sum(1 for d in devices if "realsense" in d.lower() or "d455" in d.lower() or "intel" in d.lower())
            if realsense_count > 1:
                print(f"\n⚠ {realsense_count} RealSense cameras share controller: {ctrl_name}")
                print("  They share ~5 Gbps USB 3.0 bandwidth. pipeline.start()")
                print("  negotiations may serialize. Consider distributing across")
                print("  separate controllers via a PCIe USB card.")
    else:
        print("Could not determine controller mapping.")


if __name__ == "__main__":
    main()
