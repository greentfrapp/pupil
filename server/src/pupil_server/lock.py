"""One sidecar per database, held by an OS lock the process gives up when it exits."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PID_WIDTH = 32
"""The pid is written at the start of the file, padded to this width."""

LOCKED_AT = 4096
"""The byte locked, past the pid: a Windows lock also stops others reading the range."""


class DatabaseInUse(RuntimeError):
    """Another live process owns this database."""

    def __init__(self, db_path: Path, pid: str) -> None:
        self.pid = pid
        holder = f"pid {pid}" if pid else "another process"
        super().__init__(
            f"another Pupil sidecar ({holder}) is using {db_path}. Stop it first, or set "
            "PUPIL_DB_PATH to use a different database."
        )


class DatabaseLock:
    """Held for the life of the sidecar."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._path = db_path.with_name(db_path.name + ".lock")
        self._fd: int | None = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _lock(fd)
        except OSError:
            holder = _read_pid(fd)
            os.close(fd)
            raise DatabaseInUse(self._db_path, holder) from None
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(os.getpid()).encode().ljust(PID_WIDTH))
        self._fd = fd

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            _unlock(fd)
        finally:
            os.close(fd)


def _read_pid(fd: int) -> str:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        return os.read(fd, PID_WIDTH).decode(errors="replace").strip()
    except OSError:
        return ""


if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, LOCKED_AT, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, LOCKED_AT, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
