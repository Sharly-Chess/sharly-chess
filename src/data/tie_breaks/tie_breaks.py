from abc import ABC, abstractmethod
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from enum import StrEnum
from contextlib import suppress
from decimal import Decimal
from functools import cached_property
from math import isclose
from statistics import fmean
from typing import TYPE_CHECKING, SupportsFloat, Any

from common.i18n import _, ngettext
from data.pairing import Pairing
from data.pairings import PairingSystem
from data.pairings.systems import RoundRobinPairingSystem, SwissPairingSystem
from data.player import TournamentPlayer
from data.tie_breaks.categories import (
    TieBreakCategory,
    PlayerRecordCategory,
    OpponentRecordCategory,
    RatingCategory,
    OtherCategory,
)
from data.tie_breaks.cutters import TieBreakCutter
from data.tie_breaks.options import (
    TieBreakOption,
    PlayedModifierTieBreakOption,
    ForeModifierTieBreakOption,
    KoyaLimitTieBreakOption,
    CutterTieBreakOption,
    CutterWithMedianTieBreakOption,
    EstimatedRatingsTieBreakOption,
    ReversedTieBreakOption,
    LegacyMarch2026TieBreakOption,
    TeamScoreTieBreakOption,
)
from data.tie_breaks.team_records import (
    TeamRecord,
    adjust_opponent_total,
    dummy_opponent_score,
    fore_round_is_paired,
)
from data.tie_breaks import round_formulas, unplayed_rounds
from data.tie_breaks.direct_encounter import rank_by_encounters
from data.tie_breaks.unplayed_rounds import RoundRecord, WeightedContribution
from database.sqlite.event.event_store import StoredTieBreak
from utils import Utils
from utils.enum import BoardColor, Result, ScoreType
from utils.option import OptionHandler

if TYPE_CHECKING:
    from data.tie_breaks.team_records import TeamMatchRecord
    from data.tie_breaks.team_tie_breaks import TeamTieBreakContext
    from data.tournament import Tournament


def player_rounds(
    player: TournamentPlayer, *, counted_only: bool = False
) -> list[RoundRecord]:
    """The player's rounds as the tie-breaks read them; *counted_only* leaves
    out the games against a player excluded from the standings (FIDE 6.6)."""
    point_values = player.tournament.point_values
    return [
        RoundRecord(
            round_=round_index,
            opponent_id=pairing.opponent_id,
            points=pairing.result.points(point_values),
            played=pairing.played,
            requested_bye=pairing.requested_bye,
            voluntary_unplayed=pairing.voluntary_unplayed,
        )
        for round_index, pairing in player.pairings.items()
        if not counted_only or player.game_counts_for_tie_breaks(pairing)
    ]


class TieBreakPurpose(StrEnum):
    """What a stored tie-break list is for. ``STANDINGS`` are the ranking
    criteria; ``ADVANCEMENT`` are a knock-out's Art. 12 tie-breaks for
    deciding which team goes through a level match — a separate list so the
    two never mix."""

    STANDINGS = 'STANDINGS'
    ADVANCEMENT = 'ADVANCEMENT'


