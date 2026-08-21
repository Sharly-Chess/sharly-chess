"""End-to-end Championship aggregation for team tournaments."""

import pytest

from data.championship.championship_loader import ChampionshipLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredBoard,
    StoredPairing,
    StoredPlayer,
    StoredTeam,
    StoredTeamBoard,
    StoredTournamentPlayer,
)
from database.sqlite.championship.championship_database import ChampionshipDatabase
from tests.test_config import TestUtils
from utils.enum import EventType, Result, ScoreType


GP_ID = 'test-team-championship'
EVENT_A = 'test-team-championship-a'
EVENT_B = 'test-team-championship-b'


def _seed_team_stage(event_id: str, primary_score: ScoreType) -> int:
    TestUtils.create_event(event_id, overrides={'event_type': EventType.TEAM})
    tournament = TestUtils.create_tournament(
        event_id,
        'Stage',
        overrides={
            'rounds': 1,
            'current_round': 1,
            'team_player_count': 1,
            'pairing': 'TEAM_SWISS_STANDARD',
            'primary_score': primary_score.value,
        },
    )
    assert tournament.id is not None
    with EventDatabase(event_id, write=True) as database:
        alpha_id = database.add_stored_team(
            StoredTeam(
                id=None,
                name='Alpha',
                federation='FRA',
                tournament_id=tournament.id,
            )
        )
        bravo_id = database.add_stored_team(
            StoredTeam(
                id=None,
                name='Bravo',
                federation='FRA',
                tournament_id=tournament.id,
            )
        )

        def add_player(name: str, team_id: int, pairing_number: int) -> int:
            player_id = database.add_stored_player(
                StoredPlayer(id=None, last_name=name, team_id=team_id, team_index=0)
            )
            database.add_stored_tournament_player(
                StoredTournamentPlayer(
                    tournament_id=tournament.id,
                    player_id=player_id,
                    pairing_number=pairing_number,
                )
            )
            return player_id

        alpha_player_id = add_player('Alpha player', alpha_id, 1)
        bravo_player_id = add_player('Bravo player', bravo_id, 2)
        team_board_id = database.add_stored_team_board(
            StoredTeamBoard(
                id=None,
                tournament_id=tournament.id,
                round_=1,
                team_a_id=alpha_id,
                team_b_id=bravo_id,
                index=0,
            )
        )
        board_id = database.add_stored_board(
            StoredBoard(
                id=None,
                white_player_id=alpha_player_id,
                black_player_id=bravo_player_id,
                index=0,
                team_board_id=team_board_id,
            )
        )
        database.add_stored_pairing(
            StoredPairing(
                tournament_id=tournament.id,
                player_id=alpha_player_id,
                round_=1,
                result=Result.WIN.value,
                board_id=board_id,
            )
        )
        database.add_stored_pairing(
            StoredPairing(
                tournament_id=tournament.id,
                player_id=bravo_player_id,
                round_=1,
                result=Result.LOSS.value,
                board_id=board_id,
            )
        )
    return tournament.id


@pytest.fixture
def team_championship():
    for event_id in (EVENT_A, EVENT_B):
        EventDatabase(event_id).file.unlink(missing_ok=True)
    ChampionshipDatabase(GP_ID).file.unlink(missing_ok=True)

    tournament_a = _seed_team_stage(EVENT_A, ScoreType.MATCH_POINTS)
    tournament_b = _seed_team_stage(EVENT_B, ScoreType.GAME_POINTS)
    loader = ChampionshipLoader()
    championship_id = loader.create_championship(GP_ID, competitor_type='TEAM')
    loader.add_source(championship_id, EVENT_A, tournament_a)
    loader.add_source(championship_id, EVENT_B, tournament_b)

    yield championship_id

    ChampionshipDatabase(championship_id).file.unlink(missing_ok=True)
    for event_id in (EVENT_A, EVENT_B):
        EventDatabase(event_id).file.unlink(missing_ok=True)


def _team_by_name(championship, name):
    return next(team for team in championship.teams if team.name == name)


