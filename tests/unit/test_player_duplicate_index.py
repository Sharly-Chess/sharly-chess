from datetime import date

import pytest

from data.board import PlayerRatingType
from data.event import Event
from database.sqlite.event.event_store import StoredEvent, StoredPlayer


def make_event(*players: StoredPlayer) -> Event:
    return Event(
        StoredEvent(
            uniq_id='duplicate-test',
            name='Duplicate test',
            federation='FRA',
            player_rating_type=PlayerRatingType.FIDE.value,
            enabled_plugins=['ffe'],
            stored_players=list(players),
        )
    )


def player(id_: int, **kwargs) -> StoredPlayer:
    kwargs.setdefault('last_name', f'Player {id_}')
    return StoredPlayer(id=id_, **kwargs)


@pytest.mark.unit
@pytest.mark.parametrize(
    'players',
    [
        (
            player(1, fide_id=123),
            player(2, fide_id=123),
        ),
        (
            player(
                1, last_name='Name', first_name='First', date_of_birth=date(2000, 1, 2)
            ),
            player(
                2, last_name='Name', first_name='First', date_of_birth=date(2000, 1, 2)
            ),
        ),
        (
            player(1, plugin_data={'ffe': {'ffe_licence_number': 'A12345'}}),
            player(2, plugin_data={'ffe': {'ffe_licence_number': 'A12345'}}),
        ),
    ],
)
def test_has_multi_tournament_players_finds_indexed_duplicates(
    players: tuple[StoredPlayer, StoredPlayer],
):
    assert make_event(*players).has_multi_tournament_players


@pytest.mark.unit
def test_has_multi_tournament_players_does_not_merge_missing_first_names():
    birth_date = date(2000, 1, 2)
    event = make_event(
        player(1, last_name='Name', first_name=None, date_of_birth=birth_date),
        player(2, last_name='Name', first_name=None, date_of_birth=birth_date),
    )

    assert not event.has_multi_tournament_players


@pytest.mark.unit
def test_has_multi_tournament_players_ignores_distinct_players():
    event = make_event(
        *(
            player(
                id_,
                first_name=f'First {id_}',
                date_of_birth=date(2000, 1, 1),
                fide_id=1000 + id_,
                plugin_data={'ffe': {'ffe_licence_number': f'A{id_:05d}'}},
            )
            for id_ in range(1, 1001)
        )
    )

    assert not event.has_multi_tournament_players


@pytest.mark.unit
def test_duplicate_key_is_used_when_checking_one_player():
    event = make_event(player(1, plugin_data={'ffe': {'ffe_licence_number': 'A12345'}}))
    existing_player = next(iter(event.players))
    stored_player = player(2, plugin_data={'ffe': {'ffe_licence_number': 'A12345'}})

    assert event._are_player_duplicates(stored_player, existing_player)


@pytest.mark.unit
def test_identity_keys_recognise_a_player_entered_twice():
    # The same person in two tournaments is two player records with two
    # different ids, so carrying a score over has to match on identity.
    event = make_event()
    first = player(1, first_name='First', date_of_birth=date(2000, 1, 2), fide_id=42)
    second = player(2, first_name='First', date_of_birth=date(2000, 1, 2), fide_id=42)
    second.last_name = first.last_name

    keys = event.get_player_identity_keys(first)
    assert keys & event.get_player_identity_keys(second)
    assert ('fide', 42) in keys


@pytest.mark.unit
def test_identity_keys_ignore_a_name_without_a_first_name():
    event = make_event()
    stored_player = player(1, first_name=None, date_of_birth=date(2000, 1, 2))
    assert event.get_player_identity_keys(stored_player) == set()


@pytest.mark.unit
def test_identity_keys_include_the_ffe_licence_number():
    event = make_event()
    stored_player = player(1, plugin_data={'ffe': {'ffe_licence_number': 'A12345'}})
    assert any(
        key[0] == 'plugin' for key in event.get_player_identity_keys(stored_player)
    )
