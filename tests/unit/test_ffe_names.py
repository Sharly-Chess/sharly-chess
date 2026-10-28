"""The names the _FFE_ database cut at their length or abbreviated with a
dot, as both the installed copy and the online server hold them."""

from datetime import date

import pytest

from database.sqlite.event.event_store import StoredPlayer
from plugins.ffe.utils import (
    ffe_cut_name_matches,
    ffe_held_name_matches,
    ffe_name,
    ffe_name_key_matches,
)


def test_names_are_compared_as_cut_by_the_database() -> None:
    assert ffe_name(' Loustalot-Barbe Sergent ') == 'LOUSTALOT-BARBE SERG'
    assert ffe_name('De La Fourniere De Saint-Pern') == 'DE LA FOURNIERE DE S'
    assert ffe_name('Hélène') == 'HELENE'


@pytest.mark.parametrize(
    ('held_name', 'name', 'matches'),
    [
        ('DUPONT', 'Dupont', True),
        ('MERCIER-PIQUEM.', 'Mercier-Piquemal', True),
        ('Odalric-Amb.', 'Odalric-Ambroise', True),
        ('Vladimir Serg.', 'Vladimir Sergeevich', True),
        ('MERCIER-PIQUEM.', 'Mercier', False),
        ('MERCIER-PIQUEM.', 'Mercier-Durand', False),
        # Too short to tell the names it starts apart
        ('M.', 'Martin', False),
    ],
)
def test_held_names_match_whole_cut_or_abbreviated(
    held_name: str, name: str, matches: bool
) -> None:
    assert ffe_held_name_matches(held_name, name) is matches


def test_name_keys_match_abbreviated_names_born_the_same_day() -> None:
    ffe_player = StoredPlayer(
        id=None,
        last_name='MERCIER-PIQUEM.',
        first_name='Mathieu',
        date_of_birth=date(1991, 6, 3),
    )
    assert ffe_name_key_matches(
        ('MERCIER-PIQUEMAL', 'MATHIEU', date(1991, 6, 3)), ffe_player
    )
    assert ffe_name_key_matches(('MERCIER-PIQUEMAL', 'MATHIEU', 1991), ffe_player)
    assert not ffe_name_key_matches(
        ('MERCIER-PIQUEMAL', 'MATHIEU', date(1991, 6, 4)), ffe_player
    )


@pytest.mark.parametrize(
    ('held_name', 'word', 'min_tail_length', 'matches'),
    [
        # Cut at the length of the names
        ('CHAUVET TROMMENSCHLA', 'TROMMENSCHLAGER', 2, True),
        ('LOUSTALOT-BARBE SERG', 'SERGENT', 2, True),
        ('LOUSTALOT-BARBE-SERG', 'SERGENT', 2, True),
        ('DE LA FOURNIERE DE S', 'SAINT', 1, True),
        ('DE LA FOURNIERE DE S', 'SAINT', 2, False),
        ('CHAUVET TROMMENSCHLA', 'CHAUVET', 2, False),
        # A name ending with a hyphen has no tail
        ('CORVISIERCHRISTOPHE-', 'DUPONT', 1, False),
        # Abbreviated with a dot
        ('MERCIER-PIQUEM.', 'PIQUEMAL', 1, True),
        ('MERCIER-PIQUEM.', 'MERCIER-PIQUEMAL', 2, True),
        ('Vladimir Serg.', 'SERGEEVICH', 1, True),
        # Titles and initials end with a dot too
        ('Clemens Dr.', 'DREYFUS', 1, False),
        ('Gardy S.', 'SMITH', 1, False),
        ('M.', 'MERCIER-PIQUEMAL', 2, False),
        ('G.', 'GUYONNET-BENIZE', 1, False),
    ],
)
def test_searched_words_run_past_the_end_of_cut_names(
    held_name: str, word: str, min_tail_length: int, matches: bool
) -> None:
    assert ffe_cut_name_matches(held_name, word, min_tail_length, True, True) is (
        matches
    )


def test_cut_names_only_match_the_searches_their_rules_apply_to() -> None:
    assert not ffe_cut_name_matches(
        'CHAUVET TROMMENSCHLA', 'TROMMENSCHLAGER', 2, False, True
    )
    assert not ffe_cut_name_matches('MERCIER-PIQUEM.', 'PIQUEMAL', 1, True, False)
