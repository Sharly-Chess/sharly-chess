import os
import re
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from logging import Logger
from PyInstaller.__main__ import run

from common import BASE_DIR
from common.bbp_pairings import BbpPairings
from common.i18n import locales
from common.papi_web_config import PapiWebConfig
from common.logger import get_logger, print_interactive_info, input_interactive, print_interactive_error, \
    print_interactive_success
from utils.i18n.i18n_update import I18nUpdater

logger: Logger = get_logger()

BUILD_DIR: Path = BASE_DIR / 'build'
DIST_DIR: Path = BASE_DIR / 'dist'
DATA_DIR: Path = BASE_DIR / 'export-data'
LOCALE_DIR: Path = BASE_DIR / 'locale'
basename: str = f'papi-web-{PapiWebConfig.version}'
EXPORT_DIR: Path = BASE_DIR / 'export'
PROJECT_DIR: Path = EXPORT_DIR / basename
ZIP_FILE: Path = EXPORT_DIR / f'{basename}.zip'
EXE_FILENAME: str = basename + '.exe'
SPEC_FILE: Path = BASE_DIR / f'{basename}.spec'
TEST_DIR: Path = BASE_DIR / 'export-test'
SOURCE_DIR: Path = BASE_DIR / 'src'
ICON_FILE: Path = SOURCE_DIR / 'web' / 'static' / 'images' / 'papi-web.ico'


def clean(clean_zip: bool):
    for d in [BUILD_DIR, DIST_DIR, PROJECT_DIR, ]:
        if Path(d).is_dir():
            print_interactive_info(f'Deleting folder {d}...')
            shutil.rmtree(d)
    if SPEC_FILE.is_file():
        print_interactive_info(f'Deleting file {SPEC_FILE}...')
        SPEC_FILE.unlink()
    if clean_zip:
        if ZIP_FILE.is_file():
            print_interactive_info(f'Deleting file {ZIP_FILE}...')
            ZIP_FILE.unlink()


def build_exe():
    pyinstaller_params = [
        '--clean',
        '--noconfirm',
        '--name=' + basename,
        '--onefile',
        '--hiddenimport=chessevent',
        '--hiddenimport=common',
        '--hiddenimport=data',
        '--hiddenimport=database',
        '--hiddenimport=ffe',
        '--hiddenimport=web',
        '--paths=.',
        '--icon=src/web/static/images/papi-web.ico',
        'src/papi_web.py',
    ]
    files: list[Path] = []
    web_dir = SOURCE_DIR / 'web'
    files += [file for file in (web_dir / 'templates').glob('**/*') if file.is_file()]
    static_dir = web_dir / 'static'
    files += [file for file in Path(static_dir, 'images').glob('**/*') if file.is_file()]
    files += [file for file in Path(static_dir, 'css').glob('**/*') if file.is_file()]
    files += [file for file in Path(static_dir, 'js').glob('**/*') if file.is_file()]
    lib_dir = static_dir / 'lib'
    bootstrap_dir = lib_dir / 'bootstrap' / f'bootstrap-{PapiWebConfig.bootstrap_version}-dist'
    files += [
        bootstrap_dir / 'css' / 'bootstrap.min.css',
        bootstrap_dir / 'css' / 'bootstrap.min.css.map',
        bootstrap_dir / 'js' / 'bootstrap.bundle.min.js',
        bootstrap_dir / 'js' / 'bootstrap.bundle.min.js.map',
    ]
    bootstrap_icons_dir = lib_dir / 'bootstrap-icons' / f'bootstrap-icons-{PapiWebConfig.bootstrap_icons_version}'
    files += [
        bootstrap_icons_dir / 'font' / 'bootstrap-icons.min.css',
    ]
    files += [
        file for file in (bootstrap_icons_dir / 'font' / 'fonts').glob('**/*')
        if file.is_file()
    ]
    jquery_file = lib_dir / 'jquery' / f'jquery-{PapiWebConfig.jquery_version}.min.js'
    files += [jquery_file, ]
    htmx_dir = lib_dir / 'htmx' / f'htmx-{PapiWebConfig.htmx_version}'
    files += [
        file for file in htmx_dir.glob('**/*')
        if file.is_file()
    ]
    sortable_dir = lib_dir / 'sortable' / f'sortable-{PapiWebConfig.sortable_version}'
    files += [
        file for file in sortable_dir.glob('**/*')
        if file.is_file()
    ]
    htmx_sortable_file = lib_dir / 'htmx' / f'htmx-sortable.js'
    files += [htmx_sortable_file, ]
    jstree_dir = lib_dir / 'jstree' / f'jstree-{PapiWebConfig.jstree_version}-dist'
    files += [
        file for file in jstree_dir.glob('**/*')
        if file.is_file()
    ]
    sql_dir: Path = SOURCE_DIR / 'database' / 'sql'
    files += [sql_dir / 'create_event.sql', ]
    yml_dir: Path = SOURCE_DIR / 'database' / 'yml'
    files += list(yml_dir.glob('*.yml'))
    custom_dir: Path = SOURCE_DIR / 'custom'
    files += [
        file for file in custom_dir.glob('**/*')
        if file.is_file()
    ]
    files += [
        file for file in LOCALE_DIR.glob('**/*.mo')
        if file.is_file()
    ]
    bbp = BbpPairings()
    bbp.check_installed()
    files += [bbp.executable_path]
    for file in files:
        pyinstaller_params.append(f'--add-data={file};{file.parent.relative_to(BASE_DIR)}')
    files: list[Path] = []
    files += [
        file for file in Path(
            BASE_DIR / 'venv/lib/site-packages/litestar/exceptions/responses/templates').glob('**/*')
        if file.is_file()
    ]
    for file in files:
        pyinstaller_params.append(
            f'--add-data={file};{file.parent.relative_to(BASE_DIR / "venv/lib/site-packages")}')
    run(pyinstaller_params)


