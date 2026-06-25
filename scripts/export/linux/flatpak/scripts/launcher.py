#!/usr/bin/env python3
"""
Launcher script for Sharly Chess Flatpak.

This script acts as the entrypoint for the Flatpak application,
handling proper initialization and launching the application in the Flatpak environment.
"""

import os
import sys
import logging
from pathlib import Path

# Setup logging for the launcher
logging.basicConfig(
    level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(name)s: %(message)s'
)
logger = logging.getLogger('sharly-chess-launcher')


def setup_flatpak_environment():
    """Setup environment variables for Flatpak execution."""
    logger.info('Setting up Flatpak environment...')

    # Ensure Python can find site-packages
    app_lib = Path('/app/lib')
    python_version = f'python{sys.version_info.major}.{sys.version_info.minor}'
    site_packages = app_lib / python_version / 'site-packages'

    if site_packages.exists():
        sys.path.insert(0, str(site_packages))
        logger.info(f'Added to sys.path: {site_packages}')
    else:
        logger.warning(f'site-packages not found: {site_packages}')

    # Ensure XDG directories are set properly
    # We rely on Flatpak's default XDG variables to ensure data persistence in ~/.var/app/...
    # This keeps 'events', 'logs', and 'tmp' folders inside the sandbox data directory,
    # preserving them across updates while keeping the user's home directory clean.
    xdg_data_home = os.environ.get('XDG_DATA_HOME')
    if not xdg_data_home:
        # Fallback for non-Flatpak or weird environments
        home = Path.home()
        xdg_data_home = str(
            home / '.var' / 'app' / 'com.sharlychess.SharlyChess' / 'data'
        )
        os.environ['XDG_DATA_HOME'] = xdg_data_home

    # Set working directory to XDG_DATA_HOME
    data_path = Path(xdg_data_home)
    data_path.mkdir(exist_ok=True, parents=True)
    os.chdir(data_path)

    logger.info(f'Working directory set to: {data_path}')
    logger.info('XDG directories configured')


def verify_dependencies():
    """Verify that all required dependencies are available."""
    logger.info('Verifying dependencies...')

    required_modules = [
        'litestar',
        'uvicorn',
        'toga',
        'aiosqlite',
        'jinja2',
    ]

    missing = []

    # Debug multipart specifically
    try:
        import multipart

        logger.info(f'multipart module found: {multipart.__file__}')
        try:
            from multipart import MultipartSegment  # noqa: F401

            logger.info('✓ MultipartSegment importable from multipart')
        except ImportError:
            logger.error(
                '✗ MultipartSegment NOT importable from multipart (Wrong package installed?)'
            )
    except ImportError:
        logger.warning('multipart module not found')

    for module in required_modules:
        try:
            __import__(module)
            logger.debug(f'✓ {module} available')
        except ImportError as e:
            logger.error(f'✗ {module} NOT available: {e}')
            missing.append(module)

    if missing:
        logger.error(f'Missing dependencies: {", ".join(missing)}')
        return False

    logger.info('All dependencies verified successfully')
    return True


def launch_application():
    """Launch the Sharly Chess application."""
    logger.info('Launching Sharly Chess...')

    try:
        # Set arguments before import because the module runs on import
        # We explicitly pass the current working directory (set in setup_flatpak_environment)
        # to ensure the application uses the versioned directory.
        sys.argv = ['sharly-chess', '--path', os.getcwd()]

        logger.info(f'Importing sharly_chess module with args: {sys.argv}')

        # Import the main application module
        # Note: sharly_chess.py runs the application on import
        import sharly_chess  # noqa: F401

        logger.info('Sharly Chess execution completed')

    except Exception as e:
        logger.error(f'Failed to launch application: {e}', exc_info=True)
        return False

    return True


def main():
    """Main launcher entrypoint."""
    logger.info('========== Sharly Chess Flatpak Launcher ==========')
    logger.info(f'Python: {sys.version}')
    logger.info(f'Platform: {sys.platform}')
    logger.info(f'Home: {Path.home()}')

    # Setup Flatpak environment
    setup_flatpak_environment()

    # Verify dependencies
    if not verify_dependencies():
        logger.error('Dependency verification failed')
        sys.exit(1)

    # Launch application
    if not launch_application():
        logger.error('Application launch failed')
        sys.exit(1)

    logger.info('Application terminated normally')
    sys.exit(0)


if __name__ == '__main__':
    main()
