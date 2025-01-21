import os.path
import zipfile
from contextlib import suppress
from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError
from time import time
from typing import Iterator

from requests import Response, get
from requests.exceptions import ConnectionError
from common import TMP_DIR
from common.i18n import _
from common.logger import get_logger, input_interactive, print_interactive_info, print_interactive_error, \
    print_interactive_success, print_interactive_warning
from common.papi_web_config import PapiWebConfig
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class FideDatabase(SQLiteDatabase):
    """
    The SQLite database class for FIDE players.
    """

    def __init__(self, basename: str = 'fide', write: bool = False):
        super().__init__(TMP_DIR / f'{basename}.{PapiWebConfig.event_ext}', write)

    def check(self) -> bool:
        """Check if the database exists and proposes to create it if not, or update it if too old,
        returns True if the database is available after the call, False otherwise."""
        yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
        if not self.exists():
            if (input_interactive(
                _('The FIDE database [{file}] was not found, do you want to create it (Y/n)? ').format(
                    file=self.file)).upper() or yes_answer) != yes_answer:
                return False
        else:
            age: int = int(self.file.lstat().st_mtime - time())
            if age > 2 * 24 * 60 * 60:
                days: int = age // (24 * 60 * 60)
                if (input_interactive(
                    _('The FIDE database [{file}] is obsolete ([{days}] days], do you want to update it (Y/n)? ').format(
                        file=self.file, days=days)).upper() or yes_answer) != yes_answer:
                    return True
            else:
                return True
        print_interactive_info(_('Downloading the FIDE database...'))
        fide_database_url: str = 'https://ratings.fide.com/download/players_list_legacy.zip'
        local_zip_file: Path = TMP_DIR / os.path.basename(fide_database_url)
        with suppress(FileNotFoundError):
            local_zip_file.unlink()
        try:
            response: Response = get(fide_database_url, allow_redirects=True, timeout=5)
            if response.status_code != 200:
                print_interactive_error(_('Could not download [{url}], error code [{code}].').format(
                    url=fide_database_url, code=response.status_code))
                return self.exists()
        except ConnectionError as ex:
            print_interactive_error(_('Could not download [{url}]: {ex}.').format(url=fide_database_url, ex=ex))
            return self.exists()
        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            print_interactive_error(_('No data received from [{url}].').format(url=fide_database_url))
            return True
        local_txt_file = TMP_DIR / 'players_list.txt'
        with suppress(FileNotFoundError):
            local_txt_file.unlink()
        with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
            zip_ref.extractall(TMP_DIR)
        if not local_txt_file.exists():
            print_interactive_error(_('Could not unzip data.'))
            return self.exists()
        print_interactive_info(_('Storing data...'))
        try:
            with open(PapiWebConfig.database_sql_path / 'create_fide.sql', encoding='utf-8') as f:
                self.create(f.read())
            with self:
                players_number: int = 0
                with open(local_txt_file, 'r') as file:
                    fields: dict[str, int] = {
                        'id_number': (15, str),
                        'name': (61, str),
                        'federation': (4, lambda s: s.upper()),
                        'sex': (4, lambda s: s.upper()),
                        'title': (5, lambda s: s.upper()),
                        'woman_title': (5, lambda s: s.upper()),
                        'other_title': (15, lambda s: s.upper()),
                        'standard_rating': (6, int),
                        'standard_games': (4, None),
                        'standard_k_factor': (3, int),
                        'rapid_rating': (6, int),
                        'rapid_games': (4, None),
                        'rapid_k_factor': (3, int),
                        'blitz_rating': (6, int),
                        'blitz_games': (4, None),
                        'blitz_k_factor': (3, int),
                        'year_of_birth': (6, int),
                        'flag': (4, None),
                    }
                    for line_no, line in enumerate(file, start=1):
                        if line_no > 1:
                            try:
                                data: dict[str, str] = {}
                                orig_line = line
                                for field_name, (field_size, field_type) in fields.items():
                                    if field_type:
                                        data[field_name] = field_type(line[:field_size].strip())
                                    line = line[field_size:]
                                query: str = f'INSERT INTO player({", ".join(data.keys())}) VALUES({", ".join(["?", ] * len(data))})'
                                self._execute(query, tuple(data.values()))
                                players_number += 1
                            except ValueError:
                                print_interactive_warning(
                                    _('Error at line [{line_no}] (player ignored): [{line}].').format(line_no=line_no, line=orig_line.strip()))
                self.commit()
        except OperationalError as ex:
            print_interactive_error(_('Error while creating the database: {ex}.').format(ex=ex))
            self.file.unlink()
            return False
        print_interactive_success(_('{number} players written.').format(number=players_number))
        return True

    def read_federation_ids(self) -> Iterator[str]:
        self._execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from map(lambda row: row['federation'], self._fetchall())
