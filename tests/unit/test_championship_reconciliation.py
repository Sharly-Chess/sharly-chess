"""Cross-event player reconciliation for a championship.

Builds two independent events whose tournaments share some players (by fide id
and by name+birth) and checks that a championship referencing both resolves them
into single reconciled players, including a manual merge override for a match
the automatic pass cannot make (a mistyped name with no fide id).
"""

from datetime import date

import pytest

from data.championship.championship_loader import ChampionshipLoader
from data.championship.scoring import aggregatable_tie_break_types
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer
from database.sqlite.championship.championship_database import ChampionshipDatabase
from tests.test_config import TestUtils


GP_ID = 'test-gp-circuit'
EVENT_A = 'test-gp-etape-a'
EVENT_B = 'test-gp-etape-b'


def _add_players(event_uniq_id: str, tournament_id: int, players: list[StoredPlayer]):
    event = EventLoader().load_event(event_uniq_id)
    tournament = event.tournaments_by_id[tournament_id]
    for stored_player in players:
        event.add_player(stored_player, [tournament])


def _ref(participation):
    return (
        participation.event_uniq_id,
        participation.tournament_id,
        participation.source_player_id,
    )


def _player_by_last_name(reconciled_players, last_name):
    return next(p for p in reconciled_players if p.last_name == last_name)


@pytest.fixture
def circuit():
    for event_uniq_id in (EVENT_A, EVENT_B):
        EventDatabase(event_uniq_id).file.unlink(missing_ok=True)
    ChampionshipDatabase(GP_ID).file.unlink(missing_ok=True)

    TestUtils.create_event(EVENT_A)
    tournament_a = TestUtils.create_tournament(EVENT_A, 'Etape 1').id
    TestUtils.create_event(EVENT_B)
    tournament_b = TestUtils.create_tournament(EVENT_B, 'Etape 2').id

    # Dupont: same fide id in both. Bernard: no fide, same name+birth in both.
    # Martin (A only) and Petit (B only) appear once. Rousseau is entered in A
    # and, mistyped and without a fide id, as "Rousseu" in B -> no auto match.
    _add_players(
        EVENT_A,
        tournament_a,
        [
            StoredPlayer(id=None, last_name='Dupont', first_name='Jean', fide_id=100),
            StoredPlayer(id=None, last_name='Martin', first_name='Alice', fide_id=200),
            StoredPlayer(
                id=None,
                last_name='Bernard',
                first_name='Luc',
                date_of_birth=date(2010, 5, 5),
            ),
            StoredPlayer(id=None, last_name='Rousseau', first_name='Pierre'),
        ],
    )
    _add_players(
        EVENT_B,
        tournament_b,
        [
            StoredPlayer(id=None, last_name='Dupont', first_name='Jean', fide_id=100),
            StoredPlayer(id=None, last_name='Petit', first_name='Marie', fide_id=300),
            StoredPlayer(
                id=None,
                last_name='Bernard',
                first_name='Luc',
                date_of_birth=date(2010, 5, 5),
            ),
            StoredPlayer(id=None, last_name='Rousseu', first_name='Pierre'),
        ],
    )

    ChampionshipDatabase(GP_ID).create()
    loader = ChampionshipLoader()
    loader.add_source(GP_ID, EVENT_A, tournament_a)
    loader.add_source(GP_ID, EVENT_B, tournament_b)

    yield GP_ID

    ChampionshipDatabase(GP_ID).file.unlink(missing_ok=True)
    for event_uniq_id in (EVENT_A, EVENT_B):
        EventDatabase(event_uniq_id).file.unlink(missing_ok=True)


def test_auto_match_groups_players_across_sources(circuit):
    players = ChampionshipLoader().load_championship(circuit).players

    # 6 distinct humans: Dupont, Martin, Bernard, Petit, Rousseau, Rousseu.
    assert len(players) == 6

    dupont = _player_by_last_name(players, 'Dupont')
    assert len(dupont.participations) == 2  # matched by fide id
    assert {p.event_uniq_id for p in dupont.participations} == {EVENT_A, EVENT_B}

    bernard = _player_by_last_name(players, 'Bernard')
    assert len(bernard.participations) == 2  # matched by name + birth

    martin = _player_by_last_name(players, 'Martin')
    assert len(martin.participations) == 1


