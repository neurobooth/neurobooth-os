"""Webcam / DirectShow smoke test for the Win10 -> Win11 decision (#763).

Opens the webcam through ``cv2.VideoCapture(0, cv2.CAP_DSHOW)`` exactly as
the production driver does, reports OpenCV's version and -- crucially --
``cap.getBackendName()`` so a Win11 silent fall-through from DirectShow to
the MediaFoundation compatibility shim is visible (#763 point 5), then reads
**one** frame. Emits the shared envelope to
``<log_dir>/webcam_smoke/<os>/<hostname>.json``.

Usage::

    uv run python extras/perf/webcam_smoke.py [--out PATH] [--no-json]
        [--stdout] [--strict]
"""

import sys

from _sdk_probe import smoke_cli

if __name__ == "__main__":
    sys.exit(smoke_cli("webcam", "webcam_smoke"))