class TieBreak(OptionHandler[TieBreakOption], ABC):
    """Abstract class representing a tie-break"""

    #: Whether this tie-break yields a numeric value that is meaningful to
    #: aggregate across tournaments (summed / averaged by a Championship rule).
    #: False for tie-breaks that only order players locally (direct encounter,
    #: manual play-off order).
    is_aggregatable: bool = True

    @property
    def full_name(self) -> str:
        """the full representation of the tie-break including the modifiers."""
        variation_names: list[str] = []
        for option_type in self.available_options():
            option = self._get_option(option_type)
            if option.is_variation and option.variation_name:
                variation_names.append(option.variation_name)
        if not variation_names:
            return self.name
        return f'{self.name} ({", ".join(variation_names)})'

    @property
    @abstractmethod
    def base_acronym(self) -> str:
        """Represents the tie-break in rankings documents, screens and tournament cards."""

    @property
    def picker_acronym(self) -> str:
        """Acronym shown in the picker when the user is choosing a
        tie-break type. Defaults to :attr:`base_acronym` — overridden
        on tie-breaks whose ``base_acronym`` is variant-specific (e.g.
        ``EMMSB`` for ESB) so the picker still names the *family*
        rather than one of its variants."""
        return self.base_acronym

    @property
    def picker_help_text(self) -> str:
        """Tooltip shown in the picker. Defaults to
        :attr:`base_help_text` — overridden on tie-breaks whose
        ``base_help_text`` describes the configured variant rather
        than the family."""
        return self.base_help_text

    @property
    def acronym(self) -> str:
        """Acronym built from the base acronym and the options."""
        score_basis = ''
        variations: list[str] = []
        for option_type in self.available_options():
            option = self._get_option(option_type)
            if not (option.is_variation and option.variation_acronym):
                continue
            if option.variation_acronym.startswith(':'):
                # The reference score binds to the base acronym and carries
                # its own separator, ahead of the rest: ``BH:GP/C1``.
                score_basis = option.variation_acronym
            else:
                variations.append(option.variation_acronym)
        return '/'.join([self.base_acronym + score_basis, *variations])

    @property
    def is_fide(self) -> bool:
        """Defines if the tie-break is an official FIDE tie-break or not."""
        return True

    @property
    def trf_acronym(self) -> str:
        """Acromnym or the tie-break in TRF26. Tie-breaks not defined in the
        FIDE handbook should be prefixed with `OTHER_`."""
        return f'{"" if self.is_fide else "OTHER_"}{self.acronym}'

    @property
    def team_acronym(self) -> str:
        """The acronym as the team column of *Mandatory Tie-Breaks* spells it.

        That column states the reference score on every code it holds --
        ``WIN:MP``, ``BH:GP``, ``PS:MP`` -- where the individual column carries
        no qualifier at all. So the bare form is the individual tie-break, and
        writing it in a team file names the wrong one: a reader is entitled to
        take ``WIN`` for the games a team's players won rather than the rounds
        the team won. Match points being the default is a rule for reading a
        code, not for writing one.
        """
        if TeamScoreTieBreakOption not in self.available_options():
            return self.acronym
        option = self._get_option(TeamScoreTieBreakOption)
        if option.is_variation:
            return self.acronym
        head, separator, tail = self.acronym.partition('/')
        return head + option.variation_acronym + separator + tail

    @property
    def team_trf_acronym(self) -> str:
        """The TRF26 record 212 spelling for a team competition."""
        return f'{"" if self.is_fide else "OTHER_"}{self.team_acronym}'

    @property
    @abstractmethod
    def base_help_text(self) -> str:
        """Short explanation of how the tie-break values are computed."""

    @property
    def help_text(self) -> str:
        """Help text built from the base help text and the options."""
        help_text_parts: list[str] = [self.base_help_text]
        for option_type in self.available_options():
            option = self._get_option(option_type)
            if option.is_variation and option.variation_help_text:
                help_text_parts.append(option.variation_help_text)
        return '<br/>'.join(help_text_parts)

    @property
    @abstractmethod
    def category(self) -> TieBreakCategory:
        """Category of the tie-break. Used to organize them in the select."""

    @abstractmethod
    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> SupportsFloat:
        """Compute the value of the tie-break for a player.
        As tie-breaks are intended for ranking,
        the return type need to support rich comparison with itself"""

    @property
    def is_computed_per_player(self) -> bool:
        """Determines if the values are computed player per player.
        If False, values are computed after all the others, all the tournament at once."""
        return True

    def compute_all_player_values(
        self,
        tournament: 'Tournament',
        tie_break_index: int,
        *,
        after_round: int,
    ) -> dict[int, int]:
        """Computes the values of all the players in a dict[player_id, value] format."""
        raise NotImplementedError(
            'If `is_computed_by_player` is False this method needs to be implemented.'
        )

    def get_player_variables(
        self, tournament: 'Tournament', after_round: int
    ) -> dict[int, Any]:
        """Get variables to store into the player objects for this tie-break.
        Returns a dict in format dict[player_id, variable].
        These variables are stored in Player.tie_break_variable[TieBreak.id]."""
        return {}

    @property
    def display_rank_delta(self) -> bool:
        """Defines if the rank delta should be displayed instead of the tie-break value.
        Usage: tie-breaks with not displayable values (ex: direct encounter)."""
        return False

    @property
    def is_manual(self) -> bool:
        """Defines if the tie-break is the manual one"""
        return False

    @property
    def is_final(self) -> bool:
        """Defines if the tie-break only can be used as final tie-break.
        Any tie-break used after this one will get an error."""
        return False

    @property
    def display_absolute_value(self) -> bool:
        """Defines if a negative value should be displayed as positive."""
        return False

    @property
    def display_decimals(self) -> int | None:
        """When set, the value is shown with this many decimal places (e.g.
        an average rating) rather than the points formatter, which would turn
        a fractional value into ½/¼/¾ glyphs."""
        return None

    @property
    def allow_multiple(self) -> bool:
        """Defines if the tie-break can be added multiple time with the same options."""
        return False

    @property
    def allow_unrated_players(self) -> bool:
        """Defines if the tie-break can be used with players without any rating defined."""
        return True

    @property
    def allow_estimated_players(self) -> bool:
        """Defines if the tie-break can be used with estimated players."""
        return True

    def get_warning_for_tournament(self, tournament: 'Tournament') -> str | None:
        """Get a warning to display on the tie-break row."""
        if self.is_legacy:
            return _('This tie-break uses a legacy way to compute values.')
        return None

    @property
    def forbidden_pairing_systems(self) -> list[PairingSystem]:
        """Static list of pairing systems for which this tie-break
        cannot run regardless of its options (e.g. Buchholz vs
        round-robin). Default: empty.

        For option-driven incompatibilities, override
        ``TieBreakOption.is_compatible_with`` on the relevant option —
        :meth:`is_compatible_with` aggregates both."""
        return []

    @property
    def usable_without_result_points(self) -> bool:
        """Whether this tie-break still means something when the pairing
        system's score is not a count of game points (a Keizer). Most
        tie-breaks sum opponents' game points and do not, so they are
        withheld from such systems; the few that read only results,
        counts or the primary score itself override this to ``True``."""
        return False

    @property
    def usable_as_knockout_advancement(self) -> bool:
        """Whether this tie-break may be chosen to decide which
        participant advances from a level knock-out match. Asked against
        the separate advancement list, not :meth:`is_compatible_with` (a
        knock-out's standings are the round reached, never a tie-break).

        A tie-break qualifies unless it says otherwise, so a new one is
        offered by default and each refusal carries its reason where the
        tie-break is defined. Two participants in a level match reached
        the same bracket depth, which is what most of the refusals turn
        on: anything that is a function of how far a participant got —
        the score and its restatements, the strength of the field they
        beat — is equal for both by construction. What can separate them
        is their seeding or rating, the path they took there, and
        whether they won their earlier matches outright rather than
        advancing on a tie-break of their own."""
        return not self.is_legacy

    def is_compatible_with(self, pairing_system: PairingSystem) -> bool:
        """Whether this tie-break (with its current options) can run as a
        *standings* criterion on the given pairing system. Combines the
        static ``forbidden_pairing_systems`` list with each option's
        ``is_compatible_with`` check."""
        if pairing_system in self.forbidden_pairing_systems:
            return False
        if pairing_system.eliminates_participants:
            # A knock-out ranks by the round reached, not by comparing
            # scores, so no standings tie-break is configurable on one.
            # Its Art. 12 tie-breaks live on the separate advancement list.
            return False
        if (
            not pairing_system.uses_result_points
            and not self.usable_without_result_points
        ):
            return False
        for option_type in self.available_options():
            if not self._get_option(option_type).is_compatible_with(pairing_system):
                return False
        return True

    def to_stored_value(self) -> StoredTieBreak:
        return StoredTieBreak(
            id=None,
            tournament_id=0,
            type=self.id,
            options={
                option.id: option.value
                for option in self.options
                if not option.is_legacy
            },
            index=0,
        )

    @staticmethod
    def fore_round_is_paired(player: TournamentPlayer, after_round: int) -> bool:
        """Whether Art. 8.3's hypothesis reaches *player*: it replaces the
        *paired* games of the final round with draws, so a participant who
        was not paired for that round keeps the result they were given, and
        the round stays unplayed for every other purpose."""
        return unplayed_rounds.fore_round_is_paired(player_rounds(player), after_round)

    @classmethod
    def adjusted_score(
        cls,
        player: TournamentPlayer,
        *,
        after_round: int,
        adjust_fore: bool = False,
    ) -> float:
        """Computes the adjusted score of the player for the purposes of their opponents' tie-breaks
        Only adjusts them in case of requested byes followed by all VUR.
        If *adjust_fore* is True, the adjusted score for Fore Buchholz is computed:
        the paired game of the last round is considered a draw, and the round
        counts as played."""
        tournament: Tournament = player.tournament
        caching = tournament._compute_caching_enabled
        cache_key = ('adjusted_score', after_round, adjust_fore)
        if caching:
            cached = player._compute_cache.get(cache_key)
            if cached is not None:
                return cached
        if tournament.pairing_system == RoundRobinPairingSystem():
            # Use the standings score so a game against an excluded player
            # (FIDE 6.6) does not inflate this opponent's contribution.
            score = player.standings_points(after_round)
            if caching:
                player._compute_cache[cache_key] = score
            return score
        score = unplayed_rounds.adjusted_score(
            player_rounds(player),
            after_round=after_round,
            draw=tournament.draw_points,
            fore=adjust_fore,
        )
        if caching:
            player._compute_cache[cache_key] = score
        return score

    @classmethod
    def adjusted_dummy_score(
        cls,
        dummy_score: float,
        tournament: 'Tournament',
        after_round: int,
        adjust_fore: bool = False,
        opponent: TournamentPlayer | None = None,
    ) -> float:
        # A forfeit is the only unplayed round with a scheduled opponent.
        return unplayed_rounds.dummy_score(
            dummy_score,
            draw=tournament.draw_points,
            tournament_rounds=tournament.rounds,
            opponent_adjusted=(
                cls.adjusted_score(
                    opponent, after_round=after_round, adjust_fore=adjust_fore
                )
                if opponent
                else None
            ),
        )

    @cached_property
    def is_legacy(self) -> bool:
        return any(option.is_legacy and option.value is True for option in self.options)

    @property
    def is_used_for_team_ranking(self) -> bool:
        # Override this property for tie-breaks that should not be used for team ranking.
        return True

    @property
    def is_team_tiebreak(self) -> bool:
        """True for team-only tie-breaks (MPvGP, ESB×4, EDE, SSSC,
        Berlin) — those with no individual analog. Hidden from the
        picker in individual events. False (default) on tie-breaks
        that work in both individual and team mode (BH, FB, AOB, KS,
        WIN, WON, PS, TPN — see :attr:`supports_team_mode`) and on
        tie-breaks that are individual-only (DE, SB, ARO, ...)."""
        return False

    @property
    def supports_team_mode(self) -> bool:
        """True if the tie-break can be configured on a team event and
        produces a per-team value via :meth:`compute_team_value`.
        Always True on :class:`TeamTieBreak` subclasses (team-only)
        and on the FIDE MTB26 "both" group — BH, FB, AOB, KS, WIN,
        WON, PS, TPN — overridden case by case."""
        return False

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> SupportsFloat:
        """Compute the tie-break value for one team. Overridden by
        every tie-break that returns True from
        :attr:`supports_team_mode`. The default raises so a missing
        override is caught loudly rather than silently returning
        zero — :meth:`Tournament.team_standings` guards by checking
        ``supports_team_mode`` before calling."""
        raise NotImplementedError(
            f'{type(self).__name__} does not implement compute_team_value '
            f'(supports_team_mode returns False).'
        )

    def _team_score_type(self) -> ScoreType:
        """Read ``TeamScoreTieBreakOption`` (MP/GP). MP is the FIDE
        default. Returns ``ScoreType.MATCH_POINTS`` if the option is
        absent — useful for tie-breaks that may be configured before
        the option was added."""
        try:
            opt = self._get_option(TeamScoreTieBreakOption)
        except KeyError:
            return ScoreType.MATCH_POINTS
        return (
            ScoreType.GAME_POINTS
            if opt.value == TeamScoreTieBreakOption.VALUE_GP
            else ScoreType.MATCH_POINTS
        )


class PlayerRecordTieBreak(TieBreak, ABC):
    """Base class of the tie-breaks based on the player's record."""

    @property
    def category(self) -> TieBreakCategory:
        return PlayerRecordCategory()