def test_manual_merge_override_joins_mistyped_players(circuit):
    loader = ChampionshipLoader()
    players = loader.load_championship(circuit).players

    rousseau = _player_by_last_name(players, 'Rousseau')
    rousseu = _player_by_last_name(players, 'Rousseu')
    assert len(rousseau.participations) == 1
    assert len(rousseu.participations) == 1

    refs = [
        _ref(rousseau.participations[0]),
        _ref(rousseu.participations[0]),
    ]
    loader.merge_players(circuit, refs, group_key='rousseau-pierre')

    # Reload: the override persisted and the two are now one player.
    players = loader.load_championship(circuit).players
    assert len(players) == 5
    merged = _player_by_last_name(players, 'Rousseau')
    assert len(merged.participations) == 2


def test_clearing_override_restores_auto_match(circuit):
    loader = ChampionshipLoader()
    players = loader.load_championship(circuit).players
    rousseau = _player_by_last_name(players, 'Rousseau')
    rousseu = _player_by_last_name(players, 'Rousseu')
    ref_a, ref_b = _ref(rousseau.participations[0]), _ref(rousseu.participations[0])
    loader.merge_players(circuit, [ref_a, ref_b], group_key='rousseau-pierre')

    assert len(loader.load_championship(circuit).players) == 5

    loader.clear_player_override(circuit, *ref_a)
    loader.clear_player_override(circuit, *ref_b)
    assert len(loader.load_championship(circuit).players) == 6


def test_unmerge_clears_the_whole_manual_group(circuit):
    loader = ChampionshipLoader()
    players = loader.load_championship(circuit).players
    refs = [
        _ref(_player_by_last_name(players, last_name).participations[0])
        for last_name in ('Rousseau', 'Rousseu')
    ]
    loader.merge_players(circuit, refs, group_key='rousseau-pierre')

    assert len(loader.load_championship(circuit).players) == 5

    loader.clear_player_override_group(circuit, 'rousseau-pierre')

    assert len(loader.load_championship(circuit).players) == 6


def test_championship_rules_persist_and_ranking_runs(circuit):
    loader = ChampionshipLoader()
    rules = [('TOTAL_POINTS', 4), ('COUNT_WINS', 4), ('DIRECT_ENCOUNTER', None)]
    loader.set_championship_rules(circuit, rules)

    championship = loader.load_championship(circuit)
    assert [
        (rule.type, rule.best_n)
        for rule in championship.stored_championship.stored_championship_rules
    ] == rules

    ranking = championship.ranking
    # One ranking entry per reconciled player.
    assert len(ranking) == len(championship.players) == 6
    # No results were entered, so everyone is tied at the top.
    assert all(entry.rank == 1 and entry.tied for entry in ranking)


def test_aggregatable_tie_break_types_and_computed_rule(circuit):
    loader = ChampionshipLoader()
    championship = loader.load_championship(circuit)

    types = aggregatable_tie_break_types(championship.sources)
    ids = {tie_break_class.static_id() for tie_break_class in types}
    # Core aggregatable tie-breaks are offered even though the sample events
    # were not configured with them (we compute them ourselves).
    assert ids
    # Non-numeric tie-breaks are never offered.
    assert 'DIRECT_ENCOUNTER' not in ids
    assert 'MANUAL' not in ids

    # A sum-of-tie-break rule built from an available type computes without
    # error and still ranks every player (the compute + plugin-gating path).
    chosen = next(iter(types))
    loader.set_championship_rules(
        circuit,
        [
            ('TOTAL_POINTS', 4),
            (
                'SUM_TIE_BREAK',
                4,
                {'tie_break': {'type': chosen.static_id(), 'options': {}}},
            ),
        ],
    )
    championship = loader.load_championship(circuit)
    assert len(championship.ranking) == len(championship.players)
