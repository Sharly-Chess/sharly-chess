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
import os
import sys
from pathlib import Path
from typing import Any

from packaging.version import Version

from common import BASE_DIR
from common.logger import get_logger

logger = get_logger()


class SparkleUpdater:
    # The controller and its delegate are kept alive for the process lifetime;
    # Sparkle's update runs asynchronously and would break if they were collected.
    _controller: Any = None
    _delegate: Any = None
    _feed_url: str = ''
    _init_failed = False

    @classmethod
    def is_retryable(cls) -> bool:
        return not cls._init_failed

    @staticmethod
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

    @classmethod
    def sparkle_available(cls) -> bool:
        """True when running a macOS build with Sparkle embedded."""
        return sys.platform == 'darwin' and cls._framework_binary() is not None

    @classmethod
    def _ensure_controller(cls) -> bool:
        """Load Sparkle and build the updater controller once (retained)."""
        if cls._controller is not None:
            return True
        if cls._init_failed:
            return False

        binary = cls._framework_binary()
        if binary is None:
            cls._init_failed = True
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
                    feed_url = SparkleUpdater._feed_url
                    logger.info('Providing Sparkle feed URL: %s', feed_url)
                    return ns_string.stringWithUTF8String_(feed_url.encode('utf-8'))

            updater_controller = ObjCClass('SPUStandardUpdaterController')
            _delegate = _SparkleFeedDelegate.alloc().init()
            _controller = updater_controller.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(  # noqa: E501
                True, _delegate, None
            )
        except Exception:
            logger.exception('Failed to initialise Sparkle.')
            cls._init_failed = True
            cls._controller = None
            cls._delegate = None
            return False
        return True

    @staticmethod
    def appcast_url(version: Version) -> str:
        """URL of the per-release Sparkle appcast asset for *version*.

        Each release attaches its own ``appcast.xml`` (signed in CI); the macOS
        Sparkle updater is pointed at this at runtime instead of a static feed.

        For local testing, ``SHARLY_CHESS_APPCAST_URL`` overrides the URL (e.g.
        a ``http://localhost:8000/appcast.xml`` served from a folder), so the
        full Sparkle flow can be exercised without an online release.
        """
        override = os.environ.get('SHARLY_CHESS_APPCAST_URL')
        if override:
            return override
        base_url = 'https://github.com/Sharly-Chess/sharly-chess/releases/download'
        return f'{base_url}/{version}/appcast.xml'

    @classmethod
    def check_for_update(cls, version: Version) -> bool:
        """Start Sparkle's update flow targeting *version*'s appcast.

        Returns False if Sparkle is unavailable or could not start, so the caller
        can fall back to the legacy updater. On success Sparkle takes over the UI,
        download, signature check, install and relaunch.
        """
        if not cls.sparkle_available():
            return False

        _feed_url = cls.appcast_url(version)
        if not cls._ensure_controller():
            return False

        try:
            cls._controller.checkForUpdates_(None)
        except Exception:
            logger.exception('Sparkle checkForUpdates failed.')
            return False

        logger.info('Sparkle update check started for version %s.', version)
        return True
