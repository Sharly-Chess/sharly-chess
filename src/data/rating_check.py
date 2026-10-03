"""The consistency check of the players' ratings against the installed rating
lists (TEC Manual 3.9.5.11.e–h, VCL Q133–144): which players the lists would
now give a different rating, reported for the arbiter to apply or not."""

import copy
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from common.i18n import _
from data.input_output.data_source import installed_copies_only, reliable_k_factor
from data.player import Player
from data.rating_sequences import (
    RatingSequence,
    describe_rating,
    official_rating,
    resolve_rating,
)
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.fide.fide_database import FideDatabase
from utils.enum import PlayerRatingType, RatingPreference, Cadence
from utils.types import PlayerRating, PlayerRatingAndType

if TYPE_CHECKING:
    from database.sqlite.local_source_database import LocalSourceDatabase
    from data.event import Event
    from data.input_output.data_source import DataSource
    from data.tournament_period import TournamentPeriod

LIST_TYPES = (PlayerRatingType.FIDE, PlayerRatingType.NATIONAL)


def _stored_ratings(
    stored_player: StoredPlayer,
) -> dict[Cadence, PlayerRating]:
    return {
        tournament_rating: PlayerRating.from_stored_value(
            stored_player.ratings.get(tournament_rating.value, {})
        )
        for tournament_rating in Cadence
    }


def _set_listed(
    ratings: dict[Cadence, PlayerRating],
    rating_type: PlayerRatingType,
    listed: dict[Cadence, PlayerRating],
    source: str,
) -> None:
    """Replace the values of a kind with those a list gives, sources
    included and corrections dropped. A value the list does not give is
    only cleared when that list was its source."""
    for tournament_rating in Cadence:
        rating = ratings[tournament_rating]
        listed_rating = listed[tournament_rating]
        value = listed_rating.get_type_value(rating_type)
        origin = rating.origins.get(rating_type)
        if value is None and (origin is None or origin.source != source):
            continue
        rating.set_value_from_type(
            value, rating_type, listed_rating.origins.get(rating_type)
        )


@dataclass
class RatingCheckRow:
    """A player whose ratings the lists hold differently.

    ``listed`` are the player's ratings as the lists give them now;
    ``kept`` the same with the corrections the arbiter made to them kept,
    which is what is applied unless the arbiter's own value is at stake
    (see `arbiter_value`)."""

    player: Player
    period: 'TournamentPeriod | None'
    cadence: Cadence
    preference: RatingPreference
    sequence: RatingSequence
    current: dict[Cadence, PlayerRating]
    listed: dict[Cadence, PlayerRating]
    kept: dict[Cadence, PlayerRating]

    def _resolve(self, ratings: dict[Cadence, PlayerRating]) -> PlayerRatingAndType:
        return resolve_rating(
            ratings,
            self.cadence,
            self.preference,
            self.sequence,
            self.player.event.is_single_national_rating,
            lambda: None,
        )

    @cached_property
    def current_rating(self) -> PlayerRatingAndType:
        return self._resolve(self.current)

    @cached_property
    def current_official(self) -> PlayerRatingAndType | None:
        return official_rating(self.current, self.cadence)

    @cached_property
    def arbiter_value(self) -> bool:
        """Whether the player holds a value the arbiter set: a correction
        of a list value the list does not give, or a value typed for the
        tournament rating. Such a player is listed apart and keeps that
        value unless the arbiter chooses the list."""
        for tournament_rating in Cadence:
            current = self.current[tournament_rating]
            listed = self.listed[tournament_rating]
            for rating_type in LIST_TYPES:
                if current.is_overridden(rating_type) and current.get_type_value(
                    rating_type
                ) != listed.get_type_value(rating_type):
                    return True
        return (
            self.current_rating.type == PlayerRatingType.ESTIMATED
            and not self.current_rating.prescribed
            and self.current_rating.value > 0
        )

    @cached_property
    def proposed(self) -> dict[Cadence, PlayerRating]:
        return self.listed if self.arbiter_value else self.kept

    @property
    def current_description(self) -> str:
        return describe_rating(self.current_rating)

    @property
    def proposed_description(self) -> str:
        return describe_rating(self.proposed_rating)

    @cached_property
    def proposed_rating(self) -> PlayerRatingAndType:
        return self._resolve(self.proposed)

    @cached_property
    def proposed_official(self) -> PlayerRatingAndType | None:
        return official_rating(self.proposed, self.cadence)

    @property
    def changes_rating(self) -> bool:
        """Whether applying the lists changes a rating the tournament or
        FIDE uses, rather than only where it comes from."""

        def key(rating: PlayerRatingAndType | None) -> tuple[int, int] | None:
            return None if rating is None else (rating.value, rating.type)

        return key(self.current_rating) != key(self.proposed_rating) or key(
            self.current_official
        ) != key(self.proposed_official)

    @property
    def changes_anything(self) -> bool:
        return any(
            self.current[tournament_rating].stored_value
            != self.proposed[tournament_rating].stored_value
            for tournament_rating in Cadence
        )

    def apply(self) -> Player:
        self.player.update_ratings(copy.deepcopy(self.proposed), self.period)
        return self.player