def test_team_sources_reconcile_teams_not_roster_players(team_championship):
    championship = ChampionshipLoader().load_championship(team_championship)

    assert championship.competitor_type == 'TEAM'
    assert len(championship.competitors) == len(championship.teams) == 2
    assert {team.name for team in championship.teams} == {'Alpha', 'Bravo'}
    assert all(len(team.participations) == 2 for team in championship.teams)
    with pytest.raises(RuntimeError, match='teams, not ranked players'):
        _ = championship.players


def test_team_score_basis_source_primary_match_points_and_game_points(
    team_championship,
):
    loader = ChampionshipLoader()
    loader.set_championship_rules(team_championship, [('TOTAL_POINTS', None)])

    championship = loader.load_championship(team_championship)
    alpha = _team_by_name(championship, 'Alpha')
    assert [p.points(championship.team_score_basis) for p in alpha.participations] == [
        2.0,
        1.0,
    ]
    assert championship.ranking[0].competitor.name == 'Alpha'

    loader.set_team_score_basis(team_championship, 'MATCH_POINTS')
    championship = loader.load_championship(team_championship)
    alpha = _team_by_name(championship, 'Alpha')
    assert [p.points(championship.team_score_basis) for p in alpha.participations] == [
        2.0,
        2.0,
    ]

    loader.set_team_score_basis(team_championship, 'GAME_POINTS')
    championship = loader.load_championship(team_championship)
    alpha = _team_by_name(championship, 'Alpha')
    assert [p.points(championship.team_score_basis) for p in alpha.participations] == [
        1.0,
        1.0,
    ]


def test_team_match_wins_and_direct_encounter(team_championship):
    loader = ChampionshipLoader()
    loader.set_championship_rules(
        team_championship,
        [('COUNT_WINS', None), ('DIRECT_ENCOUNTER', None)],
    )

    championship = loader.load_championship(team_championship)
    alpha = _team_by_name(championship, 'Alpha')
    bravo = _team_by_name(championship, 'Bravo')
    assert sum(p.wins for p in alpha.participations) == 2
    assert sum(p.wins for p in bravo.participations) == 0
    assert championship.ranking[0].competitor.name == 'Alpha'

    loader.set_championship_rules(team_championship, [('DIRECT_ENCOUNTER', None)])
    assert (
        loader.load_championship(team_championship).ranking[0].competitor.name
        == 'Alpha'
    )


def test_manual_team_merge_handles_a_renamed_team(team_championship):
    with EventDatabase(EVENT_B, write=True) as database:
        alpha = next(
            team for team in database.load_stored_teams() if team.name == 'Alpha'
        )
        alpha.name = 'Alpha Juniors'
        database.update_stored_team(alpha)

    loader = ChampionshipLoader()
    championship = loader.load_championship(team_championship)
    assert len(championship.teams) == 3
    alpha = _team_by_name(championship, 'Alpha')
    alpha_juniors = _team_by_name(championship, 'Alpha Juniors')
    refs = [
        (
            participation.event_uniq_id,
            participation.tournament_id,
            participation.source_competitor_id,
        )
        for team in (alpha, alpha_juniors)
        for participation in team.participations
    ]
    loader.merge_teams(team_championship, refs, group_key='alpha')

    merged = loader.load_championship(team_championship)
    assert len(merged.teams) == 2
    assert len(_team_by_name(merged, 'Alpha').participations) == 2

    loader.clear_team_override_group(team_championship, 'alpha')
    assert len(loader.load_championship(team_championship).teams) == 3


def test_individual_source_is_rejected_by_team_championship(team_championship):
    TestUtils.create_event('test-individual-source')
    tournament = TestUtils.create_tournament('test-individual-source', 'Individual')
    try:
        with pytest.raises(ValueError, match='individual tournament'):
            ChampionshipLoader().add_source(
                team_championship, 'test-individual-source', tournament.id
            )
    finally:
        EventDatabase('test-individual-source').file.unlink(missing_ok=True)
