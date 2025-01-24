import os.path
import types
import zipfile
from contextlib import suppress
from datetime import datetime
from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError, IntegrityError
from string import capwords
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
from data.util import TournamentRating, PlayerRatingType, PlayerGender, PlayerTitle, PlayerFFELicence
from database.access.ffe.ffe_access_database import FfeAccessDatabase
from database.sqlite.sqlite_database import SQLiteDatabase

logger: Logger = get_logger()


class FfeDatabase(SQLiteDatabase):
    """
    The SQLite database class for FFE players. Usage:
    1. Check if the database exists and is up-to-date and update is requested (from an interactive script):
    FfeDatabase().check()
    2. Search the database:
    with FfeDatabase() as ffe_database:
        for player in ffe_database.search_player('my name'):
            ...
    """

    def __init__(self, basename: str = 'ffe', write: bool = False):
        super().__init__(TMP_DIR / f'{basename}.{PapiWebConfig.event_ext}', write)

    def check(self) -> bool:
        """Check if the database exists and proposes to create it if not, or update it if too old,
        returns True if the database is available after the call, False otherwise."""
        yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
        if not self.exists():
            if (input_interactive(
                _('The FFE database [{file}] was not found, do you want to create it (Y/n)? ').format(
                    file=self.file)).upper() or yes_answer) != yes_answer:
                return False
        else:
            age: int = int(self.file.lstat().st_mtime - time())
            if age > 2 * 24 * 60 * 60:
                days: int = age // (24 * 60 * 60)
                if (input_interactive(
                    _('The FFE database [{file}] is obsolete ([{days}] days], do you want to update it (Y/n)? ').format(
                        file=self.file, days=days)).upper() or yes_answer) != yes_answer:
                    return True
            else:
                return True
        print_interactive_info(_('Downloading the FFE database...'))
        ffe_database_url: str = 'https://www.echecs.asso.fr/Papi/PapiData.zip'
        local_zip_file: Path = TMP_DIR / os.path.basename(ffe_database_url)
        with suppress(FileNotFoundError):
            local_zip_file.unlink()
        try:
            response: Response = get(ffe_database_url, allow_redirects=True, timeout=5)
            if response.status_code != 200:
                print_interactive_error(_('Could not download [{url}], error code [{code}].').format(
                    url=ffe_database_url, code=response.status_code))
                return self.exists()
        except ConnectionError as ex:
            print_interactive_error(_('Could not download [{url}]: {ex}.').format(url=ffe_database_url, ex=ex))
            return self.exists()
        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            print_interactive_error(_('No data received from [{url}].').format(url=ffe_database_url))
            return True
        local_mdb_file = TMP_DIR / 'Data.mdb'
        with suppress(FileNotFoundError):
            local_mdb_file.unlink()
        with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
            zip_ref.extractall(TMP_DIR)
        if not local_mdb_file.exists():
            print_interactive_error(_('Could not unzip data.'))
            return self.exists()
        print_interactive_info(_('Storing data...'))
        try:
            with open(PapiWebConfig.database_sql_path / 'create_ffe.sql', encoding='utf-8') as f:
                self._create(f.read())
            with FfeAccessDatabase(local_mdb_file) as ffe_access_database:
                self.write = True
                with self:
                    players_number: int = 0
                    for player_dict in ffe_access_database.read_player_dicts():
                        try:
                            translations: dict[str, types.FunctionType] = {
                                'ffe_id': None,
                                'ffe_licence_number': lambda s: s.strip().upper() if s else None,
                                'last_name': lambda s: s.strip().upper(),
                                'first_name': lambda s: capwords(s),
                                'gender': PlayerGender.from_papi_value,
                                'date_of_birth': lambda dt: dt.date() if dt else None,
                                'federation': None,
                                'standard_rating': int,
                                'rapid_rating': int,
                                'blitz_rating': int,
                                'standard_rating_type': PlayerRatingType.from_papi_value,
                                'rapid_rating_type': PlayerRatingType.from_papi_value,
                                'blitz_rating_type': PlayerRatingType.from_papi_value,
                                'fide_id': lambda s: int(s.strip()) if s else 0,
                                'fide_title': PlayerTitle.from_papi_value,
                                'ffe_licence': PlayerFFELicence.from_papi_value,
                                'league': None,
                                'city': None,
                                'club': None,
                            }
                            data: dict[str, Any] = {
                                field: player_dict[field] if function is None else function(player_dict[field])
                                for field, function in translations.items()
                            }
                            query: str = f'INSERT INTO player({", ".join(map(lambda s: f"`{s}`", data.keys()))}) VALUES({", ".join(["?", ] * len(data))})'
                            self._execute(query, tuple(data.values()))
                            players_number += 1
                        except ValueError:
                            print_interactive_warning(
                                _('Error reading the following row (player ignored): [{row}].').format(row=player_dict))
                    self.commit()
        except (OperationalError, IntegrityError) as ex:
            print_interactive_error(_('Error while creating the database: {ex}.').format(ex=ex))
            self.file.unlink(missing_ok=True)
            return False
        print_interactive_success(_('{number} players written.').format(number=players_number))
        return True

    def search_player(self, string: str) -> Iterator[Player]:
        tokens: list[str] = string.split(' ')
        str_fields: tuple[str, ...] = ('last_name', 'first_name', 'club', 'city', )
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
            date_of_birth=datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date(),
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
                TournamentRating.STANDARD: PlayerRatingType(row['standard_rating_type']),
                TournamentRating.RAPID: PlayerRatingType(row['rapid_rating_type']),
                TournamentRating.BLITZ: PlayerRatingType(row['blitz_rating_type']),
            },
            fide_id=row['fide_id'],
            ffe_id=row['ffe_id'],
            ffe_licence=PlayerFFELicence(row['ffe_licence']),
            ffe_licence_number=row['ffe_licence_number'],
            federation=row['federation'],
            league=row['league'],
            club=row['club'],
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=None,
        ) for row in self._fetchall())
