"""macOS auto-update via Sparkle, driven by our own version detection.

We deliberately do not use Sparkle's scheduled checks or a static
``SUFeedURL``. Our GitHub-release detection (``version_updater``) decides that
an update exists and which version; we then point Sparkle's feed at that
release's appcast asset and ask it to check. Sparkle downloads the build,
verifies its EdDSA signature against ``SUPublicEDKey`` (set in the bundle's
Info.plist at build time), installs it in place and relaunches.

The Sparkle framework is embedded in the signed ``.app`` at
``Contents/Frameworks/Sparkle.framework`` (see
``scripts/export/macos/build_and_notarize.sh``). It is therefore only present
in a real build: in dev or on non-macOS, ``sparkle_available()`` returns False
and callers fall back to the legacy updater.
"""

import ctypes
import sys
from pathlib import Path
from typing import Any

from packaging.version import Version

from common import BASE_DIR
from common.logger import get_logger
from common.version_updater import VersionUpdater

logger = get_logger()

# The controller and its delegate are kept alive for the process lifetime;
# Sparkle's update runs asynchronously and would break if they were collected.
_controller: Any = None
_delegate: Any = None
_feed_url: str = ''
_init_failed = False


def _framework_binary() -> Path | None:
    """Path to the embedded Sparkle Mach-O binary, or None if not bundled.

    In the built app, ``BASE_DIR`` is ``<App>.app/Contents/Resources``, so the
    framework lives one level up in ``Contents/Frameworks``.
    """
    framework = BASE_DIR.parent / 'Frameworks' / 'Sparkle.framework'
    for candidate in (
        framework / 'Versions' / 'Current' / 'Sparkle',
        framework / 'Sparkle',
    ):
        if candidate.exists():
            return candidate
    return None


def sparkle_available() -> bool:
    """True when running a macOS build with Sparkle embedded."""
    return sys.platform == 'darwin' and _framework_binary() is not None


def _ensure_controller() -> bool:
    """Load Sparkle and build the updater controller once (retained)."""
    global _controller, _delegate, _init_failed
    if _controller is not None:
        return True
    if _init_failed:
        return False

    binary = _framework_binary()
    if binary is None:
        _init_failed = True
        return False

    try:
        ctypes.cdll.LoadLibrary(str(binary))
        from rubicon.objc import NSObject, ObjCClass, ObjCInstance, objc_method

        ns_string = ObjCClass('NSString')

        class _SparkleFeedDelegate(NSObject):  # type: ignore[misc]
            @objc_method
            def feedURLStringForUpdater_(self, updater) -> ObjCInstance:
                # Our detection has already chosen the version; hand Sparkle
                # that release's appcast asset.
                logger.info('Providing Sparkle feed URL: %s', _feed_url)
                return ns_string.stringWithUTF8String_(_feed_url.encode('utf-8'))

        updater_controller = ObjCClass('SPUStandardUpdaterController')
        _delegate = _SparkleFeedDelegate.alloc().init()
        _controller = updater_controller.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(  # noqa: E501
            True, _delegate, None
        )
    except Exception:
        logger.exception('Failed to initialise Sparkle.')
        _init_failed = True
        _controller = None
        _delegate = None
        return False
    return True


def check_for_update(version: Version) -> bool:
    """Start Sparkle's update flow targeting *version*'s appcast.

    Returns False if Sparkle is unavailable or could not start, so the caller
    can fall back to the legacy updater. On success Sparkle takes over the UI,
    download, signature check, install and relaunch.
    """
    global _feed_url
    if not sparkle_available():
        return False

    _feed_url = VersionUpdater.appcast_url(version)
    if not _ensure_controller():
        return False

    try:
        _controller.checkForUpdates_(None)
    except Exception:
        logger.exception('Sparkle checkForUpdates failed.')
        return False

    logger.info('Sparkle update check started for version %s.', version)
    return True
