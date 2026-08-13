from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from math import ceil, floor
from typing import TYPE_CHECKING, Any

from common.i18n import _
from data.pairings.settings import PairingSetting
from web.controllers.base_controller import WebContext
from plugins.pairing_acceleration import PLUGIN_NAME

if TYPE_CHECKING:
    from data.tournament import Tournament


def _form_int(data: dict[str, str], field: str) -> int | None:
    """The field as an integer, or None when it is empty or malformed.
    :class:`WebContext` raises on malformed input; pairing settings report
    it as a form error instead, so the exception is turned into None."""
    try:
        return WebContext.form_data_to_int(data, field)
    except ValueError:
        return None


def _form_float(data: dict[str, str], field: str) -> float | None:
    """As :func:`_form_int`, for a decimal field. Note that it accepts a
    comma as the decimal separator, and normalises the value in *data*."""
    try:
        return WebContext.form_data_to_float(data, field)
    except ValueError:
        return None


class AccelerationGroup(StrEnum):
    A = 'A'
    B = 'B'
    C = 'C'


@dataclass
class AccelerationRule:
    """Virtual points granted over a range of rounds, either to an
    acceleration group or, when *number_range* is set, to an explicit
    range of pairing numbers (one TRF26 250 record).

    Any bound of either range may be left empty, meaning "from the
    start" or "to the end" — the first/last round, the first/last
    pairing number. Such a rule is resolved against the tournament each
    time it is read rather than pinned when it is saved, so it keeps
    covering the whole field as rounds and players are added.
    """

    vpoints: float
    first_round: int | None
    last_round: int | None
    group: AccelerationGroup | None = None
    points_threshold: float = 0
    number_range: tuple[int | None, int | None] | None = None

    def resolved_round_range(self, tournament: 'Tournament') -> tuple[int, int]:
        """The rounds this rule covers, with empty bounds filled in."""
        return (
            1 if self.first_round is None else self.first_round,
            tournament.rounds if self.last_round is None else self.last_round,
        )

    def resolved_number_range(self, tournament: 'Tournament') -> tuple[int, int] | None:
        """The pairing numbers this rule covers, with empty bounds
        filled in. ``None`` for a rule that addresses a group instead."""
        if self.number_range is None:
            return None
        first, last = self.number_range
        return (
            1 if first is None else first,
            tournament.player_count if last is None else last,
        )


class PairingGroupSetting(PairingSetting[tuple[int, int]], ABC):
    @classmethod
    def static_id(cls) -> str:
        return f'{PLUGIN_NAME}-GROUP_{cls.group()}_{cls.group_count()}'

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
        return f'/{PLUGIN_NAME}/group_{self.group().lower()}.html'

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
        return f'{PLUGIN_NAME}-CUSTOM_ACCELERATION'

    @staticmethod
    def static_name() -> str:
        return _('Accelerated rounds')

    @property
    def template_path(self) -> str:
        return f'/{PLUGIN_NAME}/custom_acceleration.html'

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
        return f'{PLUGIN_NAME}-INITIAL_PAIRING_SCORE'

    @staticmethod
    def static_name() -> str:
        return _('Initial pairing scores')

    @property
    def template_path(self) -> str:
        return f'/{PLUGIN_NAME}/initial_pairing_score.html'

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