class WinsTieBreak(PlayerRecordTieBreak):
    """The number of rounds where a participant obtains,
    with or without playing, as many points as awarded for a win.
    See FIDE Handbook C.07.7.1"""

    @staticmethod
    def static_id() -> str:
        return 'WINS'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @staticmethod
    def static_name() -> str:
        return _('Number of wins')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [TeamScoreTieBreakOption]

    @property
    def base_acronym(self) -> str:
        return 'WIN'

    @property
    def base_help_text(self) -> str:
        return _(
            'The number of rounds where a player obtains, with or '
            'without playing, as many points as awarded for a win.'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        return round_formulas.rounds_won(
            player_rounds(player, counted_only=True),
            after_round=after_round,
            win=Result.WIN.points(player.tournament.point_values),
        )

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> int:
        # WIN counts rounds with full win-points credited, including
        # forfeit wins and pairing-allocated byes (FIDE 7.1: "with or
        # without playing"). Uses MP (FIDE MTB26 table 2 — WIN only
        # supports :MP for teams; the :GP variant is not in the spec).
        return round_formulas.rounds_won(
            team_record.rounds(ScoreType.MATCH_POINTS),
            after_round=after_round,
            win=tournament_context.win_mp,
        )


class GamesWonTieBreak(PlayerRecordTieBreak):
    """The number of games a participant won 'over the board'.
    See FIDE Handbook C.07.7.2"""

    @staticmethod
    def static_id() -> str:
        return 'GAMES_WON'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @staticmethod
    def static_name() -> str:
        return _('Number of games won')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [TeamScoreTieBreakOption]

    @property
    def base_acronym(self) -> str:
        return 'WON'

    @property
    def base_help_text(self) -> str:
        return _('The number of games won over the board.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        return round_formulas.games_won(
            player_rounds(player, counted_only=True),
            after_round=after_round,
            win=Result.WIN.points(player.tournament.point_values),
        )

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> int:
        # WON for teams: matches won over the board — excludes forfeit
        # wins (FIDE 7.2). Pairing-allocated byes also excluded since
        # they aren't played.
        return round_formulas.games_won(
            team_record.rounds(ScoreType.MATCH_POINTS),
            after_round=after_round,
            win=tournament_context.win_mp,
        )


class GamesPlayedWithBlackTieBreak(PlayerRecordTieBreak):
    """The number of games played over the board with the Black pieces.
    See FIDE Handbook C.07.7.3"""

    @staticmethod
    def static_id() -> str:
        return 'GAMES_PLAYED_WITH_BLACK'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @staticmethod
    def static_name() -> str:
        return _('Games played with black')

    @property
    def base_acronym(self) -> str:
        return 'BPG'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Counts the games played with Black, which a knock-out hands out by
        # its colour rule — it would settle the match on the colour draw.
        return False

    @property
    def base_help_text(self) -> str:
        return _('The number of games played over the board with the Black pieces.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        return sum(
            pairing.color == BoardColor.BLACK and pairing.played
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and player.game_counts_for_tie_breaks(pairing)
        )


class GamesWonWithBlackTieBreak(PlayerRecordTieBreak):
    """The number of games won over the board with the Black pieces.
    See FIDE Handbook C.07.7.4"""

    @staticmethod
    def static_id() -> str:
        return 'GAMES_WON_WITH_BLACK'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @staticmethod
    def static_name() -> str:
        return _('Games won with Black')

    @property
    def base_acronym(self) -> str:
        return 'BWG'

    @property
    def base_help_text(self) -> str:
        return _('The number of games won over the board with the Black pieces.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        return sum(
            pairing.color == BoardColor.BLACK
            and pairing.result in (Result.WIN, Result.UNRATED_WIN)
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and player.game_counts_for_tie_breaks(pairing)
        )


class ProgressiveScoresTieBreak(PlayerRecordTieBreak):
    """The sum of progressive scores.
    After each round, a participant has a certain tournament score.
    This tie-break is calculated adding the score of the participant at the end of each round.
    Options:
      - CUTTER: Exclude the first *n* rounds
    See FIDE Handbook C.07.7.5 and C.07.14.1"""

    @staticmethod
    def static_id() -> str:
        return 'PROGRESSIVE_SCORES'

    @staticmethod
    def static_name() -> str:
        return _('Progressive scores')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [CutterTieBreakOption, TeamScoreTieBreakOption]

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self._get_option(CutterTieBreakOption).cutter

    @property
    def base_acronym(self) -> str:
        return 'PS'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # A same-depth participant's score follows the bracket round by round,
        # so the progressive sum is the same for both.
        return False

    @property
    def base_help_text(self) -> str:
        return _('The sum of the score of the player at the end of each round.')

    @property
    def help_text(self) -> str:
        help_text = self.base_help_text
        rounds_ignored = self.cutter.bottom_cut
        if rounds_ignored:
            help_text += '<br/>' + ngettext(
                'The first round is ignored.',
                'The first {rounds} rounds are ignored.',
                rounds_ignored,
            ).format(rounds=rounds_ignored)
        return help_text

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        return sum(
            player.standings_points(r)
            for r in range(1 + self.cutter.bottom_cut, after_round + 1)
        )

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        score_type = self._team_score_type()
        # Cumulative team MP (or GP) after each round; first ``cutter.bottom_cut``
        # rounds skipped (FIDE 7.5 cut variant).
        own_attr: Callable[[TeamMatchRecord], float] = (
            (lambda m: m.own_mp)
            if score_type == ScoreType.MATCH_POINTS
            else (lambda m: m.own_gp)
        )
        # The score after each round, a round with no match (a rest game)
        # leaving it where it was.
        own_by_round = {
            match.round_: own_attr(match)
            for match in team_record.matches
            if match.round_ <= after_round
        }
        running = 0.0
        total = 0.0
        for round_ in range(1, after_round + 1):
            running += own_by_round.get(round_, 0.0)
            if round_ > self.cutter.bottom_cut:
                total += running
        return total


class RoundsElectedToPlayTieBreak(PlayerRecordTieBreak):
    """The number of rounds one elected to play, i.e. the rounds where a player
    did not lose by forfeit, nor elected to take a bye (ZPB, HPB, or FPB)
    See FIDE Handbook C.07.7.6"""

    @staticmethod
    def static_id() -> str:
        return 'ROUNDS_ELECTED_TO_PLAY'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @staticmethod
    def static_name() -> str:
        return _('Rounds one Elected to Play')

    @property
    def base_acronym(self) -> str:
        return 'REP'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Counts the rounds a participant was not byed out of. A bracket bye is
        # the draw's doing, not a choice, so this would punish the seeds the
        # bracket hands them to.
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'The number of rounds in which a player '
            'did not receive a HPB, a ZPB or a forfeit loss.'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        return sum(
            pairing.result
            not in (
                Result.FORFEIT_LOSS,
                Result.DOUBLE_FORFEIT,
                Result.ZERO_POINT_BYE,
                Result.HALF_POINT_BYE,
            )
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and player.game_counts_for_tie_breaks(pairing)
        )


class StandardPointsTieBreak(PlayerRecordTieBreak):
    """The number of points in the standard 1/0.5/0 point system.
    See FIDE Handbook C.07.7.7."""

    @staticmethod
    def static_id() -> str:
        return 'STANDARD_POINTS'

    @staticmethod
    def static_name() -> str:
        return _('Standard points')

    @property
    def base_acronym(self) -> str:
        return 'STD'

    @property
    def base_help_text(self) -> str:
        return _('The number of points in the standard 1/0.5/0 point system.')

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Same-depth participants share the same points count, so it can
        # never break a level match.
        return False

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        return sum(
            pairing.result.points()
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and player.game_counts_for_tie_breaks(pairing)
        )

    def get_warning_for_tournament(self, tournament: 'Tournament') -> str | None:
        if tournament.is_standard_point_system_used:
            return _(
                'This tie-break has no effect with '
                'tournaments using the standard point system.'
            )
        return None


class PointsTieBreak(PlayerRecordTieBreak):
    """The points themselves, as a ranking criterion of their own.

    TRF26 record 212 lists the criteria that *define the standings*, and
    among the tie-break codes it accepts an extra one, ``PTS``, standing
    for the number of points (the primary score in team competitions).
    Its position in the list decides the ranking, so ``212 PTS,<rest>``
    is the classic "points first, then tie-breaks" — the spec notes it is
    the same as ``202 <rest>`` — while putting it lower lets another
    criterion outrank the score.

    It is therefore not a tie-break in the C.07 sense and appears in no
    tie-break table; it exists so that the points can take their place in
    the ordered list like anything else.
    """

    # Aggregating points as a tie-break just duplicates the Total-points /
    # Average-points Championship rules, so it is not offered there.
    is_aggregatable = False

    @staticmethod
    def static_id() -> str:
        return 'POINTS'

    @property
    def usable_without_result_points(self) -> bool:
        # On a Keizer this returns the Keizer total (see
        # ``compute_player_value``), which is exactly the primary score.
        return True

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Every participant at the same bracket depth shares the same
        # cumulative score, so the points can never break a level match.
        return False

    @staticmethod
    def static_name() -> str:
        return _('Points')

    @property
    def base_acronym(self) -> str:
        return 'PTS'

    # `is_fide` is left True: it decides the OTHER_ prefix, and PTS is
    # defined by FIDE in TRF26 itself, so it takes none — even though it
    # appears in no tie-break table.

    @property
    def base_help_text(self) -> str:
        return _(
            'The points scored in the tournament (the primary score for '
            'teams). Placed first it ranks the standings as usual; placed '
            'lower, the criteria above it outrank the score.'
        )

    @property
    def allow_multiple(self) -> bool:
        # Ranking on the same score twice can never separate anyone.
        return False

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        tournament = player.tournament
        if tournament.pairing_system.id == 'KEIZER':
            # A Keizer's primary score is its running Keizer total, not a
            # count of game points; it is what the standings rank on.
            return tournament.keizer_scorer.total(player, after_round=after_round)
        if tournament.pairing_system.eliminates_participants:
            # A knock-out ranks by the round reached, not by game points.
            return tournament.knockout.ranking_value(player, after_round=after_round)
        return player.standings_points(after_round)

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        return team_record.total(tournament_context.primary_score)


class PairingNumberTieBreak(PlayerRecordTieBreak):
    """The tournament pairing number in ascending or descending order.
    Default order is ascending.
    See FIDE Handbook C.07.7.8."""

    @staticmethod
    def static_id() -> str:
        return 'PAIRING_NUMBER'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @staticmethod
    def static_name() -> str:
        return _('Tournament pairing number')

    @property
    def base_acronym(self) -> str:
        return 'TPN'

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [ReversedTieBreakOption]

    @property
    def display_absolute_value(self) -> bool:
        return True

    @property
    def base_help_text(self) -> str:
        return ''

    @property
    def help_text(self) -> str:
        is_reversed = self._get_option(ReversedTieBreakOption).value
        if is_reversed is None:
            return _(
                'The pairing numbers of the tournament in ascending '
                'or descending order (ascending by default).'
            )
        if is_reversed:
            return _('The pairing numbers of the tournament in descending order.')
        return _('The pairing numbers of the tournament in ascending order.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        is_reversed = self._get_option(ReversedTieBreakOption).value
        pairing_number = player.pairing_number
        assert pairing_number is not None
        if is_reversed:
            return pairing_number
        return -pairing_number

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> int:
        # TPN for teams reads the team's pairing_number directly.
        is_reversed = self._get_option(ReversedTieBreakOption).value
        if team_record.pairing_number is None:
            return 0
        return (
            team_record.pairing_number if is_reversed else -team_record.pairing_number
        )


class KashdanTieBreak(PlayerRecordTieBreak):
    """Grant 4 tie-break points for a win, 2 for a draw, 1 for a loss,
    and 0 for an unplayed game.
    See USCF Handbook section 34E7."""

    @staticmethod
    def static_id() -> str:
        return 'KASHDAN'

    @staticmethod
    def static_name() -> str:
        return _('Kashdan')

    @property
    def base_acronym(self) -> str:
        return 'KA'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # A weighted restatement of the score, which two participants at the
        # same bracket depth share.
        return False

    @property
    def is_fide(self) -> bool:
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'Grant 4 tie-break points for a win, 2 for a draw, '
            '1 for a loss, and 0 for an unplayed game.'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and player.game_counts_for_tie_breaks(pairing)
        ]
        score_by_result: dict[Result, float] = {
            Result.WIN: 4,
            Result.UNRATED_WIN: 4,
            Result.DRAW: 2,
            Result.UNRATED_DRAW: 2,
            Result.PENALTY_DL: 2,
            Result.UNRATED_PENALTY_DL: 2,
            Result.LOSS: 1,
            Result.UNRATED_LOSS: 1,
            Result.PENALTY_LL: 1,
            Result.UNRATED_PENALTY_LL: 1,
            Result.FORFEIT_WIN: 0,
            Result.PAIRING_ALLOCATED_BYE: 0,
            Result.FULL_POINT_BYE: 0,
            Result.HALF_POINT_BYE: 0,
            Result.NO_RESULT: 0,
            Result.ZERO_POINT_BYE: 0,
            Result.FORFEIT_LOSS: 0,
            Result.DOUBLE_FORFEIT: 0,
        }
        return float(
            sum(pairing.result.points(score_by_result) for pairing in pairings)
        )


class OpponentRecordTieBreak(TieBreak, ABC):
    @property
    def category(self) -> TieBreakCategory:
        return OpponentRecordCategory()


class BuchholzTieBreak(OpponentRecordTieBreak, ABC):
    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Two participants who reached the same bracket depth beat the same
        # shape of field — a first-round loser, a second-round loser, and so
        # on — so every Buchholz is equal by construction, moving only on bye
        # and draw artefacts.
        return False

    @property
    def forbidden_pairing_systems(self) -> list[PairingSystem]:
        """Buchholz depends on which opponents were played, so it
        gives the same value to every player in a round-robin."""
        return [RoundRobinPairingSystem()]

    @cached_property
    def legacy_03_2026(self) -> bool:
        return self._get_option(LegacyMarch2026TieBreakOption).value

    @cached_property
    def fore_modifier(self) -> bool:
        return self._get_option(ForeModifierTieBreakOption).value

    @cached_property
    def played_modifier(self) -> bool:
        return self._get_option(PlayedModifierTieBreakOption).value

    def dummy_score(
        self,
        player: TournamentPlayer,
        *,
        after_round: int = 1,
        fore_modifier: bool = False,
        opponent: TournamentPlayer | None = None,
    ) -> float:
        """Computes the dummy score for the given pairing after *after_round*."""
        tournament = player.tournament
        if fore_modifier and self.fore_round_is_paired(player, after_round):
            dummy = player.points_before(after_round) + tournament.draw_points
        else:
            dummy = player.points_after(after_round)
        if self.legacy_03_2026:
            return dummy
        return self.adjusted_dummy_score(
            dummy,
            tournament,
            after_round=after_round,
            adjust_fore=fore_modifier,
            opponent=opponent,
        )

    _cut_sum = staticmethod(unplayed_rounds.cut_sum)


class CutBuchholzTieBreak(BuchholzTieBreak, ABC):
    """Buchholz and Fore Buchholz (Art. 8.1 and 8.3): the opponents'
    adjusted scores, cut, the latter with the paired games of the final
    round taken as drawn."""

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self._get_option(CutterWithMedianTieBreakOption).cutter

    def _player_sum(
        self, player: TournamentPlayer, *, after_round: int, fore: bool
    ) -> float:
        top_cut = self.cutter.top_cut
        bottom_cut = self.cutter.bottom_cut
        if top_cut + bottom_cut >= after_round:
            return 0
        tournament: Tournament = player.tournament
        # Art. 15.2: with pre-determined pairings, forfeits count as
        # regular games — the treatment the /P flag asks for.
        played_modifier = (
            self.played_modifier or tournament.pairing_system.predetermined_pairings
        )
        # Art. 8.3 makes the paired final round a played one: it contributes
        # its opponent's adjusted score rather than a dummy.
        fore_round = (
            after_round
            if fore and self.fore_round_is_paired(player, after_round)
            else None
        )
        scores: list[float] = []
        voluntary_unplayed: list[float] = []
        for round_index, pairing in player.pairings.items():
            if round_index > after_round:
                continue
            # The played modifier only turns a forfeit into a game against
            # the scheduled opponent: a bye has no opponent to count, and
            # neither has a forfeit whose opponent was never on the pairing
            # (a board nobody was fielded against), so both keep their dummy
            # (Art. 16.4).
            should_add_dummy = (
                pairing.unplayed
                and round_index != fore_round
                and (
                    not played_modifier
                    or pairing.opponent_id is None
                    or pairing.result
                    in (
                        Result.HALF_POINT_BYE,
                        Result.ZERO_POINT_BYE,
                        Result.FULL_POINT_BYE,
                        Result.PAIRING_ALLOCATED_BYE,
                        Result.REST_GAME,
                    )
                )
            )
            if should_add_dummy:
                dummy_points = self.dummy_score(
                    player,
                    after_round=after_round,
                    fore_modifier=fore,
                    opponent=pairing.opponent,
                )
                if pairing.voluntary_unplayed:
                    voluntary_unplayed.append(dummy_points)
                else:
                    scores.append(dummy_points)
                continue
            assert pairing.opponent_id is not None
            opponent: TournamentPlayer = tournament.players_by_id[pairing.opponent_id]
            scores.append(
                self.adjusted_score(opponent, after_round=after_round, adjust_fore=fore)
            )
        return self._cut_sum(scores, voluntary_unplayed, bottom_cut, top_cut)

    def _team_sum(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
        fore: bool,
    ) -> float:
        top_cut = self.cutter.top_cut
        bottom_cut = self.cutter.bottom_cut
        if top_cut + bottom_cut >= after_round:
            return 0.0
        score_type = self._team_score_type()
        # Art. 15.2: with pre-determined pairings, forfeits count as
        # regular matches — the treatment the /P flag asks for.
        played_modifier = (
            self.played_modifier or tournament_context.predetermined_pairings
        )
        draw_value = (
            tournament_context.draw_mp
            if score_type == ScoreType.MATCH_POINTS
            else tournament_context.draw_gp
        )

        def opponent_score(opponent_id: int) -> float:
            return adjust_opponent_total(
                all_records[opponent_id],
                score_type,
                after_round=after_round,
                draw_mp=tournament_context.draw_mp,
                draw_gp=tournament_context.draw_gp,
                adjust_fore=fore,
            )

        fore_round = (
            after_round
            if fore and fore_round_is_paired(team_record, after_round)
            else None
        )
        scores: list[float] = []
        vur: list[float] = []
        for match in team_record.matches:
            if match.round_ > after_round:
                continue
            if not tournament_context.match_counts_for_tie_breaks(match):
                continue
            should_add_dummy = match.round_ != fore_round and (
                (match.unplayed and not played_modifier)
                or (played_modifier and match.is_bye)
            )
            if should_add_dummy:
                value = dummy_opponent_score(
                    team_record,
                    score_type,
                    rounds=tournament_context.rounds,
                    draw_value=draw_value,
                    opponent_adjusted=(
                        opponent_score(match.opponent_id)
                        if not match.is_bye and match.opponent_id is not None
                        else None
                    ),
                    legacy=self.legacy_03_2026,
                    fore_after_round=after_round if fore else None,
                )
                if match.voluntary_unplayed:
                    vur.append(value)
                else:
                    scores.append(value)
                continue
            assert match.opponent_id is not None
            scores.append(opponent_score(match.opponent_id))
        return self._cut_sum(scores, vur, bottom_cut, top_cut)


class StandardBuchholzTieBreak(CutBuchholzTieBreak):
    """The sum of the scores of each of the opponents of a participant.
    Options:
      - CUTTER_WITH_MEDIAN: Remove the bottom *n* and the top *m* contributions.
    When cutting the lowest contributions, all Voluntary Unplayed Rounds
    (requested byes and forfeit losses) are cut before any other round is cut.
    Both values must be non-negative.
    *cut_top* must be at most equal to *cut_bottom*.
      - PLAYED_MODIFIER: When True, forfeit losses and wins are considered
    played against the scheduled opponent.
      - LEGACY_03_2026: Use the rules effective until March 2026 (legacy).
      - TEAM_SCORE: In team events, picks MP or GP as the reference
    score for the team-level computation (FIDE MTB26 ``BH:MP`` / ``BH:GP``).
    See FIDE Handbook C.07.8.1"""

    @staticmethod
    def static_id() -> str:
        return 'BUCHHOLZ'

    @staticmethod
    def static_name() -> str:
        return _('Buchholz')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            CutterWithMedianTieBreakOption,
            PlayedModifierTieBreakOption,
            LegacyMarch2026TieBreakOption,
            TeamScoreTieBreakOption,
        ]

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        return self._team_sum(
            team_record,
            all_records,
            tournament_context,
            after_round=after_round,
            fore=False,
        )

    @property
    def base_acronym(self) -> str:
        return 'BH'

    @property
    def base_help_text(self) -> str:
        return _('The sum of the scores of each of the opponents of the player.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        return self._player_sum(player, after_round=after_round, fore=False)


class ForeBuchholzTieBreak(CutBuchholzTieBreak):
    """the Buchholz score as if all paired games for the final round had ended in draws.
    Options:
        - CUTTER_WITH_MEDIAN: Remove the *n* lowest and the *m* highest contributions.
    When cutting the lowest contributions, all Voluntary Unplayed Rounds
    (requested byes and forfeit losses) are cut before any other round is cut.
    Both values must be non-negative.
    *cut_top* must be at most equal to *cut_bottom*.
      - PLAYED_MODIFIER: When True, forfeit losses and wins are considered
    played against the scheduled opponent.
      - LEGACY_03_2026: Use the rules effective until March 2026 (legacy).
    See FIDE Handbook C.07.8.3"""

    @staticmethod
    def static_id() -> str:
        return 'FORE_BUCHHOLZ'

    @staticmethod
    def static_name() -> str:
        return _('Fore Buchholz')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            CutterWithMedianTieBreakOption,
            PlayedModifierTieBreakOption,
            LegacyMarch2026TieBreakOption,
            TeamScoreTieBreakOption,
        ]

    @property
    def base_acronym(self) -> str:
        return 'FB'

    @property
    def base_help_text(self) -> str:
        return _(
            'Buchholz score calculated as if all paired games '
            'for the final round had ended in draws.'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        return self._player_sum(player, after_round=after_round, fore=True)

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        return self._team_sum(
            team_record,
            all_records,
            tournament_context,
            after_round=after_round,
            fore=True,
        )


class SumOfBuchholzTieBreak(BuchholzTieBreak):
    """The sum of Buchholz scores of the opponents.
    Options:
      - FORE_MODIFIER: When True, will use Fore Buchholz instead of total Buchholz.
    """

    @staticmethod
    def static_id() -> str:
        return 'SUM_OF_BUCHHOLZ'

    @staticmethod
    def static_name() -> str:
        return _('Sum of Buchholz')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            ForeModifierTieBreakOption,
            LegacyMarch2026TieBreakOption,
            TeamScoreTieBreakOption,
        ]

    @cached_property
    def sub_tie_break(self) -> TieBreak:
        options: list[TieBreakOption] = [
            self._get_option(LegacyMarch2026TieBreakOption)
        ]
        return (
            ForeBuchholzTieBreak(options)
            if self.fore_modifier
            else StandardBuchholzTieBreak(options)
        )

    @property
    def base_acronym(self) -> str:
        return 'SOB'

    @property
    def is_fide(self) -> bool:
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'The sum of the [{tie_break}] scores of '
            'the opponents played over the board.'
        ).format(tie_break=_('Fore Buchholz') if self.fore_modifier else _('Buchholz'))

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        tournament: Tournament = player.tournament
        opponents: list[TournamentPlayer | None] = [
            tournament.players_by_id.get(pairing.opponent_id)
            if pairing.opponent_id
            else None
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.opponent_id is not None
        ]
        return sum(
            float(
                self.sub_tie_break.compute_player_value(
                    opponent, after_round=after_round
                )
            )
            for opponent in opponents
            if opponent is not None
        )

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        # Non-FIDE-mandatory: sum (vs AOB's average) of each played
        # opponent's own team-BH (or team-FB when /F). Mirrors AOB but
        # without the /N division.
        sub_options: list[TieBreakOption] = [
            self._get_option(LegacyMarch2026TieBreakOption)
        ]
        with suppress(KeyError):
            sub_options.append(self._get_option(TeamScoreTieBreakOption))
        sub_tb: TieBreak = (
            ForeBuchholzTieBreak(sub_options)
            if self.fore_modifier
            else StandardBuchholzTieBreak(sub_options)
        )
        return sum(
            float(
                sub_tb.compute_team_value(
                    all_records[match.opponent_id],
                    all_records,
                    tournament_context,
                    after_round=after_round,
                )
            )
            for match in team_record.matches
            if match.round_ <= after_round
            and match.played
            and match.opponent_id is not None
            and tournament_context.match_counts_for_tie_breaks(match)  # FIDE 6.6
        )


