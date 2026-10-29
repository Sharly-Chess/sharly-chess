import asyncio
import itertools
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, date
from logging import Logger
from pathlib import Path
from typing import Any, ClassVar


from common.exception import SharlyChessException
from common.i18n import _
from common.i18n.utils import unicode_normalize
from common.logger import get_logger
from common.network import NetworkMonitor
from utils.types import RatingOrigin
from database.sql_server.sql_server import SqlServer, SqlServerCredentials
from database.sqlite.event.event_store import StoredPlayer
from plugins import PLUGINS_DIR
from plugins.ffe import PLUGIN_NAME, NATIONAL_SOURCE_ID
from plugins.ffe.papi_mappers import (
    PapiPlayerTitle,
    PapiPlayerGender,
    PapiPlayerRatingType,
    PapiPlayerFFELicence,
)
from plugins.ffe.utils import (
    FfePlayerPluginData,
    PlayerFFELicence,
    FFE_ABBREVIATED_NAME_MIN_LENGTH,
    FFE_ABBREVIATION_MIN_LENGTH,
    FFE_NAME_LENGTH,
    FfeNameKey,
    ffe_database_name_keys,
    ffe_name_key_matches,
    get_data,
    ffe_list_ratings,
)
from utils.enum import Cadence, PlayerRatingType

logger: Logger = get_logger()

# The words, federation and filters of a search
_SearchKey = tuple[tuple[str, ...], str, str]


@dataclass(frozen=True)
class _NameSearch:
    key: _SearchKey
    tokens: list[str]
    # Every word matches the player
    condition: str
    params: list[Any]
    # The number of points of the player, the lower the better
    rank: str
    rank_params: list[str]

    @property
    def order_by(self) -> str:
        return f'{self.rank}, joueur.Nom, joueur.Prenom, joueur.Ref'


