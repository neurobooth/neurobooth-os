"""Intel RealSense SDK smoke test for the Win10 -> Win11 decision (#763).

Fails loudly if pyrealsense2 is absent (the Win11 signal, not a mock
fallback). Reports the pyrealsense2 version + device serial/on-camera
firmware and starts a pipeline to grab **one** frameset, proving the
USB-bandwidth/data path is alive. Emits the shared envelope to
``<log_dir>/realsense_smoke/<os>/<hostname>.json``.

Usage::

    uv run python extras/perf/realsense_smoke.py [--out PATH] [--no-json]
        [--stdout] [--strict]
"""

import sys

from _sdk_probe import smoke_cli

if __name__ == "__main__":
    sys.exit(smoke_cli("realsense", "realsense_smoke"))