class AverageOfBuchholzTieBreak(BuchholzTieBreak):
    """The average of opponents Buchholz scores.
    Options:
      - FORE_MODIFIER: When True, will use Fore Buchholz instead of total Buchholz.
    See FIDE Handbook C.07.8.2."""

    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_OF_BUCHHOLZ'

    @staticmethod
    def static_name() -> str:
        return _('Average of opponents Buchholz')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            ForeModifierTieBreakOption,
            LegacyMarch2026TieBreakOption,
            TeamScoreTieBreakOption,
        ]

    @cached_property
    def sub_tie_break(self) -> TieBreak:
        options: list[TieBreakOption] = [
            self._get_option(LegacyMarch2026TieBreakOption)
        ]
        return (
            ForeBuchholzTieBreak(options)
            if self.fore_modifier
            else StandardBuchholzTieBreak(options)
        )

    @property
    def base_acronym(self) -> str:
        return 'AOB'

    @property
    def base_help_text(self) -> str:
        return _(
            'The average of the [{tie_break}] scores of '
            'the opponents played over the board.'
        ).format(tie_break=_('Fore Buchholz') if self.fore_modifier else _('Buchholz'))

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        tournament: Tournament = player.tournament
        opponents: list[TournamentPlayer] = [
            tournament.players_by_id[pairing.opponent_id]
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
            and pairing.opponent_id is not None
            and pairing.played
        ]
        if not opponents:
            return 0
        return sum(
            float(
                self.sub_tie_break.compute_player_value(
                    opponent, after_round=after_round
                )
            )
            for opponent in opponents
            if opponent is not None
        ) / len(opponents)

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        # AOB for teams: average of each played opponent's own team BH
        # (FB if Fore modifier). Recurse: build a child Buchholz tie-break
        # carrying the same team-score option and ask it for each
        # opponent's value.
        sub_options: list[TieBreakOption] = [
            self._get_option(LegacyMarch2026TieBreakOption)
        ]
        with suppress(KeyError):
            sub_options.append(self._get_option(TeamScoreTieBreakOption))
        sub_tb: TieBreak = (
            ForeBuchholzTieBreak(sub_options)
            if self.fore_modifier
            else StandardBuchholzTieBreak(sub_options)
        )
        opponent_records = [
            all_records[match.opponent_id]
            for match in team_record.matches
            if match.round_ <= after_round
            and match.played
            and match.opponent_id is not None
            and tournament_context.match_counts_for_tie_breaks(match)  # FIDE 6.6
        ]
        if not opponent_records:
            return 0.0
        return sum(
            float(
                sub_tb.compute_team_value(
                    opponent,
                    all_records,
                    tournament_context,
                    after_round=after_round,
                )
            )
            for opponent in opponent_records
        ) / len(opponent_records)