class FFESqlServer(SqlServer):
    TIMEOUT = 10
    CREDENTIALS_FILE: Path = PLUGINS_DIR / 'ffe' / '.sql-server-credentials'

    def __init__(self) -> None:
        super().__init__(self.CREDENTIALS_FILE, timeout=self.TIMEOUT)
        if not NetworkMonitor.connected():
            error: str = _('No internet connection')
            logger.error(error)
            raise SharlyChessException(error)

    @classmethod
    def dump_credentials(
        cls,
        host: str,
        user: str,
        password: str,
        database: str,
    ) -> None:
        SqlServerCredentials.dump(
            cls.CREDENTIALS_FILE,
            host,
            user,
            password,
            database,
        )

    PLAYER_FIELDS: tuple[str, ...] = (
        'Ref',
        'NrFFE',
        'Nom',
        'Prenom',
        'Sexe',
        'NeLe',
        'Cat',
        # not allowed: 'EC', 'Adresse', 'CP', 'TelDom', 'TelBur', 'TelPort', 'Fax', 'EMail',
        'Federation',
        'ClubRef',
        # not allowed: 'OldClubRef', 'Mute',
        'Elo',
        # not allowed: 'Elo10', 'Fide10', 'Elo01', 'Fide01',
        # not needed 'Elo03',
        'Fide03',  # RapideFide
        'Elo06',  # Blitz
        'Fide06',  # BlitzFide
        'Rapide',
        # not allowed: 'Perf', 'NbrParties', 'FideNbrParties',
        'Fide',
        'FideCode',
        'FideTitre',
        'AffType',
        # not needed 'Actif',
        # not allowed: 'BordereauRef', 'OldAffType', 'OldBordereauRef',
        # not allowed: 'Suspendu', 'MuteState', 'AJoue',
        # not allowed: 'Revue', 'RevueDu', 'RevueDuParClub', 'RevueDebut', 'NewsLetter',
        # not allowed: 'Password', 'MaJ',
    )

    CLUB_FIELDS: tuple[str, ...] = (
        # unused 'Ref',
        # unused 'NrFFE',
        'Nom',
        # not allowed: 'Intitule',
        'Commune',
        # not allowed: 'CommuneRef', 'ComiteRef',
        'Ligue',
        # not allowed: 'Adresse', 'CP', 'SalleAdresse', 'SalleCP', 'Latitude', 'Longitude',
        # not allowed: 'Tel', 'Fax', 'EMail', 'URL',
        # not needed 'Actif',
        # not allowed: 'Ouverture', 'President', 'Secretaire', 'Tresorier', 'Technique', 'Jeune',
        # not allowed: 'WebAdmin', 'WebAdminEMail', 'WebAutorisation',
        # not allowed: 'Repport', 'Nouveau', 'Electeur', 'Situation', 'PrefNr', 'PrefDate', 'Prefecture',
        # not allowed: 'NbrAffPrecedent', 'NbrBPrecedent', 'NbrAffA', 'NbrAffB', 'NbrJourOuvre',
        # not allowed: 'DivisionAdulte', 'DivisionJeune', 'DivisionFeminine', 'Label', 'Imprimer',
        # not allowed: 'Edoc', 'Handicape', 'QPV', 'Palmares', 'Login', 'Password', 'MaJ',
    )

    @staticmethod
    def _read_name(name: str) -> str:
        # A few names hold their apostrophes doubled
        return name.replace("''", "'").rstrip()

    @staticmethod
    def _held_names(name: str) -> list[str]:
        """The ways the server may hold the name."""
        if "'" in name:
            return [name, name.replace("'", "''")]
        return [name]

    @staticmethod
    def _get_stored_player_from_row(row: dict[str, Any]) -> StoredPlayer:
        date_of_birth: date | None = None
        dob = row['NeLe']
        if isinstance(dob, datetime):
            date_of_birth = dob.date()
        elif isinstance(dob, date):
            date_of_birth = dob

        fide_title = PapiPlayerTitle.get_core_object(row['FideTitre'] or '')
        return StoredPlayer(
            id=None,
            first_name=FFESqlServer._read_name(row['Prenom'] or ''),
            last_name=FFESqlServer._read_name(row['Nom']),
            date_of_birth=date_of_birth,
            gender=PapiPlayerGender.get_core_object(row['Sexe'] or ''),
            title=fide_title.open_value,
            women_title=fide_title.women_value,
            ratings=ffe_list_ratings(
                {
                    Cadence.STANDARD: (
                        row['Elo'],
                        PapiPlayerRatingType.get_core_object(row['Fide']),
                    ),
                    Cadence.RAPID: (
                        row['Rapide'],
                        PapiPlayerRatingType.get_core_object(row['Fide03']),
                    ),
                    Cadence.BLITZ: (
                        row['Elo06'],
                        PapiPlayerRatingType.get_core_object(row['Fide06']),
                    ),
                },
                RatingOrigin(NATIONAL_SOURCE_ID, date.today().isoformat(), online=True),
            ),
            fide_id=int((row['FideCode'] or '').strip("' ") or 0) or None,
            national_id=row['NrFFE'] or None,
            national_source=NATIONAL_SOURCE_ID,
            federation=row['Federation'],
            club=row['ClubNom'] if row['ClubNom'] else '',
            plugin_data={
                PLUGIN_NAME: FfePlayerPluginData(
                    ffe_licence=PapiPlayerFFELicence.get_core_object(
                        row['AffType'] or '', row['NrFFE']
                    ),
                    league=row['ClubLigue'],
                    ffe_id=row['Ref'],
                ).to_stored_value()
            },
        )

    def get_player_fields(self) -> list[str]:
        return [f'joueur.{f} AS {f}' for f in self.PLAYER_FIELDS]

    def get_club_fields(self) -> list[str]:
        return [f'club.{f} AS Club{f}' for f in self.CLUB_FIELDS]

    RATING_TYPE_CONDITION: str = f'joueur.Fide IN ({", ".join(f"'{s}'" for s in [PlayerRatingType.ESTIMATED, PlayerRatingType.NATIONAL, PlayerRatingType.FIDE])})'

    # Strings are sent as NVARCHAR, which the server compares to the VARCHAR
    # columns by converting them row by row instead of seeking their indexes
    VARCHAR: str = 'CAST(%s AS VARCHAR(100))'

    @classmethod
    def varchars(cls, count: int) -> str:
        return ', '.join([cls.VARCHAR] * count)

    @classmethod
    def _cut_name_matches(cls, start: str, min_tail_length: int) -> str:
        tails: list[str] = [
            f"RIGHT({start}, NULLIF(CHARINDEX('{separator}', REVERSE({start})), 0) - 1)"
            for separator in (' ', '-')
        ]
        matches: list[str] = [
            f"(LEN({part}) >= {min_tail_length} AND {cls.VARCHAR} LIKE {part} + '%%')"
            for part in (*tails, start)
        ]
        return f'CASE WHEN {" OR ".join(matches)} THEN 1 END'

    @classmethod
    def _cut_name_condition(
        cls, field: str, min_tail_length: int, at_length: bool, abbreviated: bool
    ) -> str:
        """The condition under which a word, given as each of its parameters,
        runs past the end of a name the server cut, as `ffe_cut_name_matches()`
        tells."""
        # The guards spare the other names the cost of the matches
        branches: list[str] = []
        if at_length:
            branches.append(
                f'WHEN LEN({field}) = {FFE_NAME_LENGTH} '
                f'THEN {cls._cut_name_matches(field, min_tail_length)}'
            )
        if abbreviated:
            abbreviation = f'LEFT({field}, LEN({field}) - 1)'
            branches.append(
                f"WHEN RIGHT({field}, 1) = '.' "
                f'THEN {cls._cut_name_matches(abbreviation, FFE_ABBREVIATION_MIN_LENGTH)}'
            )
        return f'(CASE {" ".join(branches)} END = 1)'

    @staticmethod
    def string_matches_fide_id(string: str) -> int | None:
        return int(string) if string.isdecimal() else None

    @staticmethod
    def remote_fide_id_format_1(fide_id: int) -> str:
        return str(fide_id).rjust(8, '0').ljust(10, ' ')

    @staticmethod
    def remote_fide_id_format_2(fide_id: int) -> str:
        return f"'{fide_id}'"

    async def search_player(
        self,
        string: str,
        federation: str,
        page: int = 0,
        limit: int | None = None,
        filters: dict | None = None,
    ) -> list[StoredPlayer]:
        """Searches the SQL server for the given tokens, raises SharlyChessException on error."""
        # NOTE(Amaras): Quicken search if the string looks like a complete FFE
        # licence number, so that it skips a more complex request
        string = string.upper().strip()
        if not filters:
            if PlayerFFELicence.validate(string):
                return await self.get_stored_players_by_licence_numbers([string])
            if fide_id := self.string_matches_fide_id(string):
                return await self.get_players_by_fide_id([fide_id])
        search = self._name_search(string, federation, filters)
        if not limit:
            return await self._scan(search)
        offset = page * limit
        # The whole search scans the 1.3 million players, which takes about a
        # second. Only a word that starts the last name ranks 0, the others
        # rank 1 or more: the players ranked below the number of words, which
        # come first, have their last name started by some word and are found
        # in about 100 ms by seeking the (Nom, Prenom) index. When they fill
        # the page, the scan running alongside is cancelled. The scan is read
        # at the same offset, leaving them out of it would cost its conditions
        # on every player.
        first_players_count = self._first_players_count(search)
        if first_players_count is not None and offset + limit > first_players_count:
            # Looking for first players that cannot fill the page would slow
            # the scan down by about a third
            return await self._scan(search, offset, limit)
        scan_server = type(self)()
        scan = asyncio.create_task(
            scan_server._scan_in_own_connection(search, offset, limit)
        )
        self._background_scans.add(scan)
        scan.add_done_callback(self._end_background_scan)
        try:
            first_players = await self._get_first_players(search, offset, limit)
        except BaseException:
            scan_server.cancel()
            raise
        if len(first_players) == limit:
            scan_server.cancel()
            return first_players
        return await scan

    async def search_first_players(
        self,
        string: str,
        federation: str,
        page: int,
        limit: int,
        filters: dict | None = None,
    ) -> list[StoredPlayer] | None:
        """The first players of the page of `search_player()`, found without
        its scan, or None for the searches it does not split. The page holds
        others when they do not fill it."""
        string = string.upper().strip()
        if not filters and (
            PlayerFFELicence.validate(string) or self.string_matches_fide_id(string)
        ):
            return None
        search = self._name_search(string, federation, filters)
        offset = page * limit
        first_players_count = self._first_players_count(search)
        if first_players_count is not None and offset >= first_players_count:
            return []
        return await self._get_first_players(search, offset, limit)

    async def _scan(
        self, search: _NameSearch, offset: int | None = None, limit: int | None = None
    ) -> list[StoredPlayer]:
        # A short token matches far more players than a long one, a plan
        # cached for one of them can be many times slower for the other, so
        # each search recompiles it
        return await self._get_stored_players_by_condition(
            search.condition,
            search.params + search.rank_params,
            order_by=search.order_by,
            offset=offset,
            limit=limit,
            recompile=True,
        )

    async def _scan_in_own_connection(
        self, search: _NameSearch, offset: int, limit: int
    ) -> list[StoredPlayer]:
        async with self:
            if self.cancelled:
                return []
            return await self._scan(search, offset, limit)

    async def _get_first_players(
        self, search: _NameSearch, offset: int, limit: int
    ) -> list[StoredPlayer]:
        v = self.VARCHAR
        starts = ' OR '.join([f'(joueur.Nom LIKE {v})'] * len(search.tokens))
        first_players = await self._get_stored_players_by_condition(
            f'{search.condition} AND ({starts}) AND {search.rank} < {len(search.tokens)}',
            search.params
            + [f'{token}%' for token in search.tokens]
            + search.rank_params * 2,
            order_by=search.order_by,
            offset=offset,
            limit=limit,
            recompile=True,
        )
        if len(first_players) < limit:
            # The number of first players, or more than it when the page
            # holds none of them
            counts = self._first_players_counts
            counts[search.key] = offset + len(first_players)
            while len(counts) > self.FIRST_PLAYERS_COUNTS_SIZE:
                counts.popitem(last=False)
        return first_players

    # The counts are only used to skip the first players, a stale one only
    # costs time
    FIRST_PLAYERS_COUNTS_SIZE = 100
    _first_players_counts: ClassVar[OrderedDict[_SearchKey, int]] = OrderedDict()

    @classmethod
    def _first_players_count(cls, search: _NameSearch) -> int | None:
        count = cls._first_players_counts.get(search.key)
        if count is not None:
            cls._first_players_counts.move_to_end(search.key)
        return count

    # The scans keep running until the server answers their cancellation
    _background_scans: ClassVar[set[asyncio.Task[list[StoredPlayer]]]] = set()

    @classmethod
    def _end_background_scan(cls, scan: asyncio.Task[list[StoredPlayer]]) -> None:
        cls._background_scans.discard(scan)
        if not scan.cancelled():
            scan.exception()

    def _name_search(
        self, string: str, federation: str, filters: dict | None
    ) -> _NameSearch:
        tokens: list[str] = [
            unicode_normalize(token) for token in re.split(r'\s+', string)
        ]
        name_fields: tuple[str, ...] = ('joueur.Nom', 'joueur.Prenom')
        # The other words of the search tell apart the players a single letter
        # left of a cut word would not
        min_tail_length: int = 1 if len(tokens) > 1 else 2
        # Only a search longer than the names can run past the end of a name
        # cut at their length or abbreviated, the cost of the matches is not
        # paid otherwise
        search_length: int = len(' '.join(tokens))
        at_length: bool = search_length > FFE_NAME_LENGTH
        abbreviated: bool = search_length >= FFE_ABBREVIATED_NAME_MIN_LENGTH
        conditions, params = self._process_filters(filters or {})
        for token in tokens:
            token_expressions: list[str] = []
            token_params: list[str | int] = []
            for name in self._held_names(token):
                for field in name_fields:
                    token_expressions.append(f'({field} LIKE {self.VARCHAR})')
                    token_params.append(f'%{name}%')
            # A word no longer than the shortest abbreviation tail matches it
            # as a whole
            if at_length or (abbreviated and len(token) > FFE_ABBREVIATION_MIN_LENGTH):
                for field in name_fields:
                    cut_name_condition = self._cut_name_condition(
                        field, min_tail_length, at_length, abbreviated
                    )
                    token_expressions.append(cut_name_condition)
                    token_params += [token] * cut_name_condition.count('%s')
            token_expressions.append(f'(joueur.NrFFE LIKE {self.VARCHAR})')
            token_params.append(token)
            with suppress(ValueError):
                int_value = int(token.strip())
                token_expressions.append(f'(joueur.FideCode IN ({self.varchars(2)}))')
                token_params += [
                    self.remote_fide_id_format_1(int_value),
                    self.remote_fide_id_format_2(int_value),
                ]
            conditions += [
                ' OR '.join(token_expressions),
            ]
            params += token_params
        condition: str = ' AND '.join(f'({c})' for c in conditions)

        # We build one CASE block that sorts best → worst
        order_clauses = []
        rank_params: list[str] = []
        v = self.VARCHAR
        for token in tokens:
            order_clauses.append(f"""
                CASE
                    WHEN joueur.Nom LIKE {v} AND joueur.Federation = {v} THEN 0
                    WHEN joueur.Prenom LIKE {v} AND joueur.Federation = {v} THEN 1
                    WHEN joueur.Nom LIKE {v} OR joueur.Prenom LIKE {v} THEN 2
                    WHEN joueur.Federation = {v} THEN 3
                    ELSE 4
                END
            """)

            # Params for this token in the same order
            rank_params += [
                f'{token}%',
                federation,
                f'{token}%',
                federation,
                f'{token}%',
                f'{token}%',
                federation,
            ]

        return _NameSearch(
            key=(tuple(tokens), federation, repr(sorted((filters or {}).items()))),
            tokens=tokens,
            condition=condition,
            params=params,
            rank=' + '.join(order_clauses),
            rank_params=rank_params,
        )

    async def _get_stored_player_by_condition(
        self, condition: str, params: list
    ) -> StoredPlayer | None:
        query: str = (
            f'SELECT {", ".join(self.get_player_fields() + self.get_club_fields())} '
            f'FROM joueur LEFT JOIN club on joueur.ClubRef = club.Ref '
            f'WHERE {condition} AND {self.RATING_TYPE_CONDITION}'
        )
        await self.execute(query, tuple(params))
        if row := await self.fetchone():
            return self._get_stored_player_from_row(row)
        return None

    async def _get_stored_players_by_condition(
        self,
        condition: str,
        params: list,
        order_by: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        recompile: bool = False,
    ) -> list[StoredPlayer]:
        query: str = (
            f'SELECT {", ".join(self.get_player_fields() + self.get_club_fields())} '
            f'FROM joueur LEFT JOIN club on joueur.ClubRef = club.Ref '
            f'WHERE ({condition}) AND {self.RATING_TYPE_CONDITION}'
        )
        if order_by:
            query += f' ORDER BY {order_by}'
        if offset is not None:
            query += ' OFFSET %s ROWS'
            params.append(offset)
            if limit:
                query += ' FETCH NEXT %s ROWS ONLY'
                params.append(limit)
        if recompile:
            query += ' OPTION (RECOMPILE)'
        await self.execute(query, tuple(params))
        return [self._get_stored_player_from_row(row) async for row in self.fetchall()]

    async def get_stored_player_by_ffe_id(
        self,
        player_ffe_id: int,
    ) -> StoredPlayer | None:
        return await self._get_stored_player_by_condition(
            'joueur.Ref = %s', [player_ffe_id]
        )

    async def get_stored_player_by_fide_id(
        self,
        player_fide_id: int,
    ) -> StoredPlayer | None:
        return await self._get_stored_player_by_condition(
            f'joueur.FideCode IN ({self.varchars(2)})',
            [
                self.remote_fide_id_format_1(player_fide_id),
                self.remote_fide_id_format_2(player_fide_id),
            ],
        )

    async def get_stored_players_by_licence_numbers(
        self, licence_numbers: list[str]
    ) -> list[StoredPlayer]:
        return await self._get_stored_players_by_condition(
            f'joueur.NrFFE IN ({self.varchars(len(licence_numbers))})',
            licence_numbers,
        )

    async def get_stored_players_by_fide_ids(
        self, fide_ids: list[int]
    ) -> list[StoredPlayer]:
        return await self._get_stored_players_by_condition(
            f'joueur.FideCode IN ({self.varchars(len(fide_ids) * 2)})',
            list(
                itertools.chain.from_iterable(
                    [
                        self.remote_fide_id_format_1(fide_id),
                        self.remote_fide_id_format_2(fide_id),
                    ]
                    for fide_id in fide_ids
                )
            ),
        )

    # Pages of 50 names take about 50 ms each, from about 150 the server
    # scans the whole table instead and a page takes more than 10 seconds
    NAME_KEYS_PAGE_SIZE = 50

    async def _get_stored_players_by_name_keys_page(
        self, name_keys: list[FfeNameKey]
    ) -> list[StoredPlayer]:
        names = list(
            {
                held_names
                for name_key in name_keys
                for held_names in itertools.product(
                    self._held_names(name_key[0]), self._held_names(name_key[1])
                )
            }
        )
        name_condition = (
            f'(joueur.Nom = {self.VARCHAR} AND joueur.Prenom = {self.VARCHAR})'
        )
        stored_players = await self._get_stored_players_by_condition(
            ' OR '.join([name_condition] * len(names)),
            list(itertools.chain.from_iterable(names)),
        )
        # DOB formatting is too expensive in SQL Server, we have to do the
        # matching only on the name, and match the DOB in python
        keys = set(name_keys)
        return [
            stored_player
            for stored_player in stored_players
            if keys & ffe_database_name_keys(stored_player)
        ]

    async def _get_stored_players_by_abbreviated_name_keys_page(
        self, name_keys: list[FfeNameKey]
    ) -> list[StoredPlayer]:
        """The players whose last or first name the server abbreviated with a
        dot, found by the start of the last name the abbreviation keeps."""
        conditions: list[str] = []
        params: list[str] = []
        for last_name in {name_key[0] for name_key in name_keys}:
            conditions.append(
                f"(joueur.Nom = {self.VARCHAR} AND RIGHT(joueur.Prenom, 1) = '.')"
            )
            params.append(last_name)
            if len(last_name) > FFE_ABBREVIATION_MIN_LENGTH:
                conditions.append(
                    f"(joueur.Nom LIKE {self.VARCHAR} AND RIGHT(joueur.Nom, 1) = '.')"
                )
                params.append(f'{last_name[:FFE_ABBREVIATION_MIN_LENGTH]}%')
        stored_players = await self._get_stored_players_by_condition(
            ' OR '.join(conditions), params
        )
        return [
            stored_player
            for stored_player in stored_players
            if any(ffe_name_key_matches(key, stored_player) for key in name_keys)
        ]

    # Each key brings two conditions
    ABBREVIATED_NAME_KEYS_PAGE_SIZE = NAME_KEYS_PAGE_SIZE // 2

    async def get_stored_players_by_name_keys(
        self, name_keys: list[FfeNameKey]
    ) -> list[StoredPlayer]:
        # A player matching the keys of several pages is found by each of them
        stored_players: dict[int, StoredPlayer] = {}

        async def add_pages(
            read_page: Callable[[list[FfeNameKey]], Awaitable[list[StoredPlayer]]],
            keys: list[FfeNameKey],
            page_size: int,
        ) -> None:
            while keys:
                for stored_player in await read_page(keys[:page_size]):
                    stored_players[get_data(stored_player.plugin_data, 'ffe_id')] = (
                        stored_player
                    )
                keys = keys[page_size:]

        await add_pages(
            self._get_stored_players_by_name_keys_page,
            name_keys,
            self.NAME_KEYS_PAGE_SIZE,
        )
        found_keys = {
            key
            for stored_player in stored_players.values()
            for key in ffe_database_name_keys(stored_player)
        }
        await add_pages(
            self._get_stored_players_by_abbreviated_name_keys_page,
            [name_key for name_key in name_keys if name_key not in found_keys],
            self.ABBREVIATED_NAME_KEYS_PAGE_SIZE,
        )
        return list(stored_players.values())

    async def get_players_by_fide_id(
        self,
        player_fide_ids: list[int],
    ) -> list[StoredPlayer]:
        params: list[str] = []
        for player_fide_id in player_fide_ids:
            params += [
                self.remote_fide_id_format_1(player_fide_id),
                self.remote_fide_id_format_2(player_fide_id),
            ]
        return await self._get_stored_players_by_condition(
            f'joueur.FideCode IN ({self.varchars(2 * len(player_fide_ids))})',
            params,
        )

    @classmethod
    def _process_filters(cls, filters: dict) -> tuple[list[str], list[Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if 'ffe_licence_filter' in filters:
            if filters['ffe_licence_filter'] == 'B':
                conditions.append(
                    "(joueur.AffType IN ('B', 'A') OR joueur.Federation !='fra')"
                )
            elif filters['ffe_licence_filter'] == 'A':
                conditions.append("(joueur.AffType='A' OR joueur.Federation !='fra')")
        if 'federation_filter' in filters:
            conditions.append(f'joueur.Federation = {cls.VARCHAR}')
            params.append(filters['federation_filter'])
        if 'gender_filter' in filters:
            conditions.append(f'joueur.Sexe = {cls.VARCHAR}')
            params.append(filters['gender_filter'])
        if 'ffe_league_filter' in filters:
            conditions.append(f'club.Ligue = {cls.VARCHAR}')
            params.append(filters['ffe_league_filter'])
        if 'club_filter' in filters:
            club: str = filters['club_filter']
            conditions.append(f'club.Nom LIKE {cls.VARCHAR}')
            params.append(f'%{club}%')
        if filters.get('year_of_birth_filter'):
            age_conditions = []
            for min_year, max_year in filters['year_of_birth_filter']:
                match min_year, max_year:
                    case None, None:
                        continue
                    case None, _:
                        age_conditions.append('joueur.NeLe < %s')
                        params.append(date(max_year + 1, 1, 1))
                    case _, None:
                        age_conditions.append('joueur.NeLe >= %s')
                        params.append(date(min_year, 1, 1))
                    case _, _:
                        age_conditions.append('joueur.NeLe >= %s AND joueur.NeLe < %s')
                        params += [date(min_year, 1, 1), date(max_year + 1, 1, 1)]
            if age_conditions:
                conditions.append(f'({" OR ".join(age_conditions)})')
        return conditions, params
