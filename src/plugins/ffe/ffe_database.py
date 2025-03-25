import os.path
import types
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
from common.logger import (
    get_logger,
    input_interactive,
    print_interactive_info,
    print_interactive_error,
    print_interactive_success,
    print_interactive_warning,
)
from common.network import NetworkMonitor
from common.papi_web_config import PapiWebConfig
from data.player import Player, Federation, Club
from data.util import (
    TournamentRating,
    PlayerRatingType,
    PlayerGender,
    PlayerTitle,
)
from plugins import PLUGINS_DIR

from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_access_database import FfeAccessDatabase
from plugins.ffe.util import PlayerFFELicence
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

    def __init__(self, write: bool = False):
        super().__init__(TMP_DIR / f'ffe.{PapiWebConfig.federation_database_ext}', write)

    def check(self) -> bool:
        """Check if the database exists and proposes to create it if not, or update it if too old,
        returns True if the database is available after the call, False otherwise."""
        yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
        if not self.exists():
            if not NetworkMonitor.connected():
                print_interactive_warning(_('Not connected, can not create the FFE database.'))
                return False
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
                if not NetworkMonitor.connected():
                    print_interactive_warning(_('Not connected, can not update the FFE database.'))
                    return True
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
        return self.create()

    def create(self) -> bool:
        """Create the FFE database, returns True if the database is available after the call, False otherwise."""
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

        translations: dict[str, types.FunctionType] = {
            'ffe_id': None,
            'ffe_licence_number': lambda s: s.strip().upper() if s else None,
            'last_name': lambda s: s.strip().upper(),
            'first_name': lambda s: s.strip().title() if s else '',
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
        column_names: list[str] = list(translations.keys())
        bindings: list[str] = [f':{column_name}' for column_name in column_names]
        escaped_column_names: list[str] = list(map(lambda s: f"`{s}`", column_names))
        query: str = f'INSERT INTO player({", ".join(escaped_column_names)}) VALUES({", ".join(bindings)})'
        try:
            with open(
                PLUGINS_DIR / 'ffe' / 'create_ffe.sql', encoding='utf-8'
            ) as f:
                self._create(f.read())
            with FfeAccessDatabase(local_mdb_file) as ffe_access_database:
                self.write = True
                with self:
                    player_count: int = 0
                    to_write: list[dict[str, Any]] = []
                    data: dict[str, Any]
                    for player_dict in ffe_access_database.read_player_dicts():
                        try:
                            data = {
                                field: player_dict[field]
                                if function is None
                                else function(player_dict[field])
                                for field, function in translations.items()
                            }
                            to_write.append(data)
                            player_count += 1
                            if player_count % 1000 == 0:
                                self.executemany(query, to_write)
                                print_interactive_info(
                                    _('{number} players written.').format(number=player_count),
                                    end='\r'
                                )
                                to_write.clear()
                            if player_count % 100_000 == 0:
                                self.commit()

                        except ValueError:
                            print_interactive_warning(
                                _(
                                    'Error reading the following row (player ignored): [{row}].'
                                ).format(row=player_dict)
                            )
                    if to_write:
                        self.executemany(query, to_write)
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
        self.create_indexes()
        return True

    def create_indexes(self) -> None:
        self.write = True
        with self:
            self.execute('CREATE INDEX `player_last_name` ON `player`(`last_name` COLLATE NOCASE)')
            self.execute('CREATE INDEX `player_first_name` ON `player`(`first_name` COLLATE NOCASE)')
            self.execute('CREATE INDEX `player_fide_id` ON `player`(`fide_id`)')
            self.execute('CREATE INDEX `player_ffe_licence` ON `player`(`ffe_licence_number` COLLATE NOCASE)')
            self.commit()

    @staticmethod
    def get_player_from_row(row: dict[str, Any]) -> Player | None:
        return Player(
            id=0,
            first_name=row['first_name'].title() if row['first_name'] else '',
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
            fide_id=int(row['fide_id']) if row['fide_id'] else None,
            federation=Federation(row['federation']),
            club=Club(row['club']),
            fixed=0,
            check_in=False,  # not taken into account when updating/creating/deleting the player
            pairings={},  # Pairings are read from Papi but not used
            tournament=None,
            plugin_data={
                PLUGIN_NAME: {
                    "ffe_id": row['ffe_id'],
                    "ffe_licence": PlayerFFELicence(row['ffe_licence']),
                    "ffe_licence_number": row['ffe_licence_number'],
                    "league": row['league'],
                }
            }
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
        order_conditions = ' OR '.join(['(last_name LIKE ?)', ] * len(tokens))
        params += [f'{token}%' for token in tokens]
        query: str = f'SELECT * FROM player WHERE {conditions} ORDER BY (CASE WHEN {order_conditions} THEN 0 ELSE 1 END), last_name'
        if limit:
            query += ' LIMIT ?'
            params += [limit, ]
        self.execute(query, tuple(params), )
        return (
            self.get_player_from_row(row)
            for row in self.fetchall()
        )

    def _get_player_by_id(
        self,
        field: str,
        id_: int,
    ) -> Player | None:
        self.execute(f'SELECT * FROM player WHERE {field} = ?', (id_, ))
        if row := self.fetchone():
            return self.get_player_from_row(row)
        else:
            return None

    def get_player_by_ffe_id(
        self,
        player_ffe_id: int,
    ) -> Player | None:
        return self._get_player_by_id('ffe_id', player_ffe_id)

    def get_player_by_fide_id(
        self,
        player_fide_id: int,
    ) -> Player | None:
        return self._get_player_by_id('fide_id', player_fide_id)

    def get_players_by_ffe_licence_number(self, player_ffe_licence_numbers: list[str]) -> list[Player]:
        query_array = ', '.join('?' for _ in player_ffe_licence_numbers)
        self.execute(
            f'SELECT * FROM player WHERE ffe_licence_number IN ({query_array})',
            tuple(player_ffe_licence_numbers),
        )
        return [
            self.get_player_from_row(row)
            for row in self.fetchall()
        ]
