from datetime import date

import pytest

from utils.enum import RatingPreference
from data.event import Event
from database.sqlite.event.event_store import StoredEvent, StoredPlayer
from database.sqlite.national.dsb_database import DsbDatabase
from database.sqlite.national.knsb_database import KnsbDatabase


def make_event(*players: StoredPlayer, federation: str = 'FRA') -> Event:
    return Event(
        StoredEvent(
            uniq_id='duplicate-test',
            name='Duplicate test',
            federation=federation,
            rating_preference=RatingPreference.FIDE.value,
            enabled_plugins=['ffe'] if federation == 'FRA' else [],
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
            player(1, national_id='A12345'),
            player(2, national_id='A12345'),
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
                national_id=f'A{id_:05d}',
            )
            for id_ in range(1, 1001)
        )
    )

    assert not event.has_multi_tournament_players


@pytest.mark.unit
def test_duplicate_key_is_used_when_checking_one_player():
    event = make_event(player(1, national_id='A12345'))
    existing_player = next(iter(event.players))
    stored_player = player(2, national_id='A12345')

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
@pytest.mark.parametrize('federation', ['FRA', 'NED'])
def test_identity_keys_include_the_national_identifier(federation: str):
    event = make_event(federation=federation)
    stored_player = player(1, national_id='12345')
    assert any(
        key[0] == 'national' and key[-1] == '12345'
        for key in event.get_player_identity_keys(stored_player)
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    'national_sources',
    [
        (None, None),
        (None, KnsbDatabase.national_source_id()),
        (KnsbDatabase.national_source_id(), KnsbDatabase.national_source_id()),
    ],
)
def test_a_national_identifier_alone_flags_a_duplicate(
    national_sources: tuple[str | None, str | None],
):
    first_source, second_source = national_sources
    event = make_event(
        player(1, national_id='12345', national_source=first_source),
        federation='NED',
    )
    existing_player = next(iter(event.players))
    stored_player = player(2, national_id='12345', national_source=second_source)

    assert event._are_player_duplicates(stored_player, existing_player)
    assert event.get_player_identity_keys(
        stored_player
    ) & event.get_player_identity_keys(existing_player.stored_player)


@pytest.mark.unit
def test_has_multi_tournament_players_finds_national_identifiers():
    event = make_event(
        player(1, national_id='12345'),
        player(
            2, national_id='12345', national_source=KnsbDatabase.national_source_id()
        ),
        federation='NED',
    )

    assert event.has_multi_tournament_players


@pytest.mark.unit
@pytest.mark.parametrize(
    'national_sources',
    [
        (KnsbDatabase.national_source_id(), DsbDatabase.national_source_id()),
        (None, DsbDatabase.national_source_id()),
    ],
)
def test_identifiers_of_different_federations_are_not_duplicates(
    national_sources: tuple[str | None, str | None],
):
    first_source, second_source = national_sources
    first = player(1, national_id='12345', national_source=first_source)
    second = player(2, national_id='12345', national_source=second_source)
    event = make_event(first, second, federation='NED')
    existing_player = event.players_by_id[1]

    assert not event._are_player_duplicates(second, existing_player)
    assert not event.get_player_identity_keys(first) & event.get_player_identity_keys(
        second
    )
    assert not event.has_multi_tournament_players
