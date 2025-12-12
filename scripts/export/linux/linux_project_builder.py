import os
import platform
import shlex
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

            # Debug: List all items in project_dir before iterating
            logger.info(f'Contents of project_dir ({self.project_dir}):')
            for item in Path('.').iterdir():
                logger.info(f'  - {item.name} ({item.is_dir() and "dir" or "file"})')
                if item.suffix == '.zip':
                    logger.warning(
                        f'  WARNING: Found zip file in project_dir: {item.name}'
                    )

            items_added = []
            for item in Path('.').iterdir():
                if item.name in exclude_items:
                    logger.debug(f'Skipping excluded item: {item.name}')
                    continue

                # Explicitly skip zip files (shouldn't be any, but be safe)
                if item.suffix == '.zip':
                    logger.warning(
                        f'Skipping zip file found in project_dir: {item.name}'
                    )
                    continue

                if item.is_dir():
                    # Add directory and all its contents
                    # Walk from the item (which is now relative to project_dir)
                    file_count = 0
                    for root, dirs, files in os.walk(item):
                        # Filter out zip files from the walk
                        files = [f for f in files if not f.endswith('.zip')]
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

        # Debug: List contents of the created zip file to verify it doesn't contain itself
        logger.info('Verifying zip file contents...')
        try:
            with ZipFile(self.zip_file, 'r') as verify_zip:
                zip_contents = verify_zip.namelist()
                logger.info(f'Zip file contains {len(zip_contents)} items:')
                for name in sorted(zip_contents)[:20]:  # Show first 20 items
                    logger.info(f'  - {name}')
                if len(zip_contents) > 20:
                    logger.info(f'  ... and {len(zip_contents) - 20} more items')

                # Check if zip file contains itself or another zip file
                zip_files_in_zip = [
                    name for name in zip_contents if name.endswith('.zip')
                ]
                if zip_files_in_zip:
                    logger.error(
                        f'ERROR: Zip file contains {len(zip_files_in_zip)} zip file(s):'
                    )
                    for zip_name in zip_files_in_zip:
                        logger.error(f'  - {zip_name}')
                    logger.error(
                        'This should not happen! The zip file should not contain zip files.'
                    )
        except Exception as e:
            logger.warning(f'Could not verify zip file contents: {e}')

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

        # Note: We do NOT copy X11 libraries into the AppImage
        # X11 libraries are core system components that should be provided by the host system
        # Copying them can cause compatibility issues across different Linux distributions
        # Instead, we rely on system libraries via LD_LIBRARY_PATH (set in AppRun)
        # This is the standard AppImage approach and ensures better portability

        logger.info(
            'Relying on system X11 libraries via LD_LIBRARY_PATH '
            '(standard AppImage practice for better portability)'
        )

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

# Note: Toga's WebView requires GTK3, so we don't force GTK4
# Toga will automatically use GTK3 when WebView is needed
# Set environment variables for GTK
export GTK_THEME="Adwaita"

# Force GTK to use X11 backend (not Wayland)
# This is critical - if GDK_BACKEND is set to wayland or not set, GTK might fail to connect
export GDK_BACKEND="x11"

