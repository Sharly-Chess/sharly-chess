"""The Rating List Sequence of a tournament (TEC Manual 3.9.5.7) and how a
player's tournament rating is resolved through it."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from typing import Self

from markupsafe import Markup, escape

from common.i18n import _, pgettext
from utils.date_time import format_date
from utils.enum import PlayerRatingType, RatingPreference, Cadence
from utils.types import PlayerRating, PlayerRatingAndType, RatingOrigin

FIDE_SOURCE = 'fide'

#: The rating of the players no list rates, unless an event, a tournament
#: or a plugin sets another.
DEFAULT_UNRATED_RATING = 1400


@dataclass(frozen=True)
class PrescribedRatingRule:
    """How a federation prescribes the rating of the players no list
    rates: *label* where a field shows it, *description* the rule."""

    label: str
    description: str


class RatingListFamily(StrEnum):
    """Who publishes a list: FIDE, or the federation whose national
    list the player is rated in."""

    FIDE = 'fide'
    NATIONAL = 'national'


@dataclass(frozen=True)
class RatingEntry:
    """One rating a sequence tries: the list it is read from, its kind
    and its cadence. A national list may give the FIDE rating of its
    players besides their national one."""

    family: RatingListFamily
    kind: PlayerRatingType
    cadence: Cadence

    def __post_init__(self) -> None:
        if self.kind not in (PlayerRatingType.FIDE, PlayerRatingType.NATIONAL) or (
            self.family == RatingListFamily.FIDE and self.kind != PlayerRatingType.FIDE
        ):
            raise ValueError(f'No {self.kind} rating in a {self.family} list')

    @property
    def key(self) -> str:
        if self.family == RatingListFamily.FIDE:
            return f'{self.family}:{self.cadence.value}'
        return f'{self.family}:{self.kind.key}:{self.cadence.value}'

    @classmethod
    def from_key(cls, key: str) -> Self:
        match key.split(':'):
            case [family, cadence]:
                return cls(
                    RatingListFamily(family),
                    PlayerRatingType.FIDE,
                    Cadence(int(cadence)),
                )
            case [family, kind, cadence]:
                return cls(
                    RatingListFamily(family),
                    PlayerRatingType.from_key(kind),
                    Cadence(int(cadence)),
                )
        raise ValueError(f'Unknown rating: {key}')


type RatingSequence = tuple[RatingEntry, ...]


def sequence_from_keys(keys: Iterable[str]) -> RatingSequence:
    return tuple(RatingEntry.from_key(key) for key in keys)


def sequence_keys(sequence: RatingSequence) -> list[str]:
    return [entry.key for entry in sequence]


def _sequence_groups(
    sequence: RatingSequence, then: str
) -> list[tuple[RatingListFamily, str]]:
    """The consecutive ratings of a sequence read from the same list,
    each list with the ratings tried in it, in order, e.g. "FIDE rapid ›
    national rapid"."""
    groups: list[tuple[RatingListFamily, list[RatingEntry]]] = []
    for entry in sequence:
        if groups and groups[-1][0] == entry.family:
            groups[-1][1].append(entry)
        else:
            groups.append((entry.family, [entry]))
    return [
        (
            family,
            then.join(
                entry.cadence.short_name.lower()
                if family == RatingListFamily.FIDE
                else (
                    pgettext('rating sequence', 'FIDE {cadences}')
                    if entry.kind == PlayerRatingType.FIDE
                    else pgettext('rating sequence', 'national {cadences}')
                ).format(cadences=entry.cadence.short_name.lower())
                for entry in entries
            ),
        )
        for family, entries in groups
    ]


def _compared(preference: RatingPreference | None) -> str | None:
    match preference:
        case RatingPreference.HIGHEST:
            return pgettext(
                'rating sequence', 'Highest of FIDE and national: {sequence}'
            )
        case RatingPreference.LOWEST:
            return pgettext(
                'rating sequence', 'Lowest of FIDE and national: {sequence}'
            )
    return None


