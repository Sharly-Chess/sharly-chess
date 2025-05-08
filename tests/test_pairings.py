# Needs to be imported first to avoid circular import
from plugins import manager  # Noqa E402

from utils.tests import BaseTestCase


class PairingTestCase(BaseTestCase):
    """Tests for all the pairing systems."""

    def assert_no_pairings_diff_in_tournament(self, tournament_uniq_id: str):
        tournament = self.event.tournaments_by_uniq_id[tournament_uniq_id]
        tournament.set_default_pairing_settings()
        for round_ in range(1, tournament.current_round + 1):
            diff = tournament.pairing_variation.engine.pairings_diff(tournament, round_)
            self.assertEqual(diff, [], f'round {round_}')

    # ---------------------------------------------------------------------------------
    # Swiss pairing systems
    # ---------------------------------------------------------------------------------
    """
    For each swiss system, a tournament has been generated
    with Papi using the following process:
        - Start from a tournament with the players of the TEC exercise file*
        - Settings:
            - pair first player as white
            - for accelerated pairings:
                - 2 groups rating limit: 1825 (8 - 8)
                - 3 groups rating limits: 1825 - 1625 (8 - 4 - 4)
        - For each round
            - Generate the pairings
            - fill out random standard results (win - draw - loss)

    Testing Papi-generated tournament requires to avoid unplayed game results
    (forfeits and byes) as it does not respect the FIDE floater following rule:
    "A player who, for whatever reason, does not play in a round, receives a downfloat."
    FIDE Handbook C.04.3 - A.4.b
    This rule changes in the rules effective from 1 July 2025:
    "A player who, for whatever reason, scores without playing in a round
    more points than those rewarded for a loss, also receives a downfloat."
    FIDE Handbook C.04.3 - 1.4.3
    Once these modifications have been implemented in BbpPairings,
    including forfeits and ZPB will be possible, but not HPB.

    The tests regenerate the pairings for each round
    from the results of the previous rounds.
    The generated pairings are then compared to the actual pairings.

    * https://tec.fide.com/2024/03/18/tie-break-exercise/
    """

    def test_swiss_tec_standard(self):
        self.assert_no_pairings_diff_in_tournament('tec-swiss')

    def test_swiss_papi_standard(self):
        self.assert_no_pairings_diff_in_tournament('papi-swiss')

    def test_swiss_papi_haley(self):
        self.assert_no_pairings_diff_in_tournament('papi-haley')

    def _test_swiss_papi_haley_soft(self):
        # TODO figure out what is wrong with round 5
        self.assert_no_pairings_diff_in_tournament('papi-haley-soft')

    def _test_swiss_papi_progressive(self):
        # TODO figure out what is wrong with round 5
        self.assert_no_pairings_diff_in_tournament('papi-progressive')

    def _test_swiss_papi_nicois(self):
        # TODO figure out what is wrong with round 3
        self.assert_no_pairings_diff_in_tournament('papi-nicois')

    # ---------------------------------------------------------------------------------
    # Round-Robin pairing systems
    # ---------------------------------------------------------------------------------

    def test_round_robin_tec_berger(self):
        self.assert_no_pairings_diff_in_tournament('tec-round-robin')
