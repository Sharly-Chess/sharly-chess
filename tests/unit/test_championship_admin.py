from types import SimpleNamespace
from typing import Any, cast

from data.championship.options import (
    ChampionshipCompetitorType,
    TeamScoreBasis,
)
from data.championship.scoring import DirectEncounterRule, TotalPointsRule
from web.controllers.admin.championship_admin_controller import (
    ChampionshipAdminController,
)


class FakeParticipation:
    def __init__(self, name: str, points: float, wins: int, index: int):
        self.source = SimpleNamespace(
            tournament_name=name,
            tournament=SimpleNamespace(player_count=1, team_count=1),
        )
        self.event_uniq_id = f'stage-{index}'
        self.tournament_id = index
        self.source_competitor_id = 1
        self._points = points
        self.wins = wins
        self.rank = 0
        self.coefficient = 1.0

    def points(self, _team_score_basis):
        return self._points

    def weighted_points(self, team_score_basis):
        return self.points(team_score_basis) * self.coefficient


def test_results_show_every_ordered_best_n_score():
    brian = SimpleNamespace(
        key='brian',
        last_name='MURER',
        first_name='Brian',
        fide_id=651038188,
        participations=[
            FakeParticipation('Stage 1', 6, 6, 1),
            FakeParticipation('Stage 2', 5, 5, 2),
            FakeParticipation('Stage 3', 5, 5, 3),
            FakeParticipation('Stage 4', 6, 6, 4),
            FakeParticipation('Stage 5', 6, 6, 5),
            FakeParticipation('Stage 6', 4, 4, 6),
        ],
    )
    emilien = SimpleNamespace(
        key='emilien',
        last_name='SAUZON',
        first_name='Emilien',
        fide_id=651090899,
        participations=[
            FakeParticipation('Stage 1', 5, 5, 1),
            FakeParticipation('Stage 2', 6, 6, 2),
            FakeParticipation('Stage 3', 6, 6, 3),
            FakeParticipation('Stage 4', 6, 6, 4),
            FakeParticipation('Stage 6', 5, 5, 6),
        ],
    )
    championship = SimpleNamespace(
        competitor_type=ChampionshipCompetitorType.INDIVIDUAL,
        team_score_basis=TeamScoreBasis.SOURCE_PRIMARY,
        player_age_category=lambda competitor: '',
        competitors=[brian, emilien],
        manual_positions={},
        rules=[
            TotalPointsRule(best_n=4),
            TotalPointsRule(best_n=5),
            TotalPointsRule(best_n=6),
        ],
        ranking=[],
    )
    entries = [
        SimpleNamespace(rank=1, tied=False, competitor=brian),
        SimpleNamespace(rank=2, tied=False, competitor=emilien),
    ]

    brian_row, emilien_row = ChampionshipAdminController._ranking_rows(
        cast(Any, championship), entries
    )

    assert [cell['value'] for cell in brian_row['rule_cells']] == [23, 28, 32]
    assert [cell['used'] for cell in brian_row['rule_cells']] == [True, True, True]
    assert [cell['value'] for cell in emilien_row['rule_cells']] == [23, 28, 28]
    # Stages are ordered best-first by the selection basis (points); the four
    # counted are the highest-scoring ones.
    assert [stage['name'] for stage in brian_row['stages'] if stage['counted']] == [
        'Stage 1',
        'Stage 4',
        'Stage 5',
        'Stage 2',
    ]


def test_direct_encounter_is_displayed_as_rank_progress():
    class DirectParticipation(FakeParticipation):
        def __init__(
            self, competitor_id: int, opponent_id: int, encounter_points: float
        ):
            super().__init__('Stage 1', 3, int(encounter_points == 1), 1)
            self.source_competitor_id = competitor_id
            self._encounters = [(opponent_id, encounter_points)]

        def encounters(self, _team_score_basis):
            return self._encounters

    loser = SimpleNamespace(
        key='loser',
        last_name='LOSER',
        first_name='Louis',
        fide_id=None,
        participations=[DirectParticipation(1, 2, 0)],
    )
    winner = SimpleNamespace(
        key='winner',
        last_name='WINNER',
        first_name='Wendy',
        fide_id=None,
        participations=[DirectParticipation(2, 1, 1)],
    )
    championship = SimpleNamespace(
        competitor_type=ChampionshipCompetitorType.INDIVIDUAL,
        team_score_basis=TeamScoreBasis.SOURCE_PRIMARY,
        player_age_category=lambda competitor: '',
        competitors=[loser, winner],
        manual_positions={},
        rules=[TotalPointsRule(), DirectEncounterRule()],
        ranking=[],
    )
    entries = [
        SimpleNamespace(rank=1, tied=False, competitor=winner),
        SimpleNamespace(rank=2, tied=False, competitor=loser),
    ]

    winner_row, loser_row = ChampionshipAdminController._ranking_rows(
        cast(Any, championship), entries
    )

    assert winner_row['rule_cells'][1] == {
        'value': None,
        'rank_progress': 1,
        'used': True,
        'manual': False,
    }
    assert loser_row['rule_cells'][1] == {
        'value': None,
        'rank_progress': -1,
        'used': True,
        'manual': False,
    }


def test_competitor_rows_select_players_and_carry_all_source_entries():
    brian = SimpleNamespace(
        last_name='MURER',
        first_name='Brian',
        fide_id=651038188,
        participations=[
            FakeParticipation('Stage 1', 6, 6, 1),
            FakeParticipation('Stage 2', 5, 5, 2),
        ],
    )
    for participation in brian.participations:
        participation.tournament_player = SimpleNamespace(
            full_name='Brian MURER',
            category=SimpleNamespace(name='U12'),
            gender=SimpleNamespace(short_name='M'),
        )
    championship = SimpleNamespace(
        competitor_type=ChampionshipCompetitorType.INDIVIDUAL,
        team_score_basis=TeamScoreBasis.SOURCE_PRIMARY,
        player_age_category=lambda competitor: '',
        competitors=[brian],
        stored_championship=SimpleNamespace(stored_player_overrides=[]),
    )

    row = ChampionshipAdminController._competitor_rows(cast(Any, championship))[0]

    assert row['name'] == 'MURER, Brian'
    assert row['secondary'] == '651038188'
    assert row['category'] == 'U12'
    assert row['gender'] == 'M'
    assert row['override_group_keys'] == []
    assert row['refs'] == 'stage-1|1|1;stage-2|2|1'
    # Tournaments are listed in the order they were played.
    assert [
        participation['source_name'] for participation in row['participations']
    ] == [
        'Stage 1',
        'Stage 2',
    ]
