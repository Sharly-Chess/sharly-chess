"""Championship scoring engine tests.

These exercise the pure ranking engine with light fakes standing in for the
source tournaments, so the rule semantics are tested without a database:
best-N-by-points selection, win counting on the points-selected stages, direct
encounter across stages, and a mixed ordered rule chain (the Circuit's Art. 6).
"""

from types import SimpleNamespace
from typing import Any, cast

from data.championship.reconciliation import (
    ReconciledParticipation as _RP,
)
from data.championship.reconciliation import (
    ReconciledPlayer,
)
from data.championship.scoring import (
    CountWinsRule,
    DirectEncounterRule,
    ScoringContext,
    TotalPointsRule,
    rank_competitors,
    rank_players,
)


def _rp(source, tp):
    """Build a participation from the light test fakes (cast to the real types)."""
    return _RP(cast(Any, source), cast(Any, tp))


class FakePairing:
    def __init__(self, win=False, opponent_id=None, points=0.0, played=True):
        self.win = win
        self.opponent_id = opponent_id
        self.points = points
        self.played = played


class FakeTournamentPlayer:
    def __init__(
        self,
        player_id,
        points,
        pairings=None,
        fide_id=None,
        date_of_birth=None,
        last_name='Doe',
        first_name='John',
        rank=0,
    ):
        self.id = player_id
        self.points = points
        self.rank = rank
        self.pairings_by_round = dict(enumerate(pairings or [], start=1))
        self.fide_id = fide_id
        self.date_of_birth = date_of_birth
        self.last_name = last_name
        self.first_name = first_name


class FakeTournament:
    def ensure_tournament_player_ranks_computed(self):
        pass


class FakeSource:
    def __init__(self, event_uniq_id, tournament_id):
        self.event_uniq_id = event_uniq_id
        self.tournament_id = tournament_id
        self.tournament = FakeTournament()
        self.event = None


def player(name, stages):
    """A reconciled player from ``stages`` = list of FakeTournamentPlayer, one
    per source. Each stage gets its own fake source."""
    participations = [
        _rp(FakeSource(f'{name}-ev{i}', i), tournament_player)
        for i, tournament_player in enumerate(stages, start=1)
    ]
    return ReconciledPlayer(participations)


def order(groups):
    """Flatten ranked tie-groups to the representative last names, keeping ties
    as nested lists so equal ranks are visible."""
    return [
        group[0].last_name if len(group) == 1 else [p.last_name for p in group]
        for group in groups
    ]


def test_total_points_best_n_ignores_worst_stages():
    a = player(
        'A',
        [
            FakeTournamentPlayer(1, 5, last_name='A'),
            FakeTournamentPlayer(2, 4, last_name='A'),
            FakeTournamentPlayer(3, 0, last_name='A'),
        ],
    )
    b = player(
        'B',
        [
            FakeTournamentPlayer(1, 5, last_name='B'),
            FakeTournamentPlayer(2, 3, last_name='B'),
            FakeTournamentPlayer(3, 3, last_name='B'),
        ],
    )
    # Best 2 stages: A = 9, B = 8 -> A first.
    assert order(rank_players([b, a], [TotalPointsRule(best_n=2)])) == ['A', 'B']
    # All stages: A = 9, B = 11 -> B first. best_n changes the outcome.
    assert order(rank_players([a, b], [TotalPointsRule(best_n=None)])) == ['B', 'A']


def test_count_wins_selects_best_stage_by_wins():
    # Best-N selection follows the configured rule chain, so a CountWins rule
    # picks each competitor's most-wins stage (not its most-points stage). C's
    # high-win stage is its low-points stage, and it is the one kept.
    c = player(
        'C',
        [
            FakeTournamentPlayer(1, 5, pairings=[], last_name='C'),
            FakeTournamentPlayer(
                1, 1, pairings=[FakePairing(win=True)] * 3, last_name='C'
            ),
        ],
    )
    d = player(
        'D',
        [
            FakeTournamentPlayer(1, 5, pairings=[FakePairing(win=True)], last_name='D'),
        ],
    )
    ranked = rank_players([c, d], [CountWinsRule(best_n=1)])
    # C keeps its 3-win stage, D has 1 win -> C first.
    assert order(ranked) == ['C', 'D']


def test_best_stage_points_tie_broken_by_wins():
    # Two stages tied on points: best-1-by-points keeps the higher-win one, so
    # the selection is deterministic and favours the competitor's strongest
    # stage rather than an arbitrary source order.
    a = player(
        'A',
        [
            FakeTournamentPlayer(1, 4, pairings=[], last_name='A'),
            FakeTournamentPlayer(
                1, 4, pairings=[FakePairing(win=True)] * 2, last_name='A'
            ),
        ],
    )
    b = player(
        'B',
        [FakeTournamentPlayer(1, 4, pairings=[FakePairing(win=True)], last_name='B')],
    )
    ranked = rank_players([a, b], [CountWinsRule(best_n=1)])
    # A's kept stage is the 2-win one (points tie broken by wins) -> A beats B.
    assert order(ranked) == ['A', 'B']


