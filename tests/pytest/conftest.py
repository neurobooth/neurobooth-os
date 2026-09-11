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


_DISPLAY_AVAILABLE = None


def display_available() -> bool:
    """True when this process can open a window.

    PsychoPy imports pyglet, and importing ``pyglet.window`` builds a hidden
    "shadow window" at import time. With no reachable display that raises
    ``IndexError`` from ``get_screens()[0]`` during collection, taking the
    whole run down rather than reporting a skip -- so the check has to happen
    before the import, not in a marker.

    Disabling the shadow window (``pyglet.options['shadow_window'] = False``)
    is not an alternative: on macOS PsychoPy then segfaults in
    ``gltools.getOpenGLInfo``, which calls ``glGetString`` with no context.

    The check runs in this process on purpose. A subprocess reports no screens
    even when its parent can see three, so a subprocess probe would skip these
    tests on a perfectly usable desktop.

    A display can be absent for ordinary reasons -- a CI runner, an ssh
    session, a Mac whose display has gone to sleep (``caffeinate -u`` wakes
    it) -- none of which say anything about the code under test.
    """
    global _DISPLAY_AVAILABLE
    if _DISPLAY_AVAILABLE is None:
        try:
            import pyglet

            _DISPLAY_AVAILABLE = bool(pyglet.canvas.get_display().get_screens())
        except Exception:
            # Any failure to enumerate screens means no window can be opened,
            # which is the only thing the caller needs to know.
            _DISPLAY_AVAILABLE = False
    return _DISPLAY_AVAILABLE
