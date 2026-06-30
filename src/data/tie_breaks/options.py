from abc import ABC, abstractmethod
from functools import cached_property
from types import UnionType
from typing import Any, TYPE_CHECKING

from common.exception import OptionError
from common.i18n import _, ngettext
from data.tie_breaks.cutters import NoCutTieBreakCutter, TieBreakCutter
from utils.option import Option

if TYPE_CHECKING:
    from data.pairings import PairingSystem
    from data.tie_breaks.managers import TieBreakCutterManager
    from web.utils import SelectOption


class TieBreakOption(Option, ABC):
    """Parent class of all the options of tie breaks."""

    @property
    def template_name(self) -> str:
        return f'/admin/tournaments/tie_break_options/{self.template_file_stem}.html'

    @property
    @abstractmethod
    def template_file_stem(self) -> str:
        """Stem of the file of the template."""

    @property
    def is_variation(self) -> bool:
        """Defines if the option value is the default for the tie-break or if it is a variation."""
        return self.value != self.default_value

    def is_compatible_with(self, pairing_system: 'PairingSystem') -> bool:
        """Whether this option's current value can be evaluated on the
        given pairing system. Default: always. Override on options
        whose value relies on a pairing-system capability (e.g.
        match-point scoring)."""
        return True

    @property
    def variation_acronym(self) -> str:
        """Suffix appended to the tie-break acronym when the option's
        value differs from its default (e.g. ``BH/C1``). Override to
        return a non-empty string. The empty default works for options
        whose label is already carried by the base acronym (ESB
        variant) or that don't affect the displayed name."""
        return ''

    @abstractmethod
    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        """Set the value from a variation acronym if it matches it.
        Returns True if the acronym matched the option."""

    @property
    def variation_name(self) -> str:
        """Suffix for the tie-break full name (e.g. ``Buchholz (Cut 1)``)."""
        return ''

    @property
    def variation_help_text(self) -> str:
        """Sentence appended to the tie-break help text."""
        return ''

    @property
    def is_legacy(self) -> bool:
        """Defines if the option marks the tie-break as legacy.
        Tie-breaks with legacy options can no longer be modified."""
        return False


class SilentTieBreakOption(TieBreakOption, ABC):
    """Base class of options which are not displayed."""

    @property
    def variation_acronym(self) -> str:
        return ''

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        return False

    @property
    def variation_name(self) -> str:
        return ''

    @property
    def variation_help_text(self) -> str:
        return ''


class BaseCutterTieBreakOption(TieBreakOption, ABC):
    @property
    @abstractmethod
    def include_median(self) -> bool:
        """Defines if the median cuts are included in the select."""

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return NoCutTieBreakCutter.static_id()

    @property
    def cutter_manager(self) -> 'TieBreakCutterManager':
        from data.tie_breaks.managers import TieBreakCutterManager

        return TieBreakCutterManager(self.include_median)

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        cutter = next(
            (
                cutter
                for cutter in self.cutter_manager.objects()
                if cutter.acronym == acronym
            ),
            None,
        )
        if cutter is None:
            return False
        self.value = cutter.id
        return True

    @property
    def cutter_options(self) -> dict[str, 'SelectOption']:
        from web.utils import SelectOption

        return {
            cutter.id: SelectOption(cutter.name, tooltip=cutter.help_text)
            for cutter in self.cutter_manager.objects()
        }

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self.cutter_manager.get_object(self.value)

    def validate(self):
        super().validate()
        try:
            __ = self.cutter
        except KeyError:
            raise OptionError(f'Unknown cutter: {self.value}', self)

    @property
    def template_file_stem(self) -> str:
        return 'cutter'

    @property
    def variation_acronym(self) -> str:
        return self.cutter.acronym

    @property
    def variation_name(self) -> str:
        return self.cutter.name

    @property
    def variation_help_text(self) -> str:
        return self.cutter.help_text