def test_direct_encounter_breaks_a_points_tie():
    # E and F meet in a shared stage (same source): E beats F.
    shared_source = FakeSource('shared-ev', 1)
    e_tp = FakeTournamentPlayer(
        10,
        3,
        pairings=[FakePairing(win=True, opponent_id=20, points=1.0)],
        last_name='E',
    )
    f_tp = FakeTournamentPlayer(
        20,
        3,
        pairings=[FakePairing(win=False, opponent_id=10, points=0.0)],
        last_name='F',
    )
    e = ReconciledPlayer([_rp(shared_source, e_tp)])
    f = ReconciledPlayer([_rp(shared_source, f_tp)])

    direct_encounter = DirectEncounterRule()
    context = ScoringContext([f, e])
    scores = direct_encounter.scores([f, e], context)
    assert scores == {id(f): 0.0, id(e): 1.0}

    rules = [TotalPointsRule(), direct_encounter]
    assert order(rank_players([f, e], rules)) == ['E', 'F']


def test_direct_encounter_excludes_forfeit_games():
    # E "beat" F only by forfeit. A forfeit is not a game played over the
    # board, so it does not count for the direct encounter and the tie stands.
    shared_source = FakeSource('shared-ev', 1)
    e_tp = FakeTournamentPlayer(
        10,
        3,
        pairings=[FakePairing(win=True, opponent_id=20, points=1.0, played=False)],
        last_name='E',
    )
    f_tp = FakeTournamentPlayer(
        20,
        3,
        pairings=[FakePairing(win=False, opponent_id=10, points=0.0, played=False)],
        last_name='F',
    )
    e = ReconciledPlayer([_rp(shared_source, e_tp)])
    f = ReconciledPlayer([_rp(shared_source, f_tp)])

    direct_encounter = DirectEncounterRule()
    context = ScoringContext([f, e])
    # No game counts -> the rule cannot separate them.
    assert direct_encounter.scores([f, e], context) is None

    ranked = rank_players([f, e], [TotalPointsRule(), direct_encounter])
    assert len(ranked) == 1
    assert sorted(p.last_name for p in ranked[0]) == ['E', 'F']


class FakeTeamParticipation:
    """A team's encounters in one source, with distinct primary/secondary
    scores so the extended direct encounter can be exercised."""

    has_secondary_score = True

    def __init__(self, competitor_id, primary, secondary, event='ev', tournament_id=1):
        self.event_uniq_id = event
        self.tournament_id = tournament_id
        self.source_competitor_id = competitor_id
        # A team participation is not tied to a source tournament here (no
        # tie-break computation is needed for the direct encounter).
        self.source = SimpleNamespace(tournament=None)
        self._primary = primary
        self._secondary = secondary

    def encounters(self, _team_score_basis, secondary=False):
        yield from (self._secondary if secondary else self._primary)


class FakeTeam:
    def __init__(self, name, participation):
        self.name = name
        self.participations = [participation]


def test_extended_direct_encounter_falls_back_to_secondary_score_for_teams():
    # Alpha and Bravo drew their match on match points (the primary score) but
    # Alpha won it on game points: EDE (Art. 13.3.1) reapplies the rule with
    # the secondary score and ranks Alpha first.
    alpha: Any = FakeTeam(
        'Alpha',
        FakeTeamParticipation(1, primary=[(2, 1.0)], secondary=[(2, 2.5)]),
    )
    bravo: Any = FakeTeam(
        'Bravo',
        FakeTeamParticipation(2, primary=[(1, 1.0)], secondary=[(1, 1.5)]),
    )

    de = DirectEncounterRule()
    context = ScoringContext([alpha, bravo])
    # The primary score leaves them tied (1 match point each).
    assert de.score_ranges([alpha, bravo], context) == {
        id(alpha): (1.0, 1.0),
        id(bravo): (1.0, 1.0),
    }

    ranked = cast(list[list[Any]], rank_competitors([bravo, alpha], [de]))
    assert [group[0].name for group in ranked] == ['Alpha', 'Bravo']


def test_extended_direct_encounter_leaves_teams_tied_when_both_scores_level():
    # Match drawn on both match points and game points -> EDE cannot separate.
    alpha: Any = FakeTeam(
        'Alpha',
        FakeTeamParticipation(1, primary=[(2, 1.0)], secondary=[(2, 2.0)]),
    )
    bravo: Any = FakeTeam(
        'Bravo',
        FakeTeamParticipation(2, primary=[(1, 1.0)], secondary=[(1, 2.0)]),
    )
    ranked = cast(
        list[list[Any]], rank_competitors([alpha, bravo], [DirectEncounterRule()])
    )
    assert len(ranked) == 1
    assert sorted(team.name for team in ranked[0]) == ['Alpha', 'Bravo']


