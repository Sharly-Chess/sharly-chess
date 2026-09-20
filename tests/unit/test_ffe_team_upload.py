"""Sending a team competition to the FFE website's team module.

The module has no API: Sharly reads the group page, registers the teams
and fills in one match report per match. These tests cover the reading
of the site's pages (recorded in ``ffe_team_module/``) and what Sharly
posts for a match.
"""

import contextlib
from pathlib import Path
from unittest import TestCase

import pytest
from AdvancedHTMLParser import AdvancedHTMLParser

from data.loader import EventLoader
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from plugins.ffe.ffe_team_session import (
    FFETeamSession,
    DIVISION_SELECT,
    GROUP_SELECT,
    SiteOption,
)
from plugins.ffe.utils import FFEUtils, FfeTournamentPluginData
from tests.test_config import TestUtils
from utils.enum import EventType, Result, ScoreType

PAGES = Path(__file__).parent / 'ffe_team_module'

EVENT_ID = 'test-ffe-team-upload'
TOURNAMENT_NAME = 'tournament'
BOARDS = 2


def page(name: str) -> AdvancedHTMLParser:
    parser = AdvancedHTMLParser()
    parser.parseStr((PAGES / name).read_text())
    return parser


@pytest.mark.unit
class SitePagesTestCase(TestCase):
    def test_the_competition_page_lists_the_divisions(self) -> None:
        options = FFETeamSession._options(page('competition.html'), DIVISION_SELECT)
        self.assertEqual(
            options,
            [
                SiteOption(706, 'Phase Departementale'),
                SiteOption(184, 'Phase 2'),
                SiteOption(202, 'Phase 3'),
                SiteOption(216, 'Phase Finale'),
            ],
        )

    def test_the_division_page_lists_the_groups(self) -> None:
        options = FFETeamSession._options(page('division.html'), GROUP_SELECT)
        self.assertIn(SiteOption(3593, 'Test group Swiss'), options)
        self.assertIn(SiteOption(3594, 'Test group Molter'), options)
        self.assertNotIn(1, {option.id for option in options})

    def test_a_group_without_rights_has_no_editor(self) -> None:
        self.assertIsNone(FFETeamSession.parse_group_page(page('group_no_rights.html')))

    def test_the_group_page_lists_teams_and_match_reports(self) -> None:
        group = FFETeamSession.parse_group_page(page('group.html'))
        assert group is not None
        self.assertEqual(
            group.teams_by_name, {'Sharly Test A': 2213, 'Sharly Test B': 2214}
        )
        self.assertEqual(len(group.match_reports), 1)
        report = group.match_reports[0]
        self.assertEqual((report.id, report.round), (4310, 0))
        self.assertTrue(report.is_blank)

    def test_the_match_report_form_has_four_boards(self) -> None:
        self.assertEqual(
            FFETeamSession.parse_board_count(page('match_report_form.html')), 4
        )


@pytest.mark.unit
class SiteChoiceTestCase(TestCase):
    """The division and group selects carry ``id|name`` values."""

    def test_a_choice_round_trips(self) -> None:
        data = FfeTournamentPluginData.from_form_data(
            {
                'ffe_team_login': 'group',
                'ffe_team_password': 'secret',
                'ffe_team_division': '706|Phase Departementale',
                'ffe_team_group': '3593|Test group Swiss',
            }
        )
        self.assertEqual(
            (data.team_division_id, data.team_division_name),
            (706, 'Phase Departementale'),
        )
        self.assertEqual(
            (data.team_group_id, data.team_group_name), (3593, 'Test group Swiss')
        )
        self.assertTrue(data.team_configured)
        self.assertEqual(data.to_form_data()['ffe_team_group'], '3593|Test group Swiss')

    def test_an_empty_choice_leaves_the_transfer_unconfigured(self) -> None:
        data = FfeTournamentPluginData.from_form_data(
            {
                'ffe_team_login': 'group',
                'ffe_team_password': 'secret',
                'ffe_team_division': '',
                'ffe_team_group': '',
            }
        )
        self.assertIsNone(data.team_division_id)
        self.assertFalse(data.team_configured)


