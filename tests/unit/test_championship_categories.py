"""Championship category filtering and reference-date semantics."""

from datetime import date
from typing import Any, cast

from data.championship.category import ChampionshipCategory
from data.championship.reconciliation import (
    ReconciledParticipation as _RP,
)
from data.championship.reconciliation import (
    ReconciledPlayer,
)
from data.player_categories import JuniorCategory, SeniorCategory
from database.sqlite.championship.championship_store import (
    StoredChampionshipCategory,
    StoredChampionshipCriterion,
)


def _rp(source, tp):
    """Build a participation from the light test fakes (cast to the real types)."""
    return _RP(cast(Any, source), cast(Any, tp))


class FakeTournament:
    def __init__(self, tournament_date):
        self.start_date = tournament_date
        self.stop_date = tournament_date


class FakeSource:
    def __init__(self, start_date):
        self.event_uniq_id = start_date.isoformat()
        self.tournament_id = start_date.year
        self.start_date = start_date
        self.tournament = FakeTournament(start_date)
        self.event = FakeEvent()


class FakeEvent:
    junior_categories = [JuniorCategory(10), JuniorCategory(12)]
    senior_categories = [SeniorCategory(50)]


class FakeTournamentPlayer:
    def __init__(self, player_id, category, points, year_of_birth):
        self.id = player_id
        self.category = category
        self.points = points
        self.fide_id = player_id
        self.date_of_birth = None
        self.year_of_birth = year_of_birth
        self.last_name = f'Player {player_id}'
        self.first_name = ''


class FakeChampionship:
    def __init__(self, player, base_date):
        self.players = [player]
        self.effective_age_category_base_date = base_date

    def build_ranking(self, players):
        return players


def _player_with_category_change():
    return ReconciledPlayer(
        [
            _rp(
                FakeSource(date(2025, 6, 1)),
                FakeTournamentPlayer(1, JuniorCategory(10), 3.0, 2015),
            ),
            _rp(
                FakeSource(date(2025, 10, 1)),
                FakeTournamentPlayer(1, JuniorCategory(12), 4.0, 2015),
            ),
        ]
    )


def _exact_age_category(championship, category_id):
    return ChampionshipCategory(
        championship,
        StoredChampionshipCategory(
            id=1,
            name=category_id,
            stored_criteria=[
                StoredChampionshipCriterion(
                    id=1,
                    championship_category_id=1,
                    type='AGE',
                    options={
                        'MIN_AGE_CATEGORY': category_id,
                        'MAX_AGE_CATEGORY': category_id,
                    },
                )
            ],
        ),
    )


def test_fixed_reference_date_uses_one_category_for_all_stages():
    championship = FakeChampionship(_player_with_category_change(), date(2025, 1, 1))

    u10_players = _exact_age_category(championship, 'U10').players
    u12_players = _exact_age_category(championship, 'U12').players

    assert len(u10_players) == 1
    assert len(u10_players[0].participations) == 2
    assert u12_players == []


def test_changing_reference_date_changes_player_category():
    championship = FakeChampionship(_player_with_category_change(), date(2026, 1, 1))

    u10_players = _exact_age_category(championship, 'U10').players
    u12_players = _exact_age_category(championship, 'U12').players

    assert u10_players == []
    assert len(u12_players) == 1
    assert len(u12_players[0].participations) == 2
