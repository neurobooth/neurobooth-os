"""Make the loose ``extras/`` perf scripts importable in unit tests.

``extras/perf/*.py`` use bare sibling imports (``from _baseline_common
import ...``) exactly as they do when run as scripts from that directory, so
the unit tests put ``extras/`` and ``extras/perf/`` on ``sys.path`` -- the
import-time equivalent of running from there. This only prepends paths; it
does not change behaviour for the existing ``neurobooth_os`` tests.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT / "extras", _REPO_ROOT / "extras" / "perf"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
