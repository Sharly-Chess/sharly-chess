"""Tests for packed Molter recipe replay."""

from types import SimpleNamespace

from data.pairings.molter import MolterPairingSystem
from data.pairings.molter import MolterEngine
from data.pairings.molter_recipes import (
    available_molter_recipe_rounds,
    get_molter_recipe_table,
    iter_molter_recipe_tables,
    supported_molter_recipe_team_counts,
)
from data.pairings.molter_verifier import verify_molter_table


def test_molter_recipe_resource_declares_supported_range() -> None:
    assert supported_molter_recipe_team_counts() == tuple(range(3, 21))
    assert MolterPairingSystem().supported_team_counts() == tuple(range(3, 21))
    assert available_molter_recipe_rounds(20, 12) == tuple(range(1, 14))
    assert available_molter_recipe_rounds(21, 12) == ()


def test_molter_recipe_table_replays_and_validates() -> None:
    table = get_molter_recipe_table(9, 4, 4)

    assert table is not None
    assert table.team_count == 9
    assert table.players_per_team == 4
    assert len(table.rounds) == 4
    report = verify_molter_table(table)
    assert report.ok, report.errors


def test_molter_recipe_table_reports_max_rounds_for_known_shape() -> None:
    table = get_molter_recipe_table(20, 12, 14)

    assert table is not None
    assert len(table.rounds) == 13


def test_molter_recipe_table_returns_none_for_missing_shape() -> None:
    assert get_molter_recipe_table(21, 12, 1) is None
    assert get_molter_recipe_table(20, 14, 1) is None


def test_molter_recipe_tiled_candidates_respect_round_limit() -> None:
    engine = MolterEngine()
    supported = SimpleNamespace(rounds=13, rule_set=None)
    too_long = SimpleNamespace(rounds=14, rule_set=None)

    assert engine._candidate_player_counts(20, supported)
    assert engine._candidate_player_counts(20, too_long) == ()
    assert engine._max_candidate_round_count(20, too_long) == 13


def test_molter_engine_rejects_more_than_twenty_teams() -> None:
    teams = [
        SimpleNamespace(id=index, tournament_id=1, pairing_number=index)
        for index in range(1, 22)
    ]
    tournament = SimpleNamespace(
        id=1,
        event=SimpleNamespace(sorted_teams=teams),
        team_player_count=12,
    )

    message = MolterEngine().invalid_player_count_message(tournament)

    assert message is not None
    assert '20' in message


def test_all_molter_recipes_replay_and_validate() -> None:
    tables = iter_molter_recipe_tables()

    assert len(tables) == 1008
    for table in tables:
        report = verify_molter_table(table)
        assert report.ok, (
            table.team_count,
            table.players_per_team,
            len(table.rounds),
            report.errors,
        )
