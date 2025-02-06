import os.path
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
from data.player import Player
from data.util import (
    PlayerGender,
    PlayerTitle,
    TournamentRating,
    PlayerRatingType,
    PlayerFFELicence,
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

    def __init__(self, basename: str = 'fide', write: bool = False):
        super().__init__(TMP_DIR / f'{basename}.{PapiWebConfig.event_ext}', write)

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
        tree = ElementTree.parse(local_xml_file)
        root = tree.getroot()
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
                'fide_id': ('fideid', lambda s: int(s.strip())),
                'name': ('name', None),
                'federation': ('country', lambda s: s.upper()),
                'gender': ('sex', lambda s: PlayerGender.from_fide_value(s)),
                # exception for 1001710 Vreeken, Corry
                'fide_title': (
                    'title',
                    lambda s: PlayerTitle.from_fide_value('' if s == 'WH' else s),
                ),
                'standard_rating': ('rating', int),
                'rapid_rating': ('rapid_rating', int),
                'blitz_rating': ('blitz_rating', int),
                'year_of_birth': ('birthday', lambda s: int(s) if s else 0),
            }
            players_number: int = 0
            self.write = True
            with self:
                for player_item in root.findall('./player'):
                    data: dict[str, Any] = {}
                    for field_name, (field_xml_tag, field_function) in fields.items():
                        data[field_name] = player_item.find(field_xml_tag).text or ''
                        if field_function:
                            data[field_name] = field_function(data[field_name])
                    if ',' in data['name']:
                        name_parts: list[str] = data['name'].split(',', maxsplit=2)
                        data['last_name'] = name_parts[0]
                        data['first_name'] = name_parts[1]
                        data['last_name'], data['first_name'] = data['name'].split(
                            ',', maxsplit=1
                        )
                    else:
                        data['last_name'] = data['name']
                        data['first_name'] = None
                    del data['name']
                    query: str = f'INSERT INTO player({", ".join(data.keys())}) VALUES({", ".join(["?"] * len(data))})'
                    self._execute(query, tuple(data.values()))
                    players_number += 1
                self.commit()
        except (OperationalError, IntegrityError) as ex:
            print_interactive_error(
                _('Error while creating the database: {ex}.').format(ex=ex)
            )
            self.file.unlink(missing_ok=True)
            if save:
                save.rename(self.file)
            return False
        save.unlink(missing_ok=True)
        print_interactive_success(
            _('{number} players written.').format(number=players_number)
        )
        return True

    def read_federation_ids(self) -> Iterator[str]:
        self._execute(
            'SELECT DISTINCT federation FROM `player` ORDER BY `federation`',
            (),
        )
        yield from map(lambda row: row['federation'], self._fetchall())

    def search_player(self, string: str) -> Iterator[Player]:
        tokens: list[str] = string.split(' ')
        str_fields: tuple[str, ...] = (
            'last_name',
            'first_name',
        )
        int_fields: tuple[str, ...] = ('fide_id',)
        token_conditions: dict[str, str] = {}
        for token in tokens:
            expressions = list(
                map(lambda field: f"({field} LIKE '%{token}%')", str_fields)
            )
            int_value: int
            with suppress(ValueError):
                int_value = int(token.strip())
                expressions += list(
                    map(lambda field: f'({field} = {int_value})', int_fields)
                )
            token_conditions[token] = ' OR '.join(expressions)
        conditions: str = ' AND '.join(
            map(lambda condition: f'({condition})', token_conditions.values())
        )
        self._execute(f'SELECT * FROM player WHERE {conditions}')
        return (
            Player(
                id=0,
                first_name=row['first_name'],
                last_name=row['last_name'],
                date_of_birth=datetime.strptime(
                    f'{row["year_of_birth"]}-01-01', '%Y-%m-%d'
                ).date()
                if row['year_of_birth']
                else None,
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
                    TournamentRating.STANDARD: PlayerRatingType.FIDE
                    if row['standard_rating']
                    else PlayerRatingType.ESTIMATED,
                    TournamentRating.RAPID: PlayerRatingType.FIDE
                    if row['rapid_rating']
                    else PlayerRatingType.ESTIMATED,
                    TournamentRating.BLITZ: PlayerRatingType.FIDE
                    if row['blitz_rating']
                    else PlayerRatingType.ESTIMATED,
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
            )
            for row in self._fetchall()
        )
