#!/usr/bin/env python3
"""
Standalone script: download the FFE player database (Data.mdb), convert it to SQLite,
and enrich it with arbiter titles scraped from the FFE website.
Does not depend on the full Sharly Chess app environment — only requires `requests`.
"""

import argparse
import os
import platform
import re
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import requests

PAPI_CONVERTER_VERSION = '1.3.0'
FFE_DATABASE_URL = 'https://www.echecs.asso.fr/Papi/PapiData.zip'
FFE_PUBLIC_URL = 'http://echecs.asso.fr'
MDB_FILENAME = 'Data.mdb'

# Increment when the schema changes so consumers can detect the format version.
DB_VERSION = 1
DB_FILENAME = f'ffe_players_v{DB_VERSION}.db'

FFE_LEAGUES = [
    'ARA',
    'BFC',
    'BRE',
    'CRS',
    'CVL',
    'EST',
    'GUA',
    'GUY',
    'HDF',
    'IDF',
    'MAR',
    'NAQ',
    'NCA',
    'NOR',
    'OCC',
    'PAC',
    'PDL',
    'POL',
    'REU',
]

ARBITER_TITLE_FROM_HTML = {
    'Arbitre Jeune': 'AFJ',
    'Arbitre Club': 'AFC',
    'Arbitre Open 1': 'AFO1',
    'Arbitre Open 2': 'AFO2',
    'Arbitre Elite 1': 'AFE1',
    'Arbitre Elite 2': 'AFE2',
}


# ---------------------------------------------------------------------------
# papi-converter download + MDB → SQLite conversion
# ---------------------------------------------------------------------------


def get_papi_converter_info() -> tuple[str, str, str]:
    """Returns (archive_filename, executable_subdir, executable_filename)."""
    machine = os.environ.get('BUILD_ARCH', platform.machine()).lower()
    match sys.platform:
        case 'linux':
            if machine in ('aarch64', 'arm64'):
                return (
                    'papi-converter-linux-arm64.tar.gz',
                    'papi-converter-linux-arm64',
                    'papi-converter',
                )
            elif machine in ('x86_64', 'amd64'):
                return (
                    'papi-converter-linux-x86_64.tar.gz',
                    'papi-converter-linux-x86_64',
                    'papi-converter',
                )
            else:
                raise OSError(f'Unsupported Linux architecture: {machine}')
        case 'darwin':
            return 'papi-converter-mac.tar.gz', 'papi-converter-mac', 'papi-converter'
        case 'win32':
            return (
                'papi-converter-windows.zip',
                'papi-converter-windows',
                'papi-converter.bat',
            )
        case _:
            raise NotImplementedError(f'Unsupported platform: {sys.platform}')


def download_papi_converter(install_dir: Path) -> Path:
    archive_filename, executable_subdir, executable_filename = get_papi_converter_info()
    executable_path = install_dir / executable_subdir / executable_filename
    if executable_path.exists():
        return executable_path

    url = (
        f'https://github.com/Sharly-Chess/papi-converter/releases/download'
        f'/v{PAPI_CONVERTER_VERSION}/{archive_filename}'
    )
    print(f'Downloading papi-converter from {url}...')
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    archive_path = install_dir / archive_filename
    archive_path.write_bytes(response.content)

    if archive_filename.endswith('.tar.gz'):
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(install_dir)
    else:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(install_dir)

    archive_path.unlink(missing_ok=True)

    if sys.platform in ('linux', 'darwin'):
        current = executable_path.stat().st_mode
        executable_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return executable_path


def download_ffe_mdb(target_dir: Path) -> Path:
    print(f'Downloading FFE database from {FFE_DATABASE_URL}...')
    response = requests.get(FFE_DATABASE_URL, allow_redirects=True, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f'FFE download failed with HTTP {response.status_code}')

    zip_path = target_dir / 'PapiData.zip'
    zip_path.write_bytes(response.content)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(target_dir)
    zip_path.unlink()

    mdb_path = target_dir / MDB_FILENAME
    if not mdb_path.exists():
        raise RuntimeError(f'{MDB_FILENAME} not found after extraction')
    return mdb_path


def convert_mdb_to_sqlite(papi_converter: Path, mdb_path: Path, output_path: Path):
    sql_path = output_path.with_suffix('.sql')

    print('Converting MDB to SQL dump via papi-converter...')
    result = subprocess.run(
        [
            str(papi_converter),
            '--playerdb',
            str(mdb_path.resolve()),
            str(sql_path.resolve()),
        ],
        capture_output=True,
        encoding='utf-8',
    )
    if result.returncode != 0 or not sql_path.exists():
        raise RuntimeError(
            f'papi-converter failed (exit {result.returncode}):\n'
            f'stdout: {result.stdout}\nstderr: {result.stderr}'
        )

    print('Importing SQL dump into SQLite...')
    output_path.unlink(missing_ok=True)
    conn = sqlite3.connect(str(output_path))
    try:
        conn.executescript(sql_path.read_text(encoding='utf-8'))
        conn.commit()
    finally:
        conn.close()

    sql_path.unlink(missing_ok=True)

    if not output_path.exists():
        raise RuntimeError('SQLite database was not created')

    size_mb = output_path.stat().st_size / 1_048_576
    print(f'MDB → SQLite done ({size_mb:.1f} MB)')