class _MatchReportHarness(TestCase):
    """A two-team Loubatière round with two boards, every player
    licensed unless a test says otherwise."""

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def _create(
        self,
        licences: bool = True,
        pairing: str = 'TEAM_ROUND_ROBIN_BERGER',
        teams: int = 2,
        boards: int = BOARDS,
        first_team_players: int | None = None,
        primary_score: ScoreType = ScoreType.MATCH_POINTS,
    ) -> Tournament:
        TestUtils.create_event(EVENT_ID, overrides={'event_type': EventType.TEAM})
        stored_tournament = TestUtils.create_tournament(
            EVENT_ID,
            TOURNAMENT_NAME,
            overrides={
                'rounds': 1,
                'current_round': 1,
                'team_player_count': boards,
                'pairing': pairing,
                'primary_score': primary_score,
                'match_points': {
                    Result.WIN.value: 3.0,
                    Result.DRAW.value: 2.0,
                    Result.LOSS.value: 1.0,
                },
                'game_points': {
                    Result.WIN.value: 1.0,
                    Result.DRAW.value: 0.0,
                    Result.LOSS.value: 0.0,
                },
                'rule_set': 'ffe-coupe-jean-claude-loubatiere',
            },
        )
        tournament_id = stored_tournament.id
        assert tournament_id is not None
        self.team_ids: list[int] = []
        with EventDatabase(EVENT_ID, write=True) as database:
            for seed in range(1, teams + 1):
                team_id = database.add_stored_team(
                    StoredTeam(
                        id=None,
                        name=f'Team {seed}',
                        tournament_id=tournament_id,
                        pairing_number=seed,
                        check_in=True,
                    )
                )
                self.team_ids.append(team_id)
                players = boards
                if seed == 1 and first_team_players is not None:
                    players = first_team_players
                for index in range(players):
                    plugin_data = (
                        {'ffe': {'ffe_licence_number': f'A{seed}{index:04d}'}}
                        if licences
                        else {}
                    )
                    player_id = database.add_stored_player(
                        StoredPlayer(
                            id=None,
                            last_name=f'T{seed}P{index}',
                            team_id=team_id,
                            team_index=index,
                            check_in=True,
                            plugin_data=plugin_data,
                        )
                    )
                    database.add_stored_tournament_player(
                        StoredTournamentPlayer(
                            tournament_id=tournament_id,
                            player_id=player_id,
                            pairing_number=index + 1,
                        )
                    )
        tournament = self._load()
        self.assertEqual(tournament.generate_round_pairings(1), '')
        return self._load()

    def _load(self) -> Tournament:
        with contextlib.suppress(KeyError):
            EventLoader.unload_event(EVENT_ID)
        self._event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_NAME]