class CutterTieBreakOption(BaseCutterTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUTTER'

    @property
    def include_median(self) -> bool:
        return False


class CutterWithMedianTieBreakOption(BaseCutterTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'CUTTER_WITH_MEDIAN'

    @property
    def include_median(self) -> bool:
        return True


class PlayedModifierTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'PLAYED_MODIFIER'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def template_file_stem(self) -> str:
        return 'played_modifier'

    @property
    def variation_acronym(self) -> str:
        return 'P'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym == 'P':
            self.value = True
            return True
        return False

    @property
    def variation_name(self) -> str:
        return _('forfeits played')

    @property
    def variation_help_text(self) -> str:
        return _('Forfeited games are considered as played.')


class ForeModifierTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'FORE_MODIFIER'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def template_file_stem(self) -> str:
        return 'fore_modifier'

    @property
    def variation_acronym(self) -> str:
        return 'F'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym == 'F':
            self.value = True
            return True
        return False

    @property
    def variation_name(self) -> str:
        return _('Fore')

    # help_text inherits the empty default; "Buchholz" is replaced by
    # "Fore Buchholz" inside the parent tie-break's help text directly.


class KoyaLimitTieBreakOption(TieBreakOption):
    MAX_VALUE = 5

    @staticmethod
    def static_id() -> str:
        return 'KOYA_LIMIT'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def operator(self) -> str:
        return '+' if self.value > 0 else '-'

    @property
    def is_variation(self) -> bool:
        return bool(self.value)

    @property
    def variation_acronym(self) -> str:
        return f'L{self.operator}{self.value}'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if len(acronym) != 3 or acronym[0] != 'L':
            return False
        operator = acronym[1]
        if operator not in '+-':
            return False
        try:
            value = int(acronym[2])
            if not 0 < value <= self.MAX_VALUE:
                return False
            if operator == '-':
                value = -value
            self.value = value
            return True
        except ValueError:
            return False

    @property
    def variation_name(self) -> str:
        return ngettext(
            'Limit {operator} {count} half-point',
            'Limit {operator} {count} half-points',
            abs(self.value),
        ).format(operator=self.operator)

    # help_text inherits the empty default; the limit equation is
    # surfaced through ``KoyaTieBreak.equation_suffix``.

    @property
    def template_file_stem(self) -> str:
        return 'koya_limit'

    def validate(self):
        super().validate()
        if self.value and abs(self.value) > self.MAX_VALUE:
            raise OptionError(
                _('The limit can only be adjusted by {count} half-points.').format(
                    count=self.MAX_VALUE
                ),
                self,
            )


class EstimatedRatingsTieBreakOption(SilentTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'ESTIMATED_RATINGS'

    @property
    def template_file_stem(self) -> str:
        return 'estimated_ratings'

    # variation_acronym / variation_name / variation_help_text inherit
    # the empty defaults — this option doesn't affect the displayed
    # acronym, name, or help text.

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def include_in_equals(self) -> bool:
        return False


class ReversedTieBreakOption(TieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'REVERSED'

    @property
    def template_file_stem(self) -> str:
        return 'reversed'

    @property
    def variation_acronym(self) -> str:
        return 'R'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if acronym == 'R':
            self.value = True
            return True
        return False

    @property
    def variation_name(self) -> str:
        return _('Reversed')

    @property
    def is_variation(self) -> bool:
        return bool(self.value)

    @property
    def type(self) -> type | UnionType:
        return bool | None

    @property
    def default_value(self) -> Any:
        return None


class LegacyTieBreakOption(SilentTieBreakOption, ABC):
    @property
    def template_file_stem(self) -> str:
        return ''

    @property
    def template_name(self) -> str:
        return ''

    @property
    def variation_name(self) -> str:
        return _('Legacy')

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return False

    @property
    def is_legacy(self) -> bool:
        return True


class LegacyMarch2026TieBreakOption(LegacyTieBreakOption):
    @staticmethod
    def static_id() -> str:
        return 'LEGACY_03_2026'

    @property
    def variation_help_text(self) -> str:
        return _('Rules used were only effective until march 2026 (legacy).')


class NormalizationFactorOverrideTieBreakOption(TieBreakOption):
    """SSSC :class:`/Kx` modifier — override the auto-computed
    normalisation factor F_N with an explicit integer (FIDE MTB26
    page 1: *"/Kx — Used for SSSC, to redefine the normalizing factor
    in SSSC, (/K4, /K5, …)"*). 0 = default (compute from rounds and
    team size)."""

    MAX_VALUE = 99

    @staticmethod
    def static_id() -> str:
        return 'NORMALIZATION_FACTOR'

    @property
    def type(self) -> type | UnionType:
        return int

    @property
    def default_value(self) -> Any:
        return 0

    @property
    def is_variation(self) -> bool:
        return bool(self.value)

    @property
    def variation_acronym(self) -> str:
        return f'K{self.value}'

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        if len(acronym) < 2 or acronym[0] != 'K':
            return False
        try:
            value = int(acronym[1:])
        except ValueError:
            return False
        if not 0 < value <= self.MAX_VALUE:
            return False
        self.value = value
        return True

    @property
    def variation_name(self) -> str:
        return _('Normalisation factor = {value}').format(value=self.value)

    @property
    def variation_help_text(self) -> str:
        return _(
            'Override the auto-computed normalisation factor with {value}.'
        ).format(value=self.value)

    @property
    def template_file_stem(self) -> str:
        return 'normalization_factor'

    def validate(self):
        super().validate()
        if self.value and (self.value < 1 or self.value > self.MAX_VALUE):
            raise OptionError(
                _('Normalisation factor must be between 1 and {max}.').format(
                    max=self.MAX_VALUE
                ),
                self,
            )


class TeamScoreTieBreakOption(TieBreakOption):
    """Score basis (Match Points or Game Points) a tie-break uses when
    the tournament is a team competition. FIDE MTB26 rank-order
    descriptor: ``BH:MP``, ``BH:GP``, etc. Default ``MP`` matches the
    FIDE rule *"the primary score being the default, if the reference
    score is not explicitly indicated"* — team primaries are MP by
    convention (FFE Molter being the GP exception).
    The option is meaningful only in team events; for individual
    events the picker hides it and the value is ignored."""

    VALUE_MP = 'MP'
    VALUE_GP = 'GP'

    @staticmethod
    def static_id() -> str:
        return 'TEAM_SCORE'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return self.VALUE_MP

    @property
    def template_file_stem(self) -> str:
        return 'team_score'

    @property
    def variation_acronym(self) -> str:
        # Mirrors the FIDE descriptor: ``BH:MP``, ``BH:GP``.
        return f':{self.value}'

    @property
    def variation_name(self) -> str:
        return _('match points') if self.value == self.VALUE_MP else _('game points')

    @property
    def variation_help_text(self) -> str:
        return _(
            'In team events, the tie-break is calculated using {score} '
            'as the reference score.'
        ).format(score=self.variation_name)

    def set_value_from_variation_acronym(self, acronym: str) -> bool:
        # Mirrors ``variation_acronym``: ``:MP`` / ``:GP``.
        if acronym not in (f':{self.VALUE_MP}', f':{self.VALUE_GP}'):
            return False
        self.value = acronym[1:]
        return True

    def is_compatible_with(self, pairing_system: 'PairingSystem') -> bool:
        # The match-point variant needs the pairing system to expose
        # match points. GP-only systems can't compute it.
        if self.value != self.VALUE_MP:
            return True
        return pairing_system.supports_match_points

    @property
    def is_variation(self) -> bool:
        # Show the ``:GP`` suffix only when the user picks GP; the MP
        # default is implicit (FIDE MTB26: *"primary score is the
        # default, if not explicitly indicated"*).
        return self.value != self.default_value

    @property
    def score_options(self) -> 'dict[str, Any]':
        """Select-input dict consumed by ``team_score.html``."""
        from web.utils import SelectOption

        return {
            self.VALUE_MP: SelectOption(
                name=_('Match points'),
                tooltip=_(
                    'Sum the opponents (or own) match-point totals '
                    'instead of game points.'
                ),
            ),
            self.VALUE_GP: SelectOption(
                name=_('Game points'),
                tooltip=_(
                    'Sum the opponents (or own) game-point totals '
                    'instead of match points.'
                ),
            ),
        }
