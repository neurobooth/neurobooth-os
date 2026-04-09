"""Background process monitor that logs CPU, memory, and disk IO per process.

Runs in a daemon thread, writing CSV snapshots at a configurable interval.
Designed to run for the lifetime of a session on ACQ and STM machines.

Columns: timestamp, pid, name, status, cpu_pct, mem_mb, mem_pct,
         read_mbs, write_mbs, sys_cpu_pct, sys_ram_pct, n_processes
"""

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

HEADER = "timestamp,pid,name,status,cpu_pct,mem_mb,mem_pct,read_mbs,write_mbs,sys_cpu_pct,sys_ram_pct,n_processes\n"


class ProcessMonitor:
    """Periodically snapshots top processes by CPU and writes to a CSV file.

    Parameters
    ----------
    output_path : str or Path
        CSV file to append to.
    interval_sec : int
        Seconds between snapshots (excluding the 1s CPU measurement window).
    top_n : int
        Number of top-CPU processes to record per snapshot.
    """

    def __init__(self, output_path: str, interval_sec: int = 3, top_n: int = 30):
        self._path = Path(output_path)
        self._interval = interval_sec
        self._top_n = top_n
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._prev_io: dict = {}

    def start(self) -> None:
        """Start the monitor in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("ProcessMonitor already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ProcessMonitor")
        self._thread.start()
        logger.info(f"ProcessMonitor started: {self._path}")

    def stop(self) -> None:
        """Signal the monitor to stop and wait for it to finish."""
        if self._thread is None or not self._thread.is_alive():
            return
        self._stop_event.set()
        self._thread.join(timeout=10)
        logger.info("ProcessMonitor stopped")

    def _run(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self._path.exists() or self._path.stat().st_size == 0

        try:
            with open(self._path, "a") as f:
                if write_header:
                    f.write(HEADER)
                while not self._stop_event.is_set():
                    procs = self._sample()
                    self._write_snapshot(f, procs)
                    self._stop_event.wait(timeout=self._interval)
        except Exception:
            logger.exception("ProcessMonitor crashed")

    def _sample(self) -> list:
        """Sample all processes for CPU, memory, and IO."""
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'status']):
            if proc.pid == 0:
                continue
            try:
                proc.cpu_percent()
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
                    if pid in self._prev_io:
                        prev_r, prev_w, prev_t = self._prev_io[pid]
                        dt = now - prev_t
                        if dt > 0:
                            read_rate = max((io.read_bytes - prev_r) / dt / 1024 / 1024, 0.0)
                            write_rate = max((io.write_bytes - prev_w) / dt / 1024 / 1024, 0.0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                results.append({
                    'pid': pid,
                    'name': proc.name(),
                    'status': proc.status(),
                    'cpu_pct': cpu,
                    'mem_mb': mem / 1024 / 1024,
                    'mem_pct': mem / total_ram * 100,
                    'read_mbs': read_rate,
                    'write_mbs': write_rate,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self._prev_io = new_io
        return sorted(results, key=lambda x: x['cpu_pct'], reverse=True)

    def _write_snapshot(self, f, procs: list) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
        sys_cpu = psutil.cpu_percent()
        sys_ram = psutil.virtual_memory().percent
        n_procs = len(procs)

        for p in procs[:self._top_n]:
            name = p['name'].replace(',', ';')
            f.write(
                f"{ts},{p['pid']},{name},{p['status']},"
                f"{p['cpu_pct']:.1f},{p['mem_mb']:.1f},{p['mem_pct']:.2f},"
                f"{p['read_mbs']:.2f},{p['write_mbs']:.2f},"
                f"{sys_cpu},{sys_ram},{n_procs}\n"
            )
        f.flush()