def sequence_name(
    sequence: RatingSequence,
    national_list_name: str | None,
    preference: RatingPreference | None = None,
) -> str:
    """The ratings tried, grouped by list, e.g. "FIDE list: rapid >
    standard → FFE: FIDE rapid > national rapid"."""
    name = ' → '.join(
        pgettext('rating sequence', 'FIDE list: {ratings}').format(ratings=ratings)
        if family == RatingListFamily.FIDE
        else pgettext('rating sequence', '{list}: {ratings}').format(
            list=national_list_name or _('National list'), ratings=ratings
        )
        for family, ratings in _sequence_groups(sequence, ' > ')
    )
    if (compared := _compared(preference)) is not None:
        return compared.format(sequence=name)
    return name


def sequence_html(
    sequence: RatingSequence,
    national_list_name: str | None,
    preference: RatingPreference | None = None,
) -> Markup:
    """The name of a sequence with each list as a badge."""
    arrow = Markup(' <i class="bi-arrow-right text-secondary"></i> ')
    html = arrow.join(
        Markup('{list} {ratings}').format(
            list=Markup('<span class="badge {classes}">{name}</span>').format(
                classes='bg-primary text-dark'
                if family == RatingListFamily.FIDE
                else 'text-bg-secondary',
                name=_('FIDE')
                if family == RatingListFamily.FIDE
                else national_list_name or _('National list'),
            ),
            ratings=ratings,
        )
        for family, ratings in _sequence_groups(sequence, ' › ')
    )
    if (compared := _compared(preference)) is not None:
        return Markup(escape(compared)).format(sequence=html)
    return html


def sequence_preference(
    sequence: RatingSequence, comparison: RatingPreference | None = None
) -> RatingPreference:
    """The Record 172 method a sequence amounts to: the kinds of rating
    it tries in the order it first tries them, or the comparison of the
    two kinds asked for."""
    kinds = tuple(dict.fromkeys(entry.kind for entry in sequence))
    if (
        comparison in (RatingPreference.HIGHEST, RatingPreference.LOWEST)
        and len(kinds) == 2
    ):
        return comparison
    match kinds:
        case (PlayerRatingType.NATIONAL,):
            return RatingPreference.NATIONAL
        case (PlayerRatingType.FIDE, PlayerRatingType.NATIONAL):
            return RatingPreference.FIDE_THEN_NATIONAL
        case (PlayerRatingType.NATIONAL, PlayerRatingType.FIDE):
            return RatingPreference.NATIONAL_THEN_FIDE
    return RatingPreference.FIDE


def _fide(*cadences: Cadence) -> RatingSequence:
    return tuple(
        RatingEntry(RatingListFamily.FIDE, PlayerRatingType.FIDE, cadence)
        for cadence in cadences
    )


def _copies(*cadences: Cadence) -> RatingSequence:
    return tuple(
        RatingEntry(RatingListFamily.NATIONAL, PlayerRatingType.FIDE, cadence)
        for cadence in cadences
    )


def _national(*cadences: Cadence) -> RatingSequence:
    return tuple(
        RatingEntry(RatingListFamily.NATIONAL, PlayerRatingType.NATIONAL, cadence)
        for cadence in cadences
    )


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


def with_copies(
    fide: RatingSequence, fide_cadences: frozenset[Cadence]
) -> RatingSequence:
    """FIDE list ratings followed by the FIDE ratings of the same
    cadences the national list gives."""
    return fide + _copies(
        *(entry.cadence for entry in fide if entry.cadence in fide_cadences)
    )


def _national_options(
    cadence: Cadence, national_cadences: frozenset[Cadence]
) -> list[RatingSequence]:
    """The national ratings a sequence can try, from what the list
    publishes: a list rating the cadence offers it alone or followed by
    its standard rating; any other falls back on its standard rating."""
    if cadence == STANDARD or cadence not in national_cadences:
        return [_national(STANDARD)]
    return [_national(cadence), _national(cadence, STANDARD)]


def sequence_options(
    cadence: Cadence,
    preference: RatingPreference,
    national_cadences: frozenset[Cadence],
    fide_cadences: frozenset[Cadence],
) -> list[RatingSequence]:
    """The prebuilt sequences offered for a cadence and a preference,
    the default first. Each names only ratings the lists publish."""
    fide_options = [
        with_copies(fide, fide_cadences)
        for fide in (FIDE_DEFAULT_SEQUENCES[cadence], _effective_fide(cadence))
    ]
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
                with_copies(_effective_fide(cadence), fide_cadences) + national
                for national in national_options
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