# Library path: prioritize system libraries (X11) before AppImage libraries
# This ensures GTK can find system X11 libraries to connect to the display
# System libraries must come first so X11 client libraries are accessible
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
Categories=Game;
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
        downloaded = False

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
            downloaded = True
            Path(appimagetool_cmd).chmod(0o755)

        # Create the AppImage
        self.appimage.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing AppImage if it exists
        if self.appimage.exists():
            self.appimage.unlink()

        # Diagnostic: Check architectures in AppDir (for debugging)
        logger.info('Checking architectures in AppDir...')
        architectures_found = set()

        # Also check parent directory - appimagetool might be scanning it
        logger.info('Checking AppDir parent directory for ELF files...')
        try:
            parent_elf_result = subprocess.run(
                [
                    'find',
                    str(self.appdir.parent),
                    '-maxdepth',
                    '1',
                    '-type',
                    'f',
                    '-executable',
                ],
                capture_output=True,
                text=True,
            )
            if parent_elf_result.returncode == 0 and parent_elf_result.stdout.strip():
                parent_files = parent_elf_result.stdout.strip().split('\n')
                parent_x86 = 0
                parent_arm = 0
                for pf in parent_files:
                    if pf and pf != str(self.appdir):
                        pf_result = subprocess.run(
                            ['file', pf],
                            capture_output=True,
                            text=True,
                        )
                        if pf_result.returncode == 0:
                            pf_output = pf_result.stdout
                            if 'ELF' in pf_output:
                                if 'x86-64' in pf_output or 'x86_64' in pf_output:
                                    parent_x86 += 1
                                    logger.warning(
                                        f'x86_64 ELF file in parent directory: {pf}'
                                    )
                                elif (
                                    'aarch64' in pf_output or 'ARM aarch64' in pf_output
                                ):
                                    parent_arm += 1
                if parent_x86 > 0 or parent_arm > 0:
                    logger.info(
                        f'Parent directory ELF files: x86_64={parent_x86}, ARM64={parent_arm}'
                    )
        except Exception as e:
            logger.debug(f'Could not check parent directory: {e}')

        try:
            # Use file command to check binary architectures
            # Check ALL files (not just executables) to see what appimagetool might detect
            result = subprocess.run(
                ['find', str(self.appdir), '-type', 'f'],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                all_files = result.stdout.strip().split('\n')
                logger.info(f'Found {len(all_files)} total files in AppDir')

                # Check all ELF files for architecture (appimagetool checks ELF files)
                x86_64_count = 0
                arm64_count = 0
                other_count = 0
                elf_files_checked = 0

                for file_path in all_files:
                    file_result = subprocess.run(
                        ['file', file_path],
                        capture_output=True,
                        text=True,
                    )
                    if file_result.returncode == 0:
                        file_output = file_result.stdout.strip()
                        # Only check ELF files (binaries and shared libraries)
                        if 'ELF' in file_output:
                            elf_files_checked += 1
                            # Check for architecture indicators
                            if (
                                'x86-64' in file_output
                                or 'x86_64' in file_output
                                or 'Intel 80386' in file_output
                            ):
                                architectures_found.add('x86_64')
                                x86_64_count += 1
                                if x86_64_count <= 5:  # Log first few
                                    logger.warning(
                                        f'x86_64 ELF file found: {file_path}'
                                    )
                            elif (
                                'aarch64' in file_output
                                or 'ARM aarch64' in file_output
                                or 'ARM64' in file_output
                            ):
                                architectures_found.add('aarch64')
                                arm64_count += 1
                                if arm64_count <= 5:  # Log first few
                                    logger.debug(f'ARM64 ELF file found: {file_path}')
                            else:
                                architectures_found.add('other')
                                other_count += 1
                                if other_count <= 5:  # Log first few
                                    logger.warning(
                                        f'Other architecture ELF file: {file_path} - {file_output}'
                                    )

                logger.info(f'Checked {elf_files_checked} ELF files')

                logger.info(
                    f'Architecture summary: x86_64={x86_64_count}, ARM64={arm64_count}, other={other_count}'
                )

                # Check what libraries the main executable depends on
                # This might reveal if it's finding x86_64 libraries
                main_executable = self.appdir / 'usr' / 'bin' / self.executable_name
                if main_executable.exists():
                    logger.info('Checking library dependencies of main executable...')
                    try:
                        exec_ldd_result = subprocess.run(
                            ['ldd', str(main_executable)],
                            capture_output=True,
                            text=True,
                        )
                        if exec_ldd_result.returncode == 0:
                            # Check if any dependencies point to x86_64 libraries
                            exec_lib_paths = []
                            for line in exec_ldd_result.stdout.split('\n'):
                                if '=>' in line:
                                    lib_path = line.split('=>')[1].strip().split()[0]
                                    if (
                                        lib_path
                                        and lib_path != 'not'
                                        and lib_path.startswith('/')
                                    ):
                                        exec_lib_paths.append(lib_path)

                            # Check architectures of these libraries
                            exec_lib_x86 = 0
                            exec_lib_arm = 0
                            for lib_path in exec_lib_paths[:10]:  # Check first 10
                                try:
                                    lib_file_result = subprocess.run(
                                        ['file', lib_path],
                                        capture_output=True,
                                        text=True,
                                    )
                                    if lib_file_result.returncode == 0:
                                        lib_output = lib_file_result.stdout
                                        if (
                                            'x86-64' in lib_output
                                            or 'x86_64' in lib_output
                                        ):
                                            exec_lib_x86 += 1
                                            logger.warning(
                                                f'Main executable depends on x86_64 library: {lib_path}'
                                            )
                                        elif (
                                            'aarch64' in lib_output
                                            or 'ARM aarch64' in lib_output
                                        ):
                                            exec_lib_arm += 1
                                except Exception:
                                    pass
                            if exec_lib_x86 > 0:
                                logger.warning(
                                    f'Main executable has {exec_lib_x86} x86_64 library dependencies - this might confuse appimagetool'
                                )
                            logger.info(
                                f'Main executable library architectures: x86_64={exec_lib_x86}, ARM64={exec_lib_arm}'
                            )
                    except Exception as e:
                        logger.debug(f'Could not check main executable libraries: {e}')

                # Report errors if wrong architectures are found
                if len(architectures_found) > 1:
                    logger.error(
                        f'ERROR: Multiple architectures detected in AppDir: {architectures_found}. '
                        f'This should not happen - all binaries should be {self.arch}.'
                    )
                    logger.error(
                        f'Expected architecture: {self.arch}, but found: {architectures_found}'
                    )
                elif self.arch == 'arm64' and x86_64_count > 0:
                    logger.error(
                        f'ERROR: Building ARM64 but found {x86_64_count} x86_64 binaries. '
                        'This indicates PyInstaller bundled wrong architecture libraries.'
                    )
                elif self.arch == 'x86_64' and arm64_count > 0:
                    logger.error(
                        f'ERROR: Building x86_64 but found {arm64_count} ARM64 binaries. '
                        'This indicates a configuration issue.'
                    )
        except Exception as e:
            logger.warning(f'Could not check AppDir architectures: {e}')

        # Set ARCH environment variable to match the target architecture
        # appimagetool expects 'aarch64' for ARM64, not 'arm64'
        env = os.environ.copy()
        if self.arch == 'arm64':
            arch_env = 'aarch64'
        else:
            arch_env = self.arch
        env['ARCH'] = arch_env
        logger.info(f'Setting ARCH environment variable to: {arch_env}')

        # Build command
        # If appimagetool is an AppImage, extract it and run the binary directly
        # This ensures ARCH environment variable is properly passed
        original_appimagetool_cmd = appimagetool_cmd
        wrapper_script_path = None  # Track wrapper script for cleanup

        # Check if appimagetool is an AppImage (even if found in PATH)
        # AppImages need to be extracted to properly pass ARCH environment variable
        is_appimage = False
        if isinstance(appimagetool_cmd, str):
            # Check architecture of appimagetool itself
            try:
                file_result = subprocess.run(
                    ['file', appimagetool_cmd],
                    capture_output=True,
                    text=True,
                )
                if file_result.returncode == 0:
                    logger.info(f'appimagetool file type: {file_result.stdout.strip()}')
            except Exception:
                pass

            if appimagetool_cmd.endswith('.AppImage'):
                is_appimage = True
            else:
                # Check if it's an AppImage by testing for AppImage support
                try:
                    test_result = subprocess.run(
                        [appimagetool_cmd, '--appimage-version'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if test_result.returncode == 0:
                        is_appimage = True
                        logger.info('Detected appimagetool as AppImage')
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                    # Not an AppImage or can't determine
                    pass

        if downloaded or is_appimage:
            # For AppImages, manually extract and run the binary directly
            # This avoids appimagetool scanning its own extraction directory
            import tempfile

            extract_dir = tempfile.mkdtemp(prefix='appimagetool_')
            logger.info(f'Extracting appimagetool to {extract_dir}...')
            try:
                # Extract the AppImage
                original_cwd = os.getcwd()
                os.chdir(extract_dir)
                try:
                    extract_cmd = [original_appimagetool_cmd, '--appimage-extract']
                    subprocess.run(
                        extract_cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    # Find the actual appimagetool binary (not AppRun)
                    squashfs_root = Path(extract_dir) / 'squashfs-root'
                    extracted_binary = None

                    # Try common locations for the appimagetool binary
                    possible_paths = [
                        squashfs_root / 'usr' / 'bin' / 'appimagetool',
                        squashfs_root / 'usr' / 'lib' / 'appimagetool',
                        squashfs_root / 'appimagetool',
                    ]

                    for path in possible_paths:
                        if path.exists() and path.is_file():
                            extracted_binary = path
                            logger.info(
                                f'Found appimagetool binary at: {extracted_binary}'
                            )
                            break

                    # Fallback to AppRun if binary not found
                    if extracted_binary is None:
                        extracted_binary = squashfs_root / 'AppRun'
                        if not extracted_binary.exists():
                            raise FileNotFoundError(
                                'Could not find extracted appimagetool binary or AppRun'
                            )
                        logger.info(f'Using AppRun script: {extracted_binary}')

                    extracted_binary.chmod(0o755)

                    # Check what libraries the extracted appimagetool binary depends on
                    # This might reveal if it's finding x86_64 libraries
                    logger.info('Checking libraries that appimagetool depends on...')
                    try:
                        ldd_result = subprocess.run(
                            ['ldd', str(extracted_binary)],
                            capture_output=True,
                            text=True,
                        )
                        if ldd_result.returncode == 0:
                            logger.info(
                                f'appimagetool library dependencies:\n{ldd_result.stdout}'
                            )
                            # Check if any dependencies point to x86_64 libraries
                            if (
                                'x86_64' in ldd_result.stdout
                                or 'x86-64' in ldd_result.stdout
                            ):
                                logger.warning(
                                    'appimagetool depends on x86_64 libraries - this might cause architecture detection issues'
                                )
                            # Check what architectures the libraries are
                            lib_archs = set()
                            for line in ldd_result.stdout.split('\n'):
                                if '=>' in line:
                                    # Extract library path
                                    lib_path = line.split('=>')[1].strip().split()[0]
                                    if lib_path and lib_path != 'not':
                                        try:
                                            lib_file_result = subprocess.run(
                                                ['file', lib_path],
                                                capture_output=True,
                                                text=True,
                                            )
                                            if lib_file_result.returncode == 0:
                                                lib_output = lib_file_result.stdout
                                                if (
                                                    'x86-64' in lib_output
                                                    or 'x86_64' in lib_output
                                                ):
                                                    lib_archs.add('x86_64')
                                                    logger.warning(
                                                        f'Found x86_64 library dependency: {lib_path}'
                                                    )
                                                elif (
                                                    'aarch64' in lib_output
                                                    or 'ARM aarch64' in lib_output
                                                ):
                                                    lib_archs.add('aarch64')
                                            logger.info(
                                                f'appimagetool library architectures: {lib_archs}'
                                            )
                                        except Exception:
                                            pass
                    except Exception as e:
                        logger.debug(f'Could not check library dependencies: {e}')

                    # Check if extracted appimagetool directory has mixed architectures
                    # This might be what appimagetool is detecting
                    logger.info(
                        'Checking extracted appimagetool directory for architectures...'
                    )
                    try:
                        extract_check_result = subprocess.run(
                            ['find', str(squashfs_root), '-type', 'f', '-executable'],
                            capture_output=True,
                            text=True,
                        )
                        if extract_check_result.returncode == 0:
                            extract_files = extract_check_result.stdout.strip().split(
                                '\n'
                            )
                            extract_x86 = 0
                            extract_arm = 0
                            for ef in extract_files:
                                if ef:
                                    ef_result = subprocess.run(
                                        ['file', ef],
                                        capture_output=True,
                                        text=True,
                                    )
                                    if ef_result.returncode == 0:
                                        ef_output = ef_result.stdout
                                        if (
                                            'x86-64' in ef_output
                                            or 'x86_64' in ef_output
                                        ):
                                            extract_x86 += 1
                                        elif (
                                            'aarch64' in ef_output
                                            or 'ARM aarch64' in ef_output
                                        ):
                                            extract_arm += 1
                            logger.info(
                                f'Extracted appimagetool: x86_64={extract_x86}, ARM64={extract_arm}'
                            )
                    except Exception as e:
                        logger.debug(
                            f'Could not check extracted appimagetool architectures: {e}'
                        )

                    # Use the extracted binary with ARCH explicitly set
                    # Use absolute paths and ensure we're in a clean directory
                    appdir_abs = str(self.appdir.resolve())
                    appimage_abs = str(self.appimage.resolve())
                    extracted_binary_abs = str(extracted_binary.resolve())

                    # Create a wrapper script to ensure ARCH is definitely set
                    # This is more reliable than bash -c for ensuring environment variables
                    import tempfile

                    wrapper_script = tempfile.NamedTemporaryFile(
                        mode='w', suffix='.sh', delete=False
                    )
                    wrapper_script.write(f"""#!/bin/bash
set -e
export ARCH={arch_env}
# Debug: verify ARCH is set
echo "Wrapper script: ARCH is set to: $ARCH"
# Verify ARCH is actually exported (important for appimagetool)
if [ -z "$ARCH" ]; then
    echo "ERROR: ARCH is not set!" >&2
    exit 1
fi
# Change to /tmp to avoid scanning any build directories
cd /tmp
# Ensure we're in a clean environment - unset any conflicting variables
unset BUILD_ARCH 2>/dev/null || true
# Restrict LD_LIBRARY_PATH to only aarch64 paths to prevent appimagetool
# from detecting x86_64 libraries (important for dynamically linked appimagetool on GitHub)
# This ensures appimagetool only finds ARM64 libraries
if [ "{arch_env}" = "aarch64" ]; then
    export LD_LIBRARY_PATH="/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu:/usr/local/lib/aarch64-linux-gnu"
else
    export LD_LIBRARY_PATH="/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/usr/local/lib/x86_64-linux-gnu"
fi
# Run appimagetool with absolute paths
# Use exec to ensure ARCH is definitely passed
exec env ARCH={arch_env} LD_LIBRARY_PATH="$LD_LIBRARY_PATH" {shlex.quote(extracted_binary_abs)} {shlex.quote(appdir_abs)} {shlex.quote(appimage_abs)}
""")
                    wrapper_script.close()
                    wrapper_path = Path(wrapper_script.name)
                    wrapper_path.chmod(0o755)
                    wrapper_script_path = wrapper_path  # Store for cleanup
                    cmd = ['bash', str(wrapper_path)]
                finally:
                    os.chdir(original_cwd)
            except Exception as e:
                logger.warning(f'Failed to extract appimagetool: {e}')
                # Fallback: use --appimage-extract-and-run
                appdir_str = shlex.quote(str(self.appdir))
                appimage_str = shlex.quote(str(self.appimage))
                appimagetool_str = shlex.quote(original_appimagetool_cmd)
                cmd = [
                    'bash',
                    '-c',
                    f'export ARCH={arch_env} && {appimagetool_str} --appimage-extract-and-run {appdir_str} {appimage_str}',
                ]
        else:
            # Regular binary - prepend env to ensure ARCH is set
            # This is important for AppImages that might not inherit env vars correctly
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
        finally:
            # Clean up wrapper script if it was created
            if wrapper_script_path and Path(wrapper_script_path).exists():
                try:
                    Path(wrapper_script_path).unlink()
                except Exception as e:
                    logger.debug(f'Could not clean up wrapper script: {e}')

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
