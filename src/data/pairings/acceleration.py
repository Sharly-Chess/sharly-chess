"""Accelerated variations of the Swiss pairing system.

Each variation grants *virtual points* to the players while the pairings
are generated: those points steer who meets whom without ever counting
towards the published standings. The groups a player falls in are ranges
of pairing numbers, and the custom system maps rule by rule onto the
TRF26 250 records.
"""

from abc import ABC, abstractmethod
from copy import copy
from dataclasses import replace
from datetime import date
from functools import cache, partial
from math import ceil, floor
from typing import TYPE_CHECKING, Any, Callable, Iterable

from common.i18n import _
from data.pairings.settings import (
    AccelerationGroup,
    AccelerationRule,
    PairingSetting,
)
from data.pairings.variations import SwissVariation
from utils import Utils

if TYPE_CHECKING:
    from data.player import TournamentPlayer
    from data.tournament import Tournament


def _form_int(data: dict[str, str], field: str) -> int | None:
    """The field as an integer, or None when it is empty or malformed.
    :class:`WebContext` raises on malformed input; pairing settings report
    it as a form error instead, so the exception is turned into None."""
    from web.controllers.base_controller import WebContext

    try:
        return WebContext.form_data_to_int(data, field)
    except ValueError:
        return None


def _form_float(data: dict[str, str], field: str) -> float | None:
    """As :func:`_form_int`, for a decimal field. Note that it accepts a
    comma as the decimal separator, and normalises the value in *data*."""
    from web.controllers.base_controller import WebContext

    try:
        return WebContext.form_data_to_float(data, field)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class PairingGroupSetting(PairingSetting[tuple[int, int]], ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'GROUP_{cls.group()}_{cls.group_count()}'

    @classmethod
    def static_name(cls) -> str:
        return _('Group {group_id}').format(group_id=cls.group())

    @staticmethod
    @abstractmethod
    def group() -> AccelerationGroup:
        """The acceleration group matching the setting."""

    @staticmethod
    @abstractmethod
    def group_count() -> int:
        """Number of groups used in the settings group."""

    @classmethod
    @abstractmethod
    def default_values_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        """Compute the default values of each group."""

    @property
    def template_path(self) -> str:
        return f'/admin/pairings/settings/group_{self.group().lower()}.html'

    @property
    def min_field(self) -> str:
        return f'{self.id}_min'

    @property
    def max_field(self) -> str:
        return f'{self.id}_max'

    def tooltip_representation(self, value: tuple[int, int]) -> str | None:
        return f'{value[0]} - {value[1]}'

    def from_form_data(self, data: dict[str, str]) -> tuple[int, int]:
        return (
            int(data[self.min_field]),
            int(data[self.max_field]),
        )

    def to_form_data(self, object_: tuple[int, int]) -> dict[str, str]:
        return {
            self.min_field: str(object_[0]),
            self.max_field: str(object_[1]),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field in (self.min_field, self.max_field):
            if not data.get(field, None) or int(data[field]) < 0:
                errors[self.id] = _('Positive values are expected.')
                return errors
        min_number, max_number = self.from_form_data(data)
        if min_number >= max_number:
            errors[self.id] = _('Maximum value must be greater than the minimum value.')
        return errors

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> tuple[int, int]:
        return cls.default_values_by_group(tournament)[cls.group()]

    @classmethod
    def check_value(cls, tournament: 'Tournament', value: tuple[int, int]) -> bool:
        return value[0] < value[1] <= tournament.player_count


class Base2GroupsSetting(PairingGroupSetting, ABC):
    @staticmethod
    def group_count() -> int:
        return 2

    @classmethod
    def default_values_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        player_count = tournament.player_count
        if player_count < 3:
            return {group: (0, 0) for group in AccelerationGroup}
        max_a = ceil(player_count / 4) * 2
        return {
            AccelerationGroup.A: (1, max_a),
            AccelerationGroup.B: (max_a + 1, player_count),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        if errors := super().get_data_errors(tournament, data):
            return errors

        min_number, max_number = self.from_form_data(data)
        if tournament.player_count / 4 > max_number - min_number + 1:
            return {
                self.id: _(
                    'Groups must be composed of at least 25%% of players.'
                ).replace('%%', '%')
            }
        return {}


class GroupA2GroupsSetting(Base2GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.A


class GroupB2GroupsSetting(Base2GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.B


class Base3GroupsSetting(PairingGroupSetting, ABC):
    @staticmethod
    def group_count() -> int:
        return 3

    @classmethod
    def default_values_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        """Recommended values for an ideal repartition of players.
        Ideal repartition:
            - Group A: closest multiple of 4 to a third of the players
            - Group B: closest multiple of 2 of half of the remaining players
            - Group C: remaining players"""
        player_count = len(tournament.tournament_players)
        if player_count < 3:
            return {group: (0, 0) for group in AccelerationGroup}
        if player_count < 11:
            # Min ideal repartition: A(4), B(4), C(3)
            max_a = player_count // 3
            max_b = 2 * player_count // 3
        else:
            max_a = 4 * round((player_count / 3) / 4)
            max_b = max_a + 2 * round((player_count - max_a) / 4)
        return {
            AccelerationGroup.A: (1, max_a),
            AccelerationGroup.B: (max_a + 1, max_b),
            AccelerationGroup.C: (max_b + 1, player_count),
        }

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        if errors := super().get_data_errors(tournament, data):
            return errors

        min_number, max_number = self.from_form_data(data)
        group_count = max_number - min_number + 1
        player_count = tournament.player_count
        if not player_count / 4 <= group_count <= player_count / 2:
            return {
                self.id: _(
                    'Groups must be composed of at least '
                    '25%% and at most 50%% of players.'
                ).replace('%%', '%')
            }
        return {}


class GroupA3GroupsSetting(Base3GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.A


class GroupB3GroupsSetting(Base3GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.B


class GroupC3GroupsSetting(Base3GroupsSetting):
    @staticmethod
    def group() -> AccelerationGroup:
        return AccelerationGroup.C


class CustomAccelerationSetting(PairingSetting[list[AccelerationRule]]):
    """The rules of the custom accelerated system, each one mapping to a
    TRF26 250 record: virtual points granted to a range of pairing
    numbers over a range of rounds.

    Form fields are indexed (``<id>_<index>_<field>``) so that rows can be
    added and removed client-side; the indexes only have to be distinct,
    not contiguous."""

    MAX_VPOINTS = 99.9

    @classmethod
    def static_id(cls) -> str:
        return 'CUSTOM_ACCELERATION'

    @staticmethod
    def static_name() -> str:
        return _('Accelerated rounds')

    @property
    def template_path(self) -> str:
        return '/admin/pairings/settings/custom_acceleration.html'

    def field(self, index: int, name: str) -> str:
        return f'{self.id}_{index}_{name}'

    def row_indexes(self, data: dict[str, str]) -> list[int]:
        prefix = f'{self.id}_'
        suffix = '_vpoints'
        indexes: set[int] = set()
        for key in data:
            if key.startswith(prefix) and key.endswith(suffix):
                index = key[len(prefix) : -len(suffix)]
                if index.isdigit():
                    indexes.add(int(index))
        return sorted(indexes)

    def tooltip_representation(self, value: list[AccelerationRule]) -> str | None:
        if not value:
            return None
        return str(len(value))

    def from_form_data(self, data: dict[str, str]) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=_form_float(data, self.field(index, 'vpoints')) or 0.0,
                first_round=_form_int(data, self.field(index, 'first_round')),
                last_round=_form_int(data, self.field(index, 'last_round')),
                number_range=(
                    _form_int(data, self.field(index, 'first_number')),
                    _form_int(data, self.field(index, 'last_number')),
                ),
            )
            for index in self.row_indexes(data)
        ]

    @staticmethod
    def _bound_to_form(value: int | None) -> str:
        return '' if value is None else str(value)

    def to_form_data(self, object_: list[AccelerationRule]) -> dict[str, str]:
        data: dict[str, str] = {}
        for index, rule in enumerate(object_):
            first_number, last_number = rule.number_range or (None, None)
            data |= {
                self.field(index, 'vpoints'): f'{rule.vpoints:g}',
                self.field(index, 'first_round'): self._bound_to_form(rule.first_round),
                self.field(index, 'last_round'): self._bound_to_form(rule.last_round),
                self.field(index, 'first_number'): self._bound_to_form(first_number),
                self.field(index, 'last_number'): self._bound_to_form(last_number),
            }
        return data

    @staticmethod
    def _bound_from_stored(value: Any) -> int | None:
        """An empty bound is stored as null. Rules written before that
        was possible always carry a number."""
        return None if value is None else int(value)

    @classmethod
    def to_stored_value(cls, object_: list[AccelerationRule]) -> Any:
        return [
            {
                'vpoints': rule.vpoints,
                'first_round': rule.first_round,
                'last_round': rule.last_round,
                'first_number': (rule.number_range or (None, None))[0],
                'last_number': (rule.number_range or (None, None))[1],
            }
            for rule in object_
        ]

    @classmethod
    def from_stored_value(cls, value: Any) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=float(rule['vpoints']),
                first_round=cls._bound_from_stored(rule['first_round']),
                last_round=cls._bound_from_stored(rule['last_round']),
                number_range=(
                    cls._bound_from_stored(rule['first_number']),
                    cls._bound_from_stored(rule['last_number']),
                ),
            )
            for rule in value
        ]

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> list[AccelerationRule]:
        return []

    @classmethod
    def check_value(
        cls, tournament: 'Tournament', value: list[AccelerationRule]
    ) -> bool:
        covered: set[tuple[int, int]] = set()
        for rule in value:
            number_range = rule.resolved_number_range(tournament)
            if number_range is None:
                return False
            if not 0 <= rule.vpoints <= cls.MAX_VPOINTS:
                return False
            round_range = rule.resolved_round_range(tournament)
            if not 1 <= round_range[0] <= round_range[1] <= tournament.rounds:
                return False
            first_number, last_number = number_range
            if not 1 <= first_number <= last_number <= tournament.player_count:
                return False
            cells = cls._covered_cells(round_range, number_range)
            if cells & covered:
                return False
            covered |= cells
        return True

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        covered: set[tuple[int, int]] = set()
        for index in self.row_indexes(data):
            self._get_vpoints_errors(errors, data, index)
            round_range = self._get_range(
                errors,
                data,
                index,
                'round',
                tournament.rounds,
                _('A round between 1 and {max} is expected.').format(
                    max=tournament.rounds
                ),
            )
            number_range = self._get_range(
                errors,
                data,
                index,
                'number',
                tournament.player_count,
                _('A pairing number between 1 and {max} is expected.').format(
                    max=tournament.player_count
                ),
            )
            # Overlaps are checked on the resolved ranges: two rules that
            # both run "to the end" do collide, whatever is typed.
            if round_range is None or number_range is None:
                continue
            cells = self._covered_cells(round_range, number_range)
            if overlap := cells & covered:
                round_, number = min(overlap)
                errors[self.field(index, 'first_number')] = _(
                    'Round {round} of pairing number {number} is already accelerated.'
                ).format(round=round_, number=number)
            covered |= cells
        return errors

    def _get_vpoints_errors(
        self, errors: dict[str, str], data: dict[str, str], index: int
    ):
        field = self.field(index, 'vpoints')
        vpoints = _form_float(data, field)
        if vpoints is None or not 0 <= vpoints <= self.MAX_VPOINTS:
            errors[field] = _('A value between 0 and {max} is expected.').format(
                max=f'{self.MAX_VPOINTS:g}'
            )
        elif round(vpoints * 10) != vpoints * 10:
            errors[field] = _('At most one decimal is expected.')

    def _get_range(
        self,
        errors: dict[str, str],
        data: dict[str, str],
        index: int,
        name: str,
        max_value: int,
        message: str,
    ) -> tuple[int, int] | None:
        """Read a range from the form, resolving an empty bound to the
        start or the end. The resolved range is what gets checked for
        overlaps; the emptiness itself is kept in the stored rule."""
        first_field = self.field(index, f'first_{name}')
        last_field = self.field(index, f'last_{name}')
        first = _form_int(data, first_field)
        last = _form_int(data, last_field)
        for field, value in ((first_field, first), (last_field, last)):
            if value is not None and not 1 <= value <= max_value:
                errors[field] = message
        if first_field in errors or last_field in errors:
            return None
        first = 1 if first is None else first
        last = max_value if last is None else last
        if first > last:
            errors[last_field] = _('The end of the range must not precede its start.')
            return None
        return first, last

    @staticmethod
    def _covered_cells(
        round_range: tuple[int, int], number_range: tuple[int, int]
    ) -> set[tuple[int, int]]:
        """The (round, pairing number) pairs a rule accelerates, used to
        check that no two rules accelerate the same one."""
        return {
            (round_, number)
            for round_ in range(round_range[0], round_range[1] + 1)
            for number in range(number_range[0], number_range[1] + 1)
        }


class InitialPairingScoreSetting(PairingSetting[dict[int, float]]):
    """A virtual score granted to a player for every round of the
    tournament, typically carried over from an earlier tournament of the
    event.

    Keyed by player id rather than by pairing number, so that inserting
    or deleting a player can't shift the scores onto the wrong people —
    unlike :class:`CustomAccelerationSetting`, whose rules are ranges of
    pairing numbers."""

    MAX_SCORE = 99.9

    @classmethod
    def static_id(cls) -> str:
        return 'INITIAL_PAIRING_SCORE'

    @staticmethod
    def static_name() -> str:
        return _('Initial pairing scores')

    @property
    def template_path(self) -> str:
        return '/admin/pairings/settings/initial_pairing_score.html'

    @property
    def player_field_base(self) -> str:
        """Base of the ID of the form field holding a player's initial
        score. The player ID is concatenated to the base."""
        return f'{self.id}_player_'

    def player_field(self, player_id: int) -> str:
        return f'{self.player_field_base}{player_id}'

    def tooltip_representation(self, value: dict[int, float]) -> str | None:
        scored = [score for score in value.values() if score]
        return str(len(scored)) if scored else None

    def from_form_data(self, data: dict[str, str]) -> dict[int, float]:
        scores: dict[int, float] = {}
        for field in self._player_fields(data):
            score = _form_float(data, field)
            if score:
                player_id = int(field[len(self.player_field_base) :])
                scores[player_id] = score
        return scores

    def to_form_data(self, object_: dict[int, float]) -> dict[str, str]:
        return {
            self.player_field(player_id): f'{score:g}'
            for player_id, score in object_.items()
            if score
        }

    @classmethod
    def to_stored_value(cls, object_: dict[int, float]) -> Any:
        return {str(player_id): score for player_id, score in object_.items() if score}

    @classmethod
    def from_stored_value(cls, value: Any) -> dict[int, float]:
        return {int(player_id): float(score) for player_id, score in value.items()}

    @classmethod
    def default_value(cls, tournament: 'Tournament') -> dict[int, float]:
        return {}

    @classmethod
    def check_value(cls, tournament: 'Tournament', value: dict[int, float]) -> bool:
        # Scores of players who have left the tournament are simply never
        # read, so they don't make the setting invalid: dropping the whole
        # set because of one of them would lose the arbiter's work.
        return all(0 <= score <= cls.MAX_SCORE for score in value.values())

    def get_data_errors(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field in self._player_fields(data):
            value = data[field]
            if not value:
                continue
            score = _form_float(data, field)
            if score is None or not 0 <= score <= self.MAX_SCORE:
                errors[field] = _('A value between 0 and {max} is expected.').format(
                    max=f'{self.MAX_SCORE:g}'
                )
            elif round(score * 10) != score * 10:
                errors[field] = _('At most one decimal is expected.')
        return errors

    # ---------------------------------------------------------------------
    # Filling the scores from another tournament
    # ---------------------------------------------------------------------

    ACTION_FILL = 'fill'

    @property
    def source_event_field(self) -> str:
        return f'{self.id}_source_event'

    @property
    def source_tournament_field(self) -> str:
        return f'{self.id}_source_tournament'

    @property
    def coefficient_field(self) -> str:
        return f'{self.id}_coefficient'

    @property
    def mode_field(self) -> str:
        return f'{self.id}_mode'

    @property
    def action_field(self) -> str:
        return f'{self.id}_action'

    @property
    def report_field(self) -> str:
        return f'{self.id}_report'

    def get_source_event_options(self) -> dict[str, Any]:
        """The events a carry-over can be taken from — any individual
        event, since a series often spans several. Grouped by status and
        sorted by name: the arbiter looks for a name, not for a date."""
        from data.loader import EventLoader

        today = date.today()
        current = _('Current events')
        passed = _('Passed events')
        groups: dict[str, dict[str, str]] = {current: {}, passed: {}}
        for metadata in EventLoader.get_events_metadata():
            # Events still to come hold no results to carry over.
            if metadata.is_team_event or today < metadata.start_date:
                continue
            group = passed if metadata.stop_date < today else current
            groups[group][metadata.uniq_id] = metadata.name
        # The leading entry doubles as a placeholder and keeps the select
        # from being rendered disabled when a single event is offered.
        options: dict[str, Any] = {'': _('Select an event')}
        for label, entries in groups.items():
            if entries:
                options[label] = dict(
                    sorted(entries.items(), key=lambda entry: entry[1].lower())
                )
        return options

    def get_source_tournament_options(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        source_event = self._get_source_event(tournament, data)
        if source_event is None:
            return {}
        options = {'': _('Select a tournament')}
        options |= {
            str(other.id): other.name
            for other in source_event.tournaments_by_id.values()
            if other.id is not None
            and not other.is_team_tournament
            and not (
                other.id == tournament.id
                and source_event.uniq_id == tournament.event.uniq_id
            )
        }
        return options if len(options) > 1 else {}

    def _source_event_ids(self) -> set[str]:
        return {
            uniq_id
            for entry in self.get_source_event_options().values()
            if isinstance(entry, dict)
            for uniq_id in entry
        }

    def apply_action(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[str, str]:
        """Fill the scores from the chosen tournament. Players are matched
        by identity rather than by id: the same person entered in two
        tournaments is two distinct player records."""
        if data.get(self.action_field) != self.ACTION_FILL:
            return data
        scores_by_key = self._get_source_scores(tournament, data)
        coefficient = _form_float(data, self.coefficient_field)
        if coefficient is None:
            coefficient = 1.0
        add = data.get(self.mode_field) == 'add'

        updated = dict(data)
        matched = 0
        missing = 0
        for tournament_player in tournament.tournament_players:
            field = self.player_field(tournament_player.id)
            keys = tournament.event.get_player_identity_keys(
                tournament_player.stored_player
            )
            score = next(
                (scores_by_key[key] for key in keys if key in scores_by_key), None
            )
            if score is None:
                missing += 1
                if not add:
                    updated[field] = ''
                continue
            matched += 1
            current = (_form_float(updated, field) or 0.0) if add else 0.0
            # One decimal: the TRF26 250 points field holds no more. Round
            # half up rather than to even, which reads as arbitrary here.
            filled = floor((current + score * coefficient) * 10 + 0.5) / 10
            updated[field] = f'{filled:g}' if filled else ''
        updated[self.report_field] = _(
            '{matched} players filled, {missing} not found in that tournament'
        ).format(matched=matched, missing=missing)
        return updated

    def _get_source_scores(
        self, tournament: 'Tournament', data: dict[str, str]
    ) -> dict[tuple, float]:
        """Final score of each player of the chosen tournament, keyed by
        every identity key that player can be recognised by."""
        source_event = self._get_source_event(tournament, data)
        source_id = _form_int(data, self.source_tournament_field)
        if source_event is None or source_id is None:
            return {}
        source = source_event.tournaments_by_id.get(source_id)
        if source is None:
            return {}
        scores_by_key: dict[tuple, float] = {}
        for source_player in source.tournament_players:
            score = source_player.points_total()
            for key in source_event.get_player_identity_keys(
                source_player.stored_player
            ):
                scores_by_key[key] = score
        return scores_by_key

    def _get_source_event(self, tournament: 'Tournament', data: dict[str, str]):
        from data.loader import EventLoader

        uniq_id = data.get(self.source_event_field)
        if not uniq_id:
            return None
        if uniq_id == tournament.event.uniq_id:
            return tournament.event
        if uniq_id not in self._source_event_ids():
            return None
        return EventLoader().load_event(uniq_id)

    def _player_fields(self, data: dict[str, str]) -> list[str]:
        return [
            field
            for field in data
            if field.startswith(self.player_field_base)
            and field[len(self.player_field_base) :].isdigit()
        ]


# ---------------------------------------------------------------------------
# Variations
# ---------------------------------------------------------------------------


class AcceleratedSwissVariation(SwissVariation, ABC):
    """Base of the accelerated Swiss variations."""

    @property
    def include_accelerated_rules_in_trf(self) -> bool:
        return True

    @property
    def vpoints_use_pairing_numbers(self) -> bool:
        return True


class AccelerationSwissVariation(AcceleratedSwissVariation, ABC):
    """Accelerations whose virtual points follow from the group a player
    falls in, the groups being ranges of pairing numbers."""

    @abstractmethod
    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]: ...

    @property
    def are_groups_editable(self) -> bool:
        """Defines if the pairing groups can be edited."""
        return True

    @classmethod
    @abstractmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        """Tooltip representing the group A."""

    @classmethod
    @abstractmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        """Tooltip representing the group B."""

    @classmethod
    def get_group_a_tooltip(cls, tournament: 'Tournament') -> str:
        return cls._build_tooltip(cls._get_group_a_tooltip_lines(tournament))

    @classmethod
    def get_group_b_tooltip(cls, tournament: 'Tournament') -> str:
        return cls._build_tooltip(cls._get_group_b_tooltip_lines(tournament))

    @staticmethod
    def _build_tooltip(tooltip_lines: list[tuple[str, float | None]]) -> str:
        if not tooltip_lines:
            return _('No acceleration.')
        return (
            f'<h6>{_("Virtual points")}</h6>'
            '<div '
            '   class="gap-0 d-grid align-self-center" '
            '   style="grid-template-columns: min-content min-content;"'
            '>'
            + ''.join(
                f'<div class="text-start text-nowrap">{prefix}</div>'
                f'<div class="text-start text-nowrap ps-1">'
                f'  {"→ " + Utils.points_str(points) if points is not None else ""}'
                f'</div>'
                for prefix, points in tooltip_lines
            )
            + '</div>'
        )

    @staticmethod
    def _rounds_prefix(
        min_round: int,
        max_round: int | None = None,
    ) -> str:
        if not max_round or min_round >= max_round:
            return _('Round {round}').format(round=min_round)
        else:
            return _('Rounds {min_round}-{max_round}').format(
                min_round=min_round, max_round=max_round
            )

    @classmethod
    @abstractmethod
    def get_player_group(
        cls, tournament: 'Tournament', tournament_player: 'TournamentPlayer'
    ) -> AccelerationGroup:
        """Get the acceleration group of a player in a tournament."""


class Acceleration2GroupsSwissVariation(AccelerationSwissVariation, ABC):
    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [
            GroupA2GroupsSetting(),
            GroupB2GroupsSetting(),
        ]

    @classmethod
    def get_player_group(
        cls, tournament: 'Tournament', tournament_player: 'TournamentPlayer'
    ) -> AccelerationGroup:
        _, group_a_max = tournament.pairing_settings[GroupA2GroupsSetting.static_id()]
        if tournament_player.pairing_number <= group_a_max:
            return AccelerationGroup.A
        return AccelerationGroup.B

    def update_settings_from_deleted_pairing_numbers(
        self,
        tournament: 'Tournament',
        pairing_numbers: Iterable[int],
    ) -> bool:
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA2GroupsSetting.get_value(tournament)[1]
        new_max_a = max_a
        for pairing_number in pairing_numbers:
            if pairing_number <= max_a:
                new_max_a -= 1
        previous_pairing_settings = copy(tournament.stored_tournament.pairing_settings)
        tournament.stored_tournament.pairing_settings |= {
            GroupA2GroupsSetting().id: (1, new_max_a),
            GroupB2GroupsSetting().id: (new_max_a + 1, tournament.player_count),
        }
        return (
            previous_pairing_settings != tournament.stored_tournament.pairing_settings
        )

    def update_settings_from_added_pairing_number(
        self, tournament: 'Tournament', pairing_number: int
    ):
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA2GroupsSetting.get_value(tournament)[1]
        if pairing_number <= max_a:
            max_a += 1
        tournament.stored_tournament.pairing_settings |= {
            GroupA2GroupsSetting().id: (1, max_a),
            GroupB2GroupsSetting().id: (max_a + 1, tournament.player_count),
        }
        return True

    @classmethod
    def get_acceleration_group_max_numbers(cls, tournament: 'Tournament') -> list[int]:
        _, group_a_max = tournament.pairing_settings[GroupA2GroupsSetting().id]
        return [
            group_a_max,
        ]

    @classmethod
    def get_acceleration_number_range_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        return {
            AccelerationGroup.A: tournament.pairing_settings[GroupA2GroupsSetting().id],
            AccelerationGroup.B: tournament.pairing_settings[GroupB2GroupsSetting().id],
        }


class Acceleration3GroupsSwissVariation(AccelerationSwissVariation, ABC):
    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [
            GroupA3GroupsSetting(),
            GroupB3GroupsSetting(),
            GroupC3GroupsSetting(),
        ]

    @classmethod
    @abstractmethod
    def _get_group_c_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        """Tooltip representing the group C."""

    @classmethod
    def get_group_c_tooltip(cls, tournament: 'Tournament') -> str:
        return cls._build_tooltip(cls._get_group_c_tooltip_lines(tournament))

    @classmethod
    def get_player_group(
        cls, tournament: 'Tournament', tournament_player: 'TournamentPlayer'
    ) -> AccelerationGroup:
        _, group_a_max = tournament.pairing_settings[GroupA3GroupsSetting.static_id()]
        if tournament_player.pairing_number <= group_a_max:
            return AccelerationGroup.A
        _, group_b_max = tournament.pairing_settings[GroupB3GroupsSetting.static_id()]
        if tournament_player.pairing_number <= group_b_max:
            return AccelerationGroup.B
        return AccelerationGroup.C

    def update_settings_from_deleted_pairing_numbers(
        self,
        tournament: 'Tournament',
        pairing_numbers: Iterable[int],
    ) -> bool:
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA3GroupsSetting.get_value(tournament)[1]
        max_b = GroupB3GroupsSetting.get_value(tournament)[1]
        new_max_a = max_a
        new_max_b = max_b
        for pairing_number in pairing_numbers:
            if pairing_number <= max_a:
                new_max_a -= 1
            if pairing_number <= max_b:
                new_max_b -= 1
        previous_pairing_settings = copy(tournament.stored_tournament.pairing_settings)
        tournament.stored_tournament.pairing_settings |= {
            GroupA3GroupsSetting().id: (1, new_max_a),
            GroupB3GroupsSetting().id: (new_max_a + 1, new_max_b),
            GroupC3GroupsSetting().id: (new_max_b + 1, tournament.player_count),
        }
        return (
            previous_pairing_settings != tournament.stored_tournament.pairing_settings
        )

    def update_settings_from_added_pairing_number(
        self, tournament: 'Tournament', pairing_number: int
    ):
        if not self.validate_settings(tournament):
            return False
        max_a = GroupA3GroupsSetting.get_value(tournament)[1]
        max_b = GroupB3GroupsSetting.get_value(tournament)[1]
        if pairing_number <= max_a:
            max_a += 1
        if pairing_number <= max_b:
            max_b += 1
        tournament.stored_tournament.pairing_settings |= {
            GroupA3GroupsSetting().id: (1, max_a),
            GroupB3GroupsSetting().id: (max_a + 1, max_b),
            GroupC3GroupsSetting().id: (max_b + 1, tournament.player_count),
        }
        return True

    @classmethod
    def get_acceleration_group_max_numbers(cls, tournament: 'Tournament') -> list[int]:
        _, group_a_max = tournament.pairing_settings[GroupA3GroupsSetting.static_id()]
        _, group_b_max = tournament.pairing_settings[GroupB3GroupsSetting.static_id()]
        return [
            group_a_max,
            group_b_max,
        ]

    @classmethod
    def get_acceleration_number_range_by_group(
        cls, tournament: 'Tournament'
    ) -> dict[AccelerationGroup, tuple[int, int]]:
        return {
            AccelerationGroup.A: tournament.pairing_settings[GroupA3GroupsSetting().id],
            AccelerationGroup.B: tournament.pairing_settings[GroupB3GroupsSetting().id],
            AccelerationGroup.C: tournament.pairing_settings[GroupC3GroupsSetting().id],
        }

    @staticmethod
    def _format_vpoints_inequality(
        min_points: float | None = None,
        max_points: float | None = None,
    ) -> str:
        points_name = _('points')
        min_str = Utils.points_str(min_points)
        max_str = Utils.points_str(max_points)
        if not min_points:
            inequality = f'{points_name} < {max_str}'
        elif not max_points:
            inequality = f'{points_name} ≥ {min_str}'
        else:
            inequality = f'{min_str} ≤ {points_name} < {max_str}'
        return '&nbsp;' * 4 + inequality

    @classmethod
    def _get_incremental_points_lines(
        cls,
        get_vpoints: Callable[[float], float],
        step: float,
        max_vpoints: float,
    ) -> list[tuple[str, float | None]]:
        message_lines: list[tuple[str, float | None]] = []
        points = 0.0
        previous_threshold: float | None = None
        previous_vpoints = get_vpoints(points)
        vpoints = previous_vpoints
        while vpoints < max_vpoints:
            points += step
            vpoints = get_vpoints(points)
            if previous_vpoints != vpoints:
                message_lines.append(
                    (
                        cls._format_vpoints_inequality(previous_threshold, points),
                        previous_vpoints,
                    )
                )
                previous_threshold = points
                previous_vpoints = vpoints

        message_lines.append(
            (
                cls._format_vpoints_inequality(points),
                vpoints,
            )
        )
        return message_lines


class BakuSwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'BAKU'

    @staticmethod
    def static_name():
        return _('Baku acceleration system')

    @property
    def trf_encoded_type(self) -> str:
        return 'FIDE_DUTCH_2026_BAKU'

    @property
    def include_accelerated_rules_in_trf(self) -> bool:
        # Acceleration already defined by the encoded type
        return False

    @property
    def are_groups_editable(self) -> bool:
        return False

    @classmethod
    def print_real_points(cls, tournament: 'Tournament', current_round: int) -> bool:
        return current_round <= cls.accelerated_rounds(tournament.rounds)

    @staticmethod
    def accelerated_rounds(rounds: int) -> int:
        return ceil(rounds / 2)

    @classmethod
    def full_point_rounds(cls, rounds: int) -> int:
        return ceil(cls.accelerated_rounds(rounds) / 2)

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        tournament_player: 'TournamentPlayer',
        at_round: int,
    ) -> float:
        if at_round > cls.accelerated_rounds(tournament.rounds):
            return 0
        rating_group = cls.get_player_group(tournament, tournament_player)
        if at_round > cls.full_point_rounds(tournament.rounds):
            if rating_group == AccelerationGroup.A:
                return tournament.draw_points
            else:
                return 0
        else:
            if rating_group == AccelerationGroup.A:
                return tournament.win_points
            else:
                return 0

    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]:
        rounds = tournament.rounds
        draw_points = tournament.draw_points
        win_points = tournament.win_points
        return [
            AccelerationRule(
                vpoints=win_points,
                first_round=1,
                last_round=self.full_point_rounds(rounds),
                group=AccelerationGroup.A,
            ),
            AccelerationRule(
                vpoints=draw_points,
                first_round=self.full_point_rounds(rounds) + 1,
                last_round=self.accelerated_rounds(rounds),
                group=AccelerationGroup.A,
            ),
        ]

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        draw_points = tournament.draw_points
        rounds = tournament.rounds
        win_max_rounds = cls.full_point_rounds(rounds)
        draw_max_rounds = cls.accelerated_rounds(rounds)
        return [
            (cls._rounds_prefix(1, win_max_rounds), win_points),
            (cls._rounds_prefix(win_max_rounds + 1, draw_max_rounds), draw_points),
            (cls._rounds_prefix(draw_max_rounds + 1, rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        return []


class HaleySwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY'

    @staticmethod
    def static_name() -> str:
        return _('Haley system')

    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=tournament.win_points,
                first_round=1,
                last_round=2,
                group=AccelerationGroup.A,
            ),
        ]

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        return [
            (cls._rounds_prefix(1, 2), win_points),
            (cls._rounds_prefix(3, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        return []

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        tournament_player: 'TournamentPlayer',
        at_round: int,
    ) -> float:
        if at_round <= 2:
            group = cls.get_player_group(tournament, tournament_player)
            if group == AccelerationGroup.A:
                return tournament.win_points
        return 0.0

    @classmethod
    def print_real_points(cls, tournament: 'Tournament', current_round: int) -> bool:
        return current_round <= 2


class HaleySoftSwissVariation(Acceleration2GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY_SOFT'

    @staticmethod
    def static_name() -> str:
        return _('Soft Haley system')

    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]:
        return [
            AccelerationRule(
                vpoints=tournament.win_points,
                first_round=1,
                last_round=2,
                group=AccelerationGroup.A,
            ),
            AccelerationRule(
                vpoints=tournament.draw_points,
                first_round=2,
                last_round=2,
                group=AccelerationGroup.B,
            ),
        ]

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        return [
            (cls._rounds_prefix(1, 2), win_points),
            (cls._rounds_prefix(3, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        draw_points = tournament.draw_points
        return [
            (cls._rounds_prefix(1), 0),
            (cls._rounds_prefix(2), draw_points),
            (cls._rounds_prefix(3, tournament.rounds), 0),
        ]

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        tournament_player: 'TournamentPlayer',
        at_round: int,
    ) -> float:
        # Round 1: Group A gets 1 vpoint
        # Round 2: Group A gets 1 vpoint, Group B gets .5 vpoints
        if at_round <= 2:
            group = cls.get_player_group(tournament, tournament_player)
            if group == AccelerationGroup.A:
                return tournament.win_points
            elif at_round == 2:
                return tournament.draw_points
        return 0.0

    @classmethod
    def print_real_points(cls, tournament: 'Tournament', current_round: int) -> bool:
        return current_round <= 2


class ProgressiveSwissVariation(Acceleration3GroupsSwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'PROGRESSIVE'

    @staticmethod
    def static_name() -> str:
        return _('Progressive accelerated system')

    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]:
        rounds = tournament.rounds
        draw_points = tournament.draw_points
        win_points = tournament.win_points
        rules: list[AccelerationRule] = []
        # Starting points: Group A - 2, Group B - 1, Group C - 0
        starting_vpoints_by_group = {
            AccelerationGroup.A: 2 * win_points,
            AccelerationGroup.B: win_points,
            AccelerationGroup.C: 0,
        }
        # Players cannot have more than 2 virtual points
        max_vpoints = 2 * win_points
        # If a player gets at least half the possible score,
        # their capital is set at 2 points.
        max_threshold = rounds * win_points / 2
        for group, starting_vpoints in starting_vpoints_by_group.items():
            threshold = 0.0
            vpoints = starting_vpoints
            while vpoints < max_vpoints and threshold < max_threshold:
                rule = AccelerationRule(
                    vpoints=vpoints,
                    first_round=1,
                    last_round=rounds - 2,
                    group=group,
                    points_threshold=threshold,
                )
                rules.append(rule)
                # Players get a virtual draw points for 3 real draw points
                threshold += 3 * draw_points
                vpoints += draw_points

            rule = AccelerationRule(
                vpoints=max_vpoints,
                first_round=1,
                last_round=rounds - 2,
                group=group,
                points_threshold=min(max_threshold, threshold),
            )
            rules.append(rule)
        return rules

    @classmethod
    def _get_group_a_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        win_points = tournament.win_points
        return [
            (cls._rounds_prefix(1, tournament.rounds - 2), 2 * win_points),
            (cls._rounds_prefix(tournament.rounds - 1, tournament.rounds), 0),
        ]

    @classmethod
    def _get_detailed_group_tooltip_lines(
        cls, tournament: 'Tournament', group: AccelerationGroup
    ) -> list[tuple[str, float | None]]:
        draw_points = tournament.draw_points
        win_points = tournament.win_points
        get_vpoints = partial(
            cls._compute_virtual_points,
            group=group,
            tournament_rounds=tournament.rounds,
            draw_points=draw_points,
            win_points=win_points,
        )
        return [
            (cls._rounds_prefix(1, tournament.rounds - 2), None),
            *cls._get_incremental_points_lines(
                get_vpoints, draw_points, 2 * win_points
            ),
            (cls._rounds_prefix(tournament.rounds - 1, tournament.rounds), 0),
        ]

    @classmethod
    def _get_group_b_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.B)

    @classmethod
    def _get_group_c_tooltip_lines(
        cls, tournament: 'Tournament'
    ) -> list[tuple[str, float | None]]:
        return cls._get_detailed_group_tooltip_lines(tournament, AccelerationGroup.C)

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        tournament_player: 'TournamentPlayer',
        at_round: int,
    ) -> float:
        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return 0.0
        return cls._compute_virtual_points(
            group=cls.get_player_group(tournament, tournament_player),
            tournament_rounds=tournament.rounds,
            points=tournament_player.points_before(at_round),
            draw_points=tournament.draw_points,
            win_points=tournament.win_points,
        )

    @staticmethod
    @cache
    def _compute_virtual_points(
        points: float,
        group: AccelerationGroup,
        tournament_rounds: int,
        draw_points: float,
        win_points: float,
    ) -> float:
        if 2 * points >= tournament_rounds * win_points:
            # If a player gets at least half the possible score,
            # their capital is set at 2 points.
            return 2 * win_points

        # Players get a virtual draw points for 3 real draw points
        vpoints = draw_points * (points // (3 * draw_points))

        # Starting points: Group A - 2, Group B - 1, Group C - 0
        match group:
            case AccelerationGroup.A:
                vpoints += 2 * win_points
            case AccelerationGroup.B:
                vpoints += win_points

        # Players cannot have more than 2 virtual points
        return min(2 * win_points, vpoints)

    @classmethod
    def print_real_points(cls, tournament: 'Tournament', current_round: int) -> bool:
        return current_round <= tournament.rounds - 2


class CustomAccelerationSwissVariation(AcceleratedSwissVariation):
    """Acceleration defined rule by rule by the arbiter rather than
    derived from a published system, mirroring the TRF26 250 records:
    virtual points granted to a range of pairing numbers over a range of
    rounds."""

    @staticmethod
    def variation_id() -> str:
        return 'CUSTOM'

    @staticmethod
    def static_name() -> str:
        return _('Custom accelerated system')

    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [CustomAccelerationSetting()]

    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]:
        return CustomAccelerationSetting.get_value(tournament)

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        tournament_player: 'TournamentPlayer',
        at_round: int,
    ) -> float:
        rule = cls._get_rule(tournament, tournament_player.pairing_number, at_round)
        return rule.vpoints if rule else 0.0

    @classmethod
    def print_real_points(cls, tournament: 'Tournament', current_round: int) -> bool:
        return any(
            rule.resolved_round_range(tournament)[0]
            <= current_round
            <= rule.resolved_round_range(tournament)[1]
            for rule in CustomAccelerationSetting.get_value(tournament)
        )

    @staticmethod
    def _get_rule(
        tournament: 'Tournament', pairing_number: int | None, at_round: int
    ) -> AccelerationRule | None:
        """The rule accelerating *pairing_number* at *at_round*, if any.
        Rules are validated not to overlap, so at most one applies."""
        if pairing_number is None:
            return None
        for rule in CustomAccelerationSetting.get_value(tournament):
            number_range = rule.resolved_number_range(tournament)
            assert number_range is not None
            first_number, last_number = number_range
            first_round, last_round = rule.resolved_round_range(tournament)
            if (
                first_round <= at_round <= last_round
                and first_number <= pairing_number <= last_number
            ):
                return rule
        return None

    def update_settings_from_deleted_pairing_numbers(
        self,
        tournament: 'Tournament',
        pairing_numbers: Iterable[int],
    ) -> bool:
        """Shift the rules down so that the players they accelerate keep
        being accelerated once the deleted numbers are reattributed."""
        deleted = list(pairing_numbers)
        stored_rules = self._stored_rules(tournament)
        if not deleted or not stored_rules:
            return False
        rules: list[AccelerationRule] = []
        for rule in stored_rules:
            assert rule.number_range is not None
            first_number, last_number = rule.number_range
            if first_number is not None:
                first_number -= sum(1 for number in deleted if number < first_number)
            if last_number is not None:
                last_number -= sum(1 for number in deleted if number <= last_number)
                last_number = min(last_number, tournament.player_count)
            resolved_first = 1 if first_number is None else first_number
            resolved_last = (
                tournament.player_count if last_number is None else last_number
            )
            if resolved_first <= resolved_last:
                rules.append(replace(rule, number_range=(first_number, last_number)))
        return self._store_rules(tournament, rules)

    def update_settings_from_added_pairing_number(
        self, tournament: 'Tournament', pairing_number: int
    ) -> bool:
        stored_rules = self._stored_rules(tournament)
        if not stored_rules:
            return False
        rules: list[AccelerationRule] = []
        for rule in stored_rules:
            assert rule.number_range is not None
            first_number, last_number = rule.number_range
            rules.append(
                replace(
                    rule,
                    number_range=(
                        None
                        if first_number is None
                        else first_number
                        + (1 if pairing_number <= first_number else 0),
                        None
                        if last_number is None
                        else last_number + (1 if pairing_number <= last_number else 0),
                    ),
                )
            )
        return self._store_rules(tournament, rules)

    @staticmethod
    def _stored_rules(tournament: 'Tournament') -> list[AccelerationRule] | None:
        """The stored rules, read without the validity fallback of
        ``get_value``: the numbers are shifted precisely when a deletion
        has left the stored ranges outside the tournament."""
        setting_id = CustomAccelerationSetting.static_id()
        if setting_id not in tournament.stored_pairing_settings:
            return None
        return CustomAccelerationSetting.from_stored_value(
            tournament.stored_pairing_settings[setting_id]
        )

    @staticmethod
    def _store_rules(tournament: 'Tournament', rules: list[AccelerationRule]) -> bool:
        setting = CustomAccelerationSetting()
        stored_value = CustomAccelerationSetting.to_stored_value(rules)
        if (
            tournament.stored_tournament.pairing_settings.get(setting.id)
            == stored_value
        ):
            return False
        tournament.stored_tournament.pairing_settings |= {setting.id: stored_value}
        return True


class InitialScoreSwissVariation(AcceleratedSwissVariation):
    """Acceleration by a per-player initial score, carried over from an
    earlier tournament of the event. The score counts towards the pairing
    groups of every round but never towards the published standings, so
    the results submitted for rating stay untouched."""

    @staticmethod
    def variation_id() -> str:
        return 'INITIAL_SCORE'

    @staticmethod
    def static_name() -> str:
        return _('Initial score accelerated system')

    @property
    def settings(self) -> list[PairingSetting]:
        return super().settings + [InitialPairingScoreSetting()]

    def get_tournament_accelerated_rules(
        self, tournament: 'Tournament'
    ) -> list[AccelerationRule]:
        """One rule per scored player, covering the whole tournament —
        each one written as a single-player TRF26 250 record."""
        scores = InitialPairingScoreSetting.get_value(tournament)
        rules = [
            AccelerationRule(
                vpoints=scores[tournament_player.id],
                first_round=1,
                last_round=tournament.rounds,
                number_range=(
                    tournament_player.pairing_number,
                    tournament_player.pairing_number,
                ),
            )
            for tournament_player in tournament.tournament_players
            if scores.get(tournament_player.id)
            and tournament_player.pairing_number is not None
        ]
        return sorted(rules, key=lambda rule: rule.number_range or (0, 0))

    @classmethod
    def compute_virtual_points(
        cls,
        tournament: 'Tournament',
        tournament_player: 'TournamentPlayer',
        at_round: int,
    ) -> float:
        return InitialPairingScoreSetting.get_value(tournament).get(
            tournament_player.id, 0.0
        )

    @classmethod
    def print_real_points(cls, tournament: 'Tournament', current_round: int) -> bool:
        # The initial scores apply to every round, so the real points are
        # always worth showing next to the pairing ones.
        return any(InitialPairingScoreSetting.get_value(tournament).values())


ACCELERATED_SWISS_VARIATIONS: list[type[SwissVariation]] = [
    BakuSwissVariation,
    HaleySwissVariation,
    HaleySoftSwissVariation,
    ProgressiveSwissVariation,
    CustomAccelerationSwissVariation,
    InitialScoreSwissVariation,
]


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------


class AccelerationUtils:
    @classmethod
    def set_pairing_settings_from_rating_threshold(
        cls, tournament: 'Tournament', rating_threshold: int
    ):
        from operator import attrgetter

        from database.sqlite.event.event_database import EventDatabase

        tournament.set_tournament_players_pairing_numbers()
        sorted_players = sorted(tournament.tournament_players, key=attrgetter('rating'))
        max_a = next(
            (
                player.pairing_number
                for player in sorted_players
                if player.rating >= rating_threshold
            ),
            None,
        )
        if not max_a:
            return
        tournament.stored_tournament.pairing_settings = {
            GroupA2GroupsSetting().id: (1, max_a),
            GroupB2GroupsSetting().id: (max_a + 1, tournament.player_count),
        }
        with EventDatabase(tournament.event.uniq_id, True) as database:
            database.set_tournament_pairing_settings(
                tournament.id, tournament.stored_pairing_settings
            )

    @classmethod
    def set_pairing_settings_from_dual_rating_thresholds(
        cls,
        tournament: 'Tournament',
        upper_rating_threshold: int,
        lower_rating_threshold: int,
    ):
        from operator import attrgetter

        from database.sqlite.event.event_database import EventDatabase

        tournament.set_tournament_players_pairing_numbers()
        sorted_players = sorted(tournament.tournament_players, key=attrgetter('rating'))
        max_a = next(
            (
                player.pairing_number
                for player in sorted_players
                if player.rating >= upper_rating_threshold
            ),
            None,
        )
        max_b = next(
            (
                player.pairing_number
                for player in sorted_players
                if player.rating >= lower_rating_threshold
            ),
            None,
        )
        if not max_a or not max_b:
            return
        tournament.stored_tournament.pairing_settings |= {
            GroupA3GroupsSetting().id: (1, max_a),
            GroupB3GroupsSetting().id: (max_a + 1, max_b),
            GroupC3GroupsSetting().id: (max_b + 1, tournament.player_count),
        }
        with EventDatabase(tournament.event.uniq_id, True) as database:
            database.set_tournament_pairing_settings(
                tournament.id, tournament.stored_pairing_settings
            )
