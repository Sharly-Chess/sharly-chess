from abc import ABC
from functools import cached_property
from typing import Any, override

from markupsafe import Markup, escape

from common.i18n import _, pgettext
from common.i18n.utils import ordinal_integer
from data.pairings.round_robin_grid import GridCells, GridEncounter
from data.player import TournamentPlayer
from data.tournament import Tournament
from utils import Utils
from utils.enum import BoardColor
from .column import Column, ColumnUsage


FIRST_TIE_BREAK_TOGGLE_ID = 'tie_break_first'
OTHER_TIE_BREAKS_TOGGLE_ID = 'tie_break_others'


def tie_break_toggle_id(index: int) -> str:
    """The toggle under which the tie-break at *index* is shown or hidden."""
    return FIRST_TIE_BREAK_TOGGLE_ID if index == 0 else OTHER_TIE_BREAKS_TOGGLE_ID


def tie_break_toggle_labels() -> dict[str, str]:
    return {
        FIRST_TIE_BREAK_TOGGLE_ID: _('First tie-break'),
        OTHER_TIE_BREAKS_TOGGLE_ID: _('Other tie-breaks'),
    }


GRID_TABLE_NUMBER_TOGGLE = 'grid_table_number'
GRID_RANK_TOGGLE = 'grid_rank'


def grid_table_number_header() -> str:
    return _('Table')


def grid_table_number_toggle() -> tuple[str, str]:
    """The toggle id and label hiding the grid's current-round table column."""
    return GRID_TABLE_NUMBER_TOGGLE, grid_table_number_header()


class TournamentPlayerTableColumn(Column[TournamentPlayer], ABC):
    """Base class for player table columns."""

    def __init__(self, usage: ColumnUsage):
        self.usage = usage

    @property
    def per_seat_holder(self) -> bool:
        """On a round-robin grid, whether a cell about a shared seat stacks a
        value for each player who held it (a fact about a player, such as the
        name or a tie-break) rather than one value for the seat (its number or
        its games)."""
        return True

    @property
    def is_standing(self) -> bool:
        """Whether the column shows a place in the standings (a rank, the
        score, a tie-break) rather than a fact about the player or their
        games. A participant dropped from the standings (FIDE 6.6) keeps
        its row in the crosstable, with these cells left empty."""
        return False

    @property
    def toggle_id(self) -> str | None:
        """The identifier under which the column can be hidden on the
        ranking screens, None when the column is always shown."""
        return None

    @property
    def toggle_label(self) -> str:
        """The label of the checkbox that shows or hides the column."""
        return self.header_content

    @property
    def default_hidden(self) -> bool:
        """Whether the column starts unticked in a document's column
        selection, shown only when the user turns it on."""
        return False

    @override
    def is_cell_blank_for(self, object_: TournamentPlayer) -> bool:
        return self.is_standing and object_.is_excluded_from_standings


class CheckinColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        if tournament_player.check_in:
            return '<span class="checkin-box checked"></span>'
        return '<span class="checkin-box"></span>'

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    def get_footer_content(self, tournament_players: list[TournamentPlayer]) -> Any:
        return '<span class="checkin-box"></span>' if tournament_players else ''

    @property
    def is_footer_content_safe(self) -> bool:
        return True

    def get_footer_classes(self, tournament_players: list[TournamentPlayer]) -> Any:
        return f'{self.shared_classes} opacity-0'

    @property
    def shared_classes(self) -> str:
        return 'checkin'


class NumberColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        # A running row count, whose header would say nothing.
        return ''

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/number.html'

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankColumn(TournamentPlayerTableColumn):
    @property
    @override
    def is_standing(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return pgettext('rank column header', 'Rk.')

    @override
    def is_cell_blank_for(self, object_: TournamentPlayer) -> bool:
        # The crosstable names the opponents by this number.
        return False

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        if tournament_player.is_excluded_from_standings:
            return f'({tournament_player.rank})'
        return tournament_player.rank

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class ExAequoRankColumn(TournamentPlayerTableColumn):
    @property
    @override
    def is_standing(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return pgettext('rank column header', 'Rk.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.tournament.ex_aequo_rank_by_player_id[
            tournament_player.id
        ]

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class RankOverallColumn(TournamentPlayerTableColumn):
    @property
    @override
    def is_standing(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return pgettext('rank overall column header', 'Rk. O.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return f'({ordinal_integer(tournament_player.rank)})'

    @property
    def is_cell_content_safe(self) -> bool:
        return True

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class TitleColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return '\u00a0'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.display_title

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class NameColumn(TournamentPlayerTableColumn):
    @property
    def grid_column_template(self) -> str:
        return '1fr'

    @property
    def header_content(self) -> str:
        return pgettext('name column header', 'Name')

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/name.html'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start text-nowrap name-column'


class RatingColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'rating'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Rating')

    @property
    def header_template(self) -> str | None:
        return '/admin/print/headers/rating.html'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.rating_str

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class CategoryColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'category'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Category')

    @property
    def header_content(self) -> str:
        return pgettext('category column header', 'Cat.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.category.name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class GenderColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'gender'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Gender')

    @property
    def header_content(self) -> str:
        return pgettext('gender column header', 'Gen.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.gender.short_name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class FederationColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'federation'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Federation')

    @property
    def header_content(self) -> str:
        return pgettext('federation column header', 'Fed.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.federation.name

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class ClubColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'club'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Club')

    @property
    def header_content(self) -> str:
        return pgettext('club column header', 'Club')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.club.name

    @property
    def shared_classes(self) -> str:
        return 'text-start club'


class PointsColumn(TournamentPlayerTableColumn):
    @property
    @override
    def is_standing(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return pgettext('points column header', 'Pts')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.points_str

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class PrizeMetricColumn(TournamentPlayerTableColumn):
    """Value column for the prize assignment document. Shows the metric each
    category ranks by: points for a final-standing category, average or peak
    performance for a performance-based one. The header and cell branch on the
    ``prize_category`` in scope where the column is rendered."""

    @property
    def header_template(self) -> str | None:
        return '/admin/print/cells/prize_metric_header.html'

    @property
    def cell_template(self) -> str | None:
        return '/admin/print/cells/prize_metric.html'

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class AlphaPointsColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return ''

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return f'[{tournament_player.points_str}]'

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class RoundColumn(TournamentPlayerTableColumn):
    def __init__(self, usage: ColumnUsage, round_: int):
        super().__init__(usage)
        self.round = round_

    @override
    def is_cell_struck_for(self, object_: TournamentPlayer) -> bool:
        pairing = object_.pairings_by_round.get(self.round)
        return pairing is not None and object_.game_is_annulled(pairing)

    @override
    def get_cell_classes(self, object_: TournamentPlayer) -> str:
        classes = super().get_cell_classes(object_)
        pairing = object_.pairings_by_round.get(self.round)
        if pairing is not None and pairing.result.is_adjourned:
            return f'{classes} fw-bold'
        return classes

    @property
    def header_content(self) -> str:
        return pgettext('round column header', 'R {round}').format(round=self.round)

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        pairing = tournament_player.pairings_by_round[self.round]
        content = pairing.result.to_crosstable
        if opponent := pairing.opponent:
            # A pairing with an opponent has been given a colour.
            assert pairing.color is not None
            content += (
                str(opponent.rank).rjust(3, '\u00a0') + pairing.color.to_crosstable
            )
        for extra_game in tournament_player.extra_games_in(self.round):
            content += (
                '\u00a0' + extra_game.result_of(tournament_player.id).to_crosstable
            )
        return content

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class GridNumberColumn(TournamentPlayerTableColumn):
    """The number of a seat in a round-robin grid, which heads its column."""

    def __init__(self, usage: ColumnUsage, number_by_player_id: dict[int, int]):
        super().__init__(usage)
        self.number_by_player_id = number_by_player_id

    @property
    @override
    def per_seat_holder(self) -> bool:
        return False

    @property
    def header_content(self) -> str:
        return pgettext('NB column header', 'No.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return self.number_by_player_id[tournament_player.id]

    @property
    @override
    def header_classes(self) -> str:
        return 'text-center'

    @property
    def shared_classes(self) -> str:
        return 'text-end fw-bold grid-number-cell'


class GridTableNumberColumn(TournamentPlayerTableColumn):
    """The table the seat's current-round player sits at, shown in a
    round-robin grid so people find the game being played. It can be hidden."""

    def __init__(self, usage: ColumnUsage, current_round: int | None = None):
        super().__init__(usage)
        self.current_round = current_round

    @property
    @override
    def per_seat_holder(self) -> bool:
        return False

    @property
    @override
    def toggle_id(self) -> str | None:
        return GRID_TABLE_NUMBER_TOGGLE

    @property
    def header_content(self) -> str:
        return grid_table_number_header()

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        if self.current_round is None:
            return ''
        tournament = tournament_player.tournament
        holder = tournament.tournament_players_by_id.get(
            tournament.seat_holder(tournament_player.seat_id, self.current_round)
        )
        return (holder.board_number or '') if holder is not None else ''

    @property
    def shared_classes(self) -> str:
        return 'text-center grid-table-cell'


class GridRankColumn(RankColumn):
    """The rank column of a round-robin grid, which people can hide."""

    @property
    @override
    def toggle_id(self) -> str | None:
        return GRID_RANK_TOGGLE

    @property
    @override
    def toggle_label(self) -> str:
        return _('Ranking')


class GridInputColumn(TournamentPlayerTableColumn):
    """The button opening the result-entry modal for a player's current-round
    game, on a round-robin grid that accepts input."""

    @property
    @override
    def per_seat_holder(self) -> bool:
        return False

    @property
    def header_content(self) -> str:
        return ''

    @property
    def cell_template(self) -> str | None:
        return '/user/screen/sets/round_robin_grid_input_cell.html'

    @property
    def shared_classes(self) -> str:
        return 'text-center grid-input-cell'


def grid_encounters_markup(
    encounters: list[GridEncounter], current_round: int | None = None
) -> Markup:
    """The encounters of a square of a round-robin grid, side by side, each
    on the colour played with. Encounters of *current_round* are marked so the
    round being played stands out."""
    if not encounters:
        return Markup('')
    return Markup('<span class="grid-encounters">{encounters}</span>').format(
        encounters=Markup('').join(
            grid_encounter_markup(encounter, current_round) for encounter in encounters
        )
    )


def grid_encounter_markup(
    encounter: GridEncounter, current_round: int | None = None
) -> Markup:
    """An encounter of a round-robin grid: its result, or the round it is
    played in, on the colour played with. The current round is highlighted."""
    if encounter.result is not None:
        content = escape(encounter.result)
        state = 'played'
    else:
        content = escape(
            pgettext('round column header', 'R {round}').format(round=encounter.round)
        )
        state = 'upcoming'
    match encounter.color:
        case BoardColor.WHITE:
            color = 'white'
        case BoardColor.BLACK:
            color = 'black'
        case _:
            color = 'none'
    current = ' grid-encounter-current' if encounter.round == current_round else ''
    return Markup(
        '<span class="grid-encounter grid-encounter-{color} grid-encounter-{state}'
        '{current}">{content}</span>'
    ).format(color=color, state=state, current=Markup(current), content=content)


class GridOpponentColumn(TournamentPlayerTableColumn):
    """The games of each player against the player numbered *number* in a
    round-robin grid: their results once shown, otherwise the rounds they are
    played in."""

    def __init__(
        self,
        usage: ColumnUsage,
        opponent_id: int,
        number: int,
        cells: GridCells,
        current_round: int | None = None,
    ):
        super().__init__(usage)
        self.opponent_id = opponent_id
        self.number = number
        self.cells = cells
        self.current_round = current_round

    @property
    @override
    def per_seat_holder(self) -> bool:
        return False

    def _encounters(self, tournament_player: TournamentPlayer) -> list[GridEncounter]:
        return self.cells.get(tournament_player.id, {}).get(self.opponent_id, [])

    @property
    def header_content(self) -> str:
        return str(self.number)

    @override
    def is_cell_struck_for(self, object_: TournamentPlayer) -> bool:
        return any(encounter.annulled for encounter in self._encounters(object_))

    @override
    def get_cell_classes(self, object_: TournamentPlayer) -> str:
        classes = super().get_cell_classes(object_)
        if object_.id == self.opponent_id:
            return f'{classes} grid-self'
        return classes

    @property
    @override
    def is_cell_content_safe(self) -> bool:
        return True

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return grid_encounters_markup(
            self._encounters(tournament_player), self.current_round
        )

    @property
    def shared_classes(self) -> str:
        return 'text-center grid-cell'


class TournamentColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'tournament'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Tournament')

    @property
    def header_content(self) -> str:
        return pgettext('tournament for players columns', 'Tournament')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.tournament.name

    @property
    def shared_classes(self) -> str:
        return 'text-start'


class TieBreakColumn(TournamentPlayerTableColumn):
    def __init__(
        self,
        usage: ColumnUsage,
        tournament: Tournament,
        index: int,
    ):
        super().__init__(usage)
        self.tournament = tournament
        self.index = index

    @property
    @override
    def is_standing(self) -> bool:
        return True

    @property
    @override
    def toggle_id(self) -> str | None:
        return tie_break_toggle_id(self.index)

    @property
    @override
    def toggle_label(self) -> str:
        return tie_break_toggle_labels()[tie_break_toggle_id(self.index)]

    @property
    def header_content(self) -> str:
        return self.tournament.tie_breaks[self.index].acronym

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return str(tournament_player.tie_break_values[self.index])

    @property
    def shared_classes(self) -> str:
        emphasis = 'fw-bold ' if self.index == 0 else ''
        return f'{emphasis}text-center'


class KnockoutResultColumn(TournamentPlayerTableColumn):
    """A knock-out's ranking result — 'Winner', 'Runner-up', 'Out — round N'
    or 'Still in' — shown in place of a points / tie-break column, which a
    knock-out (ranked by the round reached) does not have."""

    def __init__(self, usage: ColumnUsage, tournament: Tournament):
        super().__init__(usage)
        self.tournament = tournament

    @cached_property
    def _labels(self) -> dict[int, str]:
        return self.tournament.knockout.standing_labels()

    @property
    def header_content(self) -> str:
        return pgettext('knock-out result column', 'Result')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return self._labels.get(tournament_player.id, '')

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-center'


class TeamRankingTieBreakColumn(TournamentPlayerTableColumn):
    def __init__(
        self,
        usage: ColumnUsage,
        tournament: Tournament,
        index: int,
    ):
        super().__init__(usage)
        self.tournament = tournament
        self.index = index

    @property
    def header_content(self) -> str:
        return self.tournament.team_ranking_tie_breaks[self.index].acronym

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return str(tournament_player.team_ranking_tie_break_values[self.index])

    @property
    def shared_classes(self) -> str:
        emphasis = 'fw-bold ' if self.index == 0 else ''
        return f'{emphasis}text-center'


class PaidColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'paid'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Paid')

    @property
    def header_content(self) -> str:
        return pgettext('paid column header', 'Paid')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return Utils.currency_value_str(
            tournament_player.paid, tournament_player.tournament.event.prize_currency
        )

    def get_footer_content(self, tournament_players: list[TournamentPlayer]) -> Any:
        return Utils.currency_value_str(
            sum(tournament_player.paid for tournament_player in tournament_players),
            tournament_players[0].tournament.event.prize_currency,
        )

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class OwedColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'owed'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Owed')

    @property
    def header_content(self) -> str:
        return pgettext('owed column header', 'Owed')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return Utils.currency_value_str(
            tournament_player.owed, tournament_player.event.prize_currency
        )

    def get_footer_content(self, tournament_players: list[TournamentPlayer]) -> Any:
        return Utils.currency_value_str(
            sum(tournament_player.owed for tournament_player in tournament_players),
            tournament_players[0].event.prize_currency,
        )

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class CommentsColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'comments'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Comments')

    @property
    def header_content(self) -> str:
        return pgettext('comments column header', 'Comments')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.comment or ''

    @property
    def shared_classes(self) -> str:
        return 'text-start comments'


class PairingNumberColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'pairing_number'

    @property
    @override
    def toggle_label(self) -> str:
        return _('Pairing number')

    @property
    @override
    def default_hidden(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return pgettext('pairing number column header', 'No.')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.pairing_number or ''

    @property
    def shared_classes(self) -> str:
        return 'text-end'


class FideIdColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'fide_id'

    @property
    @override
    def toggle_label(self) -> str:
        return _('FIDE ID')

    @property
    @override
    def default_hidden(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return 'FIDE'

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.fide_id or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class NationalIdColumn(TournamentPlayerTableColumn):
    @property
    @override
    def toggle_id(self) -> str | None:
        return 'national_id'

    @property
    @override
    def toggle_label(self) -> str:
        return _('National ID')

    @property
    @override
    def default_hidden(self) -> bool:
        return True

    @property
    def header_content(self) -> str:
        return pgettext('national id column header', 'Nat. ID')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.national_id or ''

    @property
    def shared_classes(self) -> str:
        return 'text-center'


class PlayerColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Player')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'


class OpponentColumn(TournamentPlayerTableColumn):
    @property
    def header_content(self) -> str:
        return _('Opponent')

    def get_cell_content(self, tournament_player: TournamentPlayer) -> Any:
        return tournament_player.full_name

    @property
    def shared_classes(self) -> str:
        return 'fw-bold text-start'