class SonnebornBergerTieBreak(OpponentRecordTieBreak):
    """Score computed by adding, for each round,
    a value given by multiplying their score of the opponent by
    the points scored against them.
    Options:
      - CUTTER: Remove the *n* lowest contributions.
      - PLAYED_MODIFIER: When True, forfeit wins and losses will be counted
    as played games (only relevant in Swiss tournaments).
    See FIDE Handbook C.07.9.1."""

    @staticmethod
    def static_id() -> str:
        return 'SONNEBORN_BERGER'

    @staticmethod
    def static_name() -> str:
        return _('Sonneborn-Berger')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            CutterTieBreakOption,
            PlayedModifierTieBreakOption,
            LegacyMarch2026TieBreakOption,
        ]

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self._get_option(CutterTieBreakOption).cutter

    @cached_property
    def played_modifier(self) -> bool:
        return self._get_option(PlayedModifierTieBreakOption).value

    @cached_property
    def legacy_03_2026(self) -> bool:
        return self._get_option(LegacyMarch2026TieBreakOption).value

    @property
    def base_acronym(self) -> str:
        return 'SB'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Weights the same opponent scores as Buchholz by the points scored
        # against them; the bracket fixes both for participants of the same
        # depth.
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'Score computed by adding, for each round, '
            'a value given by multiplying the score of '
            'the opponent by the points scored against them.'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        tournament: Tournament = player.tournament
        cut = self.cutter.bottom_cut
        if cut >= after_round:
            return 0
        played_modifier = (
            self.played_modifier
            or tournament.pairing_system == RoundRobinPairingSystem()
        )
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        contributions: list[WeightedContribution] = []
        for pairing in pairings.values():
            if not player.game_counts_for_tie_breaks(pairing):
                continue
            # The played modifier only turns a forfeit into a game against
            # the scheduled opponent: a bye has no opponent to count and
            # keeps its dummy (Art. 16.4).
            if pairing.unplayed and (
                not played_modifier or pairing.opponent_id is None
            ):
                dummy, result = self._dummy_score(
                    player, pairing, after_round=after_round
                )
                value = dummy * result.points(tournament.point_values)
                contributions.append(
                    WeightedContribution(dummy, value, pairing.voluntary_unplayed)
                )
            elif pairing.played or (pairing.unplayed and played_modifier):
                assert pairing.opponent_id is not None
                opponent: TournamentPlayer = tournament.players_by_id[
                    pairing.opponent_id
                ]
                opponent_score = self.adjusted_score(opponent, after_round=after_round)
                contribution = (
                    pairing.result.points(tournament.point_values) * opponent_score
                )
                contributions.append(
                    WeightedContribution(opponent_score, contribution, False)
                )
        kept = unplayed_rounds.cut_least_significant(contributions, cut)
        return sum(entry.value for entry in kept)

    def _dummy_score(
        self,
        player: TournamentPlayer,
        pairing: Pairing,
        *,
        after_round: int = 1,
    ) -> tuple[float, Result]:
        """Computes the dummy score for the given pairing after *after_round*."""
        dummy = player.points_after(after_round)
        if not self.legacy_03_2026:
            dummy = self.adjusted_dummy_score(
                dummy,
                player.tournament,
                after_round=after_round,
                opponent=pairing.opponent,
            )
        match pairing.result:
            case (
                Result.FORFEIT_WIN
                | Result.PAIRING_ALLOCATED_BYE
                | Result.FULL_POINT_BYE
            ):
                return dummy, Result.WIN
            case Result.HALF_POINT_BYE:
                return dummy, Result.DRAW
            case (
                Result.ZERO_POINT_BYE
                | Result.FORFEIT_LOSS
                | Result.DOUBLE_FORFEIT
                | Result.NO_RESULT
            ):
                return dummy, Result.LOSS
            case _:
                return dummy, pairing.result


