import os
import platform
import shutil
import subprocess
import sys
from logging import Logger
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from common import SHARLY_CHESS_VERSION
from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class LinuxProjectBuilder(ProjectBuilder):
    """Linux specific class to export the project."""

    def __init__(self):
        super().__init__(clean_project_on_exit=False)
        self.executable_name: str = self.basename
        self.appdir: Path = self.project_dir / f'{self.project_name}.AppDir'

        # Detect architecture from the native runner
        machine = platform.machine().lower()

        if machine in ('aarch64', 'arm64'):
            self.arch = 'arm64'
            self.arch_lib_dir = 'aarch64-linux-gnu'
        elif machine in ('x86_64', 'amd64'):
            self.arch = 'x86_64'
            self.arch_lib_dir = 'x86_64-linux-gnu'
        else:
            raise OSError(
                f'AppImage build is not supported for architecture: {machine}'
            )

        self.appimage: Path = (
            self.export_dir
            / f'{self.project_name}-{SHARLY_CHESS_VERSION}-{self.arch}.AppImage'
        )

        # Override zip_file to include architecture name
        self.zip_file: Path = (
            self.export_dir
            / f'{self.project_name}-{SHARLY_CHESS_VERSION}-{self.arch}.zip'
        )

    @property
    def _python_dir(self) -> Path:
        """Returns the base dir for Python."""
        try:
            # devel
            return Path(os.environ['VIRTUAL_ENV']) / 'bin'
        except KeyError:
            # GitHub
            return Path(sys.executable).parent

    @property
    def hook_get_venv_lib_path(
        self,
    ) -> Path:
        """Returns the path to the libraries of the virtual environment."""
        # Try to detect Python version from sys.executable
        python_version = f'{sys.version_info.major}.{sys.version_info.minor}'
        return (
            self._python_dir
            / '..'
            / 'lib'
            / f'python{python_version}'
            / 'site-packages'
        )

    def hook_pyinstaller_additional_params(self) -> list[str]:
        """Add Linux-specific PyInstaller parameters."""
        icon_path = f'src/web/static/images/{self.project_name}.png'
        params = []
        if Path(icon_path).exists():
            params.append(f'--icon={icon_path}')

        # Collect gi.repository submodules (needed for Toga/GTK)
        # Also collect all gi data files (typelib files, etc.) needed for introspection
        params.extend(
            [
                '--collect-submodules=gi.repository',
                '--collect-all=gi',  # Collect all gi data files including typelib files
                # Ensure GObject introspection data is included
                '--hidden-import=gi.repository.GObject',
                '--hidden-import=gi.repository.Gtk',
                '--hidden-import=gi.repository.Gdk',
            ]
        )

        return params

    def hook_post_build_project(self) -> bool:
        """Create AppImage after PyInstaller build."""
        logger.info('Creating Linux AppImage...')

        # Find the PyInstaller executable
        executable = self.project_dir / self.executable_name
        if not executable.exists():
            logger.error(f'Executable not found: {executable}')
            return False

        # Create AppDir structure
        if not self._create_appdir(executable):
            return False

        # Create AppRun script
        if not self._create_apprun():
            return False

        # Create .desktop file
        if not self._create_desktop_file():
            return False

        # Copy icon
        if not self._copy_icon():
            return False

        # Create AppImage using appimagetool
        if not self._create_appimage():
            return False

        logger.info(f'AppImage created successfully: {self.appimage}')
        return True

    def build_zip_file(self) -> bool:
        """Create a zip file containing the AppImage and user folders."""
        logger.info('Creating archive [%s]...', self.zip_file)
        self.zip_file.parent.mkdir(parents=True, exist_ok=True)

        with ZipFile(self.zip_file, 'w', ZIP_DEFLATED) as zip_file:
            cwd: str = os.getcwd()

            # Add the AppImage to the zip with a simplified name
            if self.appimage.exists():
                appimage_zip_name = 'SharlyChess.AppImage'
                logger.info(f'Adding AppImage to archive as: {appimage_zip_name}')
                zip_file.write(self.appimage, appimage_zip_name)
            else:
                logger.error(f'AppImage not found: {self.appimage}')
                return False

            # Add user folders from project_dir (events, logs, custom, LICENSES, etc.)
            # Exclude _internal, executable, and AppDir
            exclude_items = {
                self.executable_name,
                self.appdir.name,
                '_internal',
                'tools',  # Tools are embedded in the executable
            }

            # Change to project_dir so paths are relative
            os.chdir(self.project_dir)

            items_added = []
            for item in Path('.').iterdir():
                if item.name in exclude_items:
                    logger.debug(f'Skipping excluded item: {item.name}')
                    continue

                if item.is_dir():
                    # Add directory and all its contents
                    # Walk from the item (which is now relative to project_dir)
                    file_count = 0
                    for root, dirs, files in os.walk(item):
                        # root is already relative to project_dir (since we chdir'd)
                        # Write directory entry
                        zip_file.write(root, root)
                        # Write files
                        for filename in files:
                            file_path = Path(root) / filename
                            zip_file.write(file_path, str(file_path))
                            file_count += 1
                    items_added.append(f'{item.name}/ ({file_count} files)')
                else:
                    # Add file at root of zip
                    zip_file.write(item, item.name)
                    items_added.append(item.name)

            logger.info(f'Added to zip: {items_added}')

            os.chdir(cwd)

        # Delete the AppImage file after creating the zip
        if self.appimage.exists():
            logger.info(f'Deleting AppImage file: {self.appimage}')
            self.appimage.unlink()

        logger.info(f'Archive created successfully: {self.zip_file}')
        return True

    def _create_appdir(self, executable: Path) -> bool:
        """Create the AppDir structure and copy files."""
        logger.info(f'Creating AppDir structure at {self.appdir}...')

        # Remove existing AppDir if it exists
        if self.appdir.exists():
            shutil.rmtree(self.appdir)

        # Create AppDir structure
        self.appdir.mkdir(parents=True)
        usr_bin = self.appdir / 'usr' / 'bin'
        usr_bin.mkdir(parents=True)
        usr_share = self.appdir / 'usr' / 'share'
        usr_share.mkdir(parents=True)

        # Copy the executable
        logger.info(f'Copying executable to {usr_bin}...')
        shutil.copy2(executable, usr_bin / self.executable_name)
        (usr_bin / self.executable_name).chmod(0o755)

        # Copy _internal directory to usr/bin (PyInstaller requires it next to the executable)
        internal_dir = self.project_dir / '_internal'
        if internal_dir.exists() and internal_dir.is_dir():
            logger.info(f'Copying _internal directory to {usr_bin}...')
            shutil.copytree(internal_dir, usr_bin / '_internal', dirs_exist_ok=True)

        # Copy all other files from project_dir to AppDir/usr/share
        logger.info('Copying application files to AppDir...')
        for item in self.project_dir.iterdir():
            if (
                item.name == self.executable_name
                or item.name == self.appdir.name
                or item.name == '_internal'
            ):
                continue
            dest = usr_share / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        return True

    def _create_apprun(self) -> bool:
        """Create the AppRun script."""
        logger.info('Creating AppRun script...')
        apprun = self.appdir / 'AppRun'

        apprun_content = f"""#!/bin/bash
# AppRun script for {self.project_name}

# Get the directory where AppRun is located (AppImage mount point)
APPDIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# Set environment variables
export PATH="$APPDIR/usr/bin:$PATH"
export APPDIR

# Toga will automatically use GTK3 when WebView is needed
# Set environment variables for GTK
export GTK_THEME="Adwaita"

# Force GTK to use X11 backend (not Wayland)
# This is critical - if GDK_BACKEND is set to wayland or not set, GTK might fail to connect
export GDK_BACKEND="x11"

# Library path: prioritize system libraries (X11) before AppImage libraries
# This ensures GTK can find system X11 libraries to connect to the display
# Also add common library paths that might contain X11/GTK libraries
export LD_LIBRARY_PATH="/usr/lib:/usr/lib/x86_64-linux-gnu:/usr/lib/aarch64-linux-gnu:/lib:/lib/x86_64-linux-gnu:/lib/aarch64-linux-gnu:/usr/local/lib:/usr/local/lib/x86_64-linux-gnu:/usr/local/lib/aarch64-linux-gnu:$APPDIR/usr/lib/x86_64-linux-gnu:$APPDIR/usr/lib/aarch64-linux-gnu:$APPDIR/usr/lib:${{LD_LIBRARY_PATH}}"

# GTK-specific environment variables
# Ensure GTK can find its settings and modules
export GTK_DATA_PREFIX="$APPDIR/usr"
export GTK_EXE_PREFIX="$APPDIR/usr"
# Support both GTK3 (for WebView) and GTK4 paths
export GTK_PATH="$APPDIR/usr/lib/x86_64-linux-gnu/gtk-3.0:$APPDIR/usr/lib/gtk-3.0:$APPDIR/usr/lib/x86_64-linux-gnu/gtk-4.0:$APPDIR/usr/lib/gtk-4.0"
# But also allow system GTK modules
export GTK_PATH="/usr/lib/x86_64-linux-gnu/gtk-3.0:/usr/lib/gtk-3.0:/usr/lib/x86_64-linux-gnu/gtk-4.0:/usr/lib/gtk-4.0:$GTK_PATH"

# Ensure DISPLAY is set for X11 applications
# First, try to get DISPLAY from the current environment (it should be set on Ubuntu with UI)
# If not set, try to detect it
if [ -z "$DISPLAY" ]; then
    # On Ubuntu with a desktop, DISPLAY is usually :0 or :1
    # Check for active X11 sockets
    if [ -S /tmp/.X11-unix/X0 ]; then
        export DISPLAY=":0"
    elif [ -S /tmp/.X11-unix/X1 ]; then
        export DISPLAY=":1"
    elif [ -n "$WAYLAND_DISPLAY" ]; then
        # Wayland detected - GTK should handle this, but set DISPLAY for compatibility
        export DISPLAY=":0"
    else
        # Try to get from the user's session (common on Ubuntu)
        # Check if we're in a graphical session
        if [ -n "$XDG_SESSION_TYPE" ] && [ "$XDG_SESSION_TYPE" = "x11" ]; then
            export DISPLAY=":0"
        elif [ -n "$XDG_SESSION_TYPE" ] && [ "$XDG_SESSION_TYPE" = "wayland" ]; then
            export DISPLAY=":0"
        else
            # Default fallback
            export DISPLAY=":0"
        fi
    fi
fi

# Export DISPLAY to ensure it's available to the application
export DISPLAY

# Also ensure XAUTHORITY is set if it exists (needed for X11 authentication)
if [ -n "$XAUTHORITY" ]; then
    export XAUTHORITY
elif [ -f "$HOME/.Xauthority" ]; then
    export XAUTHORITY="$HOME/.Xauthority"
fi

# Test if we can load X11 libraries (this helps diagnose the issue)
echo "Checking X11 library dependencies..." >&2
# Check if system X11 libraries are accessible (we rely on system libraries, not bundled ones)
X11_LIBS_FOUND=0

# Check if we can dynamically load libX11 from system
if command -v ldconfig >/dev/null 2>&1; then
    # Try to find libX11 using ldconfig
    if ldconfig -p 2>/dev/null | grep -q "libX11.so"; then
        echo "System libX11 found via ldconfig" >&2
        X11_LIBS_FOUND=1
    fi
fi

# Test if we can actually load libX11 with current LD_LIBRARY_PATH
# This is what GTK will need to do at runtime
# We prioritize system libraries, so this should find system X11 libraries
if command -v python3 >/dev/null 2>&1; then
    if python3 -c "import ctypes; ctypes.CDLL('libX11.so.6')" 2>/dev/null; then
        echo "Successfully loaded libX11.so.6 from system via Python ctypes" >&2
        X11_LIBS_FOUND=1
    else
        echo "Warning: Could not load libX11.so.6 from system" >&2
        echo "This may prevent GTK from initializing" >&2
        echo "Make sure X11 development libraries are installed on the system" >&2
    fi
fi

# Check if GTK3 libraries are accessible (GTK3 is required for WebView support)
echo "Checking GTK3 library accessibility..." >&2
if command -v python3 >/dev/null 2>&1; then
    # Try to import gi and check if GTK3 can be loaded (required for WebView)
    if python3 -c "
import sys
sys.path.insert(0, '$APPDIR/usr/bin/_internal')
try:
    import gi
    # Require GTK3 (needed for WebView - GTK4 doesn't support WebView yet)
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')  # Also require Gdk 3.0 to match Gtk 3.0
    from gi.repository import Gtk, Gdk
    # Try to initialize GTK3 display
    display = Gdk.Display.get_default()
    if display:
        print('GTK3 display initialized successfully')
    else:
        print('Warning: GTK3 display is None')
except Exception as e:
    print('Error initializing GTK3: ' + str(e))
    sys.exit(1)
" 2>&1; then
        echo "GTK3 can be initialized successfully" >&2
    else
        echo "Warning: GTK3 initialization test failed" >&2
        echo "GTK3 is required for WebView support" >&2
    fi
fi

# Note: The PyInstaller executable doesn't directly link to X11 libraries
# GTK loads them dynamically at runtime, so ldd won't show them
# The important check is whether we can load them dynamically (above)
if [ $X11_LIBS_FOUND -eq 0 ]; then
    echo "Warning: X11 libraries may not be accessible to GTK" >&2
fi

# Find the AppImage file location and change to its directory
# This allows the app to find events, logs, and other user folders
# AppImage runtime sets ARGV0 to the AppImage path
APPIMAGE_PATH="${{ARGV0}}"
if [ -n "$APPIMAGE_PATH" ] && [ -f "$APPIMAGE_PATH" ]; then
    # Resolve the AppImage path and change to its directory
    APPIMAGE_DIR="$(cd "$(dirname "$APPIMAGE_PATH")" && pwd)"
    cd "$APPIMAGE_DIR"
else
    # Fallback: look for AppImage or user folders in current directory and parents
    SEARCH_DIR="$(pwd)"
    FOUND=false
    for i in 1 2 3 4 5; do
        # Check if this directory contains the AppImage or user folders
        if ls "$SEARCH_DIR"/{self.project_name}-*.AppImage 1> /dev/null 2>&1 || \\
           [ -d "$SEARCH_DIR/events" ] || [ -d "$SEARCH_DIR/logs" ]; then
            cd "$SEARCH_DIR"
            FOUND=true
            break
        fi
        SEARCH_DIR="$(cd "$SEARCH_DIR/.." && pwd)"
        # Stop at filesystem root
        if [ "$SEARCH_DIR" = "/" ]; then
            break
        fi
    done
    if [ "$FOUND" = false ]; then
        # Last resort: use current directory
        cd "$(pwd)"
    fi
fi

# Ensure all necessary environment variables are exported and passed to the application
# This is critical for GTK/X11 to work properly
# Also ensure system libraries are accessible for X11
export LD_LIBRARY_PATH
export DISPLAY
export GDK_BACKEND
export GTK_THEME
export GTK_DATA_PREFIX
export GTK_EXE_PREFIX
export GTK_PATH
if [ -n "$XAUTHORITY" ]; then
    export XAUTHORITY
fi

# Suppress harmless warnings
# Redirect snapd mount namespace warnings to /dev/null (they're harmless)
exec 2> >(grep -v "update.go.*cannot change mount namespace" >&2 || true)

# Suppress GTK atk-bridge warning (harmless - GTK provides this natively)
export GTK_DEBUG=no-css-cache

# Run the application - explicitly pass environment variables to ensure they're available
# Use env to ensure all environment variables are passed to the executable
exec env DISPLAY="$DISPLAY" \\
    GDK_BACKEND="$GDK_BACKEND" \\
    GTK_THEME="$GTK_THEME" \\
    GTK_DATA_PREFIX="$GTK_DATA_PREFIX" \\
    GTK_EXE_PREFIX="$GTK_EXE_PREFIX" \\
    GTK_PATH="$GTK_PATH" \\
    LD_LIBRARY_PATH="$LD_LIBRARY_PATH" \\
    APPDIR="$APPDIR" \\
    "$APPDIR/usr/bin/{self.executable_name}" "$@"
"""

        with open(apprun, 'w', encoding='utf-8') as f:
            f.write(apprun_content)

        apprun.chmod(0o755)
        return True

    def _create_desktop_file(self) -> bool:
        """Create the .desktop file."""
        logger.info('Creating .desktop file...')
        desktop_file = self.appdir / f'{self.project_name}.desktop'

        desktop_content = f"""[Desktop Entry]
Type=Application
Name=Sharly Chess
GenericName=Chess Tournament Manager
Comment=Chess tournament management software
Exec={self.executable_name}
Icon={self.project_name}
Categories=Utility;
Terminal=false
StartupNotify=true
"""

        with open(desktop_file, 'w', encoding='utf-8') as f:
            f.write(desktop_content)

        return True

    def _copy_icon(self) -> bool:
        """Copy the application icon."""
        logger.info('Copying application icon...')
        icon_source = Path(f'src/web/static/images/{self.project_name}.png')

        if not icon_source.exists():
            logger.warning(f'Icon not found at {icon_source}, skipping...')
            return True  # Not critical, continue anyway

        # Create icons directory
        icons_dir = (
            self.appdir / 'usr' / 'share' / 'icons' / 'hicolor' / '512x512' / 'apps'
        )
        icons_dir.mkdir(parents=True, exist_ok=True)

        # Copy icon
        icon_dest = icons_dir / f'{self.project_name}.png'
        shutil.copy2(icon_source, icon_dest)

        # Also create a symlink in AppDir root for AppImage
        root_icon = self.appdir / f'{self.project_name}.png'
        if root_icon.exists() or root_icon.is_symlink():
            root_icon.unlink()
        root_icon.symlink_to(icon_dest.relative_to(self.appdir))

        return True

    def _create_appimage(self) -> bool:
        """Create the AppImage using appimagetool."""
        logger.info('Creating AppImage using appimagetool...')

        # Check if appimagetool is available in PATH (e.g., installed by CI)
        appimagetool_cmd = shutil.which('appimagetool')

        # Download appimagetool if not found in PATH
        # Since we're using native runners, host architecture matches target architecture
        if not appimagetool_cmd:
            logger.info('appimagetool not found in PATH. Downloading...')
            host_is_arm64 = self.arch == 'arm64'
            if not self._download_appimagetool(host_is_arm64):
                logger.error(
                    'appimagetool is required to create AppImage. Failed to download.'
                )
                logger.error(
                    'You can download it from: https://github.com/AppImage/AppImageKit/releases'
                )
                return False
            appimagetool_cmd = str(self.project_dir / 'appimagetool')
            Path(appimagetool_cmd).chmod(0o755)

        # Create the AppImage
        self.appimage.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing AppImage if it exists
        if self.appimage.exists():
            self.appimage.unlink()

        # Set ARCH environment variable to match the target architecture
        # appimagetool expects 'aarch64' for ARM64, not 'arm64'
        env = os.environ.copy()
        if self.arch == 'arm64':
            arch_env = 'aarch64'
        else:
            arch_env = self.arch
        env['ARCH'] = arch_env
        logger.info(f'Setting ARCH environment variable to: {arch_env}')

        cmd = [
            'env',
            f'ARCH={arch_env}',
            appimagetool_cmd,
            str(self.appdir),
            str(self.appimage),
        ]

        logger.info(f'Running: {" ".join(cmd)}')
        logger.info(f'ARCH will be set to: {arch_env}')
        # Verify ARCH is in environment
        if 'ARCH' in env:
            logger.info(f'ARCH in environment dict: {env["ARCH"]}')
        else:
            logger.warning('ARCH not in environment dict!')

        # On GitHub runners, also check if there are any x86_64 libraries in system paths
        # that might confuse appimagetool (since it's dynamically linked)
        if os.environ.get('GITHUB_ACTIONS'):
            logger.info(
                'Running on GitHub Actions - checking for potential architecture conflicts...'
            )
            try:
                # Check if there are x86_64 libraries in common system paths
                # that the dynamically linked appimagetool might find
                check_paths = ['/usr/lib', '/lib', '/usr/local/lib']
                for check_path in check_paths:
                    if Path(check_path).exists():
                        # This is just for info - we can't prevent appimagetool from checking these
                        logger.debug(f'System library path exists: {check_path}')
            except Exception:
                pass

        try:
            # Always use env dict - ARCH is set in env for extracted binaries,
            # and prepended via env command for AppImages
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            logger.info('appimagetool output:')
            if result.stdout:
                logger.info(result.stdout)
            if result.stderr:
                logger.warning(result.stderr)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f'appimagetool failed with return code {e.returncode}')
            if e.stdout:
                logger.error(f'stdout: {e.stdout}')
            if e.stderr:
                logger.error(f'stderr: {e.stderr}')
            return False
        except FileNotFoundError:
            logger.error('appimagetool not found. Please install appimagetool.')
            return False

    def _download_appimagetool(self, host_is_arm64: bool = False) -> bool:
        """Download appimagetool matching the native runner architecture."""
        try:
            import urllib.request
        except ImportError:
            logger.error('urllib.request not available. Cannot download appimagetool.')
            return False

        # Download appimagetool matching the runner architecture
        # Since we use native runners, host architecture matches target architecture
        if host_is_arm64:
            appimagetool_url = 'https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-aarch64.AppImage'
            arch_name = 'ARM64'
        else:
            appimagetool_url = 'https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage'
            arch_name = 'x86_64'

        appimagetool_path = self.project_dir / 'appimagetool'

        try:
            logger.info(
                f'Downloading appimagetool ({arch_name}) from {appimagetool_url}...'
            )
            urllib.request.urlretrieve(appimagetool_url, appimagetool_path)
            appimagetool_path.chmod(0o755)
            logger.info('appimagetool downloaded successfully')
            return True
        except Exception as e:
            logger.error(f'Failed to download appimagetool: {e}')
            return False
