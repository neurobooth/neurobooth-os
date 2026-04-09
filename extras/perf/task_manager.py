"""Lightweight process monitor for neurobooth machines.

Periodically snapshots the top processes by CPU usage and appends
them to a log file with ISO timestamps. Useful for capturing system
load on ACQ/STM during sessions.

Disk IO columns are per-interval rates (MB/s), not cumulative totals.

Usage:
    python extras/perf/task_manager.py                     # default: process_log.csv, 3s interval
    python extras/perf/task_manager.py -o session.csv      # custom output file
    python extras/perf/task_manager.py --interval 5        # 5 second interval
    python extras/perf/task_manager.py --top 10            # top 10 processes per snapshot
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


# Track previous IO counters per PID to compute rates
_prev_io = {}  # pid -> (read_bytes, write_bytes, timestamp)


def get_processes():
    """Sample all processes for CPU, memory, and IO usage.

    Calls cpu_percent() twice with a 1s gap so the measurement
    reflects actual utilization over that window. IO rates are
    computed as deltas from the previous snapshot.
    """
    global _prev_io

    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'status']):
        if proc.pid == 0:  # System Idle Process reports bogus CPU on Windows
            continue
        try:
            proc.cpu_percent()  # prime it
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        procs.append(proc)

    time.sleep(1)

    now = time.monotonic()
    results = []
    total_ram = psutil.virtual_memory().total
    new_io = {}

    for proc in procs:
        try:
            pid = proc.pid
            cpu = proc.cpu_percent()
            mem = proc.memory_info().rss

            read_rate = 0.0
            write_rate = 0.0
            try:
                io = proc.io_counters()
                new_io[pid] = (io.read_bytes, io.write_bytes, now)
                if pid in _prev_io:
                    prev_r, prev_w, prev_t = _prev_io[pid]
                    dt = now - prev_t
                    if dt > 0:
                        read_rate = (io.read_bytes - prev_r) / dt / 1024 / 1024
                        write_rate = (io.write_bytes - prev_w) / dt / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            results.append({
                'pid': pid,
                'name': proc.name(),
                'status': proc.status(),
                'cpu_pct': cpu,
                'mem_mb': mem / 1024 / 1024,
                'mem_pct': mem / total_ram * 100,
                'read_mbs': max(read_rate, 0.0),
                'write_mbs': max(write_rate, 0.0),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _prev_io = new_io
    return sorted(results, key=lambda x: x['cpu_pct'], reverse=True)


HEADER = "timestamp,pid,name,status,cpu_pct,mem_mb,mem_pct,read_mbs,write_mbs,sys_cpu_pct,sys_ram_pct,n_processes\n"


def write_snapshot(f, procs, top_n=30):
    """Append one snapshot (top_n processes) to the open file handle."""
    ts = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    sys_cpu = psutil.cpu_percent()
    sys_ram = psutil.virtual_memory().percent
    n_procs = len(procs)

    for p in procs[:top_n]:
        name = p['name'].replace(',', ';')  # sanitize for CSV
        f.write(
            f"{ts},{p['pid']},{name},{p['status']},"
            f"{p['cpu_pct']:.1f},{p['mem_mb']:.1f},{p['mem_pct']:.2f},"
            f"{p['read_mbs']:.2f},{p['write_mbs']:.2f},"
            f"{sys_cpu},{sys_ram},{n_procs}\n"
        )
    f.flush()


def main():
    parser = argparse.ArgumentParser(description="Log process snapshots to a CSV file.")
    parser.add_argument("-o", "--output", default="process_log.csv",
                        help="Output CSV file (default: process_log.csv)")
    parser.add_argument("--interval", type=int, default=3,
                        help="Seconds between snapshots (default: 3)")
    parser.add_argument("--top", type=int, default=30,
                        help="Number of top processes per snapshot (default: 30)")
    args = parser.parse_args()

    path = Path(args.output)
    write_header = not path.exists() or path.stat().st_size == 0

    print(f"Logging to {path.resolve()} every {args.interval}s (top {args.top} processes)")
    print("Press Ctrl+C to stop.\n")

    with open(path, "a") as f:
        if write_header:
            f.write(HEADER)

        snapshot = 0
        try:
            while True:
                procs = get_processes()
                write_snapshot(f, procs, top_n=args.top)
                snapshot += 1
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"  [{ts}] Snapshot {snapshot}: {len(procs)} processes, "
                      f"CPU {psutil.cpu_percent()}%, RAM {psutil.virtual_memory().percent}%",
                      end="\r")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n\nSaved {snapshot} snapshots to {path.resolve()}")


if __name__ == '__main__':
    main()
