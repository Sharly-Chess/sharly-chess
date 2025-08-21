import argparse
import os
import shutil
import subprocess
import json
from pathlib import Path
import sys
from pkgutil import iter_modules
from types import ModuleType

import requests
from packaging.version import Version, InvalidVersion

from common.i18n import update_i18n_files
from utils.file import shutil_delete_onerror

sys.path.extend(
    map(
        str,
        [
            Path(__file__).parents[2],  # The root path
            Path(__file__).parents[2]
            / 'src',  # The path to the sources of the application
        ],
    )
)

from zipfile import ZipFile, ZIP_DEFLATED
from logging import Logger
from PyInstaller.__main__ import run

from common import BASE_DIR, enable_experimental_features, EVENTS_FOLDER, TMP_DIR

from common import SHARLY_CHESS_VERSION
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger
from database.sqlite.config import migrations as config_migrations
from database.sqlite.event import migrations as event_migrations
from common.installation_checker import (
    InstallationChecker,
)
from plugins.manager import plugin_manager
from plugins import PLUGINS_DIR

# Enable experimental features to force the installation of the experimental tools and libs before exporting
enable_experimental_features(True)

logger: Logger = get_logger()

BUILD_DIR: Path = BASE_DIR / 'build'
DIST_DIR: Path = BASE_DIR / 'dist'
DATA_DIR: Path = BASE_DIR / 'export-data'
LOCALE_DIR: Path = BASE_DIR / 'locale'
basename: str = f'sharly-chess-{SHARLY_CHESS_VERSION}'
EXPORT_DIR: Path = BASE_DIR / 'export'
PROJECT_DIR: Path = DIST_DIR / basename
ZIP_FILE: Path = EXPORT_DIR / f'{basename}.zip'
EXE_FILENAME: str = basename + '.exe'
INTERNAL_DIRNAME: str = '_internal'
SPEC_FILE: Path = BASE_DIR / f'{basename}.spec'
TEST_DIR: Path = BASE_DIR / 'export-test'
SOURCE_DIR: Path = BASE_DIR / 'src'
FFE_SQL_SERVER_CREDENTIALS_FILE: Path = PLUGINS_DIR / 'ffe' / '.credentials'
LICENCES_DIR = PROJECT_DIR / 'LICENSES'