@dataclass
class RatingCheck:
    """The outcome of a consistency check of some players."""

    rows: list[RatingCheckRow]
    not_found: list[Player]
    lists: list['DataSource']

    @property
    def attention_count(self) -> int:
        return len(self.changes) + sum(
            1 for row in self.arbiter_values if row.changes_rating
        )

    @property
    def changes(self) -> list[RatingCheckRow]:
        return [
            row for row in self.rows if row.changes_rating and not row.arbiter_value
        ]

    @property
    def arbiter_values(self) -> list[RatingCheckRow]:
        """Players holding a value the arbiter set, which the lists would
        replace or which no list gives (TEC Manual 3.9.5.11.c)."""
        return [row for row in self.rows if row.arbiter_value]

    @property
    def source_updates(self) -> list[RatingCheckRow]:
        """Players whose ratings only change source, snapshot or
        coefficient: nothing in the pairings or the standings moves, so
        they are applied without being put to the arbiter."""
        return [
            row for row in self.rows if not row.changes_rating and not row.arbiter_value
        ]

    def apply(self, player_ids: set[int]) -> list[Player]:
        """Apply the changes chosen, and the source updates."""
        return [
            row.apply()
            for row in self.rows
            if row.player.id in player_ids
            or (not row.changes_rating and not row.arbiter_value)
        ]


def _recorded_period(player: Player) -> 'TournamentPeriod | None':
    tournament = player.optional_single_tournament
    return None if tournament is None else tournament.current_period


def _fide_list(players: list[Player]) -> dict[int, StoredPlayer] | None:
    database = FideDatabase()
    if not database.exists():
        return None
    fide_ids = [player.fide_id for player in players if player.fide_id]
    if not fide_ids:
        return {}
    with database:
        return {
            stored_player.fide_id: stored_player
            for stored_player in database.get_stored_players_by_fide_id(fide_ids)
            if stored_player.fide_id
        }


def _k_factors(
    player: Player,
    current: dict[Cadence, PlayerRating],
    listed: dict[Cadence, PlayerRating],
    in_rating_period: bool,
) -> None:
    """The coefficients (k) of the FIDE list inside its rating period, and
    outside of it what remains trustworthy of them, the player keeping
    their own where nothing does."""
    for tournament_rating in Cadence:
        rating = listed[tournament_rating]
        if in_rating_period:
            continue
        k_factor = reliable_k_factor(rating.k_factor, rating.fide, player.year_of_birth)
        rating.k_factor = (
            k_factor if k_factor is not None else current[tournament_rating].k_factor
        )


@dataclass
class ListStatus:
    """The state of a rating list the tournaments' sequences name, as the
    ratings update shows it."""

    name: str
    message: str
    warning: bool


