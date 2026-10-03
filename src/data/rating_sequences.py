"""The Rating List Sequence of a tournament (TEC Manual 3.9.5.7) and how a
player's tournament rating is resolved through it."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from typing import Self

from common.i18n import _, pgettext
from utils.date_time import format_date
from utils.enum import PlayerRatingType, RatingPreference, Cadence
from utils.types import PlayerRating, PlayerRatingAndType, RatingOrigin

FIDE_SOURCE = 'fide'


class RatingListFamily(StrEnum):
    """Who publishes a list: FIDE, or the federation whose national
    list the player is rated in."""

    FIDE = 'fide'
    NATIONAL = 'national'


@dataclass(frozen=True)
class RatingList:
    """One list of a sequence: a publisher at a cadence."""

    family: RatingListFamily
    cadence: Cadence

    @property
    def key(self) -> str:
        return f'{self.family}:{self.cadence.value}'

    @classmethod
    def from_key(cls, key: str) -> Self:
        family, cadence = key.split(':')
        return cls(RatingListFamily(family), Cadence(int(cadence)))

    def name(self, national_list_name: str | None) -> str:
        if self.family == RatingListFamily.FIDE:
            return pgettext('rating list', 'FIDE {cadence}').format(
                cadence=self.cadence.short_name.lower()
            )
        return pgettext('rating list', '{list} {cadence}').format(
            list=national_list_name or _('National'),
            cadence=self.cadence.short_name.lower(),
        )


type RatingSequence = tuple[RatingList, ...]


def sequence_from_keys(keys: Iterable[str]) -> RatingSequence:
    return tuple(RatingList.from_key(key) for key in keys)


def sequence_keys(sequence: RatingSequence) -> list[str]:
    return [rating_list.key for rating_list in sequence]


def sequence_name(sequence: RatingSequence, national_list_name: str | None) -> str:
    return ' → '.join(rating_list.name(national_list_name) for rating_list in sequence)


def _fide(*cadences: Cadence) -> RatingSequence:
    return tuple(RatingList(RatingListFamily.FIDE, cadence) for cadence in cadences)


def _national(*cadences: Cadence) -> RatingSequence:
    return tuple(RatingList(RatingListFamily.NATIONAL, cadence) for cadence in cadences)


STANDARD = Cadence.STANDARD
RAPID = Cadence.RAPID
BLITZ = Cadence.BLITZ

#: FIDE's own default sequences (TEC Manual 3.9.5.8.b): the cadence's
#: Effective list, then the remaining one.
FIDE_DEFAULT_SEQUENCES: dict[Cadence, RatingSequence] = {
    STANDARD: _fide(STANDARD, RAPID, BLITZ),
    RAPID: _fide(RAPID, STANDARD, BLITZ),
    BLITZ: _fide(BLITZ, STANDARD, RAPID),
}


def _effective_fide(cadence: Cadence) -> RatingSequence:
    return _fide(cadence) if cadence == STANDARD else _fide(cadence, STANDARD)


def _national_options(
    cadence: Cadence, national_cadences: frozenset[Cadence]
) -> list[RatingSequence]:
    """The national parts a sequence can end with, from what the list
    publishes: a list rating the cadence offers it alone or followed by
    its standard column; any other falls back on its standard column."""
    if cadence == STANDARD or cadence not in national_cadences:
        return [_national(STANDARD)]
    return [_national(cadence), _national(cadence, STANDARD)]


def sequence_options(
    cadence: Cadence,
    preference: RatingPreference,
    national_cadences: frozenset[Cadence],
) -> list[RatingSequence]:
    """The prebuilt sequences offered for a cadence and a preference,
    the default first. Each names only lists that can answer."""
    fide_options = [FIDE_DEFAULT_SEQUENCES[cadence], _effective_fide(cadence)]
    national_options = _national_options(cadence, national_cadences)
    options: list[RatingSequence]
    match preference:
        case RatingPreference.FIDE:
            options = fide_options
        case RatingPreference.NATIONAL:
            options = national_options
        case RatingPreference.FIDE_THEN_NATIONAL:
            options = [
                fide + national
                for fide in fide_options
                for national in reversed(national_options)
            ]
        case RatingPreference.NATIONAL_THEN_FIDE:
            options = [
                national + fide
                for national in national_options
                for fide in reversed(fide_options)
            ]
        case _:
            options = [
                _effective_fide(cadence) + national for national in national_options
            ]
    return list(dict.fromkeys(options))


def _family(
    origin: RatingOrigin | None, rating_type: PlayerRatingType
) -> RatingListFamily:
    if origin is None or not origin.source:
        return (
            RatingListFamily.FIDE
            if rating_type == PlayerRatingType.FIDE
            else RatingListFamily.NATIONAL
        )
    if origin.source == FIDE_SOURCE:
        return RatingListFamily.FIDE
    return RatingListFamily.NATIONAL


def cadence_marker(
    rating_type: PlayerRatingType,
    value_cadence: Cadence,
    cadence: Cadence,
    single_national_rating: bool,
) -> str:
    """The cadence a value is shown borrowed from, '' when it is the
    player's rating at the tournament's cadence.

    A FIDE standard rating is the rapid and blitz rating of a player who
    holds no other (FIDE's Effective lists), and a federation publishing
    a single rating rates every cadence on it; a rapid or blitz value
    only ranks a player in a standard tournament."""
    if value_cadence == cadence:
        return ''
    if value_cadence == STANDARD and (
        rating_type == PlayerRatingType.FIDE or single_national_rating
    ):
        return ''
    return value_cadence.marker


def _value_in(
    ratings: dict[Cadence, PlayerRating],
    rating_list: RatingList,
    rating_type: PlayerRatingType,
) -> int | None:
    rating = ratings[rating_list.cadence]
    value = rating.get_type_value(rating_type)
    if value is None:
        return None
    if _family(rating.origins.get(rating_type), rating_type) != rating_list.family:
        return None
    return value


def rating_choice_key(rating_type: PlayerRatingType, rating_list: RatingList) -> str:
    """The key of a rating the arbiter chose: its kind and its list."""
    return f'{rating_type.key}:{rating_list.key}'


def _from_choice_key(key: str) -> tuple[PlayerRatingType, RatingList]:
    rating_type, rating_list = key.split(':', 1)
    return PlayerRatingType.from_key(rating_type), RatingList.from_key(rating_list)


def _list_rating(
    ratings: dict[Cadence, PlayerRating],
    rating_list: RatingList,
    rating_type: PlayerRatingType,
    cadence: Cadence,
    is_single_national_rating: Callable[[RatingOrigin | None], bool],
) -> PlayerRatingAndType | None:
    """The value a list holds for the player, marked for a tournament of
    *cadence*."""
    value = _value_in(ratings, rating_list, rating_type)
    if value is None:
        return None
    rating = ratings[rating_list.cadence]
    origin = rating.origins.get(rating_type)
    return PlayerRatingAndType(
        value,
        rating_type,
        origin=origin,
        cadence=rating_list.cadence,
        cadence_marker=cadence_marker(
            rating_type,
            rating_list.cadence,
            cadence,
            rating_type == PlayerRatingType.NATIONAL
            and is_single_national_rating(origin),
        ),
        overridden=rating.is_overridden(rating_type),
    )


def resolve_rating(
    ratings: dict[Cadence, PlayerRating],
    cadence: Cadence,
    preference: RatingPreference,
    sequence: RatingSequence,
    is_single_national_rating: Callable[[RatingOrigin | None], bool],
    prescribed: Callable[[], int | None],
) -> PlayerRatingAndType:
    """The tournament rating of a player: the rating the arbiter chose
    while its list holds one (TEC Manual 3.9.5.7.c); else for each kind
    of rating the preference names, the first list of the sequence
    holding one; failing that, the value typed for the player, or the one
    a plugin prescribes (3.9.5.6–3.9.5.7)."""
    if pinned := ratings[cadence].pinned:
        rating_type, rating_list = _from_choice_key(pinned)
        chosen = _list_rating(
            ratings, rating_list, rating_type, cadence, is_single_national_rating
        )
        if chosen is not None:
            chosen.pinned = True
            return chosen
    found: list[PlayerRatingAndType] = []
    for rating_type in preference.kinds:
        for rating_list in sequence:
            rating = _list_rating(
                ratings, rating_list, rating_type, cadence, is_single_national_rating
            )
            if rating is not None:
                found.append(rating)
                break
        if found and preference not in (
            RatingPreference.HIGHEST,
            RatingPreference.LOWEST,
        ):
            return found[0]
    if found:
        pick = max if preference == RatingPreference.HIGHEST else min
        return pick(found, key=lambda rating_and_type: rating_and_type.value)
    manual = ratings[cadence].manual
    if manual is not None:
        return PlayerRatingAndType(manual, PlayerRatingType.ESTIMATED, cadence=cadence)
    return PlayerRatingAndType(
        prescribed() or 0,
        PlayerRatingType.ESTIMATED,
        cadence=cadence,
        prescribed=True,
    )


def official_rating(
    ratings: dict[Cadence, PlayerRating], cadence: Cadence
) -> PlayerRatingAndType | None:
    """The rating reported to FIDE (TEC Manual 3.9.5.5): the FIDE rating
    of the cadence, or the standard one for a rapid or blitz player who
    holds no other (the Effective lists). It is what the list gives: a
    correction by the arbiter changes the tournament rating only, the
    two being kept apart (3.9.5.1)."""
    for rating_list in _effective_fide(cadence):
        value_cadence = rating_list.cadence
        rating = ratings[value_cadence]
        if rating.fide is not None:
            origin = rating.origins.get(PlayerRatingType.FIDE)
            listed = (
                origin.original
                if origin is not None and origin.original is not None
                else rating.fide
            )
            return PlayerRatingAndType(
                listed,
                PlayerRatingType.FIDE,
                origin=None if origin is None else replace(origin, original=None),
                cadence=value_cadence,
            )
    return None


def other_ratings(
    ratings: dict[Cadence, PlayerRating],
    sequence: RatingSequence,
    resolved: PlayerRatingAndType,
    cadence: Cadence,
    is_single_national_rating: Callable[[RatingOrigin | None], bool],
) -> list[tuple[str, PlayerRatingAndType, bool]]:
    """The values the player holds besides the one the tournament uses,
    which the arbiter is shown and may choose (Q128–129): those of the
    lists of the sequence first, then those of any other list. Each comes
    with its choice key and whether its list is in the sequence."""
    all_lists = [
        RatingList(family, list_cadence)
        for family in RatingListFamily
        for list_cadence in Cadence
    ]
    lists = [
        *sequence,
        *(rating_list for rating_list in all_lists if rating_list not in sequence),
    ]
    others: list[tuple[str, PlayerRatingAndType, bool]] = []
    for rating_list in lists:
        for rating_type in (PlayerRatingType.FIDE, PlayerRatingType.NATIONAL):
            rating = _list_rating(
                ratings, rating_list, rating_type, cadence, is_single_national_rating
            )
            if rating is None:
                continue
            if (
                rating_type == resolved.type
                and rating_list.cadence == resolved.cadence
                and rating.origin == resolved.origin
            ):
                continue
            others.append(
                (
                    rating_choice_key(rating_type, rating_list),
                    rating,
                    rating_list in sequence,
                )
            )
    return others


def describe_rating(rating: PlayerRatingAndType) -> str:
    """Where a rating came from, as the arbiter is shown it: the list
    and the snapshot it was read from, or how it was entered (TEC
    Manual 3.9.5.11.c)."""
    from data.input_output import DataSourceManager

    if rating.type == PlayerRatingType.ESTIMATED:
        if rating.prescribed:
            return _('Prescribed by the federation') if rating.value else ''
        return _('Typed by the arbiter')
    origin = rating.origin
    if origin is None or not origin.source:
        list_name = (
            _('FIDE') if rating.type == PlayerRatingType.FIDE else _('National list')
        )
    elif origin.source == FIDE_SOURCE:
        list_name = _('FIDE')
    else:
        data_source = DataSourceManager().national_source(origin.source)
        list_name = data_source.national_source_name if data_source else origin.source
    description = list_name
    if origin is not None and origin.online:
        description += ' ' + _('online')
    if rating.cadence is not None:
        description += f' {rating.cadence.short_name.lower()}'
    if origin is not None and origin.version:
        description += f', {_format_list_version(origin.version)}'
    if (
        rating.type == PlayerRatingType.FIDE
        and origin is not None
        and origin.source not in ('', FIDE_SOURCE)
    ):
        description += f' ({_("FIDE column")})'
    if origin is not None and origin.original is not None:
        description += ' · ' + _(
            'corrected by the arbiter, the list gave {rating}'
        ).format(rating=origin.original)
    if rating.pinned:
        description += ' · ' + _('chosen by the arbiter')
    return description


def _format_list_version(version: str) -> str:
    try:
        return format_date(date.fromisoformat(version))
    except ValueError:
        return version