def generate_license_files():
    """Generate third-party license files using pip-licenses."""
    logger.info('Generating third-party license files...')

    LICENCES_DIR.mkdir(parents=True, exist_ok=True)

    # Create subdirectory for individual package licenses
    packages_dir = LICENCES_DIR / 'packages'
    packages_dir.mkdir(parents=True, exist_ok=True)

    # 1. --- Generate third-party license files using pip-licenses ---

    # Verify pip-licenses is available
    try:
        subprocess.run(['pip-licenses', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error('pip-licenses not found. Install with: pip install pip-licenses')
        raise RuntimeError('pip-licenses is required for license generation')

    # Packages to ignore - these are typically development/packaging tools, not runtime dependencies
    # You can modify this list based on your specific needs
    ignored_packages = [
        'pip-licenses',
        'prettytable',
        'tomli',
        'wcwidth',
        'setuptools',
        'pip',
        'wheel',
        # The project itself (installed in development mode)
        'sharly-chess',
    ]

    try:
        # First get package information as JSON to create individual files
        logger.info('Getting package information for individual license files...')
        result = subprocess.run(
            [
                'pip-licenses',
                '--format=json',
                '--with-license-file',
                '--ignore-packages',
            ]
            + ignored_packages,
            capture_output=True,
            text=True,
            check=True,
        )

        packages_data = json.loads(result.stdout)
        individual_files_created = []

        # Create individual license files for each package
        for package in packages_data:
            package_name = package['Name']
            package_version = package['Version']
            license_name = package['License']

            # Create a safe filename
            safe_package_name = package_name.replace('/', '_').replace(' ', '_')
            package_file = packages_dir / f'{safe_package_name}-{package_version}.txt'

            with open(package_file, 'w', encoding='utf-8') as f:
                f.write(f'Package: {package_name}\n')
                f.write(f'Version: {package_version}\n')
                f.write(f'License: {license_name}\n')
                f.write('=' * 50 + '\n\n')

                # Add license file content if available
                if 'LicenseFile' in package and package['LicenseFile']:
                    license_file_path = package['LicenseFile'].strip()

                    try:
                        license_path = Path(license_file_path)
                        if license_path.exists() and license_path.is_file():
                            with open(
                                license_path, 'r', encoding='utf-8', errors='replace'
                            ) as license_file:
                                license_content = license_file.read()
                            f.write('LICENSE FILE CONTENT:\n')
                            f.write('-' * 25 + '\n')
                            f.write(license_content)
                            f.write('\n')
                        else:
                            f.write(
                                f'License file path provided but file not found: {license_file_path}\n'
                            )
                            f.write(
                                "Please refer to the package's PyPI page or repository for license details.\n"
                            )
                    except Exception as e:
                        logger.warning(
                            f'Failed to read license file for {package_name}: {e}'
                        )
                        f.write(f'License file path: {license_file_path}\n')
                        f.write(f'Could not read license file content: {e}\n')
                        f.write(
                            "Please refer to the package's PyPI page or repository for license details.\n"
                        )
                else:
                    f.write(f'No license file content available for {package_name}.\n')
                    f.write(
                        "Please refer to the package's PyPI page or repository for license details.\n"
                    )

            individual_files_created.append(package_file.name)

        logger.info(
            f'Created {len(individual_files_created)} individual package license files using pip-licenses'
        )

    except subprocess.CalledProcessError as e:
        logger.error(f'Failed to generate license files: {e}')
        logger.error(f'stdout: {e.stdout}')
        logger.error(f'stderr: {e.stderr}')
        raise
    except Exception as e:
        logger.error(f'Unexpected error generating license files: {e}')
        raise

    # 2. --- Generate third-party license from ToolInstallers ---

    licence_info = []
    external_files_created = []

    # Helper function to process installers uniformly
    def process_installer(installer, install_dir, installer_type):
        # Check if installer has licence files OR licence type
        has_licence_files = installer.licence_files and install_dir.exists()
        has_licence_type = installer.licence_type is not None

        if has_licence_files or has_licence_type:
            logger.debug(
                f'Scanning {installer_type.lower()}: {installer.name} in {install_dir}'
            )

            # Create one combined file for this tool/library
            safe_tool_name = (
                installer.name.replace('/', '_').replace(' ', '_').replace('-', '_')
            )
            individual_file = packages_dir / f'{safe_tool_name}-{installer.version}.txt'

            try:
                with open(individual_file, 'w', encoding='utf-8') as f:
                    f.write(f'Tool/Library: {installer.name}\n')
                    f.write(f'Version: {installer.version}\n')

                    # List sources
                    sources = []
                    if has_licence_files:
                        sources.append(
                            f'Source Licence Files: {", ".join(installer.licence_files)}'
                        )
                    if has_licence_type:
                        sources.append(f'Licence Type: {installer.licence_type}')

                    if sources:
                        for source in sources:
                            f.write(f'{source}\n')

                    f.write('=' * 50 + '\n\n')

                    # First, process any licence files if they exist
                    if has_licence_files:
                        for i, licence_file_path in enumerate(installer.licence_files):
                            licence_file = install_dir / licence_file_path

                            if licence_file.exists() and licence_file.is_file():
                                if len(installer.licence_files) > 1:
                                    f.write(
                                        f'LICENCE FILE {i + 1}: {licence_file_path}\n'
                                    )
                                    f.write('-' * 40 + '\n')
                                else:
                                    f.write('LICENCE CONTENT:\n')
                                    f.write('-' * 20 + '\n')

                                try:
                                    with open(
                                        licence_file,
                                        'r',
                                        encoding='utf-8',
                                        errors='replace',
                                    ) as licence_content_file:
                                        licence_content = licence_content_file.read()
                                    f.write(licence_content)
                                    if not licence_content.endswith('\n'):
                                        f.write('\n')
                                    f.write('\n')  # Extra blank line between files
                                except Exception as e:
                                    logger.warning(
                                        f'Failed to read licence content from {licence_file}: {e}'
                                    )
                                    f.write(
                                        f'Could not read licence file content: {e}\n'
                                    )
                                    f.write(
                                        f'Licence file location: {licence_file}\n\n'
                                    )

                                licence_info.append(
                                    {
                                        'tool_name': installer.name,
                                        'tool_version': str(installer.version),
                                        'licence_file': licence_file,
                                        'individual_file': individual_file
                                        if individual_file.exists()
                                        else None,
                                    }
                                )
                            else:
                                logger.warning(
                                    f'Expected licence file not found: {licence_file} for {installer.name}'
                                )

                    # Then, if there's a licence_type, add the template content
                    if has_licence_type:
                        if has_licence_files:
                            f.write('-' * 40 + '\n')
                            f.write(f'STANDARD {installer.licence_type} LICENCE:\n')
                            f.write('-' * 40 + '\n')
                        else:
                            f.write('LICENCE CONTENT:\n')
                            f.write('-' * 20 + '\n')

                        # Path to licence templates
                        templates_dir = (
                            BASE_DIR / 'src' / 'common' / 'licence_templates'
                        )
                        template_file = templates_dir / f'{installer.licence_type}.txt'

                        try:
                            if template_file.exists():
                                with open(
                                    template_file, 'r', encoding='utf-8'
                                ) as template_content_file:
                                    template_content = template_content_file.read()
                                f.write(template_content)
                                if not template_content.endswith('\n'):
                                    f.write('\n')
                            else:
                                f.write(
                                    f'Licence template not found for type: {installer.licence_type}\n'
                                )
                                f.write(
                                    f'Please add a template file at: {template_file}\n'
                                )
                                f.write(
                                    "Or refer to the project's repository for licence details.\n"
                                )
                        except Exception as e:
                            logger.warning(
                                f'Failed to read licence template {template_file}: {e}'
                            )
                            f.write(f'Could not read licence template: {e}\n')
                            f.write(f'Template file location: {template_file}\n')

                        licence_info.append(
                            {
                                'tool_name': installer.name,
                                'tool_version': str(installer.version),
                                'licence_file': template_file
                                if template_file.exists()
                                else None,
                                'licence_type': installer.licence_type,
                                'individual_file': individual_file
                                if individual_file.exists()
                                else None,
                            }
                        )

                external_files_created.append(individual_file.name)
                logger.debug(f'Created combined licence file: {individual_file.name}')

            except Exception as e:
                logger.warning(
                    f'Failed to create licence file for {installer.name}: {e}'
                )

    # Process WebLibArchiveInstaller instances
    for installer in InstallationChecker.web_lib_installers:
        process_installer(
            installer, installer.version_install_dir, 'WebLibArchiveInstaller'
        )

    # Process ExecutableInstaller instances
    for installer in InstallationChecker.executable_installers:
        process_installer(installer, installer.install_dir, 'ExecutableInstaller')

    logger.info(
        f'Collected {len(licence_info)} licence files from external tools and libraries'
    )
    logger.info(
        f'Created {len(external_files_created)} individual external tool licence files'
    )

    # 3. --- Generate extra licence information notices ---

    notice_file = LICENCES_DIR / 'NOTICE.txt'
    logger.info(f'Creating notice file: {notice_file}')

    with open(notice_file, 'w', encoding='utf-8') as f:
        f.write(f"""SHARLY CHESS {SHARLY_CHESS_VERSION}
{SharlyChessConfig.en_copyright}
{SharlyChessConfig.url}

This software includes third-party libraries and components.
See THIRD_PARTY_LICENSES.txt for detailed license information.

For a summary of all licenses used, see LICENSE_SUMMARY.md.
Individual package licenses are available in the packages/ subdirectory.

""")

        # Add info about major license types that require attribution
        f.write("""IMPORTANT LICENSE NOTICES:

1. GNU LGPL Components:
   Some components are licensed under GNU Lesser General Public License (LGPL).
   Source code for these components is available from their respective PyPI packages.

2. Apache License Components:
   Some components are licensed under Apache License 2.0.
   See THIRD_PARTY_LICENSES.txt for required copyright notices.

3. BSD License Components:
   Some components are licensed under various BSD licenses.
   See THIRD_PARTY_LICENSES.txt for required copyright notices.

4. Mozilla Public License Components:
   Some components are licensed under Mozilla Public License 2.0.
   See THIRD_PARTY_LICENSES.txt for complete license terms.

For complete license terms and copyright notices, please refer to
THIRD_PARTY_LICENSES.txt or the individual package files in packages/.
""")

    logger.info('Licence files generated successfully')


def clean(clean_zip: bool):
    for d in [
        BUILD_DIR,
        DIST_DIR,
        PROJECT_DIR,
    ]:
        if Path(d).is_dir():
            logger.info('Deleting folder [%s]...', d)
            shutil.rmtree(d, onerror=shutil_delete_onerror)
    if SPEC_FILE.is_file():
        logger.info('Deleting file [%s]...', SPEC_FILE)
        SPEC_FILE.unlink()
    if clean_zip:
        if ZIP_FILE.is_file():
            logger.info('Deleting file [%s]...', ZIP_FILE)
            ZIP_FILE.unlink()


def build_exe():
    pyinstaller_params = [
        '--clean',
        '--noconfirm',
        '--name=' + basename,
        '--copy-metadata',
        'sharly_chess',
        '--hiddenimport=common',
        '--hiddenimport=data',
        '--hiddenimport=database',
        '--hiddenimport=pairing',
        '--hiddenimport=plugins',
        '--hiddenimport=web',
        '--hiddenimport=babel.numbers',
        '--hiddenimport=pyexcel_io.writers',
        '--hiddenimport=colorlog',
        '--paths=.',
        '--icon=src/web/static/images/sharly-chess.ico',
        '--optimize',
        '1',
        # TODO Remove this option when https://github.com/pyinstaller/pyinstaller/issues/9149 is fixed
        # this option was add in 2.7.2 as a workaround of a bug in PyInstaller
        # See https://github.com/pyinstaller/pyinstaller/issues/9149#issuecomment-2914294505
        '--exclude-module=pkg_resources',
        'src/sharly_chess.py',
    ]
    migration_base_modules: list[ModuleType] = [config_migrations, event_migrations] + [
        plugin.base_migration_module
        for plugin in plugin_manager.all_plugins
        if plugin.base_migration_module
    ]
    for base_module in migration_base_modules:
        for _, module, _ in iter_modules(base_module.__path__):
            pyinstaller_params.append(f'--hiddenimport={base_module.__name__}.{module}')

    files: list[Path] = []
    web_dir = SOURCE_DIR / 'web'
    files += [file for file in (web_dir / 'templates').glob('**/*') if file.is_file()]
    for templates_path in plugin_manager.templates_paths:
        files += [file for file in templates_path.glob('**/*') if file.is_file()]
    static_dir = web_dir / 'static'
    for static_path in plugin_manager.static_paths:
        files += [file for file in static_path.glob('**/*') if file.is_file()]
    files += [file for file in Path(static_dir, 'fonts').glob('**/*') if file.is_file()]
    files += [
        file for file in Path(static_dir, 'images').glob('**/*') if file.is_file()
    ]
    files += [file for file in Path(static_dir, 'css').glob('**/*') if file.is_file()]
    files += [file for file in Path(static_dir, 'js').glob('**/*') if file.is_file()]
    for installer in InstallationChecker.web_lib_installers:
        files += [
            installer.version_install_dir / lib_file for lib_file in installer.lib_files
        ]
    lib_dir = static_dir / 'lib'
    files += [
        lib_dir / 'htmx' / 'sortable.js',
        lib_dir / 'htmx' / 'morphdom-swap.js',
        lib_dir / 'polyglot' / 'polyglot.js',
        lib_dir / 'select2' / 'themes' / 'dark-bootstrap-5.css',
    ]
    sql_dir: Path = SOURCE_DIR / 'database' / 'sql'
    files += [
        sql_dir / 'create_fide.sql',
        PLUGINS_DIR / 'ffe' / 'create_ffe.sql',
    ]
    yml_dir: Path = SOURCE_DIR / 'database' / 'yml'
    files += list(yml_dir.glob('*.yml'))
    custom_dir: Path = SOURCE_DIR / 'custom'
    files += [file for file in custom_dir.glob('**/*') if file.is_file()]
    files += [file for file in LOCALE_DIR.glob('**/*.mo') if file.is_file()]

    # Add entire executable installer directories
    for executable_installer in InstallationChecker.executable_installers:
        installer_dir = executable_installer.executable_dir
        if installer_dir.exists():
            # Add all files in the installer directory recursively
            files += [file for file in installer_dir.glob('**/*') if file.is_file()]

    files += [
        FFE_SQL_SERVER_CREDENTIALS_FILE,
    ]

    # Use correct path separator for PyInstaller --add-data based on OS
    data_separator = ':' if os.name != 'nt' else ';'

    # Process project files (files within BASE_DIR)
    for file in files:
        try:
            relative_path = file.parent.relative_to(BASE_DIR)
            pyinstaller_params.append(
                f'--add-data={file}{data_separator}{relative_path}'
            )
        except ValueError:
            # File is outside BASE_DIR, add to root
            pyinstaller_params.append(f'--add-data={file}{data_separator}.')
            logger.info(f'Adding external file to root: {file}')
    iso4217parse_dir: Path = TMP_DIR / 'iso4217parse'
    iso4217parse_dir.mkdir(parents=True, exist_ok=True)
    iso4217parse_version = '0.6.2'
    iso4217parse_url: str = f'https://raw.githubusercontent.com/tammoippen/iso4217parse/refs/tags/v{iso4217parse_version}/iso4217parse'
    for filename in [
        'data.json',
        'symbols.json',
    ]:
        url: str = f'{iso4217parse_url}/{filename}'
        logger.info(f'Downloading {url}...')
        response = requests.get(url, stream=True, timeout=3)
        response.raise_for_status()
        file: Path = iso4217parse_dir / filename
        with open(file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info('Done.')
        pyinstaller_params.append(
            f'--add-data={file}{data_separator}{file.parent.relative_to(TMP_DIR)}'
        )

    # Add macOS-specific options when building on macOS
    if os.name != 'nt':  # macOS/Linux
        pyinstaller_params.append('--osx-bundle-identifier=com.sharly-chess.app')

    run(pyinstaller_params)


def create_project():
    logger.info('Adding data from folder [%s] to [%s]...', PROJECT_DIR, DATA_DIR)
    shutil.copytree(DATA_DIR, PROJECT_DIR, dirs_exist_ok=True)
    tools_dir: Path = PROJECT_DIR / 'tools'
    tools_dir.mkdir(parents=True, exist_ok=True)

    # create an empty events dir
    events_dir: Path = PROJECT_DIR / EVENTS_FOLDER
    events_dir.mkdir(exist_ok=True)
    # just create an empty custom dir (dev custom files are embedded in the exe since 2.4.11)
    custom_dir: Path = PROJECT_DIR / 'custom'
    custom_dir.mkdir(exist_ok=True)

    # Create a double-clickable launcher for macOS/Linux
    if os.name != 'nt':  # macOS/Linux
        launcher_path = PROJECT_DIR / 'Launch Sharly Chess.app'
        logger.info('Creating AppleScript launcher at [%s]...', launcher_path)

        # AppleScript to launch the main executable in a new Terminal window (in Dark Mode)
        applescript = f"""
            on run
                -- The path to this launcher is /path/to/dist_folder/Launch Sharly Chess.app
                -- We need the path to the folder that contains it.
                set app_path to path to me
                tell application "Finder"
                    set container_path to (container of app_path) as alias
                end tell
                set script_path to POSIX path of container_path

                tell application "Terminal"
                    activate
                    -- Create the new tab and execute the command
                    set new_tab to do script "cd " & quoted form of script_path & " && ./sharly-chess-{SHARLY_CHESS_VERSION}"

                    -- Try to set the theme to dark mode
                    try
                        set current settings of new_tab to settings set "Pro"
                    on error
                        -- If "Pro" theme isn't found, we just continue with the default
                    end try
                end tell
            end run
        """

        # Use osacompile to create the .app bundle
        cmd = [
            'osacompile',
            '-o',
            str(launcher_path),
            '-e',
            applescript,
        ]

        # Run the command
        import subprocess

        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            logger.error('Failed to create AppleScript launcher:')
            logger.error(process.stderr)
        else:
            logger.info('AppleScript launcher created successfully.')
    target_file = tools_dir / 'chessevent.bat'
    logger.info('Creating batch file [%s]]...', target_file)
    with open(target_file, 'wt', encoding='utf-8') as f:
        f.write(
            f'@echo off\n'
            f'echo Starting Sharly Chess ChessEvent client, please wait...\n'
            f'@rem Sharly Chess {SHARLY_CHESS_VERSION} - {SharlyChessConfig.en_copyright} - {SharlyChessConfig.url}\n'
            f'cd ..\n'
            f'{EXE_FILENAME} --chessevent\n'
            f'pause\n'
        )


def create_zip_files():
    logger.info('Creating archive [%s]...', ZIP_FILE)
    ZIP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(ZIP_FILE, 'w', ZIP_DEFLATED) as zip_file:
        os.chdir(PROJECT_DIR)
        for folder_name, sub_folders, file_names in os.walk('.'):
            zip_file.write(folder_name, folder_name)
        for folder_name, sub_folders, file_names in os.walk('.'):
            for filename in file_names:
                file_path: Path = Path(folder_name, filename)
                zip_file.write(file_path, file_path)
        os.chdir(BASE_DIR)


def build_test():
    if not TEST_DIR.is_dir():
        logger.info('Creating test environment in [%s]...', TEST_DIR)
        TEST_DIR.mkdir(parents=True)
    else:
        logger.info('Updating test environment in [%s]...', TEST_DIR)
        shutil.rmtree(
            TEST_DIR / '_internal', onerror=shutil_delete_onerror, ignore_errors=True
        )
    with ZipFile(ZIP_FILE, 'r') as zip_file:
        zip_file.extractall(TEST_DIR)


def main():
    # option --github is used when generating the EXE file from a GITHUB action
    # to verify that the name of the tag matches the Sharly Chess version.
    # option --preserve-build is used to skip cleanup for signing purposes
    parser = argparse.ArgumentParser()
    parser.add_argument('--github', type=str)
    parser.add_argument(
        '--preserve-build',
        action='store_true',
        help='Skip cleanup to preserve build artifacts for signing',
    )
    args = parser.parse_args()
    if args.github:
        if SHARLY_CHESS_VERSION != Version(args.github):
            raise InvalidVersion(
                f'Version [{args.github}] does not match (expected [{SHARLY_CHESS_VERSION}]).'
            )
        else:
            logger.info('Version [%s] is valid.', args.github)
    else:
        logger.info('The version is not verified (not running on GitHub).')
    if not InstallationChecker.check():
        return
    clean(clean_zip=True)
    update_i18n_files()
    build_exe()
    create_project()
    generate_license_files()
    create_zip_files()
    build_test()

    # Skip cleanup if we need to preserve build artifacts for signing
    if not args.preserve_build:
        clean(clean_zip=False)
    else:
        logger.info(
            'Preserving build artifacts for signing (--preserve-build was specified)'
        )


if __name__ == '__main__':
    main()