@pytest.mark.unit
class MatchReportTestCase(_MatchReportHarness):
    def _site_ids(self) -> dict[int, int]:
        return {team_id: 2212 + seed for seed, team_id in enumerate(self.team_ids, 1)}

    def test_the_transfer_goes_through_the_team_module(self) -> None:
        tournament = self._create()
        self.assertEqual(FFEUtils.team_competition_id(tournament), 8)
        self.assertTrue(FFEUtils.supports_team_transfer(tournament))
        self.assertTrue(FFEUtils.supports_ffe_transfer(tournament))

    def test_unlicensed_players_block_the_upload(self) -> None:
        tournament = self._create(licences=False)
        message = FFETeamSession.upload_unavailable_message(tournament)
        assert message is not None
        self.assertIn('T1P0', message)

    def test_the_report_reads_from_the_team_with_white_on_board_one(self) -> None:
        tournament = self._create()
        team_board = tournament.get_round_team_boards(1)[0]
        boards = team_board.boards
        tournament.add_result(boards[0], Result.WIN)
        tournament.add_result(boards[1], Result.DRAW)
        tournament = self._load()
        team_board = tournament.get_round_team_boards(1)[0]
        boards = team_board.boards
        match = FFETeamSession.round_matches(tournament, 1)[0]
        data = FFETeamSession.match_report_data(match, 1, self._site_ids())

        white_team_id, _ = team_board.board_team_ids(boards[0])
        assert white_team_id is not None
        self.assertEqual(data.left_team_id, self._site_ids()[white_team_id])
        self.assertEqual((data.round, data.number), (1, 1))
        # Board 1: the left team's player won with white. Board 2: the
        # left team's player had black, the draw stays a draw.
        left_board_one = boards[0].white_tournament_player
        right_board_one = boards[0].black_tournament_player
        assert right_board_one is not None
        self.assertEqual(
            data.boards[0],
            (
                FFETeamSession.licence_number(left_board_one),
                FFETeamSession.licence_number(right_board_one),
                'GainBlanc',
            ),
        )
        self.assertEqual(data.boards[1][2], 'Nulle')
        # Loubatière scoring: a draw earns no game point.
        self.assertEqual(
            (data.left_game_points, data.right_game_points), ('1.0', '0.0')
        )
        self.assertEqual((data.left_match_points, data.right_match_points), ('3', '1'))

    def test_a_win_by_the_right_team_reads_as_a_black_win(self) -> None:
        tournament = self._create()
        team_board = tournament.get_round_team_boards(1)[0]
        boards = team_board.boards
        # Board 2 is played with reversed colours: a white win there is
        # a win for the team listed on the right.
        tournament.add_result(boards[1], Result.WIN)
        tournament = self._load()
        match = FFETeamSession.round_matches(tournament, 1)[0]
        data = FFETeamSession.match_report_data(match, 1, self._site_ids())
        self.assertEqual(data.boards[1][2], 'GainNoir')
        self.assertEqual((data.left_match_points, data.right_match_points), ('1', '3'))

    def test_an_unplayed_match_carries_no_scores(self) -> None:
        tournament = self._create()
        match = FFETeamSession.round_matches(tournament, 1)[0]
        data = FFETeamSession.match_report_data(match, 1, self._site_ids())
        self.assertEqual((data.left_match_points, data.left_game_points), ('', ''))
        self.assertEqual([board[2] for board in data.boards], ['None', 'None'])

    def test_a_forfeit_reads_as_a_forfeit(self) -> None:
        tournament = self._create()
        team_board = tournament.get_round_team_boards(1)[0]
        boards = team_board.boards
        tournament.add_result(boards[0], Result.FORFEIT_LOSS)
        tournament = self._load()
        match = FFETeamSession.round_matches(tournament, 1)[0]
        data = FFETeamSession.match_report_data(match, 1, self._site_ids())
        self.assertEqual(data.boards[0][2], 'GainNoirForfait')
        self.assertEqual(data.boards[1][2], 'None')

    def test_a_forfeit_penalty_lands_in_the_game_points(self) -> None:
        """Loubatière counts a game lost by forfeit −1: the report carries
        the adjusted game points, as the site does not compute them."""
        tournament = self._create()
        team_board = tournament.get_round_team_boards(1)[0]
        boards = team_board.boards
        tournament.add_result(boards[0], Result.FORFEIT_LOSS)
        # Board 2 has reversed colours: the left team wins with black.
        tournament.add_result(boards[1], Result.LOSS)
        tournament = self._load()
        match = FFETeamSession.round_matches(tournament, 1)[0]
        # 1 point on board 2, −1 for the forfeit: 0, not below (C03 4.2.a).
        self.assertEqual(match.game_points, (0.0, 1.0))
        data = FFETeamSession.match_report_data(match, 1, self._site_ids())
        self.assertEqual(data.boards[0][2], 'GainNoirForfait')
        self.assertEqual(data.boards[1][2], 'GainBlanc')
        self.assertEqual(
            (data.left_game_points, data.right_game_points), ('0.0', '1.0')
        )
        self.assertEqual((data.left_match_points, data.right_match_points), ('1', '3'))

    def test_a_match_score_stops_at_zero(self) -> None:
        """Two forfeits and a draw: −2 on 0 points is floored at 0."""
        tournament = self._create()
        team_board = tournament.get_round_team_boards(1)[0]
        boards = team_board.boards
        tournament.add_result(boards[0], Result.FORFEIT_LOSS)
        tournament.add_result(boards[1], Result.FORFEIT_WIN)
        tournament = self._load()
        match = FFETeamSession.round_matches(tournament, 1)[0]
        self.assertEqual(match.game_points, (0.0, 2.0))

    def test_a_fixed_table_hole_is_reported_against_the_absent_team(self) -> None:
        """A Molter seat left empty has no player to name its team: the
        table does, and the absent team takes the forfeit penalty on
        that report."""
        tournament = self._create(
            pairing='MOLTER_STANDARD', teams=3, boards=4, first_team_players=3
        )
        boards = tournament.get_round_boards(1)
        holes = [
            b
            for b in boards
            if b.optional_white_tournament_player is None
            or b.black_tournament_player is None
        ]
        self.assertEqual(len(holes), 1)
        matches = FFETeamSession.round_matches(tournament, 1)
        self.assertEqual(sum(len(m.boards) for m in matches), 6)
        short_team_id = self.team_ids[0]
        match = next(m for m in matches if holes[0].id in {b.id for b in m.boards})
        self.assertIn(short_team_id, (match.team_a.id, match.team_b.id))
        short_side = 0 if match.team_a.id == short_team_id else 1
        # The opponent's forfeit win counts 1; the absent team's −1 is
        # taken off the round's reports it has points on — none here,
        # so it stays on this one.
        self.assertEqual(match.game_points[short_side], -1.0)
        self.assertEqual(match.game_points[1 - short_side], 1.0)
        data = FFETeamSession.match_report_data(match, 1, self._site_ids())
        self.assertIn(
            'GainBlancForfait' if short_side else 'GainNoirForfait',
            [b[2] for b in data.boards],
        )

    def test_a_fixed_table_penalty_is_taken_where_points_absorb_it(self) -> None:
        """The report split is the site's: the penalty leaves no report
        below zero when the team scored elsewhere in the round."""
        tournament = self._create(
            pairing='MOLTER_STANDARD', teams=3, boards=4, first_team_players=3
        )
        short_team_id = self.team_ids[0]
        for board in tournament.get_round_boards(1):
            white = board.optional_white_tournament_player
            black = board.black_tournament_player
            if white is None or black is None:
                continue
            tournament.add_result(
                board, Result.WIN if white.team_id == short_team_id else Result.LOSS
            )
        tournament = self._load()
        matches = FFETeamSession.round_matches(tournament, 1)
        short_points = [
            m.game_points[0 if m.team_a.id == short_team_id else 1]
            for m in matches
            if short_team_id in (m.team_a.id, m.team_b.id)
        ]
        self.assertTrue(all(points >= 0 for points in short_points), short_points)
        # 3 boards won, one seat empty: 3 − 1.
        self.assertEqual(sum(short_points), 2.0)

    def test_a_fixed_table_round_splits_into_one_match_per_pair_of_teams(
        self,
    ) -> None:
        """Molter pairs the players across the teams, without match
        envelopes: the site still wants one report per pair of teams."""
        tournament = self._create(
            pairing='MOLTER_STANDARD',
            teams=3,
            boards=4,
            primary_score=ScoreType.GAME_POINTS,
        )
        boards = tournament.get_round_boards(1)
        self.assertEqual(len(boards), 6)
        for board in boards:
            tournament.add_result(board, Result.WIN)
        tournament = self._load()
        matches = FFETeamSession.round_matches(tournament, 1)
        self.assertEqual(len(matches), 3)
        self.assertEqual(
            {frozenset((m.team_a.id, m.team_b.id)) for m in matches},
            {
                frozenset(pair)
                for pair in (
                    (self.team_ids[0], self.team_ids[1]),
                    (self.team_ids[0], self.team_ids[2]),
                    (self.team_ids[1], self.team_ids[2]),
                )
            },
        )
        for match in matches:
            self.assertEqual(len(match.boards), 2)
            data = FFETeamSession.match_report_data(match, 1, self._site_ids())
            self.assertEqual(len(data.boards), 2)
            self.assertEqual(
                float(data.left_game_points) + float(data.right_game_points), 2.0
            )
            # Molter has no match points (C03 4.2.b).
            self.assertEqual(
                (data.left_match_points, data.right_match_points), ('', '')
            )
