import pytest

from data.rating_sequences import (
    FIDE_DEFAULT_SEQUENCES,
    RatingList,
    RatingListFamily,
    RatingSequence,
    official_rating,
    other_ratings,
    resolve_rating,
    sequence_from_keys,
    sequence_keys,
    sequence_options,
)
from utils.enum import PlayerRatingType, RatingPreference, Cadence
from utils.types import PlayerRating, PlayerRatingAndType, RatingOrigin

STANDARD = Cadence.STANDARD
RAPID = Cadence.RAPID
BLITZ = Cadence.BLITZ
FIDE = RatingListFamily.FIDE
NATIONAL = RatingListFamily.NATIONAL

FIDE_LIST = RatingOrigin('fide', '2026-10-02')
FFE_LIST = RatingOrigin('ffe', '2026-10-01')
DSB_LIST = RatingOrigin('dsb', '2026-10-01')


def sequence(*lists: tuple[RatingListFamily, Cadence]) -> RatingSequence:
    return tuple(RatingList(family, cadence) for family, cadence in lists)


def ratings(**by_cadence: PlayerRating) -> dict[Cadence, PlayerRating]:
    return {
        cadence: by_cadence.get(cadence.form_key, PlayerRating()) for cadence in Cadence
    }


def resolve(
    player_ratings: dict[Cadence, PlayerRating],
    cadence: Cadence,
    preference: RatingPreference,
    rating_sequence: RatingSequence,
    single_national_rating: bool = False,
    prescribed: int | None = None,
) -> PlayerRatingAndType:
    return resolve_rating(
        player_ratings,
        cadence,
        preference,
        rating_sequence,
        lambda origin: single_national_rating,
        lambda: prescribed,
    )


@pytest.mark.unit
def test_a_player_in_the_main_list_gets_its_rating():
    rating = resolve(
        ratings(
            standard=PlayerRating(fide=1850, origins={PlayerRatingType.FIDE: FIDE_LIST})
        ),
        STANDARD,
        RatingPreference.FIDE,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
    )
    assert (rating.value, rating.type, rating.origin) == (
        1850,
        PlayerRatingType.FIDE,
        FIDE_LIST,
    )
    assert str(rating) == '1850\xa0F'


@pytest.mark.unit
def test_the_kinds_of_the_preference_come_before_the_lists():
    """National then FIDE over a sequence that starts with the FIDE list
    gives the national rating, which a lookup taking the lists first
    would have overridden."""
    player_ratings = ratings(
        standard=PlayerRating(
            fide=1900,
            national=1800,
            origins={
                PlayerRatingType.FIDE: FIDE_LIST,
                PlayerRatingType.NATIONAL: FFE_LIST,
            },
        )
    )
    rating = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.NATIONAL_THEN_FIDE,
        sequence((FIDE, STANDARD), (NATIONAL, STANDARD)),
    )
    assert (rating.value, rating.type) == (1800, PlayerRatingType.NATIONAL)


@pytest.mark.unit
def test_a_national_copy_of_the_fide_rating_answers_for_the_fide_kind():
    player_ratings = ratings(
        standard=PlayerRating(
            fide=1875, national=1850, origins={PlayerRatingType.FIDE: FFE_LIST}
        )
    )
    rating = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        sequence((FIDE, STANDARD), (NATIONAL, STANDARD)),
    )
    assert (rating.value, rating.type, rating.origin) == (
        1875,
        PlayerRatingType.FIDE,
        FFE_LIST,
    )


@pytest.mark.unit
def test_a_rapid_rating_only_ranks_a_standard_player():
    rating = resolve(
        ratings(rapid=PlayerRating(fide=1700)),
        STANDARD,
        RatingPreference.FIDE,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
    )
    assert (rating.suffix, rating.cadence_marker) == ('F', 'RPD')
    assert str(rating) == '1700\xa0F\xa0(RPD)'
    assert rating.__html__() == '1700\xa0F<sup>RPD</sup>'


@pytest.mark.unit
def test_a_fide_standard_rating_is_the_rapid_rating_of_a_player_without_one():
    player_ratings = ratings(standard=PlayerRating(fide=1900))
    rating = resolve(
        player_ratings, RAPID, RatingPreference.FIDE, FIDE_DEFAULT_SEQUENCES[RAPID]
    )
    assert (rating.value, rating.suffix, rating.cadence_marker) == (1900, 'F', '')
    official = official_rating(player_ratings, RAPID)
    assert official is not None
    assert (official.value, official.cadence) == (1900, STANDARD)


@pytest.mark.unit
def test_a_national_standard_rating_in_rapid_is_marked_unless_the_list_has_one_rating():
    player_ratings = ratings(standard=PlayerRating(national=1600))
    rapid_sequence = sequence((NATIONAL, RAPID), (NATIONAL, STANDARD))
    assert (
        resolve(
            player_ratings, RAPID, RatingPreference.NATIONAL, rapid_sequence
        ).cadence_marker
        == 'STD'
    )
    assert (
        resolve(
            player_ratings,
            RAPID,
            RatingPreference.NATIONAL,
            sequence((NATIONAL, STANDARD)),
            single_national_rating=True,
        ).cadence_marker
        == ''
    )


