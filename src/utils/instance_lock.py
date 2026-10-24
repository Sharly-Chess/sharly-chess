import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Self

if sys.platform == 'win32':
    import msvcrt
else:
    import fcntl

LOCK_FILE_NAME = '.instance.lock'

# The information on the running instance is written at the start of the file,
# padded to a fixed size so that a shorter rewrite never needs truncating.
_INFO_SIZE = 4096
# Windows locks are mandatory: a locked byte can not be read by the other
# processes, so the one locked sits past the information, which stays readable.
_LOCK_OFFSET = 1 << 20


class InstanceLock:
    """The lock a running Sharly Chess holds on its data folder.

    Two servers on one data folder write the same event databases, and Windows
    lets a second one start on another port without the user noticing. The lock
    is held by the operating system for as long as the process lives, so a
    crashed or killed instance never leaves a stale lock behind."""

    held: ClassVar[Self | None] = None

    def __init__(self, directory: Path):
        self.file: Path = directory / LOCK_FILE_NAME
        self._fd: int | None = None

    def acquire(self) -> bool:
        """Takes the lock, returns False if another process holds it."""
        self.file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            self.file, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o644
        )
        try:
            if sys.platform == 'win32':
                os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        self._write_info({'pid': os.getpid(), 'started': self._now()})
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        if sys.platform == 'win32':
            os.lseek(self._fd, _LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None
        if InstanceLock.held is self:
            InstanceLock.held = None

    def publish_url(self, url: str) -> None:
        """Records the address the instance serves on, for a second launch to
        send the user to it."""
        self._write_info(self.read_info() | {'url': url})

    def read_info(self) -> dict[str, Any]:
        """The information the holder of the lock wrote, empty if unreadable."""
        try:
            with open(self.file, 'rb') as file:
                data = json.loads(file.read(_INFO_SIZE).decode('utf-8').strip())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_info(self, info: dict[str, Any]) -> None:
        assert self._fd is not None
        content = json.dumps(info).encode('utf-8')[:_INFO_SIZE]
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, content.ljust(_INFO_SIZE))
        os.fsync(self._fd)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec='minutes')

    @staticmethod
    def running_message(opens_in_browser: bool) -> tuple[str, str]:
        """The title and the message a second launch shows the user."""
        from common.i18n import _

        title = _('Sharly Chess is already open')
        message = (
            _('Sharly Chess is already open on this computer.')
            + '\n\n'
            + (
                _(
                    'This second instance will close and Sharly Chess will be '
                    'shown in your browser.'
                )
                if opens_in_browser
                else _('This second instance will close.')
            )
            + '\n\n'
            + _(
                'If Sharly Chess no longer responds, force it to close, then '
                'start the application again.'
            )
        )
        return title, message

    @classmethod
    def is_held_by_another_process(cls, directory: Path) -> bool:
        if not directory.is_dir():
            return False
        if cls.held is not None and cls.held.file.parent == directory:
            return False
        lock = cls(directory)
        if not lock.acquire():
            return True
        lock.release()
        return False
