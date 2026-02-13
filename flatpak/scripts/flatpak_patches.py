from common.engine import Engine
from common.logger import print_interactive_message
from common.i18n import _
from packaging.version import Version
import os


def flatpak_install_new_version(version: Version, download_url: str) -> str | None:
    """
    Monkey patch for Engine._install_new_version in Flatpak environment.
    Instead of downloading and installing, it instructs the user to update via Flatpak.
    """
    message = (
        _('A new version ({version}) is available.').format(version=version)
        + '\n\n'
        + _(
            "Please update this application using your system's software manager or by running:"
        )
        + '\n'
        + 'flatpak update com.sharlychess.SharlyChess'
    )

    print_interactive_message(message)

    # Force exit the application
    os._exit(0)

    # Return None to indicate "success" (handled) so the app doesn't try to do anything else,
    # or we could exit if we want to force the update.
    # Given the original code returns an error message string on failure and None on success,
    # returning None here mimics a successful "handling" of the situation without actually installing.
    return None


# Apply the patch
Engine._install_new_version = staticmethod(flatpak_install_new_version)
