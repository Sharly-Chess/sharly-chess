# Needs to be imported first to avoid circular import
from plugins import manager  # Noqa E402

from utils.tests import BaseTestCase


class PairingTestCase(BaseTestCase):
    """Tests for all the pairing systems. For each swiss system,
    a tournament has been generated with Papi using the following process:
        - Start from a tournament with the players of the TEC exercise file*
        - Settings:
            - pair first player as white
            - for accelerated pairings:
                - 2 groups rating limit: 1825 (8 - 8)
                - 3 groups rating limits: 1825 - 1625 (8 - 4 - 4)
        - For each round
            - use the same byes as the exercise tournament
            - Generate the pairings
            - fill out the same results per table as the exercise tournament
    The tests regenerate the pairings for each round
    from the results of the previous rounds.
    The generated pairings are then compared to the actual pairings.

    * https://tec.fide.com/2024/03/18/tie-break-exercise/
    """

    def assert_no_pairings_diff_in_tournament(self, tournament_uniq_id: str):
        tournament = self.event.tournaments_by_uniq_id[tournament_uniq_id]
        for round_ in range(1, tournament.current_round + 1):
            diff = tournament.pairing_variation.engine.pairings_diff(tournament, round_)
            self.assertEqual(diff, [], f'round {round_}')

    def test_swiss_tec_standard(self):
        self.assert_no_pairings_diff_in_tournament('tec-swiss')

    def test_swiss_papi_standard(self):
        self.assert_no_pairings_diff_in_tournament('swiss')

    def test_swiss_haley(self):
        self.assert_no_pairings_diff_in_tournament('haley')

    def test_swiss_haley_soft(self):
        self.assert_no_pairings_diff_in_tournament('haley-soft')

    def test_swiss_progressive(self):
        self.assert_no_pairings_diff_in_tournament('progressive')

    def test_swiss_nicois(self):
        self.assert_no_pairings_diff_in_tournament('nicois')
