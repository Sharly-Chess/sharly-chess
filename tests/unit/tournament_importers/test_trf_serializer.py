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
    TrfTeam,
    TrfDeprecatedTeam,
)
from data.input_output.trf.trf_entry import AbnormalPointsAssignmentEntry
from data.input_output.trf.trf_mappers import TrfEncodedType
from data.input_output.trf.trf_serializer import TrfSerializer
from data.pairings.variations import (
    PairingVariation,
    BergerTeamRoundRobinVariation,
    DoubleBergerTeamRoundRobinVariation,
    StandardSwissVariation,
    StandardTeamSwissVariation,
)
from utils.enum import ScoreType, TeamColourType

CHINESE_WHISPERS_NUMBER = 10
TRF_PATH = Path(__file__).parent.parent.parent / 'trf'


class TestTrfSerializer(TestCase):
    maxDiff = None

    def test_team_encoded_type_decoding(self):
        """``TrfEncodedType`` decodes TRF26 team-Swiss codes into the
        right variation and score config."""
        mp = ScoreType.MATCH_POINTS
        gp = ScoreType.GAME_POINTS
        cases = {
            'FIDE_TEAM_TYPEA_MP': (TeamColourType.A, mp, None),
            'FIDE_TEAM_TYPEA_GP': (TeamColourType.A, gp, None),
            'FIDE_TEAM_TYPEA_MP_GP': (TeamColourType.A, mp, gp),
            'FIDE_TEAM_TYPEA_GP_MP': (TeamColourType.A, gp, mp),
            'FIDE_TEAM_TYPEB_MP': (TeamColourType.B, mp, None),
            'FIDE_TEAM_TYPEB_MP_GP': (TeamColourType.B, mp, gp),
            'FIDE_TEAM_TYPEB_GP_MP': (TeamColourType.B, gp, mp),
            'FIDE_TEAM_MP': (TeamColourType.NONE, mp, None),
            'FIDE_TEAM_MP_GP': (TeamColourType.NONE, mp, gp),
            'FIDE_TEAM_GP_MP': (TeamColourType.NONE, gp, mp),
        }
        for encoded_type, (colour, primary, secondary) in cases.items():
            self.assertEqual(
                TrfEncodedType.get_team_score_config(encoded_type),
                (primary, secondary),
                f'wrong score config for {encoded_type}',
            )
            self.assertEqual(
                TrfEncodedType.get_team_colour_type(encoded_type),
                colour,
                f'wrong colour type for {encoded_type}',
            )
            variation = TrfEncodedType.get_supported_pairing_variation(encoded_type)
            self.assertIsInstance(variation, StandardTeamSwissVariation)

        self.assertIsNone(TrfEncodedType.get_team_score_config('FIDE_DUTCH_2026'))
        self.assertIsNone(TrfEncodedType.get_team_score_config('FIDE_TEAM_TYPEA_FOO'))
        self.assertIsNone(TrfEncodedType.get_team_score_config('FIDE_TEAM_TYPEA_'))
        self.assertIsNone(TrfEncodedType.get_team_colour_type('FIDE_DUTCH_2026'))

        self.assertIsInstance(
            TrfEncodedType.get_supported_pairing_variation('OTHER_TEAM_ROUNDROBIN'),
            BergerTeamRoundRobinVariation,
        )
        self.assertIsInstance(
            TrfEncodedType.get_supported_pairing_variation(
                'OTHER_TEAM_DOUBLEROUNDROBIN'
            ),
            DoubleBergerTeamRoundRobinVariation,
        )

        # FIDE table codes for team round-robin must route to the Berger
        # team-RR variations, NOT be swallowed by the FIDE_TEAM_ team-Swiss
        # prefix — and they carry no score config.
        for code in (
            'FIDE_TEAM_ROUNDROBIN',
            'BERGER_TEAM_ROUNDROBIN',
            'CUSTOM_TEAM_ROUNDROBIN',
        ):
            self.assertIsInstance(
                TrfEncodedType.get_supported_pairing_variation(code),
                BergerTeamRoundRobinVariation,
                f'{code} should map to Berger team round-robin',
            )
            self.assertIsNone(TrfEncodedType.get_team_score_config(code))
        self.assertIsInstance(
            TrfEncodedType.get_supported_pairing_variation(
                'FIDE_TEAM_DOUBLEROUNDROBIN'
            ),
            DoubleBergerTeamRoundRobinVariation,
        )

        # Individual Swiss FIDE table code.
        self.assertIsInstance(
            TrfEncodedType.get_supported_pairing_variation('FIDE_DUTCH_2026'),
            StandardSwissVariation,
        )

        self.assertIsInstance(
            TrfEncodedType.get_supported_pairing_variation('FIDE_DUTCH_2025'),
            StandardSwissVariation,
        )

        # Export side: variations emit valid FIDE table codes.
        self.assertEqual(StandardSwissVariation().trf_encoded_type, 'FIDE_DUTCH_2026')
        self.assertEqual(
            BergerTeamRoundRobinVariation().trf_encoded_type, 'FIDE_TEAM_ROUNDROBIN'
        )
        self.assertEqual(
            DoubleBergerTeamRoundRobinVariation().trf_encoded_type,
            'FIDE_TEAM_DOUBLEROUNDROBIN',
        )

    # The Tournament Type Code Table for TRF_CODE 192, verbatim. The
    # parameterised forms (BERGER_ROUNDROBIN_Gn, FIDE_SCHILLER_TxP,
    # FIDE_SCHEVENINGEN_Gn) are listed in their documented default form.
    TOURNAMENT_TYPE_CODES = (
        'FIDE_DUTCH_2017 FIDE_DUTCH_2026 FIDE_DUTCH FIDE_DUBOV FIDE_BURSTEIN '
        'FIDE_DUTCH_2017_BAKU FIDE_DUTCH_2026_BAKU FIDE_DUTCH_BAKU '
        'FIDE_DUBOV_BAKU FIDE_BURSTEIN_BAKU CUSTOM_SWISS FIDE_DOUBLESWISS '
        'FIDE_DOUBLESWISS_BAKU CUSTOM_DOUBLESWISS BERGER_ROUNDROBIN '
        'BERGER_DOUBLEROUNDROBIN FIDE_ROUNDROBIN FIDE_DOUBLEROUNDROBIN '
        'CUSTOM_ROUNDROBIN FIDE_SCHILLER CUSTOM_SCHILLER FIDE_SCHEVENINGEN '
        'FIDE_DOUBLESCHEVENINGEN CUSTOM_SCHEVENINGEN CUSTOM_KNOCKOUT '
        'FIDE_TEAM_TYPEA_MP_GP FIDE_TEAM_TYPEA_GP_MP FIDE_TEAM_TYPEA_MP '
        'FIDE_TEAM_TYPEA_GP FIDE_TEAM_TYPEB_MP_GP FIDE_TEAM_TYPEB_GP_MP '
        'FIDE_TEAM_TYPEB_MP FIDE_TEAM_TYPEB_GP FIDE_TEAM_MP_GP FIDE_TEAM_GP_MP '
        'FIDE_TEAM_MP FIDE_TEAM_GP FIDE_TEAM CUSTOM_TEAM_SWISS_MP '
        'CUSTOM_TEAM_SWISS_GP FIDE_TEAM_TYPEA_MP_GP_BAKU FIDE_TEAM_TYPEA_MP_BAKU '
        'FIDE_TEAM_TYPEB_MP_GP_BAKU FIDE_TEAM_TYPEB_MP_BAKU FIDE_TEAM_MP_GP_BAKU '
        'FIDE_TEAM_MP_BAKU FIDE_TEAM_BAKU CUSTOM_TEAM_SWISS '
        'BERGER_TEAM_ROUNDROBIN BERGER_TEAM_DOUBLEROUNDROBIN '
        'FIDE_TEAM_ROUNDROBIN FIDE_TEAM_DOUBLEROUNDROBIN CUSTOM_TEAM_ROUNDROBIN '
        'CUSTOM_TEAM_KNOCKOUT'
    ).split()

    def test_exported_encoded_types_are_real_codes(self):
        """Every 192 code we write has to appear in the type table."""
        import inspect

        from data.pairings import variations
        from plugins.pairing_acceleration import pairing_variations

        emitted: set[str] = set()
        for module in (variations, pairing_variations):
            for _name, obj in vars(module).items():
                if not inspect.isclass(obj) or not issubclass(obj, PairingVariation):
                    continue
                try:
                    code = obj().trf_encoded_type
                except Exception:  # abstract / needs arguments
                    continue
                if code:
                    emitted.add(code)
        self.assertTrue(emitted, 'no encoded types were collected')
        for code in sorted(emitted):
            self.assertIn(code, self.TOURNAMENT_TYPE_CODES, f'{code} is not a 192 code')

    def test_every_encoded_type_resolves_to_a_pairing_system(self):
        """Codes we don't implement fall back with a warning rather than
        failing, but a team code must never fall back to an individual
        system, and vice versa."""
        for code in self.TOURNAMENT_TYPE_CODES:
            variation = TrfEncodedType.get_pairing_variation(code)
            self.assertIsNotNone(variation, code)
            is_team_code = 'TEAM' in code
            self.assertEqual(
                isinstance(
                    variation,
                    (
                        StandardTeamSwissVariation,
                        BergerTeamRoundRobinVariation,
                        DoubleBergerTeamRoundRobinVariation,
                    ),
                ),
                is_team_code,
                f'{code} resolved to {type(variation).__name__}',
            )

    def dumped_line(self, tournament: TrfTournament, din: str) -> str:
        for line in TrfSerializer.dumps(tournament).splitlines():
            if line.startswith(din):
                return line
        self.fail(f'no {din} record was dumped')

    def test_round_dates_use_the_same_columns_as_the_player_rounds(self):
        """TRF26 132: the first date occupies 92-99, then every 10 —
        the columns of the 001 rounds it sits above. Round-tripping
        can't catch a shift here, since the parser splits on spaces."""
        tournament = TrfTournament(
            round_dates=['26/01/05', '26/01/06', '26/01/07'],
            players=[
                TrfPlayer(
                    id=1,
                    games=[TrfGame(opponent_id=2, color='w', result='1', round=1)],
                )
            ],
        )
        dates = self.dumped_line(tournament, '132')
        self.assertEqual(dates.index('26/01/05'), 91)
        self.assertEqual(dates.index('26/01/06'), 101)
        self.assertEqual(dates.index('26/01/07'), 111)
        # The 001 round columns the dates line up with.
        player = self.dumped_line(tournament, '001')
        self.assertEqual(player[91:95], '   2')

    def test_record_columns_match_the_spec(self):
        """Every field of every record, checked against the TRF26 field
        tables with values wide enough to fill their columns — a value
        narrower than its field hides an offset, and round-tripping hides
        one entirely."""
        tournament = TrfTournament(
            round_dates=['26/01/05', '26/01/06', '26/01/07'],
            individuals_point_system={'W': 1.0, 'D': 12.5, 'L': 0.0},
            teams_point_system={'TW': 2.0, 'TD': 11.5, 'TL': 0.0},
            players=[
                TrfPlayer(
                    id=1234,
                    gender='m',
                    title='WGM',
                    name='X' * 33,
                    rating=2500,
                    federation='FRA',
                    fide_id=12345678901,
                    birth_date='1990/01/01',
                    points=12.5,
                    rank=1234,
                    games=[TrfGame(opponent_id=4321, color='w', result='1', round=1)],
                )
            ],
            teams=[
                TrfTeam(
                    id=123,
                    name='T' * 32,
                    nickname='NNNNN',
                    strength_factor=123456,
                    match_points=1234.5,
                    game_points=2345.5,
                    rank=123,
                    player_ids=[1111, 2222],
                )
            ],
            deprecated_teams=[
                TrfDeprecatedTeam(name='D' * 32, player_ids=[1111, 2222])
            ],
            round_byes=[TrfRoundBye(type='H', round=123, pairing_numbers=[1111, 2222])],
            accelerated_rounds=[
                TrfAcceleratedRound(
                    match_points=12.5,
                    game_points=23.5,
                    first_round=123,
                    last_round=234,
                    first_id=1111,
                    last_id=2222,
                )
            ],
            prohibited_pairings=[
                TrfProhibitedPairing(
                    first_round=123, last_round=234, pairing_numbers=[1111, 2222]
                )
            ],
            team_pabs=TrfTeamPABs(
                match_points=12.5, game_points=23.5, team_id_by_round={1: 111, 2: 222}
            ),
            team_forfeited_matches=[
                TrfTeamForfeitedMatch(
                    type='+-', round=123, white_team_id=111, black_team_id=222
                )
            ],
            oodo_team_pairings=[
                TrfOOdOTeamPairing(
                    round=123, team_id=111, opponent_team_id=222, boards=[1111, 2222]
                )
            ],
        )
        spec: dict[str, list[tuple[str, int, int, str]]] = {
            '001': [
                ('starting rank', 5, 8, '1234'),
                ('sex', 10, 10, 'm'),
                ('title', 11, 13, 'WGM'),
                ('name', 15, 47, 'X' * 33),
                ('rating', 49, 52, '2500'),
                ('federation', 54, 56, 'FRA'),
                ('fide number', 58, 68, '12345678901'),
                ('birth date', 70, 79, '1990/01/01'),
                ('points', 81, 84, '12.5'),
                ('rank', 86, 89, '1234'),
                ('round 1 id', 92, 95, '4321'),
                ('round 1 colour', 97, 97, 'w'),
                ('round 1 result', 99, 99, '1'),
            ],
            '132': [
                ('round 1', 92, 99, '26/01/05'),
                ('round 2', 102, 109, '26/01/06'),
                ('round 3', 112, 119, '26/01/07'),
            ],
            '162': [
                ('symbol 1', 6, 6, 'W'),
                ('points 1', 7, 10, ' 1.0'),
                ('symbol 2', 15, 15, 'D'),
                ('points 2', 16, 19, '12.5'),
            ],
            '362': [
                ('symbol 1', 5, 6, 'TW'),
                ('points 1', 7, 10, ' 2.0'),
                ('symbol 2', 14, 15, 'TD'),
                ('points 2', 16, 19, '11.5'),
            ],
            '013': [
                ('name', 5, 36, 'D' * 32),
                ('player 1', 37, 40, '1111'),
                ('player 2', 42, 45, '2222'),
            ],
            '310': [
                ('pairing number', 5, 7, '123'),
                ('name', 9, 40, 'T' * 32),
                ('nickname', 42, 46, 'NNNNN'),
                ('strength factor', 48, 53, '123456'),
                ('match points', 55, 60, '1234.5'),
                ('game points', 62, 67, '2345.5'),
                ('rank', 69, 71, '123'),
                ('player 1', 74, 77, '1111'),
                ('player 2', 79, 82, '2222'),
            ],
            '240': [
                ('type', 5, 5, 'H'),
                ('round', 7, 9, '123'),
                ('id 1', 11, 14, '1111'),
                ('id 2', 16, 19, '2222'),
            ],
            '250': [
                ('match points', 5, 8, '12.5'),
                ('game points', 10, 13, '23.5'),
                ('first round', 15, 17, '123'),
                ('last round', 19, 21, '234'),
                ('first id', 23, 26, '1111'),
                ('last id', 28, 31, '2222'),
            ],
            '260': [
                ('first round', 5, 7, '123'),
                ('last round', 9, 11, '234'),
                ('id 1', 13, 16, '1111'),
                ('id 2', 18, 21, '2222'),
            ],
            '300': [
                ('round', 5, 7, '123'),
                ('team', 9, 11, '111'),
                ('opponent', 13, 15, '222'),
                ('board 1', 17, 20, '1111'),
                ('board 2', 22, 25, '2222'),
            ],
            '320': [
                ('pab match points', 5, 8, '12.5'),
                ('pab game points', 10, 13, '23.5'),
                ('round 1', 15, 17, '111'),
                ('round 2', 19, 21, '222'),
            ],
            '330': [
                ('type', 5, 6, '+-'),
                ('round', 8, 10, '123'),
                ('white team', 12, 14, '111'),
                ('black team', 16, 18, '222'),
            ],
        }
        for din, fields in spec.items():
            line = self.dumped_line(tournament, din)
            for label, start, end, expected in fields:
                self.assertEqual(
                    line[start - 1 : end],
                    expected,
                    f'{din} {label}: expected at columns {start}-{end}',
                )

    def test_starting_rank_method_columns(self):
        """TRF26 172: the federation the National Rating Support records
        belong to at 5-7, the method at 9-13. Files written before the
        federation was added carry the bare method, and still load."""
        tournament = TrfTournament(
            starting_rank_federation='FRA', starting_rank_method='FIDON'
        )
        line = self.dumped_line(tournament, '172')
        self.assertEqual(line[4:7], 'FRA')
        self.assertEqual(line[8:13], 'FIDON')

        reloaded = TrfSerializer.loads(line)
        self.assertEqual(reloaded.starting_rank_federation, 'FRA')
        self.assertEqual(reloaded.starting_rank_method, 'FIDON')

        legacy = TrfSerializer.loads('172 FIDON')
        self.assertEqual(legacy.starting_rank_federation, '')
        self.assertEqual(legacy.starting_rank_method, 'FIDON')

        # Only meaningful alongside NRS records, so not written bare.
        self.assertNotIn(
            '172', TrfSerializer.dumps(TrfTournament(name='T')).splitlines()
        )

    def test_abnormal_points_assignment_columns(self):
        """TRF26 299. The spec's worked example puts these fields two
        columns to the left of its own field table; the table is what
        bbpPairings reads. ``[-]11.5`` is four columns wide, as it is in
        every other record, so a sign costs an integer digit."""
        tournament = TrfTournament(
            abnormal_points_assignments=[
                TrfAbnormalPointsAssignment(
                    type='D',
                    match_points=-2.0,
                    game_points=12.5,
                    round=12,
                    pairing_numbers=[123, 4],
                )
            ]
        )
        line = self.dumped_line(tournament, '299')
        self.assertEqual(line[4], 'D')  # 5: type
        self.assertEqual(line[7:11], '-2.0')  # 8-11: match points
        self.assertEqual(line[13:17], '12.5')  # 14-17: game points
        self.assertEqual(line[19:22], ' 12')  # 20-22: round
        self.assertEqual(line[23:27], ' 123')  # 24-27: first team/player
        self.assertEqual(line[28:32], '   4')  # 29-32: second, stride 5

        # The ### ruler above the records has to line up with them.
        header = self.dumped_line(tournament, '### T')
        self.assertEqual(header[7:11], 'MMMM')
        self.assertEqual(header[13:17], 'GGGG')
        self.assertEqual(header[19:22], 'RRR')
        self.assertEqual(header[23:27], 'PPP1')

    def test_abnormal_points_assignments_match_bbppairings(self):
        """Lines taken verbatim from the bbpPairings test fixtures, which
        is the reader we hand these records to."""
        entry = AbnormalPointsAssignmentEntry()
        cases = {
            '299          -0.5    1    2': TrfAbnormalPointsAssignment(
                type=' ',
                match_points=None,
                game_points=-0.5,
                round=1,
                pairing_numbers=[2],
            ),
            '299     3.0          1    4': TrfAbnormalPointsAssignment(
                type=' ',
                match_points=3.0,
                game_points=None,
                round=1,
                pairing_numbers=[4],
            ),
            '299    -5.0          1    1': TrfAbnormalPointsAssignment(
                type=' ',
                match_points=-5.0,
                game_points=None,
                round=1,
                pairing_numbers=[1],
            ),
        }
        for line, expected in cases.items():
            self.assertEqual(entry.parse(line[4:]), expected, line)
            self.assertEqual('299 ' + entry.format(expected), line, line)

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
        assert np is not None
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
