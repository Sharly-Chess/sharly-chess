from common.i18n import _
from data.pairings.variations import SwissVariation
from data.player import Player
from data.tournament import Tournament
from utils.enum import Result


class HaleySwissVariation(SwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY'

    @staticmethod
    def static_name() -> str:
        return _('Haley system')

    @staticmethod
    def compute_virtual_points(
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        rating_limit = tournament.rating_limit1
        assert rating_limit is not None
        point_values = tournament.point_values
        vpoints = Result.LOSS.points(point_values)
        if at_round <= 2 and player.rating >= rating_limit:
            vpoints = Result.GAIN.points(point_values)
        return vpoints

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= 2


class HaleySoftSwissVariation(SwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'HALEY_SOFT'

    @staticmethod
    def static_name() -> str:
        return _('Soft Haley system')

    @staticmethod
    def compute_virtual_points(
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        # Round 1: All players above rating_limit1 get 1 vpoint
        # Round 2: All players above rating_limit1 get 1 vpoint
        # Round 2: All other players get .5 vpoints
        # bottom of page #138 on
        # https://dna.ffechecs.fr/wp-content/uploads/sites/2/2023/10/Livre-arbitre-octobre-2023.pdf,
        # please remove if OK
        rating_limit = tournament.rating_limit1
        assert rating_limit is not None
        point_values = tournament.point_values
        vpoints = Result.LOSS.points(point_values)
        if at_round <= 2 and player.rating >= rating_limit:
            vpoints = Result.GAIN.points(point_values)
        elif at_round == 2 and player.rating < rating_limit:
            vpoints = Result.DRAW.points(point_values)
        return vpoints

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= 2


class ProgressiveSwissVariation(SwissVariation):
    @staticmethod
    def variation_id() -> str:
        return 'PROGRESSIVE'

    @staticmethod
    def static_name() -> str:
        return _('Progressive accelerated system')

    @staticmethod
    def compute_virtual_points(
        tournament: Tournament,
        player: Player,
        at_round: int,
    ) -> float:
        rating_limit1 = tournament.rating_limit1
        assert rating_limit1 is not None
        rating_limit2 = tournament.rating_limit1
        assert rating_limit2 is not None

        point_values = tournament.point_values
        draw_points = Result.DRAW.points(point_values)
        gain_points = Result.GAIN.points(point_values)
        loss_points = Result.LOSS.points(point_values)

        if at_round >= tournament.rounds - 1:
            # Before the second to last round, we remove the virtual
            # points, and use a simple Swiss Dutch system.
            return loss_points

        points = player.points_before(at_round)
        if 2 * points >= tournament.rounds * gain_points:
            # If a player gets at least half the possible score,
            # their capital is set at 2 points.
            return 2 * gain_points

        # Players get a virtual draw point for each 3 real draw points
        vpoints = draw_points * (points // (3 * draw_points))

        # Starting points: Group A - 2, Group B - 1, Group C - 0
        if player.rating >= rating_limit1:
            vpoints += 2 * gain_points
        elif player.rating >= rating_limit2:
            vpoints += gain_points

        # Players cannot have more than 2 virtual points
        return min(2 * gain_points, vpoints)

    @staticmethod
    def print_real_points(current_round: int, rounds: int) -> bool:
        return current_round <= rounds - 2