def list_statuses(event: 'Event', players: list[Player]) -> list[ListStatus]:
    """The state of each list the rating lists of the players' tournaments
    name: installed (and how current), read online, or missing, and the
    cadences it does not publish."""
    from data.input_output import DataSourceManager
    from data.input_output.data_source import FideDataSource, LocalDataSource
    from data.rating_sequences import RatingListFamily

    manager = DataSourceManager()
    sequences = {
        event.rating_resolution(player.optional_single_tournament)[2]
        for player in players
    } or {event.rating_resolution(None)[2]}
    named = {rating_list for sequence in sequences for rating_list in sequence}

    def cadences(family: RatingListFamily) -> list[Cadence]:
        return sorted(
            {
                rating_list.cadence
                for rating_list in named
                if rating_list.family == family
            }
        )

    def name(list_name: str, list_cadences: list[Cadence]) -> str:
        return '{list} ({cadences})'.format(
            list=list_name,
            cadences=', '.join(cadence.short_name.lower() for cadence in list_cadences),
        )

    statuses: list[ListStatus] = []
    if fide_cadences := cadences(RatingListFamily.FIDE):
        fide = manager.get_object(FideDataSource.static_id())
        message, warning = (
            fide.info_or_warning_message
            if fide.is_available
            else (_('Not installed'), True)
        )
        statuses.append(ListStatus(name(_('FIDE'), fide_cadences), message, warning))
    if national_cadences := cadences(RatingListFamily.NATIONAL):
        sources = {
            player.national_source
            for player in players
            if player.national_id and player.national_source
        }
        if (
            event.national_rating_source
            and event.national_rating_source.national_source_id
        ):
            sources.add(event.national_rating_source.national_source_id)
        if not sources:
            statuses.append(
                ListStatus(
                    name(_('National'), national_cadences),
                    _('No national list installed'),
                    True,
                )
            )
        for source in sorted(sources):
            known = manager.national_source(source)
            list_name = known.national_source_name if known else source
            if known is None or not known.is_available:
                message, warning = _('Not installed'), True
            elif isinstance(known, LocalDataSource) and not known.is_installed:
                message, warning = _('Read online'), False
            else:
                message, warning = known.info_or_warning_message
                if isinstance(known, LocalDataSource) and known.tries_online_first:
                    message += ' · ' + _('online database tried first')
            unpublished = [
                cadence
                for cadence in national_cadences
                if known is not None and cadence not in known.national_cadences
            ]
            if unpublished:
                message = ' · '.join(
                    part
                    for part in (
                        message,
                        _('publishes no {cadences} rating').format(
                            cadences=', '.join(
                                c.short_name.lower() for c in unpublished
                            )
                        ),
                    )
                    if part
                )
                warning = True
            statuses.append(
                ListStatus(name(list_name, national_cadences), message, warning)
            )
    return statuses


