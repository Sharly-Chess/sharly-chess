import os.path
from string import capwords
from xml.etree import ElementTree
import zipfile
from contextlib import suppress
from datetime import datetime
from logging import Logger
from pathlib import Path
from sqlite3 import OperationalError, IntegrityError
from time import time
from types import FunctionType
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
)
from common.papi_web_config import PapiWebConfig
from data.player import Player, Federation, Club
from data.util import (
    PlayerGender,
    PlayerTitle,
    TournamentRating,
    PlayerRatingType,
)
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

    def __init__(self, write: bool = False):
        super().__init__(TMP_DIR / f'fide.{PapiWebConfig.federation_database_ext}', write)

    def check(self) -> bool:
        """Check if the database exists and proposes to create it if not, or update it if too old,
        returns True if the database is available after the call, False otherwise."""
        yes_answer: str = _('Y *** THE LETTER TO ANSWER YES')
        if not self.exists():
            if (
                input_interactive(
                    _(
                        'The FIDE database [{file}] was not found, do you want to create it (Y/n)? '
                    ).format(file=self.file)
                ).upper()
                or yes_answer
            ) != yes_answer:
                return False
        else:
            age: int = int(time() - self.file.lstat().st_mtime)
            if age > 2 * 24 * 60 * 60:
                days: int = age // (24 * 60 * 60)
                if (
                    input_interactive(
                        _(
                            'The FIDE database [{file}] is obsolete ([{days}] days], do you want to update it (Y/n)? '
                        ).format(file=self.file, days=days)
                    ).upper()
                    or yes_answer
                ) != yes_answer:
                    return True
            else:
                return True
        return self.create()

    def create(self) -> bool:
        """Create the FIDE database, returns True if the database is available after the call, False otherwise."""
        print_interactive_info(_('Downloading the FIDE database...'))
        fide_database_url: str = (
            'https://ratings.fide.com/download/players_list_xml_legacy.zip'
        )
        local_zip_file: Path = TMP_DIR / os.path.basename(fide_database_url)
        with suppress(FileNotFoundError):
            local_zip_file.unlink()
        try:
            response: Response = get(fide_database_url, allow_redirects=True, timeout=5)
            if response.status_code != 200:
                print_interactive_error(
                    _('Could not download [{url}], error code [{code}].').format(
                        url=fide_database_url, code=response.status_code
                    )
                )
                return self.exists()
        except ConnectionError as ex:
            print_interactive_error(
                _('Could not download [{url}]: {ex}.').format(
                    url=fide_database_url, ex=ex
                )
            )
            return self.exists()
        local_zip_file.write_bytes(response.content)
        if not local_zip_file.exists():
            print_interactive_error(
                _('No data received from [{url}].').format(url=fide_database_url)
            )
            return True
        local_xml_file: Path = TMP_DIR / 'players_list_xml.xml'
        with suppress(FileNotFoundError):
            local_xml_file.unlink()
        with zipfile.ZipFile(local_zip_file, 'r') as zip_ref:
            zip_ref.extractall(TMP_DIR)
        if not local_xml_file.exists():
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
                PapiWebConfig.database_sql_path / 'create_fide.sql', encoding='utf-8'
            ) as f:
                self._create(f.read())
            fields: dict[str, tuple[str, FunctionType | None]] = {
                'fideid': ('fide_id', lambda s: int(s.strip())),
                'name': ('name', None),
                'country': ('federation', lambda s: s.upper()),
                'sex': ('gender', lambda s: PlayerGender.from_fide_value(s)),
                # exception for 1001710 Vreeken, Corry
                'title': (
                    'fide_title',
                    lambda s: PlayerTitle.from_fide_value('' if s == 'WH' else s),
                ),
                'rating': ('standard_rating', int),
                'rapid_rating': ('rapid_rating', int),
                'blitz_rating': ('blitz_rating', int),
                'birthday': ('year_of_birth', lambda s: int(s) if s else 0),
            }
            player_count: int = 0
            self.write = True
            with self:
                for event, elem in ElementTree.iterparse(local_xml_file, events=("start", "end")):
                    if event == 'start' and elem.tag == 'player':
                        data: dict[str, Any] = {}
                        
                    if event == 'end' and elem.tag == 'player':
                        query: str = f'INSERT INTO player({", ".join(data.keys())}) VALUES({", ".join(["?"] * len(data))})'
                        self.execute(query, tuple(data.values()))
                        player_count += 1
                        if player_count % 1000 == 0:
                            print_interactive_info(_('{number} players written.').format(number=player_count), end='\r')
                        
                    elif event == 'end' and elem.tag in fields:
                        (field_name, field_function) = fields[elem.tag]
                        data[field_name] = elem.text or ''
                        if field_function:
                            data[field_name] = field_function(data[field_name])
                        
                        if field_name == 'name':
                            if ',' in data['name']:
                                last_name, first_name = data['name'].split(',', maxsplit=1)
                                data['last_name'] = last_name.strip()
                                data['first_name'] = first_name.strip()
                            else:
                                data['last_name'] = data['name'].strip()
                                data['first_name'] = None
                            del data['name']
                    
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

    def read_federation_ids(self) -> Iterator[str]:
        self.execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from map(lambda row: row['federation'], self._fetchall())

    @staticmethod
    def get_player_from_row(row: dict[str, Any]) -> Player | None:
        return Player(
            id=0,
            first_name=capwords(row['first_name']) if row['first_name'] else '',
            last_name=row['last_name'].upper(),
            date_of_birth=datetime.strptime(
                f'{row["year_of_birth"] or 1900}-01-01', '%Y-%m-%d'
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
                TournamentRating.STANDARD:
                    PlayerRatingType.FIDE if row['standard_rating'] else PlayerRatingType.ESTIMATED,
                TournamentRating.RAPID:
                    PlayerRatingType.FIDE if row['rapid_rating'] else PlayerRatingType.ESTIMATED,
                TournamentRating.BLITZ:
                    PlayerRatingType.FIDE if row['blitz_rating'] else PlayerRatingType.ESTIMATED,
            },
            fide_id=row['fide_id'],
            federation=Federation(row['federation']),
            club=Club(''),
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
        self.execute(query, tuple(params), )
        return (
            self.get_player_from_row(row)
            for row in self._fetchall()
        )


    def get_player_by_fide_id(self, player_fide_id: int) -> Player | None:
        self.execute(f'SELECT * FROM player WHERE fide_id = ?', (player_fide_id, ))
        return self.get_player_from_row(self._fetchone())
