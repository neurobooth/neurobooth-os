# -*- coding: utf-8 -*-
"""Advisory single-byte file locking, on Windows and on POSIX.

The GUI enforces one running instance by holding an exclusive lock on the first
byte of ``gui.lock`` for the life of the process. Only the first byte is locked,
so a second launch can still read the holder's PID and start time -- which the
lock file carries from offset 1 -- without contending for the lock itself.

Windows provides that through ``msvcrt.locking``; POSIX through ``fcntl.lockf``.
Importing ``msvcrt`` unconditionally, as ``gui.py`` used to, fails at import
time on every non-Windows machine.

The two implementations are not identical and the difference matters:

* Windows byte-range locks are **mandatory** and their behaviour for two
  handles in the same process is documented as undefined.
* POSIX ``lockf`` locks are **advisory** and are owned per-process, not per
  descriptor, so the same process re-locking succeeds rather than failing, and
  closing *any* descriptor for the file drops the lock.

Both are sufficient for the case this guards -- two separate processes racing,
the double-click -- but a test must exercise that with a real subprocess rather
than a same-process second acquire.
"""

import os
import sys

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


def try_lock(file_descriptor: int) -> bool:
    """Try to take an exclusive lock on the first byte, without blocking.

    Args:
        file_descriptor: An open, writable descriptor. Its offset is moved to
            the start of the file.

    Returns:
        ``True`` if the lock was taken, ``False`` if another process holds it.

    Raises:
        OSError: For failures other than contention, which the caller should
            not mistake for "someone else has it".
    """
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    try:
        if sys.platform == "win32":
            msvcrt.locking(file_descriptor, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.lockf(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB, 1)
    except OSError as e:
        # EACCES / EAGAIN mean "held elsewhere"; anything else is a real fault.
        # Windows reports contention as EACCES (errno 13) from msvcrt.locking.
        import errno
        if e.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return False
        raise
    return True


def unlock(file_descriptor: int) -> None:
    """Release the first-byte lock. Safe to call when the lock is already gone."""
    try:
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        if sys.platform == "win32":
            msvcrt.locking(file_descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.lockf(file_descriptor, fcntl.LOCK_UN, 1)
    except OSError:
        # The descriptor may already be closed, or the lock already dropped by
        # process exit. Releasing a lock that is not held is not a failure.
        pass