async def check_ratings(
    event: 'Event', players: list[Player], installed_only: bool = False
) -> RatingCheck:
    """Compare the ratings of *players* with what the lists give them
    now, in the slice of their tournament being played; each national
    list is read from the source the user chose for it, its installed
    copy alone with *installed_only*."""
    from data.input_output import DataSourceManager
    from data.input_output.data_source import DataSource, FideDataSource

    fide_players = _fide_list(players)
    fide_database = FideDatabase()
    lists: list[DataSource] = []
    if fide_players is not None:
        lists.append(DataSourceManager().get_object(FideDataSource.static_id()))
    players_by_source: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        if player.national_id and player.national_source:
            players_by_source[player.national_source].append(player)
    national_matches: dict[int, StoredPlayer] = {}
    for source, source_players in players_by_source.items():
        data_source = DataSourceManager().national_source(source)
        if data_source is None:
            continue
        if installed_only:
            with installed_copies_only():
                stored_players = await data_source.get_match_stored_players(
                    source_players
                )
        else:
            stored_players = await data_source.get_match_stored_players(source_players)
        if stored_players is None:
            continue
        lists.append(data_source)
        for player in source_players:
            match = next(
                (
                    stored_player
                    for stored_player in stored_players
                    if data_source.check_player_match(
                        player.stored_player, stored_player
                    )
                ),
                None,
            )
            if match is not None:
                national_matches[player.id] = match

    rows: list[RatingCheckRow] = []
    not_found: list[Player] = []
    for player in players:
        tournament = player.optional_single_tournament
        cadence, preference, sequence = event.rating_resolution(tournament)
        period = _recorded_period(player)
        current = player.ratings_for(period)
        listed = copy.deepcopy(current)
        fide_match = (
            fide_players.get(player.fide_id)
            if fide_players is not None and player.fide_id
            else None
        )
        national_match = national_matches.get(player.id)
        if national_match is not None:
            national_ratings = _stored_ratings(national_match)
            source = player.national_source or ''
            _set_listed(listed, PlayerRatingType.NATIONAL, national_ratings, source)
            _set_listed(listed, PlayerRatingType.FIDE, national_ratings, source)
        if fide_match is not None:
            fide_ratings = _stored_ratings(fide_match)
            for tournament_rating in Cadence:
                fide_rating = fide_ratings[tournament_rating]
                rating = listed[tournament_rating]
                if fide_rating.fide is not None:
                    rating.set_value_from_type(
                        fide_rating.fide,
                        PlayerRatingType.FIDE,
                        fide_rating.origins.get(PlayerRatingType.FIDE),
                    )
                rating.k_factor = fide_rating.k_factor
            _k_factors(
                player,
                current,
                listed,
                fide_database.covers_rating_period(player.fide_k_factor_reference_date),
            )
        if (player.fide_id and fide_players is not None and fide_match is None) or (
            player.national_id
            and player.national_source in players_by_source
            and national_match is None
            and any(
                data_source.national_source_id == player.national_source
                for data_source in lists
            )
        ):
            not_found.append(player)
        kept = copy.deepcopy(listed)
        for tournament_rating in Cadence:
            rating = current[tournament_rating]
            for rating_type in LIST_TYPES:
                if rating.is_overridden(rating_type):
                    value = rating.get_type_value(rating_type)
                    assert value is not None
                    kept[tournament_rating].override(value, rating_type)
        row = RatingCheckRow(
            player=player,
            period=period,
            cadence=cadence,
            preference=preference,
            sequence=sequence,
            current=current,
            listed=listed,
            kept=kept,
        )
        if row.changes_anything or row.arbiter_value:
            rows.append(row)
    return RatingCheck(rows=rows, not_found=not_found, lists=lists)


def list_versions() -> dict[str, float]:
    """The snapshot of every installed rating list, by list: what tells a
    list update apart from the copies a check was last made against."""
    from database.sqlite.local_source_database import LocalSourceDatabaseManager

    return {
        database.id: database.updated_at_timestamp
        for database in LocalSourceDatabaseManager().objects()
        if database.exists() and database.updated_at_timestamp is not None
    }


def stale_lists(lists: list['DataSource']) -> list['LocalSourceDatabase']:
    """The installed copies of *lists* their source has a newer list than,
    or whose outdate delay has run out: a check against them would report
    against a stale list (TEC Manual 3.9.5.11.f, VCL Q141). Asks the
    sources that tell."""
    from data.input_output.data_source import LocalDataSource

    return [
        data_source.database
        for data_source in lists
        if isinstance(data_source, LocalDataSource)
        and (
            data_source.database.is_outdated or data_source.database.is_behind_source()
        )
    ]


@dataclass
class _AutomaticCheck:
    versions: dict[str, float]
    count: int
    stale: bool = False


#: The outcome of the last automatic check of the events opened last.
_automatic_checks: OrderedDict[str, _AutomaticCheck] = OrderedDict()
_AUTOMATIC_CHECKS_KEPT = 16


async def automatic_check(event: 'Event') -> int:
    """How many players of *event* the installed lists would give another
    rating (VCL Q139–140): checked when the event is first opened, then
    again once a list has changed or a player was updated. No server is
    asked."""
    versions = list_versions()
    cached = _automatic_checks.get(event.uniq_id)
    if cached is not None and not cached.stale and cached.versions == versions:
        return cached.count
    rating_check = await check_ratings(
        event, list(event.players_by_id.values()), installed_only=True
    )
    _automatic_checks[event.uniq_id] = _AutomaticCheck(
        versions=versions, count=rating_check.attention_count
    )
    _automatic_checks.move_to_end(event.uniq_id)
    while len(_automatic_checks) > _AUTOMATIC_CHECKS_KEPT:
        _automatic_checks.popitem(last=False)
    return rating_check.attention_count


def forget_automatic_check(event: 'Event') -> None:
    """Have the next automatic check made again, the players having
    changed."""
    if (cached := _automatic_checks.get(event.uniq_id)) is not None:
        cached.stale = True
