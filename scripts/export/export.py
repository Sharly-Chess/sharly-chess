import argparse
import os
import shutil
from pathlib import Path
import sys
from pkgutil import iter_modules
from types import ModuleType

from packaging.version import Version, InvalidVersion

from common.i18n import update_i18n_files

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

# Needs to be imported first to avoid circular import
from plugins.manager import plugin_manager  # Noqa

from common import BASE_DIR, enable_experimental_features, EVENTS_FOLDER
from data.pairings.engines import BbpPairings
from common import SHARLY_CHESS_VERSION
from common.sharly_chess_config import SharlyChessConfig
from common.logger import get_logger
from database.sqlite.config import migrations as config_migrations
from database.sqlite.event import migrations as event_migrations
from common.installation_checker import (
    InstallationChecker,
)
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
OLD_ZIP_FILE: Path = EXPORT_DIR / f'papi-web-{SHARLY_CHESS_VERSION}.zip'
EXE_FILENAME: str = basename + '.exe'
INTERNAL_DIRNAME: str = '_internal'
SPEC_FILE: Path = BASE_DIR / f'{basename}.spec'
TEST_DIR: Path = BASE_DIR / 'export-test'
SOURCE_DIR: Path = BASE_DIR / 'src'
FFE_SQL_SERVER_CREDENTIALS_FILE: Path = PLUGINS_DIR / 'ffe' / '.credentials'


def clean(clean_zip: bool):
    for d in [
        BUILD_DIR,
        DIST_DIR,
        PROJECT_DIR,
    ]:
        if Path(d).is_dir():
            logger.info('Deleting folder [%s]...', d)
            shutil.rmtree(d)
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
    files += [BbpPairings().executable_path]
    files += [
        FFE_SQL_SERVER_CREDENTIALS_FILE,
    ]
    for file in files:
        pyinstaller_params.append(
            f'--add-data={file};{file.parent.relative_to(BASE_DIR)}'
        )
    run(pyinstaller_params)


def create_project():
    logger.info('Adding data from folder [%s] to [%s]...', PROJECT_DIR, DATA_DIR)
    shutil.copytree(DATA_DIR, PROJECT_DIR, dirs_exist_ok=True)
    tools_dir: Path = PROJECT_DIR / 'tools'
    tools_dir.mkdir(parents=True, exist_ok=True)
    bbp_pairings: BbpPairings = BbpPairings()
    bbp_pairings_dir: Path = (
        tools_dir / 'bbpPairings' / f'bbpPairings-v{bbp_pairings.version}'
    )
    bbp_pairings_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        'Copying [%s] to [%s]...', bbp_pairings.executable_dir, bbp_pairings_dir
    )
    shutil.copytree(bbp_pairings.executable_dir, bbp_pairings_dir, dirs_exist_ok=True)
    # create an empty events dir
    events_dir: Path = PROJECT_DIR / EVENTS_FOLDER
    events_dir.mkdir(exist_ok=True)
    # just create an empty custom dir (dev custom files are embedded in the exe since 2.4.11)
    custom_dir: Path = PROJECT_DIR / 'custom'
    custom_dir.mkdir(exist_ok=True)
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
    shutil.copy(ZIP_FILE, OLD_ZIP_FILE)


def build_test():
    if not TEST_DIR.is_dir():
        logger.info('Creating test environment in [%s]...', TEST_DIR)
        TEST_DIR.mkdir(parents=True)
    else:
        logger.info('Updating test environment in [%s]...', TEST_DIR)
        shutil.rmtree(TEST_DIR / '_internal', ignore_errors=True)
    with ZipFile(ZIP_FILE, 'r') as zip_file:
        zip_file.extractall(TEST_DIR)


def main():
    # option --github is used when generating the EXE file from a GITHUB action
    # to verify that the name of the tag matches the Sharly Chess version.
    parser = argparse.ArgumentParser()
    parser.add_argument('--github', type=str)
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
    create_zip_files()
    build_test()
    clean(clean_zip=False)


if __name__ == '__main__':
    main()
