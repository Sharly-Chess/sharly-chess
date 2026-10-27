import os
import subprocess
import sys


def relaunch_command() -> list[str]:
    """The command that starts Sharly Chess again as it was started, the
    options of the command line included."""
    if getattr(sys, 'frozen', False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


def relaunch() -> None:
    """Starts Sharly Chess again and leaves at once.

    The instance starting completes what this one asked for — the move of the
    data folder — and waits for the folder to be let go: an open file holds
    both the folder and the lock until the process holding it is gone, so this
    one goes now rather than through the usual shutdown, which keeps the log
    file open to the end.
    """
    arguments: dict[str, object] = {'close_fds': True}
    if sys.platform == 'win32':
        arguments['creationflags'] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        arguments['start_new_session'] = True
    subprocess.Popen(relaunch_command(), **arguments)  # type: ignore[call-overload]
    os._exit(0)
