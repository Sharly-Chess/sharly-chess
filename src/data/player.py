from operator import attrgetter
import weakref
from collections import Counter
from datetime import date
from functools import total_ordering, cached_property
from typing import TYPE_CHECKING, Any
from trf import Player as TrfPlayer
from trf.Player import Game as TrfGame

from common.i18n import _
from data.pairing import Pairing
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredPlayer, StoredPairing
from plugins.manager import plugin_manager
from plugins.utils import PluginData
from utils import Utils
from utils.enum import (
    PlayerGender,
    PlayerTitle,
    BoardColor,
    Result,
    TitleNorm,
    TournamentRating,
    PlayerRatingType,
    PlayerCategory,
)
from utils.types import (
    Federation,
    Club,
    PlayerRating,
    PlayerRatingAndType,
    NormCheckResult,
    TieBreakValue,
)
from utils.fide_ratings import percentage_score_rating_difference

if TYPE_CHECKING:
    from _weakref import ReferenceType
    from data.event import Event
    from data.tournament import Tournament


@total_ordering
class Player:
    # TODO (Molrn - multi tournament) Split into 2 classes:
    #  - Player(event, stored_player)
    #  - TournamentPlayer(tournament, player, stored_tournament_player)
    def __init__(
        self,
        tournament: 'Tournament',
        stored_player: StoredPlayer,
    ):
        self._tournament_ref: 'ReferenceType[Tournament]' = weakref.ref(tournament)
        self.stored_player = stored_player
        self.stored_tournament_player = self.stored_player.stored_tournament_player
        self.ratings = self._get_ratings()
        self.plugin_data = self._get_plugin_data()
        self.transient_plugin_data: dict[str, object] = {}

        # TournamentPlayer
        self.pairings_by_round = self._get_pairings_by_round()
        self.points: float | None = None
        self.vpoints: float | None = None
        self.board_id: int | None = None
        self.board_number: int | None = None
        self.color: BoardColor | None = None
        self._tie_break_values: list[TieBreakValue] | None = None
        self._rank: int | None = None
        self.time_control_trf25: str | None = None
        self.time_control_modified: bool | None = None
        self.tie_break_variables: dict[str, Any] = {}

    @staticmethod
    def plugin_data_class_by_plugin_id() -> dict[str, type[PluginData]]:
        return {
            plugin_id: plugin_data_class
            for plugin_id, plugin_data_class in plugin_manager.hook.get_player_plugin_data_class()
        }

    @property
    def event(self) -> 'Event':
        # TODO (Molrn - multi tournament) replace by an event ref
        return self.tournament.event

    @property
    def id(self) -> int:
        assert self.stored_player.id is not None
        return self.stored_player.id

    @property
    def last_name(self) -> str:
        return self.stored_player.last_name

    @property
    def first_name(self) -> str:
        return self.stored_player.first_name or ''

    @staticmethod
    def player_full_name(
        first_name: str | None,
        last_name: str,
    ) -> str:
        if first_name:
            return _('{first_name} {last_name}').format(
                first_name=first_name or '', last_name=last_name
            )
        return last_name

    @property
    def full_name(self) -> str:
        return self.player_full_name(self.first_name, self.last_name)

    @property
    def date_of_birth(self) -> date | None:
        return self.stored_player.date_of_birth

    @property
    def year_of_birth(self) -> int:
        return self.date_of_birth.year if self.date_of_birth else 0

    @property
    def gender(self) -> PlayerGender:
        return PlayerGender(self.stored_player.gender)

    @property
    def mail(self) -> str | None:
        return self.stored_player.mail

    @property
    def phone(self) -> str | None:
        return self.stored_player.phone

    @property
    def comment(self) -> str | None:
        return self.stored_player.comment

    @property
    def owed(self) -> float:
        return self.stored_player.owed

    @property
    def paid(self) -> float:
        return self.stored_player.paid

    @property
    def title(self) -> PlayerTitle:
        return PlayerTitle(self.stored_player.title)

    @property
    def fide_id(self) -> int | None:
        return self.stored_player.fide_id

    @property
    def federation(self) -> Federation:
        return Federation(self.stored_player.federation)

    @property
    def club(self) -> Club:
        return Club(self.stored_player.club or '')

    @property
    def fixed(self) -> int | None:
        return self.stored_player.fixed

    @property
    def check_in(self) -> bool:
        return self.stored_player.check_in

    def replace_stored_player(self, stored_player: StoredPlayer):
        self.stored_player = stored_player
        self.plugin_data = self._get_plugin_data()
        self.ratings = self._get_ratings()

    def _get_plugin_data(self) -> dict[str, PluginData]:
        return {
            plugin_id: plugin_data_class.from_stored_value(
                self.stored_player.plugin_data.get(plugin_id, {})
            )
            for plugin_id, plugin_data_class in self.plugin_data_class_by_plugin_id().items()
        }

    def _get_ratings(self) -> dict[TournamentRating, PlayerRating]:
        return {
            TournamentRating(tr_value): PlayerRating.from_stored_value(rating)
            for tr_value, rating in self.stored_player.ratings.items()
        }

    def get_rating_and_type(
        self, tournament_rating: TournamentRating, player_rating_type: PlayerRatingType
    ) -> PlayerRatingAndType:
        player_ratings = self.ratings[tournament_rating]
        rating: int | None = None
        type_: PlayerRatingType = PlayerRatingType.ESTIMATED
        if player_rating_type == PlayerRatingType.FIDE:
            rating = player_ratings.fide
            type_ = PlayerRatingType.FIDE
        elif player_rating_type == PlayerRatingType.NATIONAL:
            rating = player_ratings.national
            type_ = PlayerRatingType.NATIONAL
        if rating is None:
            if player_ratings.estimated:
                return PlayerRatingAndType(
                    player_ratings.estimated, PlayerRatingType.ESTIMATED
                )

            rating_and_type = plugin_manager.hook_for_event(
                self.event, 'get_player_rating'
            )(
                tournament_rating=tournament_rating,
                player_rating_type=player_rating_type,
                player=self,
            )
            if rating_and_type:
                return rating_and_type

        return PlayerRatingAndType(rating or 0, type_)

    @property
    def has_real_rating(self) -> bool:
        return any(
            rating.fide is not None or rating.national is not None
            for rating in self.ratings.values()
        )

    @property
    def first_real_rating_str(self) -> str:
        for tournament_rating in TournamentRating:
            rating_and_type = self.get_rating_and_type(
                tournament_rating, PlayerRatingType.FIDE
            )
            if rating_and_type.type == PlayerRatingType.ESTIMATED:
                rating_and_type = self.get_rating_and_type(
                    tournament_rating, PlayerRatingType.NATIONAL
                )
            if rating_and_type.type != PlayerRatingType.ESTIMATED:
                return f'{rating_and_type} ({tournament_rating.acronym})'
        raise ValueError('Player expected to have a real rating')

    def update_ratings(self, ratings: dict[TournamentRating, PlayerRating]):
        for tournament_rating, player_rating in ratings.items():
            self.stored_player.ratings[tournament_rating.value] = (
                player_rating.stored_value
            )
        self.ratings = self._get_ratings()

    @property
    def not_paired_str(self) -> str:
        return (
            _('Unpaired *** FEMALE')
            if self.gender == PlayerGender.FEMALE
            else _('Unpaired *** MALE')
        )

    @property
    def exempt_str(self) -> str:
        return (
            _('Exempt *** FEMALE')
            if self.gender == PlayerGender.FEMALE
            else _('Exempt *** MALE')
        )

    # --------------------------------------------------------------------------
    # TournamentPlayer
    # --------------------------------------------------------------------------

    @property
    def tournament(self) -> 'Tournament':
        if (tournament := self._tournament_ref()) is None:
            raise RuntimeError('Reference has been garbage collected')
        return tournament

    @property
    def pairing_number(self) -> int | None:
        return self.stored_tournament_player.pairing_number

    def _get_default_pairing(self, round_: int) -> Pairing:
        return Pairing(
            self,
            StoredPairing(
                tournament_id=self.tournament.id,
                player_id=self.id,
                round_=round_,
                result=Result.NO_RESULT.value,
                board_id=None,
            ),
            exists=False,
        )

    def _get_pairings_by_round(self) -> dict[int, Pairing]:
        known_pairings: dict[int, Pairing] = {}
        for stored_pairing in self.stored_tournament_player.stored_pairings:
            pairing = Pairing(self, stored_pairing)
            known_pairings[pairing.round] = pairing
        return {
            round_: (
                known_pairings[round_]
                if round_ in known_pairings
                else self._get_default_pairing(round_)
            )
            for round_ in range(1, self.tournament.rounds + 1)
        }

    def delete_pairing(self, round_: int, event_database: EventDatabase):
        event_database.delete_stored_pairing(
            self.pairings_by_round[round_].stored_pairing
        )
        self.pairings_by_round[round_] = self._get_default_pairing(round_)

    @property
    def estimated(self) -> bool:
        return self.rating_type == PlayerRatingType.ESTIMATED

    @cached_property
    def category(self) -> PlayerCategory:
        if self.tournament:
            tournament_start = self.tournament.start_date
            tournament_end = self.tournament.stop_date
        else:
            tournament_start, tournament_end = None, None
        return PlayerCategory.from_year_of_birth(
            self.event, self.year_of_birth, tournament_start, tournament_end
        )

    @property
    def rating(self) -> int:
        return self._tournament_rating.value

    @property
    def rating_type(self) -> PlayerRatingType:
        return self._tournament_rating.type

    @property
    def rating_str(self) -> str:
        return str(self._tournament_rating)

    def fide_will_override_with_standard_rating(
        self, tournament_rating: TournamentRating, player_rating_type: PlayerRatingType
    ) -> bool:
        if player_rating_type != PlayerRatingType.FIDE:
            # We only override for tournament that are using the FIDE ratings
            return False

        ratings = self.ratings.get(tournament_rating, None)
        if ratings and ratings.fide is not None:
            return False

        if tournament_rating != TournamentRating.STANDARD:
            ratings = self.ratings.get(TournamentRating.STANDARD, None)
            if ratings and ratings.fide is not None:
                return True

        return False

    def rating_is_overridden(
        self, tournament_rating: TournamentRating, player_rating_type: PlayerRatingType
    ) -> bool:
        return (
            self.tournament.override_unrated_rapid_blitz
            and self.fide_will_override_with_standard_rating(
                tournament_rating, player_rating_type
            )
        )

    @property
    def manual_tiebreak(self) -> int | None:
        return self.stored_tournament_player.manual_tiebreak

    @property
    def rating_used_by_fide(self) -> PlayerRatingAndType:
        if self.fide_will_override_with_standard_rating(
            self.tournament.rating, self.tournament.player_rating_type
        ):
            rating = self.ratings.get(TournamentRating.STANDARD)
            assert rating is not None
            assert rating.fide is not None
            return PlayerRatingAndType(rating.fide, PlayerRatingType.FIDE)

        return self.get_rating_and_type(
            self.tournament.rating, self.tournament.player_rating_type
        )

    @property
    def _tournament_rating(self) -> PlayerRatingAndType:
        if self.rating_is_overridden(
            self.tournament.rating, self.tournament.player_rating_type
        ):
            rating = self.ratings.get(TournamentRating.STANDARD)
            assert rating is not None
            assert rating.fide is not None
            return PlayerRatingAndType(rating.fide, PlayerRatingType.FIDE)

        return self.get_rating_and_type(
            self.tournament.rating, self.tournament.player_rating_type
        )

    @property
    def ratings_str(self) -> str:
        return '/'.join(
            [
                str(
                    self.get_rating_and_type(
                        tournament_rating, self.tournament.player_rating_type
                    )
                )
                for tournament_rating in TournamentRating
            ]
        )

    @property
    def fide_rating_coefficient(self) -> int:
        """Make a best guess of the FIDE rating coefficient (k) for this player."""
        if self.rating_used_by_fide.type != PlayerRatingType.FIDE:
            return 40
        if self.rating_used_by_fide.value > 2400:
            return 10
        if isinstance(self.date_of_birth, date):
            today = date.today()
            age = (
                today.year
                - self.date_of_birth.year
                - (
                    (today.month, today.day)
                    < (self.date_of_birth.month, self.date_of_birth.day)
                )
            )
            if age < 18:
                return 40
        return 20

    @property
    def first_fide_rating(self) -> tuple[int | None, str | None]:
        """Calculate a players first FIDE rating based on this tournament."""
        games = [
            pairing
            for pairing in self.pairings.values()
            if pairing.played
            and pairing.opponent
            and pairing.opponent.rating_type == PlayerRatingType.FIDE
        ]
        if len(games) == 0:
            return None, _('No games against FIDE rated opponents.')
        if all(game.loss for game in games):
            return None, _(
                'The player did not win any games against FIDE rated opponents.'
            )

        # Average rating of opponents + 2 fictional opponents with 1800 rating against which the player draws
        total_opponent_ratings = 1800 * 2
        for game in games:
            if game.opponent and game.opponent.rating_used_by_fide:
                total_opponent_ratings += game.opponent.rating_used_by_fide.value

        num_games = len(games) + 2
        average_rating = Utils.round_ranking(total_opponent_ratings / num_games)
        score = (
            sum(game.result.point_value for game in games) + Result.DRAW.point_value * 2
        )
        average_score = score / num_games
        rating_difference = percentage_score_rating_difference[
            round(average_score * 100)
        ]
        return average_rating + rating_difference, None

    @property
    def point_values(self) -> dict[Result, float] | None:
        return self.tournament.point_values

    def points_before(self, before_round: int, only_played: bool = False) -> float:
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        # NOTE(Amaras) if you were to include the current round
        # in the computation, boards regularly change their ordering
        # during the current round as results are added
        return sum(
            pairing.result.points(self.point_values)
            for round_, pairing in self.pairings.items()
            if round_ < before_round and (pairing.played or not only_played)
        )

    def points_after(self, after_round: int) -> float:
        # NOTE(Amaras) this does not rely on the fact that insertion order
        # is preserved in 3.6+ dict, because I can't be sure insertion order
        # is the correct (increasing) round order
        # NOTE(Amaras) if you were to include the current round
        # in the computation, boards regularly change their ordering
        # during the current round as results are added
        return sum(
            pairing.result.points(self.point_values)
            for round_index, pairing in self.pairings.items()
            if round_index <= after_round
        )

    def total_points(self, only_played: bool = False) -> float:
        return sum(
            pairing.result.points(self.point_values)
            for pairing in self.pairings.values()
            if pairing.played or not only_played
        )

    def compute_points(self, *, before_round: int):
        """Computes and stores the points scored by the player before round `before_round` (returns None)"""
        self.points = self.points_before(before_round)

    def points_total(self) -> float:
        return sum(
            pairing.result.points(self.point_values)
            for pairing in self.pairings.values()
        )

    def add_points(self, points: float):
        """If `self.points` is set, add `points` to it.
        Otherwise, leave `self.points` as None."""
        if self.points is not None:
            self.points += points

    @property
    def points_str(self) -> str:
        return Utils.points_str(self.points)

    def add_vpoints(self, vpoints: float):
        """If `self.vpoints` is set, add `vpoints` to it.
        Otherwise, leave `self.vpoints` as None."""
        if self.vpoints is not None:
            self.vpoints += vpoints

    @property
    def vpoints_str(self) -> str:
        return Utils.points_str(self.vpoints)

    @property
    def byes_count(self) -> int:
        byes_count = 0
        for pairing in self.pairings_by_round.values():
            if pairing.result == Result.HALF_POINT_BYE:
                byes_count += 1
            elif pairing.result == Result.FULL_POINT_BYE:
                byes_count += 2
        return byes_count

    def to_trf(
        self,
        after_round: int,
        next_round_pairings_as_zpb: bool,
        include_next_round_bye: bool,
    ) -> TrfPlayer:
        games: list[TrfGame] = []
        from data.input_output.trf_mappers import TrfPlayerGender, TrfPlayerTitle

        for round_nb, pairing in self.pairings.items():
            trf_game = pairing.to_trf(round_nb)
            if round_nb <= after_round:
                games.append(trf_game)
            elif round_nb == after_round + 1:
                if include_next_round_bye and pairing.next_round_bye:
                    games.append(trf_game)
                elif next_round_pairings_as_zpb and not pairing.needs_pairing:
                    games.append(
                        TrfGame(
                            startrank=0,
                            color='-',
                            result=Result.ZERO_POINT_BYE.to_trf,
                            round=round_nb,
                        )
                    )

        return TrfPlayer(
            startrank=self.pairing_number,
            name=f'{self.last_name}, {self.first_name or ""}'[:32],
            sex=TrfPlayerGender.get_outer_value(self.gender),
            title=TrfPlayerTitle.get_outer_value(self.title),
            rating=self.rating,
            fed=self.federation.name,
            id=self.fide_id,
            birthdate=(
                self.date_of_birth.strftime('%Y/%m/%d') if self.date_of_birth else ''
            ),
            points=self.points_after(after_round),
            rank=self.rank,
            games=games,
        )

    # FIXME(Amaras): this should not be in the Player class
    def reset_board(self):
        self.board_id = None
        self.board_number = None
        self.color = None

    # FIXME(Amaras): this should not be in the Player class
    def set_board(self, board_id: int, board_number: int, color: BoardColor):
        self.board_id = board_id
        self.board_number = board_number
        self.color = color

    def achieves_any_title_norm(self) -> dict[TitleNorm, NormCheckResult]:
        from data.pairings.systems import RoundRobinPairingSystem

        results: dict[TitleNorm, NormCheckResult] = {
            tn: NormCheckResult(
                title_norm=tn, meets_gender=tn.satisfies_gender_requirement(self.gender)
            )
            for tn in TitleNorm.values()
        }

        # Gather data from pairings
        rounds = self.tournament.rounds
        played_games = 0
        federations_counter: Counter[Federation] = Counter()
        titles_counter: Counter[PlayerTitle] = Counter()
        results_list: list[Result] = []
        forfeits_or_byes = 0
        opponents: list[Player] = []
        ignored_opponents_ids: set[int] = set()

        is_round_robin = self.tournament.pairing_system == RoundRobinPairingSystem()

        for rnd, pairing in self.pairings_by_round.items():
            if pairing.result.is_board_bye or pairing.result == Result.FORFEIT_WIN:
                forfeits_or_byes += 1

            if pairing.opponent and not pairing.result.is_unplayed:
                played_games += 1
                opponent = pairing.opponent

                # 1.4.2b (Ignore games against unrated players who score zero against rated opponents in round robin tournaments.)
                if is_round_robin and opponent.rating_type != PlayerRatingType.FIDE:
                    scored_zero_against_rated = False
                    for opponent_pairing in opponent.pairings_by_round.values():
                        if (
                            opponent_pairing.opponent
                            and opponent_pairing.result.is_loss
                            and opponent_pairing.opponent.rating_type
                            == PlayerRatingType.FIDE
                        ):
                            scored_zero_against_rated = True
                            break
                    if scored_zero_against_rated:
                        ignored_opponents_ids.add(opponent.id)
                        continue

                # 1.4.2a (Ignore games against opponents who do not belong to FIDE federations)
                if opponent.federation == 'NON':
                    ignored_opponents_ids.add(opponent.id)
                    continue
                else:
                    federations_counter[opponent.federation] += 1

                if opponent.title != PlayerTitle.NONE:
                    titles_counter[opponent.title] += 1
                results_list.append(pairing.result)
                opponents.append(opponent)

        # Precompute required titles counts
        required_titles = {
            tn: Counter({t: titles_counter.get(t, 0) for t in tn.required_titles})
            for tn in TitleNorm.values()
        }

        score = sum(r.points() for r in results_list)

        # Process each norm
        for tn, res in results.items():
            res.ignored_opponents_ids = ignored_opponents_ids
            min_rounds = tn.minimum_rounds(self.tournament)

            # Games criterion
            if played_games < min_rounds:
                res.not_enough_games = _('At least %(min)d games must be played.')
            elif (
                rounds == min_rounds
                and played_games == min_rounds - 1
                and forfeits_or_byes != 1
            ):
                res.not_enough_games = _('At least %(min)d games must be played.')

            res.played_games = played_games

            # Federation criterion
            own_count = federations_counter.get(self.federation, 0)
            num_feds = len(federations_counter)
            msg = _(
                '<b>1.4.3</b> At least two federations other than that of the title applicant must be included, except 1.4.3a - 1.4.3d shall be exempt.'
            )
            if own_count != 0:
                if num_feds <= 2:
                    res.not_enough_federations = msg
                if own_count > tn.maximum_of_own_federation(rounds):
                    res.too_many_own_federation = _(
                        "<b>1.4.4</b> A maximum of 3/5 of the opponents may come from the applicant's federation."
                    )
            else:
                if num_feds < 2:
                    res.not_enough_federations = msg
            res.from_own_federations_count = own_count
            res.from_host_federations_count = federations_counter.get(
                Federation(self.event.federation), 0
            )
            res.federations_count = num_feds

            # Too many in one federation
            if federations_counter:
                top_fed, top_count = federations_counter.most_common(1)[0]
                max_fed = tn.maximum_of_one_federation(rounds)
                if top_count > max_fed:
                    res.too_many_one_federation = (
                        top_fed,
                        _(
                            '<b>1.4.4</b> A maximum of 2/3 of the opponents from one federation.'
                        ),
                    )

            # Title holders criterion
            num_titles = sum(titles_counter.values())
            if num_titles < tn.minimum_title_holders(rounds):
                res.not_enough_title_holders = _(
                    '<b>1.4.5a</b> At least 50%% of the opponents shall be title-holders, excluding CM and WCM.'
                )

            res.num_title_holders = num_titles
            res.title_counts = titles_counter

            # Required titles criterion
            req = required_titles.get(tn, Counter())
            total_req = sum(req.values())
            if total_req < tn.minimum_required_titles(self.tournament):
                res.not_enough_required_titles = _(
                    '<b>1.4.5</b> For this norm, at least {min} opponents must have these title(s): {titles}'
                ).format(
                    min=tn.minimum_required_titles(self.tournament),
                    titles=', '.join(str(title) for title in tn.required_titles),
                )
            res.required_titles = list(req.keys())
            res.required_titles_met = total_req

            # Score criterion
            if score < TitleNorm.minimum_score(rounds):
                res.score_too_low = _(
                    '<b>1.4.8b</b> The minimum score is 35%% for all norms.'
                )

            res.score = score

        # Rating / performance criteria
        opponents.sort(
            key=lambda o: o.rating if o.rating_type == PlayerRatingType.FIDE else 1400
        )

        for tn, res in results.items():
            rating_list = [
                PlayerRatingAndType(
                    opponent.rating
                    if opponent.rating_type == PlayerRatingType.FIDE
                    else 1400,
                    opponent.rating_type,
                )
                for opponent in opponents
            ]

            # Minimum rating floor
            if rating_list and rating_list[0].value < tn.minimum_rating:
                rating_list[0].value = tn.minimum_rating
                rating_list[0].type = PlayerRatingType.FIDE
                res.adjusted_player = opponents[0]
                res.adjusted_player_rating = tn.minimum_rating
                rating_list.sort(key=attrgetter('value'))

            res.num_rated_players = len(
                [r for r in rating_list if r.type == PlayerRatingType.FIDE]
            )

            values = [r.value for r in rating_list]
            avg = Utils.round_ranking(sum(values) / len(values)) if values else 0
            if avg < tn.minimum_average:
                res.average_too_low = _(
                    '<b>1.4.8a</b> The minimum average rating of the opponents for this norm is {min}.'
                ).format(min=tn.minimum_average)

            res.average_rating = avg

            max_score = Result.WIN.points() * len(results_list)
            bonus = (
                Utils.performance_bonus(
                    Utils.round_ranking(100 * score / max_score) / 100
                )
                if max_score
                else 0
            )
            performance = avg + bonus
            res.performance = performance
            if performance < tn.minimum_performance:
                res.performance_too_low = _(
                    '<b>1.4.8</b> The minimum performance for this norm is {min}.'
                ).format(min=tn.minimum_performance)
                new_score = score
                draw_points = Result.DRAW.points()
                while new_score < max_score:
                    new_score += draw_points
                    new_bonus = (
                        Utils.performance_bonus(
                            Utils.round_ranking(100 * new_score / max_score) / 100
                        )
                        if max_score
                        else 0
                    )
                    if res.average_rating + new_bonus >= tn.minimum_performance:
                        res.performance_diff = score - new_score
                        break
            else:
                new_score = score
                draw_points = Result.DRAW.points()
                while new_score > 0:
                    new_score -= draw_points
                    new_bonus = (
                        Utils.performance_bonus(
                            Utils.round_ranking(100 * new_score / max_score) / 100
                        )
                        if max_score
                        else 0
                    )
                    if res.average_rating + new_bonus < tn.minimum_performance:
                        res.performance_diff = score - new_score - draw_points
                        break

        # 1.4.3d exception
        #
        # Swiss System tournaments in which participants include in every round at least
        # - 20 FIDE rated players
        # - not from the host federation
        # - from at least 3 different federations,
        #  -at least 10 of whom hold GM, IM, WGM or WIM titles.
        # For this purpose, players will be counted only if they miss at most one round (excluding pairing allocated byes)

        eligible_players: list[Player] = []

        # Build a list of eligible players
        for p in self.tournament.players_by_id.values():
            if p.rating_type != PlayerRatingType.FIDE:
                continue
            if (
                p.federation == Federation(self.tournament.event.federation)
                or p.federation == 'NON'  # 1.4.2a
            ):
                continue
            missed_rounds = 0
            for r, pairing in p.pairings_by_round.items():
                if pairing.unplayed and pairing.result not in [
                    Result.FORFEIT_WIN,
                    Result.PAIRING_ALLOCATED_BYE,
                    Result.REST_GAME,
                ]:
                    missed_rounds += 1
            if missed_rounds > 1:
                continue

            eligible_players.append(p)

        # Per-round counts among eligible & present -----------------
        worst_players: float = float('inf')
        worst_federations: float = float('inf')
        worst_titled: float = float('inf')
        meets_156 = True

        for rnd in range(1, self.tournament.rounds + 1):
            present: list[Player] = []
            for p in eligible_players:
                pairing: Pairing | None = p.pairings_by_round.get(rnd)
                if pairing and (
                    pairing.played
                    or pairing.result
                    in [
                        Result.PAIRING_ALLOCATED_BYE,
                        Result.REST_GAME,
                    ]
                ):
                    present.append(p)

            n_players = len(present)
            n_titled = sum(1 for p in present if p.title != PlayerTitle.NONE)

            # 1.4.2a
            present_not_fid = [p for p in present if p.federation != 'FID']
            n_feds = len({p.federation for p in present_not_fid})

            # Track worst (minimum) across rounds
            worst_players = min(worst_players, n_players)
            worst_federations = min(worst_federations, n_feds)
            worst_titled = min(worst_titled, n_titled)

        # Handle case of zero rounds gracefully
        if worst_players is float('inf'):
            worst_players = 0
            worst_federations = 0
            worst_titled = 0

        msg = _(
            '<b>1.4.3d</b> Swiss System tournaments in which participants include in every round at least 20 FIDE rated players, not from the host federation, from at least 3 different federations, at least 10 of whom hold GM, IM, WGM or WIM titles.'
        )
        for tn, res in results.items():
            res.all_federations_count = int(worst_federations)
            res.not_enough_all_federations = (
                msg if res.all_federations_count < 3 else None
            )

            res.eligible_players_title_count = int(worst_titled)
            res.not_enough_all_title_holders = (
                msg if res.eligible_players_title_count < 10 else None
            )

            res.eligible_players_count = int(worst_players)
            res.not_enough_foreign_players = (
                msg if res.eligible_players_count < 20 else None
            )

        # 1.5.6a
        #
        # Check if the average rating of the top 40 eligible players is at least 2000 in every round

        eligible_players: list[Player] = []

        # Build a list of eligible players
        for p in self.tournament.players_by_id.values():
            if p.rating_type != PlayerRatingType.FIDE:
                continue
            if (
                p.federation == 'NON'  # 1.4.2a
            ):
                continue

            missed_rounds = 0
            for r, pairing in p.pairings_by_round.items():
                if pairing.unplayed and pairing.result not in [
                    Result.FORFEIT_WIN,
                    Result.PAIRING_ALLOCATED_BYE,
                    Result.REST_GAME,
                ]:
                    missed_rounds += 1
            if missed_rounds > 1:
                continue

            eligible_players.append(p)

        for rnd in range(1, self.tournament.rounds + 1):
            present: list[Player] = []
            for p in eligible_players:
                pairing: Pairing | None = p.pairings_by_round.get(rnd)
                if pairing and (
                    pairing.played
                    or pairing.result
                    in [
                        Result.PAIRING_ALLOCATED_BYE,
                        Result.REST_GAME,
                    ]
                ):
                    present.append(p)

            n_players = len(present)

            # 1.5.6a
            # Check if the average rating of the top 40 eligible players is at least 2000 in every round
            if n_players < 40:
                meets_156 = False
            else:
                top_rated = sorted([p.rating for p in present], reverse=True)[:40]
                avg: float = sum(top_rated) / len(top_rated) if top_rated else 0
                if avg < 2000:
                    meets_156 = False

        for tn, res in results.items():
            res.requirement_156a_met = meets_156

        return results

    @cached_property
    def has_real_pairings(self) -> bool:
        """Returns True if the player has already been paired with an opponent
        (i.e. can not be deleted from the tournament anymore)."""
        for pairing in self.pairings.values():
            if pairing.opponent_id is not None or pairing.exempt:
                return True
        return False

    @property
    def has_withdrawn(self) -> bool:
        """Returns True if the player has withdrawn from the tournament."""
        if self.tournament.finished:
            return False

        # We check that the player only has zero-point byes for all future rounds
        # We ignore the current round if they are paired
        for round_ in range(
            max(self.tournament.current_round, 1), self.tournament.rounds + 1
        ):
            if (
                round_ < self.tournament.rounds
                and self.pairings_by_round[round_].paired
            ) or self.pairings_by_round[round_].zero_point_bye:
                continue
            return False
        return True

    @property
    def first_pab_round(self) -> int | None:
        return next(
            (
                round_
                for round_, pairing in self.pairings.items()
                if pairing.result == Result.PAIRING_ALLOCATED_BYE
            ),
            None,
        )

    def round_played_against(self, opponent_id: int) -> int | None:
        """Get the round at which the player has played against the player *opponent_id*.
        Return None if they have not played against each other."""
        return next(
            (
                round_
                for round_, pairing in self.pairings.items()
                if pairing.opponent_id == opponent_id
            ),
            None,
        )

    @cached_property
    def can_check_in_out(self) -> bool:
        """Returns True if the player can check-in/out, i.e. does not have a ZPB for the next round."""
        if self.tournament.finished:
            return False
        if self.tournament.playing:
            return False
        if not self.tournament.check_in_open:
            return False
        pairing: Pairing = self.pairings[self.tournament.current_round + 1]
        return (
            not pairing.zero_point_bye
            and not pairing.half_point_bye
            and not pairing.full_point_bye
        )

    @property
    def color_str(self) -> str:
        return str(self.color or '')

    # -------------------------------------------------------------------------
    # Ranking
    # -------------------------------------------------------------------------

    @property
    def tie_break_values(self) -> list[TieBreakValue]:
        """Returns the player's tie-break values as strings."""
        assert self._tie_break_values is not None, (
            'Player._tie_break_values is not set, call Tournament.compute_player_ranks() before.'
        )
        return self._tie_break_values

    def compute_tie_break_values(self, *, after_round: int):
        self._tie_break_values = [
            TieBreakValue(
                tie_break,
                tie_break.compute_player_value(self, after_round=after_round)
                if tie_break.is_computed_per_player
                else 0,
            )
            for tie_break in self.tournament.tie_breaks
        ]

    @property
    def rank(self) -> int:
        assert self._rank, (
            'Player._rank is not set, call Tournament.compute_player_ranks() before.'
        )
        return self._rank

    @rank.setter
    def rank(self, rank: int):
        self._rank = rank

    @cached_property
    def crosstable_strings(self) -> list[str]:
        assert self.tournament is not None
        return [
            pairing.result.to_crosstable
            + (
                f'{self.tournament.players_by_id[pairing.opponent_id].rank:>3}'
                f'{pairing.color.to_crosstable}'
                if pairing.opponent_id and pairing.color
                else ''
            )
            for pairing in self.pairings.values()
        ]

    @property
    def starting_rank_sort_key(self) -> tuple:
        return -self.rating, -self.title, self.last_name, self.first_name or ''

    @property
    def board_number_sort_key(self) -> tuple:
        return -(self.vpoints or 0.0), self.pairing_number or 0

    @property
    def before_manual_rank_key(self) -> tuple:
        from data.tie_breaks.tie_breaks import ManualTieBreak

        tie_break_sort_key: list = []
        tie_break_found = False
        for tie_break_value in self.tie_break_values:
            if isinstance(tie_break_value.tie_break, ManualTieBreak):
                tie_break_found = True
                break
            tie_break_sort_key.append(-float(tie_break_value.value))
        if not tie_break_found:
            tie_break_sort_key = []
        return (-(self.points or 0.0),) + tuple(tie_break_sort_key)

    def rank_sort_key_before_tie_break(self, tie_break_index: int) -> tuple:
        """Returns a rank sort key up to the tie-break of index *tie_break_index*."""
        tie_break_sort_key: list = []
        for tie_break_value in self.tie_break_values[:tie_break_index]:
            tie_break_sort_key.append(-float(tie_break_value.value))
        return (-(self.points or 0.0),) + tuple(tie_break_sort_key)

    def rank_sort_key_without_tie_break(self, tie_break_index: int) -> tuple:
        """Returns a rank sort key as if the tie-break of type *tie_break_type* was not set."""

        tie_break_sort_key = tuple(
            -float(tie_break_value.value)
            for index, tie_break_value in enumerate(self.tie_break_values)
            if index != tie_break_index
        )

        return (-(self.points or 0.0),) + tie_break_sort_key + (self.pairing_number,)

    @property
    def rank_sort_key(self) -> tuple:
        tie_break_sort_key = tuple(
            -float(tie_break_value.value) for tie_break_value in self.tie_break_values
        )
        return (-(self.points or 0.0),) + tie_break_sort_key + (self.pairing_number,)

    def __le__(self, other: 'Player') -> bool:
        # p1 <= p2 calls p1.__le__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        return self.board_number_sort_key > other.board_number_sort_key

    def __eq__(self, other):
        # p1 == p2 calls p1.__eq__(p2)
        if not isinstance(other, Player):
            return NotImplemented
        return self.board_number_sort_key == other.board_number_sort_key

    def __str__(self):
        return (
            f'(#{self.id} rank={self._rank} ratings={self.ratings_str} '
            f'title={self.title.value} gender={self.gender.value} '
            f'name={self.last_name} {self.first_name} points={self.points})'
        )

    def __repr__(self):
        return f'{self.__class__.__name__}(tournament={self.tournament!r}, stored_player={self.stored_player!r})'

    # --------------------------------------------------------------------------
    # Legacy
    # --------------------------------------------------------------------------

    @property
    def pairings(self) -> dict[int, Pairing]:
        return self.pairings_by_round
