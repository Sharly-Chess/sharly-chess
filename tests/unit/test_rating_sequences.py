import pytest

from data.rating_sequences import (
    FIDE_DEFAULT_SEQUENCES,
    RatingEntry,
    RatingListFamily,
    RatingSequence,
    official_rating,
    other_ratings,
    resolve_rating,
    sequence_from_keys,
    sequence_keys,
    sequence_name,
    sequence_options,
    sequence_preference,
)
from utils.enum import PlayerRatingType, RatingPreference, Cadence
from utils.types import PlayerRating, PlayerRatingAndType, RatingOrigin

STANDARD = Cadence.STANDARD
RAPID = Cadence.RAPID
BLITZ = Cadence.BLITZ

FIDE_LIST = RatingOrigin('fide', '2026-10-02')
FFE_LIST = RatingOrigin('ffe', '2026-10-01')
DSB_LIST = RatingOrigin('dsb', '2026-10-01')


def fide(cadence: Cadence) -> RatingEntry:
    return RatingEntry(RatingListFamily.FIDE, PlayerRatingType.FIDE, cadence)


def copy(cadence: Cadence) -> RatingEntry:
    return RatingEntry(RatingListFamily.NATIONAL, PlayerRatingType.FIDE, cadence)


def national(cadence: Cadence) -> RatingEntry:
    return RatingEntry(RatingListFamily.NATIONAL, PlayerRatingType.NATIONAL, cadence)


def sequence(*entries: RatingEntry) -> RatingSequence:
    return entries


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
def test_the_first_rating_of_the_sequence_the_player_holds_is_used():
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
        sequence(national(STANDARD), fide(STANDARD)),
    )
    assert (rating.value, rating.type) == (1800, PlayerRatingType.NATIONAL)
    rating = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        sequence(fide(STANDARD), national(STANDARD)),
    )
    assert (rating.value, rating.type) == (1900, PlayerRatingType.FIDE)


@pytest.mark.unit
def test_the_fide_rating_a_national_list_gives_is_tried_on_its_own():
    player_ratings = ratings(
        standard=PlayerRating(
            fide=1875,
            national=1850,
            origins={
                PlayerRatingType.FIDE: FFE_LIST,
                PlayerRatingType.NATIONAL: FFE_LIST,
            },
        )
    )
    rating = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        sequence(fide(STANDARD), copy(STANDARD), national(STANDARD)),
    )
    assert (rating.value, rating.type, rating.origin) == (
        1875,
        PlayerRatingType.FIDE,
        FFE_LIST,
    )
    rating = resolve(
        player_ratings,
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        sequence(fide(STANDARD), national(STANDARD)),
    )
    assert (rating.value, rating.type) == (1850, PlayerRatingType.NATIONAL)


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
    rapid_sequence = sequence(national(RAPID), national(STANDARD))
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
            sequence(national(STANDARD)),
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
        sequence(fide(STANDARD), national(STANDARD)),
    )
    assert rating.value == expected


@pytest.mark.unit
def test_the_other_ratings_are_listed_those_of_the_sequence_first():
    player_ratings = ratings(
        standard=PlayerRating(national=1600, fide=1700),
        rapid=PlayerRating(national=1650),
    )
    rapid_sequence = sequence(national(RAPID), national(STANDARD))
    resolved = resolve(player_ratings, RAPID, RatingPreference.NATIONAL, rapid_sequence)
    others = other_ratings(
        player_ratings, rapid_sequence, resolved, RAPID, lambda origin: False
    )
    assert [
        (key, rating.value, in_sequence) for key, rating, in_sequence in others
    ] == [
        ('national:n:1', 1600, True),
        ('fide:1', 1700, False),
    ]