def create_project():
    papi_web_config: PapiWebConfig = PapiWebConfig()
    print_interactive_info(f'Creating folder {PROJECT_DIR} from {DATA_DIR}...')
    shutil.copytree(DATA_DIR, PROJECT_DIR)
    dist_exe_file: Path = DIST_DIR / EXE_FILENAME
    print_interactive_info(f'Moving {dist_exe_file} to {PROJECT_DIR}...')
    bin_dir: Path = PROJECT_DIR / 'bin'
    bin_dir.mkdir(exist_ok=True)
    shutil.move(dist_exe_file, bin_dir)
    # create an empty events dir
    events_dir: Path = PROJECT_DIR / 'events'
    events_dir.mkdir(exist_ok=True)
    # just create an empty custom dir (dev custom files are embedded in the exe since 2.4.11)
    custom_dir: Path = PROJECT_DIR / 'custom'
    custom_dir.mkdir(exist_ok=True)
    target_file: Path = PROJECT_DIR / 'server.bat'
    print_interactive_info(f'Creating batch file {target_file}...')
    with open(target_file, 'wt', encoding='utf-8') as f:
        f.write(f'@echo off\n'
                f'echo Starting Papi-web, please wait...\n'
                f'@rem Papi-web {papi_web_config.version} - {papi_web_config.copyright} - {papi_web_config.url}\n'
                f'bin\\{EXE_FILENAME} --server\n'
                f'pause\n')
    target_file = PROJECT_DIR / 'ffe.bat'
    print_interactive_info(f'Creating batch file {target_file}...')
    with open(target_file, 'wt', encoding='utf-8') as f:
        f.write(f'@echo off\n'
                f'echo Starting Papi-web FFE client, please wait...\n'
                f'@rem Papi-web {papi_web_config.version} - {papi_web_config.copyright} - {papi_web_config.url}\n'
                f'bin\\{EXE_FILENAME} --ffe\n'
                f'pause\n')
    target_file = PROJECT_DIR / 'chessevent.bat'
    print_interactive_info(f'Creating batch file {target_file}...')
    with open(target_file, 'wt', encoding='utf-8') as f:
        f.write(f'@echo off\n'
                f'echo Starting Papi-web ChessEvent client, please wait...\n'
                f'@rem Papi-web {papi_web_config.version} - {papi_web_config.copyright} - {papi_web_config.url}\n'
                f'bin\\{EXE_FILENAME} --chessevent\n'
                f'pause\n')


def create_zip():
    print_interactive_info(f'Creating archive {ZIP_FILE}...')
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
        print_interactive_info(f'Creating test environment in {TEST_DIR}...')
        TEST_DIR.mkdir(parents=True)
    else:
        print_interactive_info(f'Updating test environment in {TEST_DIR}...')
    with ZipFile(ZIP_FILE, 'r') as zip_file:
        zip_file.extractall(TEST_DIR)


def update_readme():
    papi_web_config: PapiWebConfig = PapiWebConfig()
    readme: Path = Path('README.md')
    if not re.match(r'^\d+\.\d+\.\d+$', str(papi_web_config.version)):
        return
    if (input_interactive(f'Do you want to update {readme} with version {papi_web_config.version} (y/N)?').upper() or 'N') != 'Y':
        return
    print_interactive_info(f'Updating {readme}...')
    lines_before_comment: list[str] = []
    lines_after_comment: list[str] = []
    # Read the lines until the expected comment is found
    with open(readme, 'rt', encoding='utf-8') as f:
        comment: str = '<!-- DO NOT EDIT! (START) -->'
        comment_found: bool = False
        for line in f:
            lines_before_comment.append(line)
            if line.startswith(comment):
                comment_found = True
                break
        if not comment_found:
            print_interactive_error(f'Could not edit [{readme}] (comment [{comment}] not found).')
            return
        comment: str = '<!-- DO NOT EDIT! (END) -->'
        comment_found: bool = False
        for line in f:
            if line.startswith(comment):
                comment_found = True
            if comment_found:
                lines_after_comment.append(line)
        if not comment_found:
            print_interactive_error(f'Could not edit [{readme}] (comment [{comment}] not found).')
            return
    lines: list[str] = [
        f'- **[Télécharger la dernière version stable ({papi_web_config.version})](https://github.com/papi-web-org/papi-web/releases/download/{papi_web_config.version}/papi-web-{papi_web_config.version}.zip)**\n'
    ]
    with open(readme, 'w', encoding='utf-8') as f:
        for line in lines_before_comment + lines + lines_after_comment:
            f.write(line)
    print_interactive_success(f'Successfully updated {readme}.')


def update_pyproject():
    papi_web_config: PapiWebConfig = PapiWebConfig()
    pyproject_file: Path = Path('pyproject.toml')
    print_interactive_info(f'Updating {pyproject_file}...')
    with open(pyproject_file, 'r') as file:
        content = file.read()
    content = re.sub(r'version\s*=\s*"[\d\\.]+"', f'version = "{papi_web_config.version}"', content)
    with open(pyproject_file, 'w') as file:
        file.write(content)
    print_interactive_success(f'Successfully updated {pyproject_file}.')


def main():
    clean(clean_zip=True)
    if not I18nUpdater(locales).check_trusted_locales():
        if (input_interactive(
                'Translations are not perfect for trusted locales, do you want to continue (y/N):'
        ).upper() or 'N') != 'Y':
            return
    build_exe()
    create_project()
    create_zip()
    build_test()
    clean(clean_zip=False)
    update_readme()
    update_pyproject()


main()
