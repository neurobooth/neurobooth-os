"""iPhone usbmux smoke test for the Win10 -> Win11 decision (#763).

Enumerates iPhones over the usbmux socket and, in smoke mode, performs a
**connect + handshake then immediate close** -- the smallest action that
proves the usbmux path is alive and that exercises the #669
``select.select()`` socket-close race well enough to catch its recurrence on
Win11. It does **not** start a recording: an iPhone capture would produce
video the transfer workflow sweeps to permanent storage (the same constraint
that made #762's iPhone co-runner synthetic). Emits the shared envelope to
``<log_dir>/iphone_smoke/<os>/<hostname>.json``.

Usage::

    uv run python extras/perf/iphone_smoke.py [--out PATH] [--no-json]
        [--stdout] [--strict]
"""

import sys

from _sdk_probe import smoke_cli

if __name__ == "__main__":
    sys.exit(smoke_cli("iphone", "iphone_smoke"))