# ---------------------------------------------------------------------------
# FFE arbiter scraping
# ---------------------------------------------------------------------------


class _FFEPageParser(HTMLParser):
    """Minimal HTML parser that extracts ASP.NET viewstate fields, table rows,
    and whether a 'next page' arrow is present."""

    def __init__(self):
        super().__init__()
        self.viewstate: str = ''
        self.viewstate_generator: str = ''
        self.rows: list[list[str]] = []
        self.has_next_page: bool = False
        self._in_tr = False
        self._current_row: list[str] = []
        self._in_td = False
        self._current_td = ''

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'tr':
            self._in_tr = True
            self._current_row = []
        elif tag == 'td' and self._in_tr:
            self._in_td = True
            self._current_td = ''
        elif tag == 'input':
            id_ = attrs_dict.get('id', '')
            if id_ == '__VIEWSTATE':
                self.viewstate = attrs_dict.get('value', '')
            elif id_ == '__VIEWSTATEGENERATOR':
                self.viewstate_generator = attrs_dict.get('value', '')
        elif tag == 'img':
            src = attrs_dict.get('src', '').lower()
            if src == 'images/t_fleche_d.gif':
                self.has_next_page = True

    def handle_endtag(self, tag):
        if tag == 'tr':
            if self._in_tr:
                self.rows.append(self._current_row[:])
            self._in_tr = False
            self._current_row = []
        elif tag == 'td' and self._in_td:
            self._current_row.append(self._current_td.strip())
            self._in_td = False

    def handle_data(self, data):
        if self._in_td:
            self._current_td += data


def _validate_ffe_licence(s: str) -> bool:
    return bool(re.match(r'^[A-Z]\d{5}$', s))


def scrape_ffe_arbiters() -> dict[str, str]:
    """Returns {ffe_licence_number: arbiter_title_string} for all leagues."""
    print('Scraping FFE arbiter titles...')
    session = requests.Session()

    # Initialise — gets initial viewstate cookies
    html = session.get(FFE_PUBLIC_URL, timeout=30).text
    p = _FFEPageParser()
    p.feed(html)
    viewstate = p.viewstate
    viewstate_generator = p.viewstate_generator

    arbiters: dict[str, str] = {}

    for league in FFE_LEAGUES:
        url = f'{FFE_PUBLIC_URL}/ListeArbitres.aspx?Action=DNALIGUE&Ligue={league}'
        page = 1
        while True:
            if page == 1:
                response = session.get(url, timeout=30)
            else:
                response = session.post(
                    url,
                    data={
                        '__EVENTTARGET': 'ctl00$ContentPlaceHolderMain$PagerFooter',
                        '__EVENTARGUMENT': 'd',
                        '__VIEWSTATE': viewstate,
                        '__VIEWSTATEGENERATOR': viewstate_generator,
                    },
                    timeout=30,
                )

            p = _FFEPageParser()
            p.feed(response.text)

            if p.viewstate:
                viewstate = p.viewstate
            if p.viewstate_generator:
                viewstate_generator = p.viewstate_generator

            for row in p.rows:
                if len(row) >= 3 and _validate_ffe_licence(row[0]):
                    title = ARBITER_TITLE_FROM_HTML.get(row[2], '')
                    if title:
                        arbiters[row[0]] = title

            if not p.has_next_page:
                break
            page += 1

        print(f'  {league}: done')

    print(f'Scraped {len(arbiters)} arbiters in total.')
    return arbiters


def enrich_with_arbiter_titles(db_path: Path, arbiters: dict[str, str]):
    print('Writing arbiter titles into SQLite...')
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute('ALTER TABLE player ADD COLUMN ffe_arbiter_title TEXT')
        conn.executemany(
            'UPDATE player SET ffe_arbiter_title = ? WHERE ffe_licence_number = ?',
            [(title, licence) for licence, title in arbiters.items()],
        )
        conn.commit()
    finally:
        conn.close()
    print('Done.')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description='Generate FFE SQLite player database')
    parser.add_argument(
        '--output',
        type=Path,
        default=Path(DB_FILENAME),
        help='Path for the output SQLite file',
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        papi_converter = download_papi_converter(tmp)
        mdb_path = download_ffe_mdb(tmp)
        convert_mdb_to_sqlite(papi_converter, mdb_path, args.output.resolve())

    arbiters = scrape_ffe_arbiters()
    enrich_with_arbiter_titles(args.output.resolve(), arbiters)

    size_mb = args.output.stat().st_size / 1_048_576
    print(f'Output: {args.output} ({size_mb:.1f} MB)')


if __name__ == '__main__':
    main()