def _value_in(ratings: dict[Cadence, PlayerRating], entry: RatingEntry) -> int | None:
    rating = ratings[entry.cadence]
    value = rating.get_type_value(entry.kind)
    if value is None:
        return None
    if _family(rating.origins.get(entry.kind), entry.kind) != entry.family:
        return None
    return value


def _list_rating(
    ratings: dict[Cadence, PlayerRating],
    entry: RatingEntry,
    cadence: Cadence,
    is_single_national_rating: Callable[[RatingOrigin | None], bool],
) -> PlayerRatingAndType | None:
    """The value a list holds for the player, marked for a tournament of
    *cadence*."""
    value = _value_in(ratings, entry)
    if value is None:
        return None
    rating = ratings[entry.cadence]
    origin = rating.origins.get(entry.kind)
    return PlayerRatingAndType(
        value,
        entry.kind,
        origin=origin,
        cadence=entry.cadence,
        cadence_marker=cadence_marker(
            entry.kind,
            entry.cadence,
            cadence,
            entry.kind == PlayerRatingType.NATIONAL
            and is_single_national_rating(origin),
        ),
        overridden=rating.is_overridden(entry.kind),
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
    while its list holds one (TEC Manual 3.9.5.7.c); else the first
    rating of the sequence the player holds, or for a highest or lowest
    preference the higher or lower of the first FIDE and the first
    national ones; failing that, the value typed for the player, or the
    one a plugin prescribes (3.9.5.6–3.9.5.7)."""
    if pinned := ratings[cadence].pinned:
        try:
            chosen_entry: RatingEntry | None = RatingEntry.from_key(pinned)
        except ValueError:
            chosen_entry = None
        if chosen_entry is not None and (
            chosen := _list_rating(
                ratings, chosen_entry, cadence, is_single_national_rating
            )
        ):
            chosen.pinned = True
            return chosen
    comparison = preference in (RatingPreference.HIGHEST, RatingPreference.LOWEST)
    found: dict[PlayerRatingType, PlayerRatingAndType] = {}
    for entry in sequence:
        if entry.kind in found:
            continue
        rating = _list_rating(ratings, entry, cadence, is_single_national_rating)
        if rating is None:
            continue
        if not comparison:
            return rating
        found[entry.kind] = rating
    if found:
        pick = max if preference == RatingPreference.HIGHEST else min
        return pick(found.values(), key=lambda rating_and_type: rating_and_type.value)
    manual = ratings[cadence].manual
    prescribed_value = prescribed()
    # A typed value no different from the prescribed one is the prescribed
    # one: nothing tells them apart, and it follows the player's category
    if manual is not None and manual != prescribed_value:
        return PlayerRatingAndType(manual, PlayerRatingType.ESTIMATED, cadence=cadence)
    return PlayerRatingAndType(
        prescribed_value or 0,
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


ALL_ENTRIES: RatingSequence = tuple(
    entry for entries in (_fide, _copies, _national) for entry in entries(*Cadence)
)


def other_ratings(
    ratings: dict[Cadence, PlayerRating],
    sequence: RatingSequence,
    resolved: PlayerRatingAndType,
    cadence: Cadence,
    is_single_national_rating: Callable[[RatingOrigin | None], bool],
) -> list[tuple[str, PlayerRatingAndType, bool]]:
    """The values the player holds besides the one the tournament uses,
    which the arbiter is shown and may choose (Q128–129): those of the
    sequence first, then any other. Each comes with its key and whether
    the sequence tries it."""
    entries = [
        *sequence,
        *(entry for entry in ALL_ENTRIES if entry not in sequence),
    ]
    others: list[tuple[str, PlayerRatingAndType, bool]] = []
    for entry in entries:
        rating = _list_rating(ratings, entry, cadence, is_single_national_rating)
        if rating is None:
            continue
        if (
            entry.kind == resolved.type
            and entry.cadence == resolved.cadence
            and rating.origin == resolved.origin
        ):
            continue
        others.append((entry.key, rating, entry in sequence))
    return others


def describe_rating(rating: PlayerRatingAndType) -> str:
    """Where a rating came from, as the arbiter is shown it: the list
    and the snapshot it was read from, or how it was entered (TEC
    Manual 3.9.5.11.c)."""
    from data.input_output import DataSourceManager

    if rating.type == PlayerRatingType.ESTIMATED:
        if rating.prescribed:
            return _('Rating of unrated players') if rating.value else ''
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
