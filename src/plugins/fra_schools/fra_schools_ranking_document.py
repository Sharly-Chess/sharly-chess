from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from statistics import mean
from typing import Any, Optional, override, Callable

from common.exception import OptionError
from common.i18n import _
from data.columns import player_table as columns
from data.columns.handlers import PlayerColumnHandler
from data.columns.player_table import TournamentPlayerTableColumn
from data.player import TournamentPlayer, Utils
from data.print_documents import PrintOption
from data.print_documents.documents import (
    PrintDocument,
    RoundPrintOption,
    TournamentPrintOption,
)
from plugins.fra_schools.fra_schools_controller import FRASchool, FRASchoolsUtils
from utils.enum import PlayerGender
from web.utils import ColumnUsage


@dataclass
class SchoolTeam:
    school: FRASchool
    label: str
    players: list[TournamentPlayer]
    total_points: float
    is_complete: bool

    tie_break_sums: list[float] = field(default_factory=list)
    avg_age_years: Optional[float] = None
    missing_girls: int = 0
    missing_boys: int = 0
    missing_slots: int = 0


class FraSchoolsRankingPrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'fra-schools-ranking'

    @staticmethod
    def static_name() -> str:
        return _('Ranking by school')

    @staticmethod
    def available_options() -> list[type[PrintOption]]:
        return [TournamentPrintOption, RoundPrintOption]

    @property
    def title(self) -> str:
        return _('Ranking by school after round #{round}').format(
            round=self.ranking_round
        )

    @property
    def ranking_round(self) -> int:
        return (
            self._get_option(RoundPrintOption).value
            or self.tournament.max_ranking_round
        )

    @property
    def template_name(self) -> str:
        return 'print/fra_schools_ranking.html'

    def _team_from_pool(
        self, pool_in_order: list[TournamentPlayer]
    ) -> tuple[list[TournamentPlayer], dict]:
        """
        Build one team (up to 8 contributors) from a school's pool using the 2G/2B/4ANY rule.
        Returns (selected_players, meta).
        """
        girls = [p for p in pool_in_order if p.player.gender == PlayerGender.FEMALE]
        boys = [p for p in pool_in_order if p.player.gender == PlayerGender.MALE]

        selected: list[TournamentPlayer] = []

        # Reserve slots
        GIRL_SLOTS = 2
        BOY_SLOTS = 2
        ANY_SLOTS = 4

        chosen_girls = girls[:GIRL_SLOTS]
        selected.extend(chosen_girls)
        missing_girls = max(0, GIRL_SLOTS - len(chosen_girls))

        chosen_boys = [p for p in boys if p not in selected][:BOY_SLOTS]
        selected.extend(chosen_boys)
        missing_boys = max(0, BOY_SLOTS - len(chosen_boys))

        # Fill ANY slots (do NOT compensate missing girl/boy with extra ANY; ANY is exactly 4)
        already = set(p.player.id for p in selected)
        remainder = [p for p in pool_in_order if p.player.id not in already]
        any_fillers = remainder[:ANY_SLOTS]
        selected.extend(any_fillers)

        # Cap to 8 contributors
        selected = selected[:8]
        selected.sort(key=lambda p: p.rank)

        # Compute meta
        missing_slots = 8 - len(selected) - missing_girls - missing_boys

        meta = {
            'missing_girls': missing_girls,
            'missing_boys': missing_boys,
            'missing_slots': missing_slots,
        }
        return selected, meta

    @property
    def ordered_school_teams(self) -> list[SchoolTeam]:
        """
        Produce ranked school teams (A, B, ...) following the 2G/2B/4ANY rule.
        Uses tournament-wide ordering and points/tiebreaks already computed by compute_player_ranks().
        """

        assert self.event is not None
        plugin_data = FRASchoolsUtils.get_event_plugin_data(self.event)
        ordered_players: list[TournamentPlayer] = list(
            self.tournament.compute_tournament_player_ranks(
                after_round=self.ranking_round
            ).values()
        )

        # Group by school
        schools: dict[int, list[TournamentPlayer]] = {}
        for p in ordered_players:
            player_plugin_data = FRASchoolsUtils.get_player_plugin_data(p.player)
            school = player_plugin_data.fra_school_id
            if not school:
                continue
            schools.setdefault(school, []).append(p)

        teams: list[SchoolTeam] = []

        for school_id, pool in schools.items():
            remaining = list(pool)
            team_idx = 0
            while remaining:
                team_idx += 1
                label = chr(ord('A') + (team_idx - 1))  # "A", "B", ...

                selected, meta = self._team_from_pool(remaining)

                if not selected:
                    break

                total_points = sum(p.points_after(self.ranking_round) for p in selected)
                girls_selected = sum(
                    1 for p in selected if p.player.gender == PlayerGender.FEMALE
                )
                boys_selected = sum(
                    1 for p in selected if p.player.gender == PlayerGender.MALE
                )
                is_complete = (
                    len(selected) == 8 and girls_selected >= 2 and boys_selected >= 2
                )

                # Aggregate tiebreaks (sum over contributors)
                num_tbs = len(self.tournament.tie_breaks)
                tb_sums: list[float] = [0.0] * num_tbs
                for p in selected:
                    for i in range(num_tbs):
                        val = p.tie_break_values[i].value
                        tb_sums[i] += float(val) if val is not None else 0.0

                # Average age (younger is better).
                today = date.today()
                ages = []
                for p in selected:
                    dob: date | None = p.player.date_of_birth
                    if isinstance(dob, date):
                        # Compute precise age in years (fractional)
                        age = (today - dob).days / 365.2425  # average solar year
                        ages.append(age)

                avg_age_years: float | None = mean(ages) if ages else None

                teams.append(
                    SchoolTeam(
                        school=plugin_data.fra_schools_by_id[school_id],
                        label=label,
                        players=selected,
                        total_points=total_points,
                        is_complete=is_complete,
                        tie_break_sums=tb_sums,
                        avg_age_years=avg_age_years,
                        missing_girls=meta['missing_girls'],
                        missing_boys=meta['missing_boys'],
                        missing_slots=meta['missing_slots'],
                    )
                )

                # Consume used players for the next team (B, C, …)
                used_ids = {p.player.id for p in selected}
                remaining = [p for p in remaining if p.player.id not in used_ids]

        # Sort per rules: complete first, then total points desc, then TBs, then younger average age
        def sort_key(t: SchoolTeam):
            base = [0 if t.is_complete else 1, -t.total_points]
            base.extend([-x for x in getattr(t, 'tie_break_sums', [])])
            dob_key = -(t.avg_age_years or 0.0)
            base.append(dob_key)

            return tuple(base)

        teams_by_school: dict[int, list[SchoolTeam]] = defaultdict(list)
        for team in teams:
            teams_by_school[team.school.id].append(team)

        # Remove labels when there's only one team for that school
        for team_list in teams_by_school.values():
            if len(team_list) == 1:
                team_list[0].label = ''

        teams.sort(key=sort_key)
        return teams

    @override
    def validate_options(self):
        super().validate_options()
        ranking_round = self._get_option(RoundPrintOption)
        if ranking_round.value is None:
            if self.tournament.max_ranking_round < 1:
                raise OptionError(
                    _('The tournament has not yet started.'),
                    ranking_round,
                )
            return
        if ranking_round.value > self.tournament.rounds:
            raise OptionError(
                _(
                    'This round is not valid (the tournament has {rounds} rounds).'
                ).format(rounds=self.tournament.rounds),
                ranking_round,
            )
        if ranking_round.value > self.tournament.max_ranking_round:
            raise OptionError(
                _('This round is not finished (last finished: #{round}).').format(
                    round=self.tournament.max_ranking_round
                ),
                ranking_round,
            )

    @property
    def player_columns(self) -> list[TournamentPlayerTableColumn]:
        tournament = self.tournament
        column_types: list[Callable[[ColumnUsage], TournamentPlayerTableColumn]] = [
            columns.RankColumn,
            columns.NameColumn,
            columns.CategoryColumn,
            columns.GenderColumn,
            columns.PointsColumn,
        ]
        for index in range(len(tournament.tie_breaks)):
            column_types.append(
                partial(columns.TieBreakColumn, tournament=tournament, index=index)
            )
        return PlayerColumnHandler(self.get_event(), ColumnUsage.PRINT).get_columns(
            column_types
        )

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'tournament': self.tournament,
            'subtitle': self.tournament.name,
            'ordered_school_teams': self.ordered_school_teams,
            'player_columns': self.player_columns,
            'ordinal_integer': Utils.ordinal_integer,
            'localized_number': Utils.localized_number,
        }
