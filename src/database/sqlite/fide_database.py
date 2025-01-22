import os.path
import zipfile
from contextlib import suppress
from datetime import datetime
from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError, IntegrityError
from time import time
from typing import Iterator, Any

from requests import Response, get
from requests.exceptions import ConnectionError

from common import TMP_DIR
from common.i18n import _
from common.logger import get_logger, input_interactive, print_interactive_info, print_interactive_error, \
    print_interactive_success, print_interactive_warning
from common.papi_web_config import PapiWebConfig
from data.player import Player
from data.util import PlayerGender, PlayerTitle, TournamentRating, PlayerRatingType, PlayerFFELicence
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class FideDatabase(SQLiteDatabase):
    """
    The SQLite database class for FIDE players. Usage:
    1. Check if the database exists and is up-to-date and update is requested (from an interactive script):
    FideDatabase().check()
    2. Search the database:
    with FideDatabase() as fide_database:
        for player in fide_database.search_player('my name'):
            ...
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
            self.write = True
            with self:
                players_number: int = 0
                with open(local_txt_file, 'r') as file:
                    fields: dict[str, int] = {
                        'fide_id': (15, lambda s: int(s.strip())),
                        'name': (61, str),
                        'federation': (4, lambda s: s.upper()),
                        'gender': (4, lambda s: PlayerGender.from_fide_value(s)),
                        'fide_title': (5, lambda s: PlayerTitle.from_fide_value(s)),
                        'woman_title': (5, None),
                        'other_title': (15, None),
                        'standard_rating': (6, int),
                        'standard_games': (4, None),
                        'standard_k_factor': (3, None),
                        'rapid_rating': (6, int),
                        'rapid_games': (4, None),
                        'rapid_k_factor': (3, None),
                        'blitz_rating': (6, int),
                        'blitz_games': (4, None),
                        'blitz_k_factor': (3, None),
                        'year_of_birth': (6, int),
                        'flag': (4, None),
                    }
                    line_normal_length: int = 0
                    for line_no, line in enumerate(file, start=1):
                        if line_no == 1:
                            line_normal_length = len(line)
                            continue
                        try:
                            data: dict[str, Any] = {}
                            orig_line: str = line
                            # if the line length is more than the expected length, we assume that the too-big field
                            # is other_title (see FIDE ID 3101959)
                            gap: int = len(line) - line_normal_length
                            for field_name, (field_size, field_type) in fields.items():
                                real_field_size: int = field_size + (gap if field_name == 'other_title' else 0)
                                if field_type:
                                    title: str = 'WH'
                                    if field_name in ['fide_title'] and title in line[:real_field_size]:
                                        data[field_name] = ''
                                        print_interactive_warning(
                                            _('Added player [{fide_id} {name}] by ignoring title [{title}].').format(
                                                fide_id=data["fide_id"], name=data["name"].strip(), title=title))
                                    else:
                                        data[field_name] = field_type(line[:real_field_size].strip())
                                line = line[real_field_size:]
                            if ',' in data['name']:
                                name_parts: list[str] = data['name'].split(',', maxsplit=2)
                                data['last_name'] = name_parts[0]
                                data['first_name'] = name_parts[1]
                                data['last_name'], data['first_name'] = data['name'].split(',', maxsplit=1)
                            else:
                                data['last_name'] = data['name']
                                data['first_name'] = None
                            if gap:
                                print_interactive_warning(
                                    _('Added player [{fide_id} {name}] by adding [{gap}] chars to field [{field}].').format(
                                        fide_id=data["fide_id"], name=data["name"].strip(), gap=gap, field='other_title'))
                            del data['name']
                            query: str = f'INSERT INTO player({", ".join(data.keys())}) VALUES({", ".join(["?", ] * len(data))})'
                            self._execute(query, tuple(data.values()))
                            players_number += 1
                        except ValueError as ex:
                            print_interactive_warning(
                                _('Error at line [{line_no}]: [{ex}] (player ignored: [{line}]).').format(line_no=line_no, ex=ex, line=orig_line.strip()))
                self.commit()
        except (OperationalError, IntegrityError) as ex:
            print_interactive_error(_('Error while creating the database: {ex}.').format(ex=ex))
            self.file.unlink(missing_ok=True)
            return False
        print_interactive_success(_('{number} players written.').format(number=players_number))
        return True

    def read_federation_ids(self) -> Iterator[str]:
        self._execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from map(lambda row: row['federation'], self._fetchall())

    def search_player(self, string: str) -> Iterator[Player]:
        tokens: list[str] = string.split(' ')
        str_fields: tuple[str, ...] = ('last_name', 'first_name', )
        int_fields: tuple[str, ...] = ('fide_id', )
        token_conditions: dict[str, str] ={}
        for token in tokens:
            expressions = list(map(lambda field: f'({field} LIKE \'%{token}%\')', str_fields))
            int_value: int
            with suppress(ValueError):
                int_value = int(token.strip())
                expressions += list(map(lambda field: f'({field} = {int_value})', int_fields))
            token_conditions[token] = ' OR '.join(expressions)
        conditions: str = ' AND '.join(map(lambda condition: f'({condition})', token_conditions.values()))
        self._execute(f'SELECT * FROM player WHERE {conditions}')
        return (Player(
            id=0,
            first_name=row['first_name'],
            last_name=row['last_name'],
            date_of_birth=datetime.strptime(f"{row['year_of_birth']}-01-01", '%Y-%m-%d').date() if row['year_of_birth'] else None,
            gender=PlayerGender(row['gender']),
            mail='',
            phone='',
            comment='',
            owed=0.0,
            paid=0.0,
            title=PlayerTitle(row['fide_title']),
            ratings={
                TournamentRating.STANDARD: row['standard_rating'],
                TournamentRating.RAPID: row['rapid_rating'],
                TournamentRating.BLITZ: row['blitz_rating'],
            },
            rating_types={
                TournamentRating.STANDARD: PlayerRatingType.FIDE if row['standard_rating'] else PlayerRatingType.ESTIMATED,
                TournamentRating.RAPID: PlayerRatingType.FIDE if row['rapid_rating'] else PlayerRatingType.ESTIMATED,
                TournamentRating.BLITZ: PlayerRatingType.FIDE if row['blitz_rating'] else PlayerRatingType.ESTIMATED,
            },
            fide_id=row['fide_id'],
            ffe_id=0,
            ffe_licence=PlayerFFELicence.NONE,
            ffe_licence_number=None,
            federation=row['federation'],
            league='',
            club='',
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=None,
        ) for row in self._fetchall())
