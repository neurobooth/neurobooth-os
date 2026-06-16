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


def pytest_sessionfinish(session, exitstatus):
    """Safety net so a leaked thread can never silently hang the whole suite.

    The suite exercises real device threads; a test that leaves a *non-daemon*
    thread alive (e.g. a listener parked in a blocking read) makes the
    interpreter's ``threading._shutdown()`` block forever joining it, so the
    process hangs after every test has already passed -- with no output. This
    arms a daemon timer once the session ends: if the process hasn't exited
    within the grace period, it dumps every thread's stack (making the offending
    thread obvious instead of requiring a bisect) and force-exits with the real
    status. On a normal run the process exits in well under a second and the
    timer is simply abandoned, so this is a no-op unless something actually hangs.
    """
    import faulthandler
    import os
    import sys
    import threading

    def _force_exit() -> None:
        sys.stderr.write(
            "\n[conftest] interpreter did not exit within 30s of the test session "
            "ending -- a non-daemon thread was likely leaked. Thread dump follows:\n"
        )
        faulthandler.dump_traceback(file=sys.stderr)
        os._exit(int(exitstatus) if exitstatus is not None else 0)

    watchdog = threading.Timer(30.0, _force_exit)
    watchdog.daemon = True
    watchdog.start()