def test_direct_encounter_uses_games_from_stages_dropped_by_best_n():
    # Each player's best-1-by-points stage is a 6-point solo stage; they only
    # met in a 2-point stage that best-N drops. DE scans *all* participations,
    # not the best-N subset, so it still finds and uses that game.
    e_high = FakeSource('e-high', 1)
    f_high = FakeSource('f-high', 1)
    shared = FakeSource('shared', 2)
    e = ReconciledPlayer(
        [
            _rp(e_high, FakeTournamentPlayer(1, 6, last_name='E')),
            _rp(
                shared,
                FakeTournamentPlayer(
                    10,
                    2,
                    pairings=[FakePairing(win=True, opponent_id=20, points=1.0)],
                    last_name='E',
                ),
            ),
        ]
    )
    f = ReconciledPlayer(
        [
            _rp(f_high, FakeTournamentPlayer(1, 6, last_name='F')),
            _rp(
                shared,
                FakeTournamentPlayer(
                    20,
                    2,
                    pairings=[FakePairing(win=False, opponent_id=10, points=0.0)],
                    last_name='F',
                ),
            ),
        ]
    )
    # Tied on best-1 points (6 each); DE breaks it with the dropped-stage game.
    rules = [TotalPointsRule(best_n=1), DirectEncounterRule()]
    assert order(rank_players([f, e], rules)) == ['E', 'F']


def test_direct_encounter_leaves_untouched_when_never_met():
    g = player('G', [FakeTournamentPlayer(1, 3, last_name='G')])
    h = player('H', [FakeTournamentPlayer(1, 3, last_name='H')])
    # Equal points, no game between them -> still a tie after DE.
    ranked = rank_players([g, h], [TotalPointsRule(), DirectEncounterRule()])
    assert len(ranked) == 1
    assert sorted(p.last_name for p in ranked[0]) == ['G', 'H']


def test_direct_encounter_does_not_treat_an_unplayed_game_as_a_loss():
    shared_source = FakeSource('shared-ev', 1)
    e = ReconciledPlayer(
        [
            _rp(
                shared_source,
                FakeTournamentPlayer(
                    10,
                    3,
                    pairings=[
                        FakePairing(opponent_id=20, points=0.5),
                        FakePairing(opponent_id=30, points=1.0),
                    ],
                    last_name='E',
                ),
            )
        ]
    )
    f = ReconciledPlayer(
        [
            _rp(
                shared_source,
                FakeTournamentPlayer(
                    20,
                    3,
                    pairings=[FakePairing(opponent_id=10, points=0.5)],
                    last_name='F',
                ),
            )
        ]
    )
    g = ReconciledPlayer(
        [
            _rp(
                shared_source,
                FakeTournamentPlayer(
                    30,
                    3,
                    pairings=[FakePairing(opponent_id=10, points=0.0)],
                    last_name='G',
                ),
            )
        ]
    )
    context = ScoringContext([e, f, g])
    direct_encounter = DirectEncounterRule()

    assert direct_encounter.score_ranges([e, f, g], context) == {
        id(e): (1.5, 1.5),
        id(f): (0.5, 1.5),
        id(g): (0.0, 1.0),
    }
    assert direct_encounter.split([e, f, g], context) == [[e, f, g]]


def test_incomplete_direct_encounter_falls_through_to_later_best_n_rules():
    sources = [FakeSource(f'stage-{index}', 1) for index in range(1, 7)]

    def circuit_player(last_name, player_id, stage_points, pairings_by_stage):
        return ReconciledPlayer(
            [
                _rp(
                    sources[index],
                    FakeTournamentPlayer(
                        player_id,
                        points,
                        pairings=pairings_by_stage.get(index),
                        last_name=last_name,
                    ),
                )
                for index, points in enumerate(stage_points)
                if points is not None
            ]
        )

    sauzon = circuit_player(
        'SAUZON',
        10,
        [5, 6, 6, 6, None, 5],
        {
            0: [FakePairing(opponent_id=20, points=0.0)],
            1: [FakePairing(opponent_id=20, points=1.0)],
            2: [FakePairing(opponent_id=30, points=1.0)],
        },
    )
    murer = circuit_player(
        'MURER',
        20,
        [6, 5, 5, 6, 6, 4],
        {
            0: [FakePairing(opponent_id=10, points=1.0)],
            1: [FakePairing(opponent_id=10, points=0.0)],
        },
    )
    dupont = circuit_player(
        'DUPONT',
        30,
        [6, 6, 6, 5],
        {2: [FakePairing(opponent_id=10, points=0.0)]},
    )

    rules = [
        TotalPointsRule(best_n=4),
        DirectEncounterRule(),
        TotalPointsRule(best_n=5),
        TotalPointsRule(best_n=6),
    ]
    assert order(rank_players([sauzon, murer, dupont], rules)) == [
        'MURER',
        'SAUZON',
        'DUPONT',
    ]


def test_ranking_assigns_shared_positions_for_true_ties():
    g = player('G', [FakeTournamentPlayer(1, 3, last_name='G')])
    h = player('H', [FakeTournamentPlayer(1, 3, last_name='H')])
    top = player('T', [FakeTournamentPlayer(1, 9, last_name='T')])
    groups = rank_players([g, h, top], [TotalPointsRule()])
    # Winner alone, then G and H tied together.
    assert order(groups) == ['T', ['G', 'H']]
