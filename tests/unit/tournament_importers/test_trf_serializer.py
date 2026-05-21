from pathlib import Path
from unittest import TestCase

from data.input_output.trf.trf_data import (
    TrfTournament,
    TrfPlayer,
    TrfGame,
    TrfAcceleratedRound,
    TrfRoundBye,
    TrfProhibitedPairing,
    TrfTeamPABs,
    TrfTeamForfeitedMatch,
    TrfAbnormalPointsAssignment,
    TrfOOdOTeamPairing,
)
from data.input_output.trf.trf_serializer import TrfSerializer

CHINESE_WHISPERS_NUMBER = 10
TRF_PATH = Path(__file__).parent.parent.parent / 'trf'


class TestTrfSerializer(TestCase):
    maxDiff = None

    def test_load_example_trf16(self):
        filename = TRF_PATH / 'example_trf16.trf'
        with open(filename) as f:
            tour = TrfSerializer.load(f)

        self.assertEqual(tour.name, '9. Karl-Mala-Gedenkturnier')
        self.assertEqual(tour.city, 'Frankfurt (Main) /GER')
        self.assertEqual(tour.federation, '')
        self.assertEqual(tour.start_date, '28. 07. 2005')
        self.assertEqual(tour.end_date, '31. 07. 2005')
        self.assertEqual(tour.num_players, 284)
        self.assertEqual(tour.num_rated_players, 146)
        self.assertEqual(tour.num_teams, 0)
        self.assertEqual(tour.type, 'Individual: Swiss-System (Standard)')
        self.assertEqual(tour.chief_arbiter, 'Ralph Blum (SV Griesheim)')
        self.assertEqual(
            tour.deputy_arbiters, ['NSR Thomas Rondio, NSR Wolfgang Hettler']
        )
        self.assertEqual(tour.allotted_time, '40/120, 60')
        self.assertEqual(tour.round_dates, [])
        self.assertEqual(tour.num_rounds_estimation, 7)

        for p in tour.players:
            self.assertIsInstance(p, TrfPlayer)

            for g in p.games:
                self.assertIsInstance(g, TrfGame)

        self.assertEqual(tour.players[25].name, 'Schaffer,Hendrik')
        self.assertEqual(tour.players[144].fide_id, 24615480)
        self.assertEqual(tour.players[114].rating, 1994)
        self.assertEqual(tour.players[81].birth_date, '1965.09.07')
        self.assertEqual(tour.players[74].games[4], TrfGame(188, 'w', '1', 5))

    def test_load_example_trf26(self):
        filename = TRF_PATH / 'example_trf26.trf'
        with open(filename) as f:
            tour = TrfSerializer.load(f)

        self.assertEqual(tour.name, "Grandmommy's Cup")
        self.assertEqual(tour.city, 'Test')
        self.assertEqual(tour.federation, 'FID')
        self.assertEqual(tour.start_date, '2024/01/01')
        self.assertEqual(tour.end_date, '2024/01/14')
        self.assertEqual(tour.num_players, 249)
        self.assertEqual(tour.num_rated_players, 249)
        self.assertEqual(tour.num_teams, 50)
        self.assertEqual(tour.type, 'FIDE-TEAM-BAKU')
        self.assertEqual(tour.chief_arbiter, 'The Chief Arbiter')
        self.assertEqual(tour.deputy_arbiters[0], 'The first Deputy Chief Arbiter')
        self.assertEqual(tour.allotted_time, "100'x40+15'+30\"")
        self.assertEqual(len(tour.round_dates), 14)
        self.assertEqual(tour.round_dates[3], '24/01/04')
        self.assertEqual(tour.num_rounds, 14)
        self.assertEqual(tour.encoded_type, 'FIDE_TEAM_BAKU')
        self.assertEqual(len(tour.tie_breaks), 4)
        self.assertEqual(tour.tie_breaks[2], 'BH:MP/C1/P')
        self.assertEqual(tour.time_control, '40/6000+30:900+30')
        self.assertEqual(tour.num_rounds, 14)
        self.assertEqual(tour.board_color_sequence, 'WBWB')
        self.assertEqual(tour.teams_point_system, {'TW': 2.0, 'TD': 1.0, 'TL': 0.0})

        self.assertEqual(len(tour.players), 249)
        for p in tour.players:
            self.assertIsInstance(p, TrfPlayer)
            for g in p.games:
                self.assertIsInstance(g, TrfGame)

        self.assertEqual(tour.players[144].name, 'Test0145 Player0145')
        self.assertEqual(tour.players[25].fide_id, 72623454321)
        self.assertEqual(tour.players[74].rating, 2321)
        self.assertEqual(tour.players[114].birth_date, '1993/00/00')
        self.assertEqual(tour.players[81].games[6], TrfGame(56, 'b', '1', 7))
        np = tour.players[13].national_player_by_federation.get('FRA')
        self.assertIsNotNone(np)
        self.assertEqual(np.player_id, 14)
        self.assertEqual(np.gender, 'm')
        self.assertEqual(np.classification, 'A')
        self.assertEqual(np.name, 'Test0014 Player0014')
        self.assertEqual(np.rating, 2700)
        self.assertEqual(np.origin, 'BRE')
        self.assertEqual(np.national_id, 'L01854')
        self.assertEqual(np.birth_date, '1990/00/00')

        self.assertEqual(len(tour.teams), 50)
        self.assertEqual(tour.teams[45].name, 'Uzbekistan')
        self.assertEqual(tour.teams[22].nickname, 'CZE')
        self.assertEqual(tour.teams[12].strength_factor, 2327)
        self.assertEqual(tour.teams[25].match_points, 9.0)
        self.assertEqual(tour.teams[32].game_points, 19.5)
        self.assertEqual(tour.teams[5].rank, 6)
        self.assertEqual(tour.teams[7].player_ids, [8, 75, 54, 66, 64])

        self.assertEqual(len(tour.accelerated_rounds), 4)
        self.assertEqual(
            tour.accelerated_rounds[1],
            TrfAcceleratedRound(
                match_points=2.0,
                game_points=None,
                first_round=1,
                last_round=1,
                first_id=4,
                last_id=25,
            ),
        )
        self.assertEqual(len(tour.round_byes), 18)
        self.assertEqual(
            tour.round_byes[10],
            TrfRoundBye(type='F', round=6, pairing_numbers=[16]),
        )
        self.assertEqual(len(tour.prohibited_pairings), 1)
        self.assertEqual(
            tour.prohibited_pairings[0],
            TrfProhibitedPairing(
                first_round=1, last_round=14, pairing_numbers=[1, 11, 16]
            ),
        )
        self.assertEqual(
            tour.team_pabs,
            TrfTeamPABs(
                match_points=1.0,
                game_points=2.0,
                team_id_by_round={
                    3: 50,
                    4: 49,
                    6: 46,
                    7: 48,
                    8: 45,
                    10: 36,
                    11: 43,
                    14: 40,
                },
            ),
        )
        self.assertEqual(len(tour.team_forfeited_matches), 22)
        self.assertEqual(
            tour.team_forfeited_matches[5],
            TrfTeamForfeitedMatch(
                type='-+',
                round=8,
                white_team_id=27,
                black_team_id=14,
            ),
        )
        self.assertEqual(len(tour.abnormal_points_assignments), 2)
        self.assertEqual(
            tour.abnormal_points_assignments[0],
            TrfAbnormalPointsAssignment(
                type='+',
                match_points=2.0,
                game_points=2.5,
                round=1,
                pairing_numbers=[1],
            ),
        )
        self.assertEqual(len(tour.oodo_team_pairings), 141)
        self.assertEqual(
            tour.oodo_team_pairings[9],
            TrfOOdOTeamPairing(
                round=2,
                team_id=14,
                opponent_team_id=2,
                boards=[51, 60, 120, None],
            ),
        )
        self.assertEqual(len(tour.informative_team_pairings_records), 50)
        self.assertEqual(
            tour.informative_team_pairings_records[21],
            '22 SVK   20 32.0  10 w ==== 1234  12 b 1101 1254  '
            '13 w 1100 1234   8 b 00=1 1235  37 w 110= 1234  11 b 1==0 1234   '
            '9 w 11=0 1234   7 w 10=1 1234   4 b 1=== 1534       FFFF       '
            '19 b 11=0 1254  18 w 00=0 1234   6 b 11=0 1234   3 w 1010 1234',
        )
        self.assertEqual(len(tour.informative_team_results_records), 50)
        self.assertEqual(
            tour.informative_team_results_records[15],
            '16 IND3    20   33.5    4 w  2.5     3 b  1.5     '
            '1 w  2.0    12 w  2.5     2 b  2.5   FPB    4.0    19 b  3.0     '
            '6 w  2.0    18 w  1.5    11 b  1.5     8 b  2.5     5 w  2.5     '
            '9 w  3.0    13 b  2.5',
        )

    def test_example_trf16_chinese_whispers(self):
        self.chinese_whispers_from_file('example_trf16')

    def test_example_trf26_chinese_whispers(self):
        self.chinese_whispers_from_file('example_trf26')

    def test_2020_06_chinese_whispers(self):
        self.chinese_whispers_from_file('2020_06')

    def test_2021_03_chinese_whispers(self):
        self.chinese_whispers_from_file('2021_03')

    def chinese_whispers_from_file(self, name):
        filename = TRF_PATH / f'{name}.trf'
        with open(filename) as f:
            trf_string = f.read()
        tour0 = TrfSerializer.loads(trf_string)
        self.chinese_whispers(tour0)

    def chinese_whispers(self, tour0):
        dumped = TrfSerializer.dumps(tour0)

        for i in range(CHINESE_WHISPERS_NUMBER):
            itertext = f' in iteration {i + 1}'

            tour = TrfSerializer.loads(dumped)
            dumped = TrfSerializer.dumps(tour)

            self.assertIsInstance(tour, TrfTournament)
            self.assertEqual(
                tour.name, tour0.name, 'Diff of {tournament.name}' + itertext
            )
            self.assertEqual(
                tour.city, tour0.city, 'Diff of {tournament.city}' + itertext
            )
            self.assertEqual(
                tour.federation,
                tour0.federation,
                'Diff of {tournament.federation}' + itertext,
            )
            self.assertEqual(
                tour.start_date,
                tour0.start_date,
                'Diff of {tournament.start_date}' + itertext,
            )
            self.assertEqual(
                tour.end_date,
                tour0.end_date,
                'Diff of {tournament.end_date}' + itertext,
            )
            self.assertEqual(
                tour.num_players,
                tour0.num_players,
                'Diff of {tournament.num_players}' + itertext,
            )
            self.assertEqual(
                tour.num_rated_players,
                tour0.num_rated_players,
                'Diff of {tournament.num_rated_players}' + itertext,
            )
            self.assertEqual(
                tour.num_teams,
                tour0.num_teams,
                'Diff of {tournament.num_teams}' + itertext,
            )
            self.assertEqual(
                tour.type, tour0.type, 'Diff of {tournament.type}' + itertext
            )
            self.assertEqual(
                tour.chief_arbiter,
                tour0.chief_arbiter,
                'Diff of {tournament.chief_arbiter}' + itertext,
            )
            self.assertEqual(
                tour.deputy_arbiters,
                tour0.deputy_arbiters,
                'Diff of {tournament.deputy_arbiters}' + itertext,
            )
            self.assertEqual(
                tour.allotted_time,
                tour0.allotted_time,
                'Diff of {tournament.allotted_time}' + itertext,
            )
            self.assertEqual(
                tour.round_dates,
                tour0.round_dates,
                'Diff of {tournament.round_dates}' + itertext,
            )
            self.assertEqual(
                tour.xx_fields,
                tour0.xx_fields,
                'Diff of {tournament.xx_fields}' + itertext,
            )

            self.assertEqual(len(tour.players), len(tour0.players))
            for j, (player, player0) in enumerate(zip(tour.players, tour0.players)):
                self.assertIsInstance(player, TrfPlayer)
                self.assertEqual(
                    player.id, player0.id, f'Diff of {{player[{j}].id}}' + itertext
                )
                self.assertEqual(
                    player.gender,
                    player0.gender,
                    f'Diff of {{player[{j}].gender}}' + itertext,
                )
                self.assertEqual(
                    player.title,
                    player0.title,
                    f'Diff of {{player[{j}].title}}' + itertext,
                )
                self.assertEqual(
                    player.name,
                    player0.name,
                    f'Diff of {{player[{j}].name}}' + itertext,
                )
                self.assertEqual(
                    player.rating,
                    player0.rating,
                    f'Diff of {{player[{j}].rating}}' + itertext,
                )
                self.assertEqual(
                    player.federation,
                    player0.federation,
                    f'Diff of {{player[{j}].federation}}' + itertext,
                )
                self.assertEqual(
                    player.id, player0.id, f'Diff of {{player[{j}].id}}' + itertext
                )
                self.assertEqual(
                    player.birth_date,
                    player0.birth_date,
                    f'Diff of {{player[{j}].birth_date}}' + itertext,
                )
                self.assertEqual(
                    player.points,
                    player0.points,
                    f'Diff of {{player[{j}].points}}' + itertext,
                )
                self.assertEqual(
                    player.rank,
                    player0.rank,
                    f'Diff of {{player[{j}].rank}}' + itertext,
                )
                self.assertEqual(
                    player.games,
                    player0.games,
                    f'Diff of {{player[{j}].games}}' + itertext,
                )