class KoyaTieBreak(OpponentRecordTieBreak):
    """The number of points achieved against all players
    who have scored at 50% of the maximum possible score.
    This is only used in Round-Robin tournaments, but is still
    defined for Swiss tournaments.
    Options:
      - KOYA_LIMIT: Number of half-points above / below the 50% limit
      required for opponents to be considered.
    See FIDE Handbook C.07.9.2."""

    @staticmethod
    def static_id() -> str:
        return 'KOYA'

    @staticmethod
    def static_name() -> str:
        return _('Koya system')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [KoyaLimitTieBreakOption, TeamScoreTieBreakOption]

    @cached_property
    def limit(self) -> int | None:
        return self._get_option(KoyaLimitTieBreakOption).value

    @property
    def forbidden_pairing_systems(self) -> list[PairingSystem]:
        return [SwissPairingSystem()]

    @property
    def base_acronym(self) -> str:
        return 'KS'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Reads the points scored against opponents who reached half the
        # maximum — a proportion of a full field that a bracket, whose losers
        # stop playing, never produces.
        return False

    @property
    def equation_suffix(self) -> str:
        if not self.limit:
            return ''
        member = ngettext(
            '{count} half-point', '{count} half-points', abs(self.limit)
        ).format(count=abs(self.limit))
        operator = '-' if self.limit < 0 else '+'
        return f' {operator} {member}'

    @property
    def base_help_text(self) -> str:
        equation = _('50%% of the maximum possible score').replace('%%', '%')
        return _(
            'The number of points achieved against all players '
            'who have scored at least L points (L = {equation}).'
        ).format(equation=equation + self.equation_suffix)

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> float:
        tournament: Tournament = player.tournament
        win_points = tournament.win_points
        score_limit = 0.5 * win_points * after_round
        if self.limit:
            draw_points = tournament.draw_points
            score_limit += draw_points * self.limit
        pairings: dict[int, Pairing] = {
            round_index: pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        }
        score = 0.0
        for pairing in pairings.values():
            if pairing.opponent_id is None:
                continue
            if not player.game_counts_for_tie_breaks(pairing):
                continue
            opponent = tournament.players_by_id[pairing.opponent_id]
            opponent_score = opponent.standings_points(after_round)
            if opponent_score >= score_limit:
                score += pairing.result.points(tournament.point_values)
        return score

    @property
    def supports_team_mode(self) -> bool:
        return True

    def compute_team_value(
        self,
        team_record: 'TeamRecord',
        all_records: dict[int, 'TeamRecord'],
        tournament_context: 'TeamTieBreakContext',
        *,
        after_round: int,
    ) -> float:
        score_type = self._team_score_type()
        # 50% of max possible team score over ``after_round`` matches.
        # For MP: win_mp × rounds × 0.5. For GP: team_player_count × rounds × 0.5.
        if score_type == ScoreType.MATCH_POINTS:
            max_per_round = tournament_context.win_mp
            half_step = tournament_context.draw_mp
        else:
            max_per_round = float(tournament_context.team_player_count)
            half_step = tournament_context.draw_gp / max(
                tournament_context.team_player_count, 1
            )
        score_limit = 0.5 * max_per_round * after_round
        if self.limit:
            score_limit += half_step * self.limit
        score = 0.0
        for match in team_record.matches:
            if match.round_ > after_round or match.opponent_id is None:
                continue
            if not tournament_context.match_counts_for_tie_breaks(match):
                continue
            opponent = all_records[match.opponent_id]
            if opponent.total(score_type) >= score_limit:
                score += team_record.own_against(match, score_type)
        return score


class OpponentRatingTieBreak(TieBreak, ABC):
    @property
    def category(self) -> TieBreakCategory:
        return RatingCategory()

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [EstimatedRatingsTieBreakOption]

    @property
    def allow_unrated_players(self) -> bool:
        return False

    @property
    def allow_estimated_players(self) -> bool:
        return self._get_option(EstimatedRatingsTieBreakOption).value

    def get_warning_for_tournament(self, tournament: 'Tournament') -> str | None:
        if tournament.estimated_count:
            return _(
                'This tie-break is not recommended with '
                'estimated players ({count} in the tournament).'
            ).format(count=tournament.estimated_count)
        if tournament.multiple_fide_periods:
            return _(
                'This tie-break is not recommended on tournaments '
                'lasting over multiple FIDE periods.'
            )
        return None


