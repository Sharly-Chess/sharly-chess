"""A player or a team that has been paired can no longer be deleted."""

import contextlib

import pytest

from common.exception import PairedDeletionError
from data.event import Event
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType

INDIVIDUAL_EVENT_ID = 'test-paired-deletion-individual'
TEAM_EVENT_ID = 'test-paired-deletion-team'


def _load(uniq_id: str) -> Event:
    with contextlib.suppress(KeyError):
        EventLoader.unload_event(uniq_id)
    return EventLoader().load_event(uniq_id)


@pytest.mark.unit
class TestPairedPlayerDeletion:
    """A player entered in two tournaments, who plays only in the second."""

    def setup_method(self) -> None:
        TestUtils.create_event(INDIVIDUAL_EVENT_ID)
        tournament_ids = [
            TestUtils.create_tournament(
                INDIVIDUAL_EVENT_ID,
                name,
                overrides={'rounds': 3, 'pairing': 'SWISS_STANDARD'},
            ).id
            for name in ('First', 'Second')
        ]
        with EventDatabase(INDIVIDUAL_EVENT_ID, write=True) as database:

            def add_player(last_name: str, tournament_ids: list) -> int:
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=last_name,
                        first_name='Test',
                        ratings={1: {'standard': 2000}},
                    )
                )
                for tournament_id in tournament_ids:
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id, player_id=player_id
                        )
                    )
                return player_id

            self.shared_id = add_player('SHARED', tournament_ids)
            for last_name in ('BRAVO', 'CHARLIE', 'DELTA'):
                add_player(last_name, tournament_ids[1:])
            self.unpaired_id = add_player('ECHO', tournament_ids[:1])
        # A Tournament holds its event weakly, so the event is kept here.
        event = _load(INDIVIDUAL_EVENT_ID)
        assert event.tournaments_by_name['Second'].generate_round_pairings(1) == ''

    def teardown_method(self) -> None:
        TestUtils.delete_event(INDIVIDUAL_EVENT_ID)

    def test_a_player_paired_in_any_tournament_cannot_be_deleted(self) -> None:
        event = _load(INDIVIDUAL_EVENT_ID)
        player = event.players_by_id[self.shared_id]
        assert player.paired_tournament is event.tournaments_by_name['Second']
        with pytest.raises(PairedDeletionError):
            event.delete_player(player)
        assert self.shared_id in _load(INDIVIDUAL_EVENT_ID).players_by_id

    def test_a_player_never_paired_can_be_deleted(self) -> None:
        event = _load(INDIVIDUAL_EVENT_ID)
        event.delete_player(event.players_by_id[self.unpaired_id])
        assert self.unpaired_id not in _load(INDIVIDUAL_EVENT_ID).players_by_id


@pytest.mark.unit
class TestPairedTeamDeletion:
    BOARDS = 4

    def setup_method(self) -> None:
        TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
        tournament_id = TestUtils.create_tournament(
            TEAM_EVENT_ID,
            'tournament',
            overrides={
                'rounds': 3,
                'team_player_count': self.BOARDS,
                'pairing': 'TEAM_SWISS_STANDARD',
            },
        ).id
        self.team_ids: list[int] = []
        with EventDatabase(TEAM_EVENT_ID, write=True) as database:
            for seed in range(1, 5):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                self.team_ids.append(team_id)
                for index in range(self.BOARDS):
                    player_id = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{index}',
                            team_id=team_id,
                            team_index=index,
                            check_in=True,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_id,
                            pairing_number=(seed - 1) * self.BOARDS + index + 1,
                        )
                    )

    def teardown_method(self) -> None:
        TestUtils.delete_event(TEAM_EVENT_ID)

    def test_a_team_not_yet_paired_can_be_deleted(self) -> None:
        event = _load(TEAM_EVENT_ID)
        event.delete_team(event.teams_by_id[self.team_ids[0]])
        assert self.team_ids[0] not in _load(TEAM_EVENT_ID).teams_by_id

    def test_a_paired_team_cannot_be_deleted(self) -> None:
        event = _load(TEAM_EVENT_ID)
        assert event.tournaments_by_name['tournament'].generate_round_pairings(1) == ''
        event = _load(TEAM_EVENT_ID)
        team = event.teams_by_id[self.team_ids[0]]
        with pytest.raises(PairedDeletionError):
            event.delete_team(team)
        assert self.team_ids[0] in _load(TEAM_EVENT_ID).teams_by_id