@pytest.mark.unit
def test_a_corrected_value_keeps_its_kind_and_source():
    rating = PlayerRating(fide=1840, origins={PlayerRatingType.FIDE: FIDE_LIST})
    rating.override(1850, PlayerRatingType.FIDE)
    assert rating.origins[PlayerRatingType.FIDE] == RatingOrigin(
        'fide', '2026-10-02', 1840
    )
    resolved = resolve(
        ratings(standard=rating),
        STANDARD,
        RatingPreference.FIDE,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
    )
    assert (resolved.value, resolved.suffix) == (1850, 'F*')
    official = official_rating(ratings(standard=rating), STANDARD)
    assert official is not None
    assert (official.value, official.suffix) == (1840, 'F')

    rating.override(1840, PlayerRatingType.FIDE)
    assert rating.origins[PlayerRatingType.FIDE] == FIDE_LIST
    assert PlayerRating.from_stored_value(rating.stored_value) == rating


@pytest.mark.unit
def test_a_player_no_list_answers_for_gets_the_typed_or_prescribed_value():
    typed = resolve(
        ratings(standard=PlayerRating(manual=1500)),
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
        prescribed=1399,
    )
    assert (typed.value, typed.suffix, typed.prescribed) == (1500, 'E', False)
    prescribed = resolve(
        ratings(),
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
        prescribed=1399,
    )
    assert (prescribed.value, prescribed.suffix, prescribed.prescribed) == (
        1399,
        'E',
        True,
    )
    assert (
        official_rating(ratings(standard=PlayerRating(manual=1500)), STANDARD) is None
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    'preference, expected',
    [(RatingPreference.HIGHEST, 1900), (RatingPreference.LOWEST, 1800)],
)
def test_highest_and_lowest_read_both_kinds(preference, expected):
    player_ratings = ratings(standard=PlayerRating(fide=1800, national=1900))
    rating = resolve(
        player_ratings,
        STANDARD,
        preference,
        sequence((FIDE, STANDARD), (NATIONAL, STANDARD)),
    )
    assert rating.value == expected


@pytest.mark.unit
def test_the_other_ratings_are_listed_those_of_the_sequence_first():
    player_ratings = ratings(
        standard=PlayerRating(national=1600, fide=1700),
        rapid=PlayerRating(national=1650),
    )
    rapid_sequence = sequence((NATIONAL, RAPID), (NATIONAL, STANDARD))
    resolved = resolve(player_ratings, RAPID, RatingPreference.NATIONAL, rapid_sequence)
    others = other_ratings(
        player_ratings, rapid_sequence, resolved, RAPID, lambda origin: False
    )
    assert [
        (key, rating.value, in_sequence) for key, rating, in_sequence in others
    ] == [
        ('n:national:1', 1600, True),
        ('f:fide:1', 1700, False),
    ]


@pytest.mark.unit
def test_the_rating_the_arbiter_chose_is_used_while_its_list_holds_one():
    player_ratings = ratings(
        standard=PlayerRating(fide=1700, national=1600, pinned='n:national:1')
    )
    chosen = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.FIDE,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
    )
    assert (chosen.value, chosen.type, chosen.pinned) == (
        1600,
        PlayerRatingType.NATIONAL,
        True,
    )
    assert (
        PlayerRating.from_stored_value(player_ratings[STANDARD].stored_value)
        == player_ratings[STANDARD]
    )

    player_ratings[STANDARD].national = None
    fallen_back = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.FIDE,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
    )
    assert (fallen_back.value, fallen_back.pinned) == (1700, False)


@pytest.mark.unit
def test_fide_default_sequences_follow_the_tec_manual():
    assert sequence_keys(FIDE_DEFAULT_SEQUENCES[STANDARD]) == [
        'fide:1',
        'fide:2',
        'fide:3',
    ]
    assert sequence_keys(FIDE_DEFAULT_SEQUENCES[RAPID]) == [
        'fide:2',
        'fide:1',
        'fide:3',
    ]
    assert sequence_keys(FIDE_DEFAULT_SEQUENCES[BLITZ]) == [
        'fide:3',
        'fide:1',
        'fide:2',
    ]
    assert sequence_from_keys(['fide:2', 'national:1']) == sequence(
        (FIDE, RAPID), (NATIONAL, STANDARD)
    )


@pytest.mark.unit
def test_only_lists_that_can_answer_are_offered():
    all_cadences = frozenset(Cadence)
    standard_only = frozenset({STANDARD})
    with_rapid = sequence_options(RAPID, RatingPreference.NATIONAL, all_cadences)
    assert with_rapid == [
        sequence((NATIONAL, RAPID)),
        sequence((NATIONAL, RAPID), (NATIONAL, STANDARD)),
    ]
    assert sequence_options(RAPID, RatingPreference.NATIONAL, standard_only) == [
        sequence((NATIONAL, STANDARD))
    ]
    assert sequence_options(
        BLITZ, RatingPreference.NATIONAL, frozenset({STANDARD, RAPID})
    ) == [sequence((NATIONAL, STANDARD))]
    assert sequence_options(STANDARD, RatingPreference.FIDE, all_cadences) == [
        FIDE_DEFAULT_SEQUENCES[STANDARD],
        sequence((FIDE, STANDARD)),
    ]
    assert sequence_options(
        STANDARD, RatingPreference.FIDE_THEN_NATIONAL, all_cadences
    ) == [
        FIDE_DEFAULT_SEQUENCES[STANDARD] + sequence((NATIONAL, STANDARD)),
        sequence((FIDE, STANDARD), (NATIONAL, STANDARD)),
    ]
