import logging
import os
import sys
import warnings
from pathlib import Path

from pathvalidate import validate_filepath, ValidationError

# Nuclear option: Override warnings.warn to block specific messages
# warnings.filterwarnings simply would not work
_original_warn = warnings.warn


def _filtered_warn(*args, **kwargs):
    """Custom warn function that filters out known problematic warnings"""
    if len(args) > 0:
        message_str = str(args[0])

        # List of warning messages to suppress
        suppressed_messages = [
            'server parameter is deprecated, use dsn instead',
        ]

        # Check if this message should be suppressed
        for suppressed in suppressed_messages:
            if suppressed in message_str:
                return  # Suppress this warning

        # Also suppress if it's a DeprecationWarning category
        if len(args) > 1 and args[1] is DeprecationWarning:
            category_str = str(args[1])
            if 'DeprecationWarning' in category_str:
                return

    # If not suppressed, call the original warn function
    _original_warn(*args, **kwargs)


warnings.warn = _filtered_warn

try:
    if sys.platform == 'win32':
        # Windows marks the downloaded files as unsure and blocks their usage.
        # On the first run, all the files of the distribution are unmarked.

        base_dir: Path = Path(sys.argv[0]).resolve().parent
        tracer: Path = base_dir / 'tmp' / '.unblock_files'
        if tracer.exists():
            print(f'Unblocking files in : {base_dir}')
            for root_, __, files in os.walk(base_dir):
                for name in files:
                    path = os.path.join(root_, name)
                    # Remove Zone.Identifier ADS if it exists
                    ads_path = path + ':Zone.Identifier'
                    try:
                        os.remove(ads_path)
                        print(f'Unblocked: {path}')
                    except FileNotFoundError:
                        pass  # not blocked or already unblocked
                    except Exception as e:
                        print(f'Failed to unblock {path}: {e}')
            # Remove not to run twice
            tracer.unlink()

    elif sys.platform == 'darwin':
        # Prevent MacOS from sleeping the windowed app when it's in the background
        from rubicon.objc import ObjCClass

        NSProcessInfo = ObjCClass('NSProcessInfo')
        NSProcessInfo.processInfo.beginActivityWithOptions_reason_(
            0x00FFFFFF,  # NSActivityUserInitiated | NSActivityLatencyCritical
            'Prevent App Nap',
        )

    elif sys.platform == 'linux':
        # Patch gi.require_version to handle "already required" case gracefully
        # This prevents errors when GTK is required multiple times (e.g., by runtime hook and toga_gtk)
        try:
            import gi  # type: ignore[import-not-found]

            _original_require_version = gi.require_version

            def _patched_require_version(namespace, version):
                """Patched version that handles 'already required' or 'already loaded' gracefully."""
                try:
                    return _original_require_version(namespace, version)
                except ValueError as e:
                    error_str = str(e)
                    # If the error is "already requires version" or "already loaded", that's fine - continue
                    # This happens when GTK is required multiple times (e.g., by pre-check and toga_gtk)
                    if (
                        'already requires version' in error_str
                        or 'already loaded' in error_str
                    ):
                        return
                    # Otherwise, re-raise the error
                    raise

            gi.require_version = _patched_require_version
            # Note: We don't force GTK4 here because Toga's WebView requires GTK3
            # Toga will automatically use the appropriate GTK version based on what's available
            # We only require GObject to ensure it's available
            try:
                gi.require_version('GObject', '2.0')
                # Don't force GTK4 - let Toga choose (it needs GTK3 for WebView)
                # gi.require_version('Gtk', '4.0')  # Commented out - Toga needs GTK3 for WebView
            except (ImportError, ValueError):
                # gi not available or already required, that's fine
                pass
        except ImportError:
            # gi not available, skip patching
            pass

    import argparse
    import asyncio

    from utils.scripts import init_script

    arguments = init_script()

    from common import DEVEL_ENV, TEST_ENV
    from common.logger import (
        get_logger,
        print_interactive_error,
        set_logging_config,
    )
    from gui.server_gui_toga import SharlyChessServerToga
    from web.server_engine import ServerEngine
    from antivirus.control import search_missing_files
    from antivirus.detect import detect_antivirus_programs

    logger = get_logger()

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        help='force the web port tu use',
    )
    if DEVEL_ENV:
        parser.add_argument(
            '-d',
            '--debug',
            help='on the webserver, if there is an uncaught exception, drop to PDB',
            action='store_true',
        )
    if DEVEL_ENV or TEST_ENV:
        parser.add_argument(
            '--cli',
            action='store_true',
            help='Force console/CLI mode (default is GUI for bundled apps)',
        )
    parser.add_argument(
        '-g',
        '--generate-tournament',
        action='store_true',
        help='generate a random tournament',
    )
    parser.add_argument(
        '-s',
        '--random-seed',
        type=int,
        help='the random seed to use (to reproduce tournament generation)',
    )
    parser.add_argument(
        '-c',
        '--check-tournament',
        action='store_true',
        help='generate a random tournament',
    )
    parser.add_argument(
        'input_file',
        type=str,
        help='the input file',
        nargs='?',
    )
    parser.add_argument(
        '-o',
        '--output-file',
        type=str,
        help='the output file',
    )

    args = parser.parse_args(arguments)

    if args.generate_tournament or args.check_tournament:
        trf_input_file_path: Path
        if args.generate_tournament:
            if not args.output_file:
                print_interactive_error('Argument --output-file is needed, exiting.')
                sys.exit(1)
            try:
                validate_filepath(args.output_file)
            except ValidationError:
                print_interactive_error(
                    f'Invalid output file [{args.output_file}], exiting.'
                )
                sys.exit(1)
            trf_input_file_path = Path(args.output_file)
            if args.check_tournament:
                if args.input_file:
                    print_interactive_error(
                        'Input file not needed with argument --generate-tournament, ignored.'
                    )
        else:
            if not args.input_file:
                print_interactive_error('Input file is required, exiting.')
                sys.exit(1)
            try:
                validate_filepath(args.input_file)
            except ValidationError:
                print_interactive_error(
                    f'Invalid input file [{args.input_file}], exiting.'
                )
                sys.exit(1)
            trf_input_file_path = Path(args.input_file)

        from data.pairings.checkers import BbpPairingsChecker
        from data.pairings.generators import BbpPairingsGenerator

        if args.generate_tournament:
            BbpPairingsGenerator().generate_tournament(
                trf_input_file_path,
                args.random_seed,
            )
        if args.check_tournament:
            if not trf_input_file_path.exists():
                print_interactive_error(
                    f'TRF input file [{trf_input_file_path}] not found, exiting.'
                )
                sys.exit(1)
            BbpPairingsChecker().check_tournament(trf_input_file_path)

        sys.exit(0)

    port = args.port or None
    debug = args.debug if DEVEL_ENV else False
    if debug:
        # set the log level to DEBUG before loading the logging configuration of the application
        set_logging_config(console_log_level=logging.DEBUG)

    if error_message := search_missing_files(folder=Path(), delete_control_file=True):
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror('Sharly Chess startup error', error_message)
        root.destroy()
        sys.exit(1)
    detect_antivirus_programs()
    # Check if GUI mode should be used
    if not TEST_ENV and not (DEVEL_ENV and args.cli):
        # Pre-check GTK availability on Linux before trying to create the app
        gtk_available = True
        if sys.platform == 'linux':
            logger.info('Performing GTK3 pre-check before GUI initialization...')
            try:
                import os
                import gi  # type: ignore[import-not-found]

                # Require GTK3 (needed for WebView support - GTK4 doesn't support WebView yet)
                try:
                    gi.require_version('Gtk', '3.0')
                    gi.require_version(
                        'Gdk', '3.0'
                    )  # Also require Gdk 3.0 to match Gtk 3.0
                    gtk_version = '3.0'
                    logger.debug('GTK3 available (required for WebView support)')
                except (ImportError, ValueError) as e:
                    logger.exception(
                        'GTK3 is required for WebView support but is not available. '
                        'Please install GTK3 development libraries (e.g., libgtk-3-dev on Ubuntu/Debian).'
                    )
                    raise ImportError('GTK3 is required but not available') from e

                from gi.repository import Gdk  # type: ignore[import-not-found]

                # Log environment variables for debugging
                logger.debug('DISPLAY: %s', os.environ.get('DISPLAY'))
                logger.debug('GDK_BACKEND: %s', os.environ.get('GDK_BACKEND'))
                logger.debug(
                    'LD_LIBRARY_PATH: %s', os.environ.get('LD_LIBRARY_PATH', '')[:200]
                )
                logger.debug('GTK version: %s', gtk_version)

                # Try to open the display explicitly if DISPLAY is set
                display = None
                display_name = os.environ.get('DISPLAY')
                if display_name:
                    try:
                        # Try to open the display explicitly
                        display = Gdk.Display.open(display_name)
                        logger.debug('Successfully opened display: %s', display_name)
                    except Exception as e:
                        logger.debug('Failed to open display explicitly: %s', e)
                        # Fall back to getting default display
                        display = Gdk.Display.get_default()
                else:
                    # No DISPLAY set, try default
                    display = Gdk.Display.get_default()

                if display is None:
                    logger.warning(
                        f'GTK{gtk_version} cannot access display (Gdk.Display.get_default() returned None). '
                        'Falling back to CLI mode.'
                    )
                    gtk_available = False
                else:
                    logger.info(
                        f'GTK{gtk_version} display check passed, proceeding with GUI initialization'
                    )
                    logger.debug(
                        'GTK display name: %s',
                        display.get_name() if display else 'None',
                    )
            except Exception as e:
                logger.warning(
                    'GTK pre-check failed: %s. Falling back to CLI mode.',
                    e,
                    exc_info=True,
                )
                gtk_available = False

        # Create and run the Toga app - this should block until the app exits
        if gtk_available:
            logger.info('Creating Toga application...')
            try:
                app = SharlyChessServerToga(debug=debug, port=port)
                logger.info(
                    'Toga application created successfully, starting main loop...'
                )
                app.main_loop()
                sys.exit(0)
            except RuntimeError as e:
                # Catch GTK display errors and fall back to CLI mode
                error_str = str(e)
                if (
                    'Cannot identify an active display' in error_str
                    or 'display' in error_str.lower()
                ):
                    logger.warning(
                        'GUI mode failed (display error): %s. Falling back to CLI mode.',
                        error_str,
                    )
                    # Log additional diagnostic information
                    import os

                    logger.debug(
                        'DISPLAY environment variable: %s', os.environ.get('DISPLAY')
                    )
                    logger.debug(
                        'GDK_BACKEND environment variable: %s',
                        os.environ.get('GDK_BACKEND'),
                    )
                    logger.debug(
                        'LD_LIBRARY_PATH: %s',
                        os.environ.get('LD_LIBRARY_PATH', '')[:200],
                    )
                    logger.info(
                        'To use GUI mode, ensure DISPLAY is set and X11 is accessible. '
                        'You can also use --cli to force CLI mode.'
                    )
                    # Fall through to CLI mode below
                else:
                    raise
            except Exception as e:
                # Log any other GUI initialization errors for debugging
                logger.exception(
                    'GUI initialization failed with unexpected error: %s',
                    e,
                )
                raise

    # Original console mode
    try:
        se: ServerEngine = ServerEngine(debug=debug, port=port)
        asyncio.run(se.serve())
    except KeyboardInterrupt:
        pass

except Exception:
    import traceback

    message = traceback.format_exc()
    try:
        from common.logger import get_logger

        logger = get_logger()
        logger.exception(message)
    except Exception:
        pass

    test_env = os.getenv('TEST_ENV') == 'true'
    if test_env:
        sys.exit(1)

    title = 'Sharly Chess startup error'

    if sys.platform == 'win32':
        import tkinter
        from tkinter import messagebox

        base_dir = Path(sys.argv[0]).resolve().parent
        if not os.access(base_dir, os.W_OK):
            message = (
                f'Write permission is missing from [{base_dir.absolute()}].\n'
                'Check the permissions of the directory then try again.'
            )

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()

    elif sys.platform == 'darwin':
        import subprocess

        message = message.replace('"', '\\"')
        script = (
            f'display alert "{title}" message "{message}" as critical buttons {{"OK"}}'
        )
        subprocess.run(['osascript', '-e', script], check=True)

    elif sys.platform == 'linux':
        print(f'{title}: {message}')
