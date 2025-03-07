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
from common.logger import (
    get_logger,
    input_interactive,
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
    print_interactive_warning,
)
from common.papi_web_config import PapiWebConfig
from data.player import Player
from data.util import (
    TournamentRating,
    PlayerRatingType,
    PlayerGender,
    PlayerTitle,
)
from database.access.ffe.ffe_access_database import FfeAccessDatabase
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.ffe.util import PlayerFFELicence

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

    def __init__(self, write: bool = False):
        super().__init__(TMP_DIR / f'ffe.{PapiWebConfig.federation_database_ext}', write)

    def check(self) -> bool:
        """Check if the database exists and proposes to create it if not, or update it if too old,
        returns True if the database is available after the call, False otherwise."""
        yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
        if not self.exists():
            if (
                input_interactive(
                    _(
                        'The FFE database [{file}] was not found, do you want to create it (Y/n)? '
                    ).format(file=self.file)
                ).upper()
                or yes_answer
            ) != yes_answer:
                return True
        else:
            age: int = int(time() - self.file.lstat().st_mtime)
            if age > 2 * 24 * 60 * 60:
                days: int = age // (24 * 60 * 60)
                if (
                    input_interactive(
                        _(
                            'The FFE database [{file}] is obsolete ([{days}] days], do you want to update it (Y/n)? '
                        ).format(file=self.file, days=days)
                    ).upper()
                    or yes_answer
                ) != yes_answer:
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
                print_interactive_error(
                    _('Could not download [{url}], error code [{code}].').format(
                        url=ffe_database_url, code=response.status_code
                    )
                )
                return self.exists()
        except ConnectionError as ex:
            print_interactive_error(
                _('Could not download [{url}]: {ex}.').format(
                    url=ffe_database_url, ex=ex
                )
            )
            return self.exists()
        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            print_interactive_error(
                _('No data received from [{url}].').format(url=ffe_database_url)
            )
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
        # if the file already exists, save it to restore it on error.
        save: Path | None = None
        if self.file.exists():
            save = self.file.with_suffix('.save')
            save.unlink(missing_ok=True)
            self.file.rename(save)
        try:
            with open(
                PapiWebConfig.database_sql_path / 'create_ffe.sql', encoding='utf-8'
            ) as f:
                self._create(f.read())
            with FfeAccessDatabase(local_mdb_file) as ffe_access_database:
                self.write = True
                with self:
                    player_count: int = 0
                    for player_dict in ffe_access_database.read_player_dicts():
                        try:
                            translations: dict[str, types.FunctionType] = {
                                'ffe_id': None,
                                'ffe_licence_number': lambda s: s.strip().upper()
                                if s
                                else None,
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
                                field: player_dict[field]
                                if function is None
                                else function(player_dict[field])
                                for field, function in translations.items()
                            }
                            query: str = f'INSERT INTO player({", ".join(map(lambda s: f"`{s}`", data.keys()))}) VALUES({", ".join(["?"] * len(data))})'
                            self._execute(query, tuple(data.values()))
                            player_count += 1
                            if player_count % 1000 == 0:
                                print_interactive_info(_('{number} players written.').format(number=player_count), end='\r')
                    
                        except ValueError:
                            print_interactive_warning(
                                _(
                                    'Error reading the following row (player ignored): [{row}].'
                                ).format(row=player_dict)
                            )
                    self.commit()
        except (OperationalError, IntegrityError) as ex:
            print_interactive_error(
                _('Error while creating the database: {ex}.').format(ex=ex)
            )
            self.file.unlink(missing_ok=True)
            if save:
                save.rename(self.file)
            return False
        if save:
            save.unlink(missing_ok=True)
        print_interactive_success(
            _('{number} players written.').format(number=player_count)
        )
        return True

    @staticmethod
    def get_player_from_row(row: dict[str, Any]) -> Player | None:
        return Player(
            id=0,
            first_name=capwords(row['first_name']) if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            date_of_birth=datetime.strptime(
                row['date_of_birth'], '%Y-%m-%d'
            ).date(),
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
                TournamentRating.STANDARD: PlayerRatingType(
                    row['standard_rating_type']
                ),
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
        ) if row else None

    def search_player(
        self,
        string: str,
        limit: int = 0,  # no limit set if no param or null param passed
    ) -> Iterator[Player]:
        tokens: list[str] = string.split(' ')
        str_fields: tuple[tuple[str, str, str], ...] = (
            ('last_name', '%', '%'),
            ('first_name', '', '%'),
            ('club', '%', '%'),
            ('city', '%', '%'),
            ('ffe_licence_number', '', '')
        )
        int_fields: tuple[str, ...] = ('fide_id',)
        token_conditions: dict[str, str] = {}
        params: list[Any] = []
        for token in tokens:
            expressions = [f'({field[0]} LIKE ?)' for field in str_fields]
            params += [f'{field[1]}{token}{field[2]}' for field in str_fields]
            int_value: int
            with suppress(ValueError):
                int_value = int(token.strip())
                expressions += [f'({field} = ?)' for field in int_fields]
                params += [int_value, ] * len(int_fields)
            token_conditions[token] = ' OR '.join(expressions)
        conditions: str = ' AND '.join(
            map(lambda condition: f'({condition})', token_conditions.values())
        )
        order_conditions = ' OR '.join([f'(last_name LIKE ?)', ] * len(tokens))
        params += [f'{token}%' for token in tokens]
        query: str = f'SELECT * FROM player WHERE {conditions} ORDER BY (CASE WHEN {order_conditions} THEN 0 ELSE 1 END), last_name'
        if limit:
            query += ' LIMIT ?'
            params += [limit, ]
        self._execute(query, tuple(params), )
        return (
            self.get_player_from_row(row)
            for row in self._fetchall()
        )

    def get_player_by_ffe_id(self, player_ffe_id: int) -> Player | None:
        self._execute(f'SELECT * FROM player WHERE ffe_id = ?', (player_ffe_id, ))
        return self.get_player_from_row(self._fetchone())

    def get_player_by_fide_id(self, player_fide_id: int) -> Player | None:
        self._execute(f'SELECT * FROM player WHERE fide_id = ?', (player_fide_id,))
        return self.get_player_from_row(self._fetchone())