@pytest.mark.unit
def test_the_rating_the_arbiter_chose_is_used_while_its_list_holds_one():
    player_ratings = ratings(
        standard=PlayerRating(fide=1700, national=1600, pinned='national:n:1')
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
    keys = ['fide:2', 'national:f:2', 'national:n:1']
    assert sequence_from_keys(keys) == sequence(
        fide(RAPID), copy(RAPID), national(STANDARD)
    )
    assert sequence_keys(sequence_from_keys(keys)) == keys
    with pytest.raises(ValueError):
        sequence_from_keys(['fide:n:1'])


@pytest.mark.unit
def test_only_ratings_the_lists_publish_are_offered():
    all_cadences = frozenset(Cadence)
    standard_only = frozenset({STANDARD})
    none: frozenset[Cadence] = frozenset()
    assert sequence_options(RAPID, RatingPreference.NATIONAL, all_cadences, none) == [
        sequence(national(RAPID)),
        sequence(national(RAPID), national(STANDARD)),
    ]
    assert sequence_options(RAPID, RatingPreference.NATIONAL, standard_only, none) == [
        sequence(national(STANDARD))
    ]
    assert sequence_options(
        BLITZ, RatingPreference.NATIONAL, frozenset({STANDARD, RAPID}), none
    ) == [sequence(national(STANDARD))]
    assert sequence_options(STANDARD, RatingPreference.FIDE, all_cadences, none) == [
        FIDE_DEFAULT_SEQUENCES[STANDARD],
        sequence(fide(STANDARD)),
    ]
    assert sequence_options(
        STANDARD, RatingPreference.FIDE_THEN_NATIONAL, all_cadences, none
    ) == [
        FIDE_DEFAULT_SEQUENCES[STANDARD] + sequence(national(STANDARD)),
        sequence(fide(STANDARD), national(STANDARD)),
    ]
    assert sequence_options(
        RAPID, RatingPreference.FIDE_THEN_NATIONAL, standard_only, standard_only
    )[1] == sequence(fide(RAPID), fide(STANDARD), copy(STANDARD), national(STANDARD))


@pytest.mark.unit
def test_a_sequence_amounts_to_the_kinds_it_tries_first():
    fide_first = sequence(fide(STANDARD), copy(STANDARD), national(STANDARD))
    assert sequence_preference(FIDE_DEFAULT_SEQUENCES[STANDARD]) == (
        RatingPreference.FIDE
    )
    assert sequence_preference(sequence(national(STANDARD))) == (
        RatingPreference.NATIONAL
    )
    assert sequence_preference(fide_first) == RatingPreference.FIDE_THEN_NATIONAL
    assert sequence_preference(sequence(national(STANDARD), fide(STANDARD))) == (
        RatingPreference.NATIONAL_THEN_FIDE
    )
    assert sequence_preference(fide_first, RatingPreference.LOWEST) == (
        RatingPreference.LOWEST
    )
    assert sequence_preference(
        FIDE_DEFAULT_SEQUENCES[STANDARD], RatingPreference.HIGHEST
    ) == (RatingPreference.FIDE)


@pytest.mark.unit
def test_a_sequence_is_named_rating_by_rating_grouped_by_list():
    assert (
        sequence_name(
            sequence(
                fide(RAPID),
                fide(STANDARD),
                copy(RAPID),
                copy(STANDARD),
                national(RAPID),
            ),
            'FFE',
        )
        == 'FIDE list: rapid > standard → FFE: FIDE rapid > FIDE standard > '
        'national rapid'
    )
    assert (
        sequence_name(
            sequence(fide(STANDARD), national(STANDARD)),
            None,
            RatingPreference.HIGHEST,
        )
        == 'Highest of FIDE and national: FIDE list: standard → National list: '
        'national standard'
    )


@pytest.mark.unit
def test_a_typed_value_equal_to_the_prescribed_one_is_the_prescribed_one():
    """Nothing tells them apart, so it follows the player's category as the
    prescribed value does."""
    rating = resolve(
        ratings(standard=PlayerRating(manual=1399)),
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
        prescribed=1399,
    )
    assert (rating.value, rating.prescribed) == (1399, True)
    typed = resolve(
        ratings(standard=PlayerRating(manual=1450)),
        STANDARD,
        RatingPreference.FIDE_THEN_NATIONAL,
        FIDE_DEFAULT_SEQUENCES[STANDARD],
        prescribed=1399,
    )
    assert (typed.value, typed.prescribed) == (1450, False)


@pytest.mark.unit
def test_stored_sequences_spell_out_the_kinds_of_their_preference(tmp_path):
    from database.sqlite.event.migrations.m115_rating_sequence_entries import (
        Migration,
    )
    from database.sqlite.sqlite_database import SQLiteDatabase

    file = tmp_path / 'event.db'
    SQLiteDatabase(file, write=True)._create(
        'CREATE TABLE info (rating_preference INTEGER);'
        'CREATE TABLE tournament (id INTEGER PRIMARY KEY, '
        'rating_preference INTEGER, rating_sequence TEXT);'
        'CREATE TABLE player (id INTEGER PRIMARY KEY, ratings TEXT);'
        'CREATE TABLE player_period (id INTEGER PRIMARY KEY, ratings TEXT)'
    )
    with SQLiteDatabase(file, write=True) as database:
        database.execute('INSERT INTO info (rating_preference) VALUES (NULL)')
        database.executemany(
            'INSERT INTO tournament (rating_preference, rating_sequence) VALUES (?, ?)',
            [
                (None, '["fide:2", "fide:1", "national:2"]'),
                (3, '["fide:2", "national:2"]'),
                (4, '["fide:1", "national:1"]'),
                (2, '["national:2", "national:1"]'),
                (None, ''),
            ],
        )
        database.execute(
            'INSERT INTO player (ratings) VALUES (?)',
            ('{"1": {"fide": 1800, "national": 1700, "pinned": "n:national:1"}}',),
        )
        database.execute(
            'INSERT INTO player_period (ratings) VALUES (?)',
            ('{"2": {"fide": 1750, "pinned": "f:national:2"}}',),
        )
        migration = Migration(database)  # type: ignore[arg-type]
        migration.forward()
        database.execute('SELECT ratings FROM player_period')
        assert '"pinned": "national:f:2"' in database.fetchone()['ratings']
        database.execute('SELECT rating_sequence FROM tournament ORDER BY id')
        assert [row['rating_sequence'] for row in database.fetchall()] == [
            '["fide:2", "fide:1", "national:f:2"]',
            '["fide:2", "national:f:2", "national:n:2"]',
            '["national:n:1", "fide:1", "national:f:1"]',
            '["national:n:2", "national:n:1"]',
            '',
        ]
        database.execute('SELECT ratings FROM player')
        assert '"pinned": "national:n:1"' in database.fetchone()['ratings']
        migration.backward()
        database.execute('SELECT rating_sequence FROM tournament ORDER BY id')
        assert [row['rating_sequence'] for row in database.fetchall()][1] == (
            '["fide:2", "national:2"]'
        )