class AverageRatingOpponentsTieBreak(OpponentRatingTieBreak):
    """The average rating of opponents.
    Only opponents met over the board will be counted.
    WARNING: This assumes everyone has a rating; if an opponent does not have
    a rating, they will be removed from consideration.
    Options:
      - CUTTER_WITH_MEDIAN: Remove the *n* lowest and the *m* highest ratings.
    See FIDE Handbook C.07.10.1"""

    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_RATING_OPPONENTS'

    @staticmethod
    def static_name() -> str:
        return _('Average rating of opponents')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            CutterWithMedianTieBreakOption,
            EstimatedRatingsTieBreakOption,
        ]

    @cached_property
    def cutter(self) -> TieBreakCutter:
        return self._get_option(CutterWithMedianTieBreakOption).cutter

    @property
    def base_acronym(self) -> str:
        return 'ARO'

    @property
    def base_help_text(self) -> str:
        return _('The average of the ratings of the opponents played over the board.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        tournament: Tournament = player.tournament
        top_cut = self.cutter.top_cut
        bottom_cut = self.cutter.bottom_cut
        if top_cut + bottom_cut >= after_round:
            return 0
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
        ]
        ratings = []
        for pairing in pairings:
            if pairing.unplayed:
                continue
            if not player.game_counts_for_tie_breaks(pairing):
                continue
            assert pairing.opponent_id is not None
            opponent = tournament.players_by_id[pairing.opponent_id]
            ratings.append(opponent.rating)
        ratings = sorted(ratings)
        ratings = ratings[bottom_cut:-top_cut] if top_cut else ratings[bottom_cut:]
        if not ratings:
            return 0
        average = sum(ratings) / len(ratings)
        return Utils.round_ranking(average)


class TournamentPerformanceRatingTieBreak(OpponentRatingTieBreak):
    """The Average Rating of the Opponents, added
    to a number resulting from the conversion of the fractional score
    into RD (see FIDE Rating Regulations for the Conversion Table).
    See FIDE Handbook C.07.10.2."""

    @staticmethod
    def static_id() -> str:
        return 'TOURNAMENT_PERFORMANCE_RATING'

    @staticmethod
    def static_name() -> str:
        return _('Tournament performance rating')

    @property
    def base_acronym(self) -> str:
        return 'TPR'

    @property
    def base_help_text(self) -> str:
        return _(
            "Tie-break based on the opponents' ratings and the player's "
            'score (consult the FIDE Handbook for more details).'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        tournament: Tournament = player.tournament
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round and pairing.played
        ]
        ratings = []
        score = 0.0
        for pairing in pairings:
            if not player.game_counts_for_tie_breaks(pairing):
                continue
            assert pairing.opponent_id is not None
            opponent = tournament.players_by_id[pairing.opponent_id]
            ratings.append(opponent.rating)
            score += pairing.result.points(tournament.point_values)
        if not ratings:
            return 0
        max_score = len(ratings) * tournament.win_points
        average = sum(ratings) / len(ratings)
        # The conversion table is read on the percentage rounded to the
        # nearest whole number, 0.5 up, the way every rounding in the
        # FIDE regulations goes (C.07 Art. 10.1, B.02 Art. 8.3.4).
        fractional_score = Utils.round_ranking(100 * score / max_score) / 100
        bonus = Utils.performance_bonus(fractional_score)
        return Utils.round_ranking(average + bonus)


class AveragePerformanceRatingOpponentsTieBreak(OpponentRatingTieBreak):
    """The average of the tournament performance rating of the
    opponents, only taking played games into account.
    See FIDE Handbook C.07.10.4."""

    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_PERFORMANCE_RATING_OPPONENTS'

    @staticmethod
    def static_name() -> str:
        return _('Average performance rating of opponents')

    @property
    def base_acronym(self) -> str:
        return 'APRO'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Averages a rating measure over the opponents rather than over the
        # path itself; across a bracket's handful of games it separates on
        # noise. ARO and TPR measure the path directly.
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'The average of the [{tie_break}] scores of '
            'the opponents played over the board.'
        ).format(tie_break=_('Tournament performance rating'))

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        tournament: Tournament = player.tournament
        played_games: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
            and pairing.played
            and player.game_counts_for_tie_breaks(pairing)
        ]
        performance_ratings = []
        performance_tie_break = TournamentPerformanceRatingTieBreak()
        for pairing in played_games:
            assert pairing.opponent_id is not None
            opponent: TournamentPlayer = tournament.players_by_id[pairing.opponent_id]
            opponent_tpr = performance_tie_break.compute_player_value(
                opponent, after_round=after_round
            )
            performance_ratings.append(opponent_tpr)
        if not performance_ratings:
            return 0
        average = sum(performance_ratings) / len(performance_ratings)
        return Utils.round_ranking(average)


class PerfectTournamentPerformanceTieBreak(OpponentRatingTieBreak):
    """The lowest rating that a participant should have for their
    expected score to be greater than or equal to their tournament score.
    This assumes that all players are rated, or at least have an estimation.
    See FIDE Handbook C.07.10.3."""

    @staticmethod
    def static_id() -> str:
        return 'PERFECT_TOURNAMENT_PERFORMANCE'

    @staticmethod
    def static_name() -> str:
        return _('Perfect tournament performance')

    @property
    def base_acronym(self) -> str:
        return 'PTP'

    @property
    def base_help_text(self) -> str:
        return _(
            'The lowest rating that a player should have for their '
            'expected score to be greater than or equal to their score.'
        )

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        played_rounds: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
            and pairing.played
            and player.game_counts_for_tie_breaks(pairing)
        ]
        if not played_rounds:
            return 0
        tournament: Tournament = player.tournament
        actual_score = Decimal(
            sum(
                pairing.result.points(tournament.point_values)
                for pairing in played_rounds
            )
        )
        if actual_score == len(played_rounds) * Result.LOSS.points(
            tournament.point_values
        ):
            return -800 + min(
                tournament.players_by_id[pairing.opponent_id].rating
                for pairing in played_rounds
                if pairing.opponent_id is not None
            )
        ratings: list[int] = [
            tournament.players_by_id[pairing.opponent_id].rating
            for pairing in played_rounds
            if pairing.opponent_id is not None
        ]
        performance_tie_break = TournamentPerformanceRatingTieBreak()
        first_estimation = performance_tie_break.compute_player_value(
            player, after_round=after_round
        )
        first_expected_score = self._expected_score(
            first_estimation, ratings, tournament.point_values
        )
        if isclose(first_expected_score, actual_score, abs_tol=0.01):
            mid = Utils.round_ranking(first_estimation)
        else:
            if not first_expected_score:
                return 0
            second_estimation = Utils.round_ranking(
                first_estimation * actual_score / first_expected_score
            )
            second_expected_score = self._expected_score(
                second_estimation, ratings, tournament.point_values
            )

            if first_expected_score >= second_expected_score:
                low, high = second_estimation, first_estimation
            else:
                low, high = first_estimation, second_estimation
            while not isclose(
                actual_score,
                mid_score := self._expected_score(
                    (mid := Utils.round_ranking((low + high) / 2)),
                    ratings,
                    tournament.point_values,
                ),
                abs_tol=0.01,
            ):
                if mid_score >= actual_score:
                    if high == mid:
                        break
                    high = mid
                else:
                    if low == mid:
                        break
                    low = mid
        # Wherever the search landed, the answer is the lowest rating whose
        # expected score reaches the actual one: step down while it does,
        # then back up to the first that does.
        while (
            self._expected_score(mid, ratings, tournament.point_values) >= actual_score
        ):
            mid -= 1
        while (
            self._expected_score(mid, ratings, tournament.point_values) < actual_score
        ):
            mid += 1
        return mid

    @classmethod
    def _expected_score(
        cls,
        player_rating: int,
        opponent_ratings: Iterable[int],
        point_values: dict[Result, float] | None = None,
    ) -> Decimal:
        chances = [
            cls.win_chances(player_rating, opponent_rating)
            for opponent_rating in opponent_ratings
        ]
        return Decimal(
            sum(
                chance[0] * Decimal(Result.WIN.points(point_values))
                + chance[1] * Decimal(Result.LOSS.points(point_values))
                for chance in chances
            )
        )

    @staticmethod
    def win_chances(
        player_rating: int, opponent_rating: int
    ) -> tuple[Decimal, Decimal]:
        difference = abs(player_rating - opponent_rating)
        # FIDE Rating Regulations 8.1b: the first rating difference each
        # expected score covers, from 0.50 up.
        lower_bounds: list[int] = [
            0,
            4,
            11,
            18,
            26,
            33,
            40,
            47,
            54,
            62,
            69,
            77,
            84,
            92,
            99,
            107,
            114,
            122,
            130,
            138,
            146,
            154,
            163,
            171,
            180,
            189,
            198,
            207,
            216,
            226,
            236,
            246,
            257,
            268,
            279,
            291,
            303,
            316,
            329,
            345,
            358,
            375,
            392,
            412,
            433,
            457,
            485,
            518,
            560,
            620,
            736,
        ]
        difference_index = bisect_right(lower_bounds, difference) - 1
        high = Decimal('0.5') + Decimal('0.01') * difference_index
        low = 1 - high
        if player_rating >= opponent_rating:
            return high, low
        return low, high


