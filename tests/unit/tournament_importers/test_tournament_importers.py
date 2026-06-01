import tempfile
from datetime import date
from pathlib import Path
from unittest import TestCase

import pytest

from data.event import Event
from data.input_output import TournamentImporter
from data.input_output.tournament_importer_options import FileOption
from data.input_output.trf.trf_data import (
    TrfGame,
    TrfPlayer,
    TrfTeam,
    TrfTournament,
)
from data.input_output.trf.trf_importer import TrfTournamentImporter
from data.input_output.trf.trf_serializer import TrfSerializer
from data.loader import EventLoader
from data.pairings.settings import ColorSeedSetting
from data.pairings.variations import StandardTeamSwissVariation
from data.tournament import Tournament
from plugins.ffe.ffe_tournament_importers import (
    PapiJsonTournamentImporter,
    PapiTournamentImporter,
)
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.pairing_acceleration.pairing_variations import BakuSwissVariation
from tests.test_config import TestUtils
from utils.enum import (
    BoardColor,
    EventType,
    PlayerGender,
    PlayerRatingType,
    PlayerTitle,
    Result,
    ScoreType,
    TeamColourType,
)

EVENT_ID = 'test-tournament-importers-event'
BASE_PATH = Path(__file__).parent


@pytest.mark.unit
class TournamentImporterTestCase(TestCase):
    event: Event

    def setUp(self):
        super().setUp()
        TestUtils.create_event(EVENT_ID)
        self.event = EventLoader().load_event(EVENT_ID)

    def tearDown(self):
        TestUtils.delete_event(EVENT_ID)
        super().tearDown()

    def _import_tournament(self, importer: TournamentImporter) -> Tournament:
        tournament_id = importer.load_tournament(self.event)
        self.event = EventLoader().load_event(EVENT_ID)
        return self.event.tournaments_by_id[tournament_id]

    def test_trf_import(self):
        file_path = BASE_PATH / 'trf-import-test.trf'
        importer = TrfTournamentImporter([FileOption(file_path)])
        tournament = self._import_tournament(importer)
        self.assertEqual(tournament.name, 'TRF import test')
        self.assertEqual(tournament.location, 'Sharly-Chess HQ')
        first_day = date(year=2025, month=9, day=13)
        second_day = date(year=2025, month=9, day=14)
        self.assertEqual(tournament.start_date, first_day)
        self.assertEqual(tournament.stop_date, second_day)
        date_by_round = {
            round_: datetime_.date() if datetime_ else None
            for round_, datetime_ in tournament.round_datetimes.items()
        }
        expected_date_by_round = {
            1: first_day,
            2: first_day,
            3: first_day,
            4: second_day,
            5: second_day,
        }
        self.assertEqual(date_by_round, expected_date_by_round)
        self.assertEqual(tournament.rounds, 5)
        self.assertEqual(
            tournament.pairing_settings.get(ColorSeedSetting().id), BoardColor.BLACK
        )
        self.assertEqual(tournament.player_rating_type, PlayerRatingType.NATIONAL)
        self.assertEqual(tournament.pairing_variation.id, BakuSwissVariation().id)

        self.assertEqual(len(tournament.players), 16)
        player = tournament.tournament_players_by_pairing_number.get(1)
        self.assertIsNotNone(player)
        self.assertEqual(player.gender, PlayerGender.MAN)
        self.assertEqual(player.title, PlayerTitle.GRANDMASTER)
        self.assertEqual(player.last_name, 'CARLSEN')
        self.assertEqual(player.first_name, 'Magnus')
        self.assertEqual(player.fide_rating_value, 2840)
        self.assertEqual(player.federation.name, 'NOR')
        self.assertEqual(player.date_of_birth, date(year=1990, month=11, day=30))

        self.assertEqual(player.national_rating_value, 2200)
        ffe_data = FFEUtils.get_player_plugin_data(player)
        self.assertEqual(ffe_data.ffe_licence, PlayerFFELicence.A)
        self.assertEqual(ffe_data.ffe_licence_number, 'D50113')
        self.assertEqual(ffe_data.league, 'IDF')

        results_player = tournament.tournament_players_by_pairing_number[9]
        results = [pairing.result for pairing in results_player.pairings.values()]
        expected_results = [
            Result.LOSS,
            Result.LOSS,
            Result.HALF_POINT_BYE,
            Result.FORFEIT_LOSS,
            Result.PAIRING_ALLOCATED_BYE,
        ]
        self.assertEqual(results, expected_results)

    def test_trf_team_swiss_import(self):
        """Import a TRF26 file carrying team rosters (310) + team
        match-point system (362) + board-colour sequence (352) +
        team-Swiss encoded type (192). The importer should:
        - decode the encoded_type into the team-Swiss variation;
        - set primary_score / secondary_score from the code suffix;
        - create one StoredTeam per 310 record (TPN → pairing_number);
        - assign each player to the right team in lineup order;
        - read match_points / color_pattern / team_player_count."""
        # Recreate the event as a Team event so the team-Swiss
        # variation is registered when the importer resolves
        # ``stored_tournament.pairing``.
        TestUtils.delete_event(EVENT_ID)
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        self.event = EventLoader().load_event(EVENT_ID)

        trf_path = self._write_team_trf(
            tempfile.NamedTemporaryFile(
                'w', encoding='utf-8', suffix='.trfx', delete=False
            )
        )
        try:
            importer = TrfTournamentImporter([FileOption(Path(trf_path))])
            self.assertEqual(importer.get_not_importable_features(self.event), [])
            tournament = self._import_tournament(importer)
        finally:
            Path(trf_path).unlink(missing_ok=True)

        self.assertEqual(tournament.name, 'Team Swiss import test')
        self.assertEqual(
            tournament.pairing_variation.id, StandardTeamSwissVariation().id
        )
        self.assertTrue(tournament.is_team_tournament)
        self.assertEqual(tournament.team_player_count, 2)
        self.assertEqual(tournament.primary_score, ScoreType.MATCH_POINTS)
        self.assertEqual(tournament.secondary_score, ScoreType.GAME_POINTS)
        self.assertEqual(tournament.team_colour_type, TeamColourType.A)
        self.assertEqual(tournament.color_pattern, 'WB')
        # PAB default = DRAW points in team Swiss; ``Tournament``
        # injects it for us so the dict always contains four entries.
        self.assertEqual(
            tournament.match_points,
            {
                Result.WIN: 2.0,
                Result.DRAW: 1.0,
                Result.LOSS: 0.0,
                Result.PAIRING_ALLOCATED_BYE: 1.0,
            },
        )

        self.assertEqual(len(tournament.players), 8)
        self.assertEqual(len(tournament.teams), 4)
        teams_by_pn = tournament.teams_by_pairing_number
        self.assertEqual(set(teams_by_pn), {1, 2, 3, 4})
        self.assertEqual(teams_by_pn[1].name, 'Alphas')
        team_1_player_names = sorted(p.last_name for p in teams_by_pn[1].players)
        self.assertEqual(team_1_player_names, ['ALPHA-ONE', 'ALPHA-TWO'])

    @staticmethod
    def _write_team_trf(file_obj) -> str:
        """Build a minimal TRF26 team Swiss (4 teams × 2 players, no
        rounds played) and write it to ``file_obj``. Returns the file
        path so the caller can clean it up. The fixture is generated
        instead of stored on disk so it stays robust to changes in TRF
        column formatting (which is the serializer's concern)."""
        team_names = [
            ('Alphas', 'ALP', 'Alpha'),
            ('Betas', 'BET', 'Beta'),
            ('Gammas', 'GAM', 'Gamma'),
            ('Deltas', 'DEL', 'Delta'),
        ]
        trf_tournament = TrfTournament(
            name='Team Swiss import test',
            city='Sharly-Chess HQ',
            federation='FRA',
            start_date='2026/06/01',
            end_date='2026/06/02',
            num_rounds=3,
            initial_color=BoardColor.WHITE.value,
            encoded_type='FIDE_TEAM_TYPEA_MP_GP',
            board_color_sequence='WB',
            teams_point_system={'TW': 2.0, 'TD': 1.0, 'TL': 0.0},
            starting_rank_method='FIDON',
            pairing_controller_id='Sharly Chess',
        )
        next_player_id = 1
        trf_teams: list[TrfTeam] = []
        for tpn, (name, nickname, last_prefix) in enumerate(team_names, start=1):
            player_ids = []
            for position, suffix in enumerate(['ONE', 'TWO'], start=1):
                player = TrfPlayer(
                    id=next_player_id,
                    gender='m',
                    title='',
                    name=f'{last_prefix.upper()}-{suffix}, Player',
                    rating=2000 + tpn * 10 + position,
                    federation='FRA',
                    fide_id=0,
                    birth_date='2000/01/01',
                    points=0.0,
                    rank=0,
                    games=[],
                )
                trf_tournament.players.append(player)
                player_ids.append(player.id)
                next_player_id += 1
            trf_teams.append(
                TrfTeam(
                    id=tpn,
                    name=name,
                    nickname=nickname,
                    strength_factor=0,
                    match_points=0.0,
                    game_points=0.0,
                    rank=tpn,
                    player_ids=player_ids,
                )
            )
        trf_tournament.teams = trf_teams
        trf_tournament.num_players = len(trf_tournament.players)
        trf_tournament.num_teams = len(trf_tournament.teams)
        # Each player needs at least one game record so the round count
        # is derivable; record a single round-1 zero-point bye for now.
        for player in trf_tournament.players:
            player.games.append(TrfGame(opponent_id=0, color='-', result='Z', round=1))

        path = file_obj.name
        TrfSerializer.dump(file_obj, trf_tournament)
        file_obj.close()
        return path

    def test_trf_team_round_trip_with_oodo(self):
        """Re-importing a TRF26 file emitted by Sharly preserves every
        team-specific field the spec lets us encode: variation, score
        config + colour rule (192), match-points (362), per-team PAB
        override (320), per-game-point override (162), colour pattern
        (352), team rosters (310), per-round historical lineups (300),
        the round count (142), and the actual board-by-board
        round-1 match order.

        Uses a real loubatiere-style team Swiss export saved as
        ``trf-team-import-test.trf``."""
        TestUtils.delete_event(EVENT_ID)
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        self.event = EventLoader().load_event(EVENT_ID)

        importer = TrfTournamentImporter(
            [FileOption(BASE_PATH / 'trf-team-import-test.trf')]
        )
        tournament = self._import_tournament(importer)

        # --- top-level tournament fields ---
        self.assertTrue(tournament.is_team_tournament)
        self.assertEqual(tournament.team_player_count, 4)
        self.assertEqual(tournament.rounds, 3)
        self.assertEqual(tournament.color_pattern, 'WBBW')
        self.assertEqual(
            tournament.pairing_variation.id, StandardTeamSwissVariation().id
        )
        # FIDE_TEAM_TYPEA_MP_GP → Type A colour preferences, primary
        # MP, secondary GP for colour allocation.
        from utils.enum import TeamColourType

        self.assertEqual(tournament.team_colour_type, TeamColourType.A)
        self.assertEqual(tournament.primary_score, ScoreType.MATCH_POINTS)
        self.assertEqual(tournament.secondary_score, ScoreType.GAME_POINTS)

        # --- 362 team-point system + 320 team-PAB override ---
        match_points = tournament.match_points
        self.assertEqual(match_points[Result.WIN], 3.0)
        self.assertEqual(match_points[Result.DRAW], 1.0)
        self.assertEqual(match_points[Result.LOSS], 0.0)
        # 320 said PAB MP = 2.0, PAB GP = 5.0 — both must round-trip
        # to the stored tournament.
        self.assertEqual(match_points[Result.PAIRING_ALLOCATED_BYE], 2.0)
        self.assertEqual(tournament.pab_points, 5.0)
        # 162 override on PAB game points (only key present in the
        # source file).
        self.assertEqual(
            tournament.stored_tournament.game_points,
            {Result.PAIRING_ALLOCATED_BYE.value: 5.0},
        )

        # --- 310 team rosters + team membership ---
        self.assertEqual(len(tournament.teams), 5)
        teams_by_pn = tournament.teams_by_pairing_number
        self.assertEqual(set(teams_by_pn), {1, 2, 3, 4, 5})
        self.assertEqual(teams_by_pn[1].name, 'ERP A')
        self.assertEqual(teams_by_pn[5].name, 'Tour de chartreuse A')
        erp_a_player_pns = sorted(
            tp.pairing_number
            for tp in tournament.tournament_players
            if tp.team_id == teams_by_pn[1].id
        )
        self.assertEqual(erp_a_player_pns, [7, 10, 14, 15])

        # --- 300 historical round lineups + per-match board order ---
        # ERP A's match in round 1: OOdO lineup is [10, 15, 7, 14], so
        # boards 0..3 must hold AUBRY, MINETTO, BEC, BERNARD Alex
        # exactly in that order. (310 has the players in a *different*
        # order — [7, 10, 15, 14] — which is what the old fallback
        # would produce; this test exists to prevent regressing back
        # to that fallback when OOdO is present.)
        team_a = teams_by_pn[1]
        round_1_match = next(
            tb
            for tb in tournament.team_boards_by_id.values()
            if tb.round == 1 and tb.stored_team_board.team_a_id == team_a.id
        )
        self.assertIsNotNone(round_1_match.team_b)
        self.assertEqual(
            [board.stored_board.index for board in round_1_match.boards],
            [0, 1, 2, 3],
        )

        def team_a_pn_per_board(team_match):
            result: list[int] = []
            for board in team_match.boards:
                for player in (
                    board.white_tournament_player,
                    board.black_tournament_player,
                ):
                    if player is not None and player.team_id == team_a.id:
                        result.append(player.pairing_number)
                        break
            return result

        self.assertEqual(team_a_pn_per_board(round_1_match), [10, 15, 7, 14])

        # ERP A's round-1 lineup must also be persisted in
        # ``team_round_lineup`` so subsequent rounds see the historical
        # board assignment (otherwise the next round's UI defaults to
        # the 310 roster).
        self.assertTrue(team_a.has_explicit_round_lineup(1))
        lineup_player_ids = [p.id for p in team_a.get_round_lineup(1)]
        lineup_pns = [
            tournament.tournament_players_by_id[pid].pairing_number
            for pid in lineup_player_ids
        ]
        self.assertEqual(lineup_pns, [10, 15, 7, 14])

        # --- per-round match order on the round page ---
        # OOdO lists round 1 as (1,3), (4,2), so canonicalised by
        # pairing number the matches are (1,3) team_board.index 0,
        # (2,4) team_board.index 1, (5, None) team_board.index 2.
        round_1_matches = sorted(
            (tb for tb in tournament.team_boards_by_id.values() if tb.round == 1),
            key=lambda tb: tb.index,
        )
        pn_pairs = [
            (
                tournament.event.teams_by_id[
                    tb.stored_team_board.team_a_id
                ].pairing_number,
                tournament.event.teams_by_id[
                    tb.stored_team_board.team_b_id
                ].pairing_number
                if tb.stored_team_board.team_b_id is not None
                else None,
            )
            for tb in round_1_matches
        ]
        # Orientation comes from the 300 records' first-seen entry per
        # match: ERP A appears with ERP B as opponent first (so team_a
        # = ERP A here), but for the Crest/Lyon match the 300 listed
        # Lyon as team_id first → orientation (4, 2). Tour got the
        # round-1 PAB.
        self.assertEqual(pn_pairs, [(1, 3), (4, 2), (5, None)])

        # --- 001 game records ↔ pairing import ---
        # Player 10 (AUBRY) had a round-1 win over player 21 (DUBOIS
        # P), so the pairing record must reflect that.
        aubry = tournament.tournament_players_by_pairing_number[10]
        round_1_pairing = aubry.pairings[1]
        self.assertEqual(round_1_pairing.result, Result.WIN)
        self.assertIsNotNone(round_1_pairing.opponent)
        self.assertEqual(round_1_pairing.opponent.pairing_number, 21)

        # --- round 2 reconstruction ---
        # The source TRF has round 2 with three matches: Lyon vs ERP A
        # (with two real boards + two unplayed slots on the ERP A
        # side), Crest vs Tour, and ERP B with the PAB. All three
        # must show up in ``team_boards_by_round``; previously the
        # importer was dropping the Lyon vs ERP A match and only
        # surfacing the lone-team groups.
        round_2_matches = [
            tb for tb in tournament.team_boards_by_id.values() if tb.round == 2
        ]
        match_keys = sorted(
            (
                tournament.event.teams_by_id[
                    tb.stored_team_board.team_a_id
                ].pairing_number,
                tournament.event.teams_by_id[
                    tb.stored_team_board.team_b_id
                ].pairing_number
                if tb.stored_team_board.team_b_id is not None
                else None,
            )
            for tb in round_2_matches
        )
        self.assertIn((4, 1), match_keys, 'Lyon vs ERP A missing in round 2')
        self.assertIn((2, 5), match_keys, 'Crest vs Tour missing in round 2')
        self.assertIn((3, None), match_keys, 'ERP B PAB missing in round 2')

    def test_trf_team_into_individual_event_is_rejected(self):
        """A team TRF must not be importable into an individual event,
        and a non-team TRF must not be importable into a team event."""
        from common.exception import ImporterError

        trf_path = self._write_team_trf(
            tempfile.NamedTemporaryFile(
                'w', encoding='utf-8', suffix='.trfx', delete=False
            )
        )
        try:
            # Default ``self.event`` is an individual event.
            individual_importer = TrfTournamentImporter([FileOption(Path(trf_path))])
            features = individual_importer.get_not_importable_features(self.event)
            self.assertTrue(
                any('individual event' in feature for feature in features),
                f'expected cross-type warning, got {features!r}',
            )
            with self.assertRaises(ImporterError):
                individual_importer.load_tournament(self.event)
        finally:
            Path(trf_path).unlink(missing_ok=True)

        # Now swap to a team event and try importing an individual TRF.
        TestUtils.delete_event(EVENT_ID)
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        self.event = EventLoader().load_event(EVENT_ID)
        individual_trf = BASE_PATH / 'trf-import-test.trf'
        team_event_importer = TrfTournamentImporter([FileOption(individual_trf)])
        features = team_event_importer.get_not_importable_features(self.event)
        self.assertTrue(
            any('team event' in feature for feature in features),
            f'expected cross-type warning, got {features!r}',
        )
        with self.assertRaises(ImporterError):
            team_event_importer.load_tournament(self.event)

    def test_papi_import(self):
        file_path = BASE_PATH / 'papi-import-test.papi'
        importer = PapiTournamentImporter([FileOption(file_path)])
        tournament = self._import_tournament(importer)
        self.assertEqual(tournament.name, 'Papi import test')
        self.assertEqual(len(tournament.players), 16)

    def test_papi_json_import(self):
        file_path = BASE_PATH / 'papi-json-import-test.json'
        importer = PapiJsonTournamentImporter([FileOption(file_path)])
        tournament = self._import_tournament(importer)
        self.assertEqual(tournament.name, 'Papi JSON import test')
        self.assertEqual(len(tournament.players), 16)
