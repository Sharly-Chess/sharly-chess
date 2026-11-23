"""The round-robin pairings document numbers a team's fixed table on the
rounds it prints, including the rounds not paired yet.

The document prints every round at once, the future ones from the computed
schedule rather than from stored boards. Those future rounds must place a
fixed team on its table just as the pairing will, or the printed schedule
would disagree with itself from the first round paired.
"""

import contextlib
from unittest import TestCase

import pytest

from data.loader import EventLoader
from data.print_documents.documents import RoundRobinSchedulePrintDocument
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType


EVENT_ID = 'test-team-fixed-table-document'
TOURNAMENT_NAME = 'rr'
N = 2
TEAMS = 4


@pytest.mark.unit
class TeamFixedTableDocumentTestCase(TestCase):
    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _create(self) -> None:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': TEAMS - 1,
                'team_player_count': N,
                'pairing': 'TEAM_ROUND_ROBIN_BERGER',
            },
        )
        self.team_ids: list[int] = []
        with EventDatabase(EVENT_ID, write=True) as db:
            tournament = next(
                t for t in db.load_stored_tournaments() if t.name == TOURNAMENT_NAME
            )
            tid = tournament.id
            assert tid is not None
            for seed in range(1, TEAMS + 1):
                team_id = db.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team{seed}',
                        tournament_id=tid,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                self.team_ids.append(team_id)
                for p_index in range(N):
                    pid = db.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{p_index}',
                            team_id=team_id,
                            team_index=p_index,
                            check_in=True,
                        )
                    )
                    db.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tid, player_id=pid, pairing_number=p_index
                        )
                    )

    def _load(self):
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]

    def test_future_rounds_place_the_fixed_team_on_its_table(self):
        self._create()

        # Pin the first team to table 2, and pair nothing. The first team
        # heads the schedule, so without the pin it would print on table 1.
        tournament = self._load()
        pinned = self.team_ids[0]
        pinned_name = tournament.event.teams_by_id[pinned].name
        with EventDatabase(EVENT_ID, write=True) as db:
            team = tournament.event.teams_by_id[pinned]
            team.stored_team.fixed = 2
            team.update(db)

        tournament = self._load()
        engine = tournament.pairing_variation.engine
        rounds_data = RoundRobinSchedulePrintDocument._team_rounds_data(
            tournament, engine, tournament.rounds
        )

        # Nothing is paired, so every round is drawn from the schedule.
        for round_data in rounds_data:
            numbers = [m['number'] for m in round_data['matches']]
            # Two matches a round, numbered compactly as 1 and 2.
            self.assertEqual(sorted(numbers), ['1', '2'])
            pinned_match = next(
                m
                for m in round_data['matches']
                if pinned_name in (m['left'], m['right'])
            )
            self.assertEqual(
                pinned_match['number'],
                '2',
                f'round {round_data["number"]} should seat the pinned team '
                'at its fixed table',
            )
