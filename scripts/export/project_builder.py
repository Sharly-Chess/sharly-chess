import json
import os
import shutil
import subprocess
from abc import ABC
from argparse import ArgumentParser, Namespace
from logging import Logger
from pathlib import Path
from pkgutil import iter_modules
from types import ModuleType
from zipfile import ZipFile, ZIP_DEFLATED

from PyInstaller.__main__ import run
from packaging.version import Version, InvalidVersion

import plugins.chess_results
import plugins.ffe
import plugins.fra_schools
from common import BASE_DIR
from common import SHARLY_CHESS_VERSION
from common.installation_checker import (
    InstallationChecker,
)
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from database.sqlite.config import migrations as config_migrations
from database.sqlite.event import migrations as event_migrations
from plugins.manager import plugin_manager
from utils.file import shutil_delete_onerror

logger: Logger = get_logger()


class ProjectBuilder(ABC):
    """OS-agnostic class to export the project."""

    def __init__(
        self,
        clean_project_on_exit: bool,
    ):
        """Initializes the builder."""
        self.build_dir: Path = BASE_DIR / 'build'
        self.data_dir: Path = BASE_DIR / 'export-data'
        self.locale_dir: Path = BASE_DIR / 'locale'
        self.project_name: str = 'sharly-chess'
        self.basename: str = f'{self.project_name}-{SHARLY_CHESS_VERSION}'
        self.export_dir: Path = BASE_DIR / 'export'
        self.project_dir: Path = BASE_DIR / 'dist' / self.basename
        self.spec_file: Path = BASE_DIR / f'{self.basename}.spec'
        self.src_dir: Path = BASE_DIR / 'src'
        self.licences_dir = self.project_dir / 'LICENSES'
        self.control_file: Path = Path('tmp', 'control_file.json')
        self.zip_file: Path = self.export_dir / f'{self.basename}.zip'
        self.test_dir: Path = BASE_DIR / 'export-test' / self.basename
        self.clean_project_on_exit: bool = clean_project_on_exit
        parser = ArgumentParser(description='Export Sharly Chess.')
        # option --github is used when generating the EXE file from a GITHUB action
        # to verify that the name of the tag matches the Sharly Chess version.
        parser.add_argument('--github', type=str)
        self.hook_add_params(parser)
        args: Namespace = parser.parse_args()
        if args.github:
            if SHARLY_CHESS_VERSION != Version(args.github):
                raise InvalidVersion(
                    f'Version [{args.github}] does not match (expected [{SHARLY_CHESS_VERSION}]).'
                )
            else:
                logger.info('Version [%s] is valid.', args.github)
        else:
            logger.info('The version is not verified (not running on GitHub).')
        self.runs_on_github: bool = bool(args.github)
        self.hook_check_params(args)

    def run(self) -> bool:
        self.clean_on_startup()
        if not self.build_project():
            return False
        if not self.build_zip_file():
            return False
        if not self.build_test():
            return False
        self.clean_on_exit()
        return True

    def hook_extend_sys_path(
        self,
    ):
        """Let the builder extend to path (needed by external commands)."""

    def hook_add_params(
        self,
        parser: ArgumentParser,
    ):
        """Let the builder add params (for example to pass secrets on the command line)."""

    def hook_check_params(
        self,
        args: Namespace,
    ):
        """Let the builder control the params passed to the program."""

    @staticmethod
    def _delete_folder(
        folder: Path,
    ):
        if folder.is_dir():
            logger.info('Deleting folder [%s]...', folder)
            shutil.rmtree(folder, onerror=shutil_delete_onerror)

    @staticmethod
    def _delete_file(
        file: Path,
    ):
        if file.is_file():
            logger.info('Deleting file [%s]...', file)
            file.unlink()

    def clean_on_startup(self):
        self._delete_folder(self.build_dir)
        self._delete_file(self.spec_file)
        self._delete_folder(self.project_dir)
        self._delete_file(self.zip_file)
        self.hook_post_clean_on_startup()

    def hook_post_clean_on_startup(self):
        """Runs at the end of `clean_on_startup`"""

    @property
    def hook_get_venv_lib_path(
        self,
    ) -> Path:
        """Returns the path to the libraries of the virtual environment."""
        raise NotImplementedError(f'Class {self.__class__} not implemented yet.')

    def clean_on_exit(self):
        self._delete_folder(self.build_dir)
        self._delete_file(self.spec_file)
        if self.clean_project_on_exit:
            self._delete_folder(self.project_dir)

    def build_project(self) -> bool:
        logger.info('Creating project folder [%s]...', self.project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        # Important: build the EXE prior to copy any other data
        # to the project folder or PyInstaller fails on Windows with the error:
        # PermissionError: [WinError 5] Access refused
        if not self._build_exe():
            return False
        logger.info(
            'Adding data from folder [%s] to [%s]...', self.project_dir, self.data_dir
        )
        shutil.copytree(self.data_dir, self.project_dir, dirs_exist_ok=True)
        if not self._generate_license_files():
            return False
        if not self.build_control_file():
            return False
        if not self.hook_post_build_project():
            return False
        return True

    def _generate_license_files(self) -> bool:
        """Generate third-party license files using pip-licenses.
        Return True on success and False otherwise."""
        logger.info('Generating third-party license files...')

        self.licences_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectory for individual package licenses
        packages_dir = self.licences_dir / 'packages'
        packages_dir.mkdir(parents=True, exist_ok=True)

        # 1. --- Generate third-party license files using pip-licenses ---

        # Verify pip-licenses is available
        try:
            subprocess.run(
                ['pip-licenses', '--version'], capture_output=True, check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error(
                "pip-licenses not found. Install with: 'pip install pip-licenses' or 'pip install -e .[export]'."
            )
            return False

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
            self.project_name,
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
                package_file = (
                    packages_dir / f'{safe_package_name}-{package_version}.txt'
                )

                with open(package_file, 'w', encoding='utf-8') as f:
                    f.write(f'Package: {package_name}\n')
                    f.write(f'Version: {package_version}\n')
                    f.write(f'License: {license_name}\n')
                    f.write('=' * 50 + '\n\n')

                    package_error: bool = False
                    # Add license file content if available
                    if 'LicenseFile' in package and package['LicenseFile']:
                        license_file_path = package['LicenseFile'].strip()

                        try:
                            license_path = Path(license_file_path)
                            if license_path.exists() and license_path.is_file():
                                with open(
                                    license_path,
                                    'r',
                                    encoding='utf-8',
                                    errors='replace',
                                ) as license_file:
                                    license_content = license_file.read()
                                f.write('LICENSE FILE CONTENT:\n')
                                f.write('-' * 25 + '\n')
                                f.write(license_content)
                                f.write('\n')
                            else:
                                f.write(
                                    f'License file path provided but file not found: [{license_file_path}].\n'
                                )
                                package_error = True
                        except Exception as e:
                            logger.warning(
                                'Failed to read license file [%s] for package [%s]: %s',
                                license_file_path,
                                package_name,
                                str(e),
                            )
                            f.write(f'License file path: {license_file_path}\n')
                            f.write(f'Could not read license file content: {e}\n')
                            package_error = True
                    else:
                        f.write(
                            f'No license file content available for {package_name}.\n'
                        )
                        package_error = True
                    if package_error:
                        f.write(
                            "Please refer to the package's PyPI page or repository for license details.\n"
                        )

                individual_files_created.append(package_file.name)

            logger.info(
                'Created %d individual package license files using pip-licenses',
                len(individual_files_created),
            )

        except subprocess.CalledProcessError as e:
            logger.error('Failed to generate license files: %s', str(e))
            logger.error('stdout: %s', e.stdout)
            logger.error('stderr: %s', e.stderr)
            return False
        except Exception as e:
            logger.error('Unexpected error generating license files: %s', str(e))
            return False

        # 2. --- Generate third-party license from ToolInstallers ---

        licence_info = []
        external_files_created = []

        # Helper function to process installers uniformly
        def process_installer(installer_, install_dir, installer_type):
            # Check if installer has licence files OR licence type
            has_licence_files = installer_.licence_files and install_dir.exists()
            has_licence_type = installer_.licence_type is not None

            if has_licence_files or has_licence_type:
                logger.debug(
                    f'Scanning {installer_type.lower()}: {installer_.name} in {install_dir}'
                )

                # Create one combined file for this tool/library
                safe_tool_name = (
                    installer_.name.replace('/', '_')
                    .replace(' ', '_')
                    .replace('-', '_')
                )
                individual_file = (
                    packages_dir / f'{safe_tool_name}-{installer_.version}.txt'
                )

                try:
                    with open(individual_file, 'w', encoding='utf-8') as f_:
                        f_.write(f'Tool/Library: {installer_.name}\n')
                        f_.write(f'Version: {installer_.version}\n')

                        # List sources
                        sources = []
                        if has_licence_files:
                            sources.append(
                                f'Source Licence Files: {", ".join(installer_.licence_files)}'
                            )
                        if has_licence_type:
                            sources.append(f'Licence Type: {installer_.licence_type}')

                        if sources:
                            for source in sources:
                                f_.write(f'{source}\n')

                        f_.write('=' * 50 + '\n\n')

                        # First, process any licence files if they exist
                        if has_licence_files:
                            for i, licence_file_path in enumerate(
                                installer_.licence_files
                            ):
                                licence_file = install_dir / licence_file_path

                                if licence_file.exists() and licence_file.is_file():
                                    if len(installer_.licence_files) > 1:
                                        f_.write(
                                            f'LICENCE FILE {i + 1}: {licence_file_path}\n'
                                        )
                                        f_.write('-' * 40 + '\n')
                                    else:
                                        f_.write('LICENCE CONTENT:\n')
                                        f_.write('-' * 20 + '\n')

                                    try:
                                        with open(
                                            licence_file,
                                            'r',
                                            encoding='utf-8',
                                            errors='replace',
                                        ) as licence_content_file:
                                            licence_content = (
                                                licence_content_file.read()
                                            )
                                        f_.write(licence_content)
                                        if not licence_content.endswith('\n'):
                                            f_.write('\n')
                                        f_.write('\n')  # Extra blank line between files
                                    except Exception as e:
                                        logger.warning(
                                            'Failed to read licence content from [%s]: %s',
                                            licence_file,
                                            str(e),
                                        )
                                        f_.write(
                                            f'Could not read licence file content: {e}\n'
                                        )
                                        f_.write(
                                            f'Licence file location: {licence_file}\n\n'
                                        )

                                    licence_info.append(
                                        {
                                            'tool_name': installer_.name,
                                            'tool_version': str(installer_.version),
                                            'licence_file': licence_file,
                                            'individual_file': individual_file
                                            if individual_file.exists()
                                            else None,
                                        }
                                    )
                                else:
                                    logger.warning(
                                        'Expected licence file not found: [%s] for [%s]',
                                        licence_file,
                                        installer_.name,
                                    )

                        # Then, if there's a licence_type, add the template content
                        if has_licence_type:
                            if has_licence_files:
                                f_.write('-' * 40 + '\n')
                                f_.write(
                                    f'STANDARD {installer_.licence_type} LICENCE:\n'
                                )
                                f_.write('-' * 40 + '\n')
                            else:
                                f_.write('LICENCE CONTENT:\n')
                                f_.write('-' * 20 + '\n')

                            # Path to licence templates
                            templates_dir = (
                                BASE_DIR / 'src' / 'common' / 'licence_templates'
                            )
                            template_file = (
                                templates_dir / f'{installer_.licence_type}.txt'
                            )

                            try:
                                if template_file.exists():
                                    with open(
                                        template_file, 'r', encoding='utf-8'
                                    ) as template_content_file:
                                        template_content = template_content_file.read()
                                    f_.write(template_content)
                                    if not template_content.endswith('\n'):
                                        f_.write('\n')
                                else:
                                    f_.write(
                                        f'Licence template not found for type: {installer_.licence_type}\n'
                                    )
                                    f_.write(
                                        f'Please add a template file at: {template_file}\n'
                                    )
                                    f_.write(
                                        "Or refer to the project's repository for licence details.\n"
                                    )
                            except Exception as e:
                                logger.warning(
                                    'Failed to read licence template [%s]: %s',
                                    template_file,
                                    str(e),
                                )
                                f_.write(f'Could not read licence template: {e}\n')
                                f_.write(f'Template file location: {template_file}\n')

                            licence_info.append(
                                {
                                    'tool_name': installer_.name,
                                    'tool_version': str(installer_.version),
                                    'licence_file': template_file
                                    if template_file.exists()
                                    else None,
                                    'licence_type': installer_.licence_type,
                                    'individual_file': individual_file
                                    if individual_file.exists()
                                    else None,
                                }
                            )

                    external_files_created.append(individual_file.name)
                    logger.debug(
                        'Created combined licence file: %s', individual_file.name
                    )

                except Exception as e:
                    logger.warning(
                        'Failed to create licence file for [%s]: %s',
                        installer_.name,
                        str(e),
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
            'Collected %d licence files from external tools and libraries.',
            len(licence_info),
        )
        logger.info(
            'Created %d individual external tool licence files.',
            len(external_files_created),
        )

        # 3. --- Generate extra licence information notices ---

        notice_file = self.licences_dir / 'NOTICE.txt'
        logger.info('Creating notice file [%s]...', notice_file)

        with open(notice_file, 'w', encoding='utf-8') as f:
            f.write(f"""SHARLY CHESS {SHARLY_CHESS_VERSION}
    {SharlyChessConfig.en_copyright}
    {SharlyChessConfig.web_url}

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

        logger.info('Licence files generated successfully.')
        return True

    def _build_exe(self) -> bool:
        pyinstaller_params = [
            '--clean',
            '--noconfirm',
            '--name=' + self.basename,
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
            '--hiddenimport=toga',
            '--paths=.',
            '--optimize',
            '1',
            'src/sharly_chess.py',
        ]
        migration_base_modules: list[ModuleType] = [
            config_migrations,
            event_migrations,
        ] + [
            plugin.base_migration_module
            for plugin in plugin_manager.all_plugins
            if plugin.base_migration_module
        ]
        for base_module in migration_base_modules:
            for _, module, _ in iter_modules(base_module.__path__):
                pyinstaller_params.append(
                    f'--hiddenimport={base_module.__name__}.{module}'
                )

        files: list[Path] = []
        web_dir = self.src_dir / 'web'
        files += [
            file for file in (web_dir / 'templates').glob('**/*') if file.is_file()
        ]
        for templates_path in plugin_manager.templates_paths:
            files += [file for file in templates_path.glob('**/*') if file.is_file()]
        for locale_path in plugin_manager.locale_paths:
            files += [file for file in locale_path.glob('**/*.mo') if file.is_file()]
        for static_path in plugin_manager.static_paths:
            files += [file for file in static_path.glob('**/*') if file.is_file()]
        static_dir = web_dir / 'static'
        files += [
            file for file in Path(static_dir, 'fonts').glob('**/*') if file.is_file()
        ]
        files += [
            file for file in Path(static_dir, 'images').glob('**/*') if file.is_file()
        ]
        files += [
            file for file in Path(static_dir, 'css').glob('**/*') if file.is_file()
        ]
        files += [
            file for file in Path(static_dir, 'js').glob('**/*') if file.is_file()
        ]
        for installer in InstallationChecker.web_lib_installers:
            files += [
                installer.version_install_dir / lib_file
                for lib_file in installer.lib_files
            ]
        lib_dir = static_dir / 'lib'
        files += [
            lib_dir / 'htmx' / 'sortable.js',
            lib_dir / 'htmx' / 'morphdom-swap.js',
            lib_dir / 'polyglot' / 'polyglot.js',
            lib_dir / 'select2' / 'themes' / 'dark-bootstrap-5.css',
        ]
        custom_dir: Path = self.src_dir / 'custom'
        files += [file for file in custom_dir.glob('**/*') if file.is_file()]
        files += [file for file in self.locale_dir.glob('**/*.mo') if file.is_file()]

        # Add entire executable installer directories
        for executable_installer in InstallationChecker.executable_installers:
            installer_dir = executable_installer.executable_dir
            if installer_dir.exists():
                # Add all files in the installer directory recursively
                files += [file for file in installer_dir.glob('**/*') if file.is_file()]

        files += [
            self.src_dir / '.fide-database-enc-credentials',
            plugins.chess_results.PLUGIN_DIR / '.credentials',
            plugins.ffe.PLUGIN_DIR / '.sql-server-credentials',
            plugins.ffe.PLUGIN_DIR / '.database-enc-credentials',
            plugins.fra_schools.PLUGIN_DIR / '.database-enc-credentials',
        ]

        # Add GUI resources
        gui_dir: Path = self.src_dir / 'gui'
        files += [file for file in gui_dir.glob('**/*') if file.is_file()]

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
        venv_lib_path = self.hook_get_venv_lib_path
        toga_path: Path = venv_lib_path / 'toga'
        iso4217parse_path: Path = venv_lib_path / 'iso4217parse'
        for file in [
            toga_path / '__init__.pyi',
            iso4217parse_path / 'data.json',
            iso4217parse_path / 'symbols.json',
        ]:
            pyinstaller_params.append(
                f'--add-data={file}{data_separator}{file.parent.relative_to(venv_lib_path)}'
            )
        pyinstaller_params += self.hook_pyinstaller_additional_params()
        run(pyinstaller_params)
        return True

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return []

    def hook_post_build_project(self) -> bool:
        """Executed after the project build, return True on success and False on failure."""
        return True

    def build_control_file(self) -> bool:
        """Build a JSON file with all the needed files for control purposes."""
        return True

    def build_zip_file(self) -> bool:
        logger.info('Creating archive [%s]...', self.zip_file)
        self.zip_file.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(self.zip_file, 'w', ZIP_DEFLATED) as zip_file:
            cwd: str = os.getcwd()
            os.chdir(self.project_dir)
            for folder_name, sub_folders, file_names in os.walk('.'):
                zip_file.write(folder_name, folder_name)
            for folder_name, sub_folders, file_names in os.walk('.'):
                for filename in file_names:
                    file_path: Path = Path(folder_name, filename)
                    zip_file.write(file_path, file_path)
            os.chdir(cwd)
        return True

    def build_test(self) -> bool:
        if self.test_dir.exists():
            logger.info('Deleting folder [%s]...', self.test_dir)
            shutil.rmtree(self.test_dir, onerror=shutil_delete_onerror)
        logger.info('Creating test environment in [%s]...', self.test_dir)
        self.test_dir.mkdir(parents=True)
        with ZipFile(self.zip_file, 'r') as zip_file:
            zip_file.extractall(self.test_dir)
        return True
