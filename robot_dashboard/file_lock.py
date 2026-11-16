"""Registry advisory locking; native flock on POSIX, exclusive byte lock on Windows."""

import os

if os.name != "nt":
    from fcntl import LOCK_EX, LOCK_SH, LOCK_UN, flock
else:
    import errno
    import msvcrt
    import time

    LOCK_EX, LOCK_SH, LOCK_UN = 2, 1, 8

    def flock(fd, mode):
        os.lseek(fd, 0, os.SEEK_SET)
        if mode == LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return
        # Windows readers serialize too; never emulate a lock with a no-op.
        # Avoid the CRT's coarse blocking retry while another Python thread owns it.
        deadline = time.monotonic() + 30
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EDEADLK} or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)