class AveragePerfectPerformanceTieBreak(OpponentRatingTieBreak):
    """The average of the Perfect Tournament Performances
    of the opponents (only those who played).
    See FIDE Hand book C.07.10.5."""

    @staticmethod
    def static_id() -> str:
        return 'AVERAGE_PERFECT_PERFORMANCE'

    @staticmethod
    def static_name() -> str:
        return _('Average perfect performance of opponents')

    @property
    def base_acronym(self) -> str:
        return 'APPO'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # Averages a rating measure over the opponents rather than over the
        # path itself; across a bracket's handful of games it separates on
        # noise. ARO and PTP measure the path directly.
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'The average of the [{tie_break}] scores of '
            'the opponents played over the board.'
        ).format(tie_break=_('Perfect tournament performance'))

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        pairings: list[Pairing] = [
            pairing
            for round_index, pairing in player.pairings.items()
            if round_index <= after_round
            and pairing.played
            and player.game_counts_for_tie_breaks(pairing)  # FIDE 6.6
        ]
        ptp_tie_break = PerfectTournamentPerformanceTieBreak()
        tournament: Tournament = player.tournament
        ptp = [
            ptp_tie_break.compute_player_value(
                tournament.players_by_id[pairing.opponent_id],
                after_round=after_round,
            )
            for pairing in pairings
            if pairing.opponent_id is not None
        ]

        if not ptp:
            return 0
        return Utils.round_ranking(sum(ptp) / len(ptp))


class PlayerRatingTieBreak(OpponentRatingTieBreak):
    """The player's rating in ascending or descending order.
    Default order is descending.
    See FIDE Handbook C.07.10.6."""

    @staticmethod
    def static_id() -> str:
        return 'RATING'

    @property
    def usable_without_result_points(self) -> bool:
        # The player's own rating — no game points involved, and the
        # customary tie-break after a Keizer score.
        return True

    @staticmethod
    def static_name() -> str:
        return _('Rating')

    @property
    def base_acronym(self) -> str:
        return 'RTNG'

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            ReversedTieBreakOption,
            EstimatedRatingsTieBreakOption,
        ]

    @property
    def display_absolute_value(self) -> bool:
        return True

    @property
    def base_help_text(self) -> str:
        return ''

    @property
    def help_text(self) -> str:
        is_reversed = self._get_option(ReversedTieBreakOption).value
        if is_reversed is None:
            return _(
                'The ratings in ascending or descending order (descending by default).'
            )
        if is_reversed:
            return _('The ratings in ascending order.')
        return _('The ratings in descending order.')

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        is_reversed = self._get_option(ReversedTieBreakOption).value
        if is_reversed:
            return -player.rating
        return player.rating


class DirectEncounterTieBreak(TieBreak):
    """Direct Encounter score.
    Options:
      - PLAYED_MODIFIER: When False and the tournament is a Swiss tournament, all forfeit games
    will be excluded from consideration.
    See FIDE Handbook C.07.6."""

    is_aggregatable = False

    @staticmethod
    def static_id() -> str:
        return 'DIRECT_ENCOUNTER'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @classmethod
    def static_name(cls) -> str:
        return _('Direct encounter')

    @staticmethod
    def available_options() -> list[type[TieBreakOption]]:
        return [
            PlayedModifierTieBreakOption,
        ]

    @cached_property
    def played_modifier(self) -> bool:
        return self._get_option(PlayedModifierTieBreakOption).value

    @property
    def base_acronym(self) -> str:
        return 'DE'

    @property
    def usable_as_knockout_advancement(self) -> bool:
        # The only game the two have ever played against each other is the one
        # that just drew. It is also the one tie-break computed per rank
        # group rather than per participant, so a match would read 0 against
        # 0 even where the bracket did let them meet twice.
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'Tie-break favoring players which have won '
            'against the players they are tied with '
            '(consult the FIDE handbook for more details).'
        )

    @property
    def category(self) -> TieBreakCategory:
        return OtherCategory()

    @property
    def display_rank_delta(self) -> bool:
        return True

    @property
    def allow_multiple(self) -> bool:
        return True

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        """The value is computed all the players at once (see `compute_all_player_values`)."""
        return 0

    @property
    def is_computed_per_player(self) -> bool:
        return False

    def compute_all_player_values(
        self,
        tournament: 'Tournament',
        tie_break_index: int,
        *,
        after_round: int,
    ) -> dict[int, int]:
        """Form groups of tied players. Amongst each group,
        attribute (if possible) an integer value from 0 to len(group).
        """

        # Group players by the rank sort key before the tie-break. Players
        # excluded from the standings (FIDE 6.6) take no part in the direct
        # encounter — they are neither ranked nor counted as opponents.
        players_by_rank_group: dict[tuple, list[TournamentPlayer]] = defaultdict(list)
        for player in tournament.players:
            if player.is_excluded_from_standings:
                continue
            rank_group = player.rank_sort_key_before_tie_break(tie_break_index)
            players_by_rank_group[rank_group].append(player)

        values_by_player_id: dict[int, int] = {}
        point_values = tournament.point_values.copy()
        # Art. 6.1.1: a forfeit is excluded from the encounters unless the
        # regulations include it, and an excluded game is not an encounter
        # at all — the two are left as having not met, which is what
        # decides whether the standings between them can place anybody.
        excluded_results: frozenset[Result] = frozenset()
        if (
            tournament.pairing_system == SwissPairingSystem()
            and not self.played_modifier
        ):
            excluded_results = frozenset(
                {
                    Result.FORFEIT_WIN,
                    Result.DOUBLE_FORFEIT,
                    Result.FORFEIT_LOSS,
                }
            )
        for player_group in players_by_rank_group.values():
            players_by_id = {player.id: player for player in player_group}

            def min_max(
                player_id: int,
                group_ids: Sequence[int],
                players_by_id: dict[int, TournamentPlayer] = players_by_id,
            ) -> tuple[float, float]:
                return self._compute_player_min_max_points(
                    players_by_id[player_id],
                    [players_by_id[group_id] for group_id in group_ids],
                    after_round,
                    point_values,
                    excluded_results,
                )

            rank_by_encounters(list(players_by_id), min_max, values_by_player_id)
        return values_by_player_id

    @staticmethod
    def _compute_player_min_max_points(
        player: TournamentPlayer,
        player_group: list[TournamentPlayer],
        after_round: int,
        point_values: dict[Result, float] | None,
        excluded_results: frozenset[Result] = frozenset(),
    ) -> tuple[float, float]:
        """Compute the min and max possible points a player
        can achieve against other players of the group."""
        group_player_ids = tuple(
            player_.id for player_ in player_group if player_.id != player.id
        )
        group_pairings_by_opponent_id: dict[int, list[float]] = defaultdict(list)
        for round_, pairing in player.pairings_by_round.items():
            if (
                round_ <= after_round
                and pairing.opponent_id in group_player_ids
                and pairing.result not in excluded_results
            ):
                group_pairings_by_opponent_id[pairing.opponent_id].append(
                    pairing.result.points(point_values)
                )
        group_points: float = 0.0
        not_played: int = 0
        for opponent_id in group_player_ids:
            if group_pairings_by_opponent_id[opponent_id]:
                group_points += float(fmean(group_pairings_by_opponent_id[opponent_id]))
            else:
                not_played += 1
        return (
            group_points + Result.LOSS.points(point_values) * not_played,
            group_points + Result.WIN.points(point_values) * not_played,
        )

    @property
    def is_used_for_team_ranking(self) -> bool:
        return False


class ManualTieBreak(TieBreak):
    """Used for play-off's, etc"""

    is_aggregatable = False

    @staticmethod
    def static_id() -> str:
        return 'MANUAL'

    @property
    def usable_without_result_points(self) -> bool:
        return True

    @classmethod
    def static_name(cls) -> str:
        return _('Manual')

    @property
    def base_acronym(self) -> str:
        return 'MAN'

    @property
    def is_fide(self) -> bool:
        return False

    @property
    def base_help_text(self) -> str:
        return _(
            'After the last round, reorder manually '
            'the tied players from the Pairings tab.'
        )

    @property
    def category(self) -> TieBreakCategory:
        return OtherCategory()

    @property
    def display_rank_delta(self) -> bool:
        return True

    @property
    def is_manual(self) -> bool:
        return True

    def compute_player_value(
        self, player: TournamentPlayer, *, after_round: int
    ) -> int:
        if not player.tournament.finished:
            return 0
        return player.stored_tournament_player.manual_tiebreak or 0

    @property
    def is_used_for_team_ranking(self) -> bool:
        return False
