"""FLIR / Spinnaker SDK smoke test for the Win10 -> Win11 decision (#763).

Fails loudly if PySpin is absent (that is the Win11 signal -- not a mock
fallback). Reports the Spinnaker library version + camera serial/firmware
and grabs **one** frame to prove the data path is alive. Importing the
production driver also applies its ``KMP_DUPLICATE_LIB_OK`` workaround, which
#763 wants measured on Win11. Emits the shared envelope to
``<log_dir>/flir_smoke/<os>/<hostname>.json``.

Usage::

    uv run python extras/perf/flir_smoke.py [--out PATH] [--no-json]
        [--stdout] [--strict]
"""

import sys

from _sdk_probe import smoke_cli

if __name__ == "__main__":
    sys.exit(smoke_cli("flir", "flir_smoke"))
