from dataclasses import dataclass, field
import unittest

from src.data.pairing import Pairing
from src.data.util import Result, BoardColor, PlayerGender, PlayerTitle, TournamentRating
from src.data.player import TournamentPlayer
from src.tie_breaks import swiss


@dataclass
class Tournament:
    players_by_id: dict[int, TournamentPlayer] = field(default_factory=dict)


class SwissTieBreaks(unittest.TestCase):
    def setUp(self):
        self.tournament = Tournament(
            {
               2: TournamentPlayer(
                   2, 'Bruno', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 2100,
                   pairings={
                       1: Pairing(BoardColor.BLACK, 10, Result.GAIN),
                       2: Pairing(BoardColor.WHITE, 7, Result.GAIN),
                       3: Pairing(BoardColor.BLACK, 1, Result.DRAW),
                       4: Pairing(BoardColor.WHITE, 16, Result.GAIN),
                       5: Pairing(BoardColor.BLACK, 3, Result.DRAW)
                   }),
                1: TournamentPlayer(
                    1, 'Alyx', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 2200,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 9, Result.GAIN),
                        2: Pairing(BoardColor.BLACK, 13, Result.DRAW),
                        3: Pairing(BoardColor.WHITE, 2, Result.DRAW),
                        4: Pairing(BoardColor.BLACK, 15, Result.GAIN),
                        5: Pairing(BoardColor.WHITE, 4, Result.DRAW)
                    }
                ),
                3: TournamentPlayer(
                    3, 'Charline', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 2100,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 11, Result.DRAW),
                        2: Pairing(BoardColor.BLACK, 6, Result.GAIN),
                        3: Pairing(BoardColor.WHITE, 8, Result.GAIN),
                        4: Pairing(BoardColor.BLACK, 4, Result.DRAW),
                        5: Pairing(BoardColor.WHITE, 2, Result.DRAW),
                    }
                ),
                4: TournamentPlayer(
                    4, 'David', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 2050,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 12, Result.GAIN),
                        2: Pairing(None, None, Result.HALF_POINT_BYE),
                        3: Pairing(BoardColor.WHITE, 8, Result.GAIN),
                        4: Pairing(BoardColor.WHITE, 3, Result.DRAW),
                        5: Pairing(BoardColor.BLACK, 2, Result.DRAW),
                    }
                ),
                16: TournamentPlayer(
                    16, 'Stephan', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1450,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 8, Result.DRAW),
                        2: Pairing(BoardColor.BLACK, 11, Result.GAIN),
                        3: Pairing(BoardColor.WHITE, 7, Result.GAIN),
                        4: Pairing(BoardColor.BLACK, 2, Result.LOSS),
                        5: Pairing(BoardColor.WHITE, 15, Result.GAIN),
                    }
                ),
                6: TournamentPlayer(
                    6, 'Franck', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1950,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 14, Result.LOSS),
                        2: Pairing(BoardColor.WHITE, 3, Result.LOSS),
                        3: Pairing(None, None, Result.PAIRING_ALLOCATED_BYE),
                        4: Pairing(BoardColor.WHITE, 10, Result.GAIN),
                        5: Pairing(BoardColor.BLACK, 8, Result.GAIN),
                    }
                ),
                5: TournamentPlayer(
                    5, 'Helene', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 2000,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 13, Result.LOSS),
                        2: Pairing(BoardColor.BLACK, 15, Result.LOSS),
                        3: Pairing(BoardColor.WHITE, 11, Result.GAIN),
                        4: Pairing(BoardColor.BLACK, 7, Result.DRAW),
                        5: Pairing(BoardColor.WHITE, 10, Result.GAIN),
                    }
                ),
                8: TournamentPlayer(
                    8, 'Irina', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1850,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 16, Result.DRAW),
                        2: Pairing(BoardColor.WHITE, 14, Result.GAIN),
                        3: Pairing(BoardColor.BLACK, 3, Result.LOSS),
                        4: Pairing(BoardColor.WHITE, 13, Result.GAIN),
                        5: Pairing(BoardColor.WHITE, 6, Result.LOSS),
                    }
                ),
                11: TournamentPlayer(
                    11, 'Maria', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1700,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 3, Result.DRAW),
                        2: Pairing(BoardColor.WHITE, 16, Result.LOSS),
                        3: Pairing(BoardColor.BLACK, 5, Result.LOSS),
                        4: Pairing(None, 9, Result.FORFEIT_GAIN),
                        5: Pairing(BoardColor.WHITE, 7, Result.GAIN)
                    }
                ),
                12: TournamentPlayer(
                    12, 'Nick', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1650,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 4, Result.LOSS),
                        2: Pairing(None, None, Result.PAIRING_ALLOCATED_BYE),
                        3: Pairing(None, 14, Result.FORFEIT_GAIN),
                        4: Pairing(None, None, Result.ZERO_POINT_BYE),
                        5: Pairing(None, None, Result.ZERO_POINT_BYE)
                    }
                ),
                14: TournamentPlayer(
                    14, 'Paul', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1550,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 6, Result.GAIN),
                        2: Pairing(BoardColor.BLACK, 8, Result.LOSS),
                        3: Pairing(None, 12, Result.FORFEIT_LOSS),
                        4: Pairing(None, None, Result.ZERO_POINT_BYE),
                        5: Pairing(BoardColor.BLACK, 13, Result.GAIN)
                    }
                ),
                15: TournamentPlayer(
                    15, 'Reine', '', None, PlayerGender.NONE, 0, 'FIDE', PlayerTitle.NONE, 1500,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 7, Result.LOSS),
                        2: Pairing(BoardColor.WHITE, 5, Result.GAIN),
                        3: Pairing(BoardColor.BLACK, 10, Result.GAIN),
                        4: Pairing(BoardColor.WHITE, 1, Result.LOSS),
                        5: Pairing(BoardColor.BLACK, 16, Result.LOSS)
                    }
                ),
                7: TournamentPlayer(
                    7, 'Genevieve', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1900,
                    pairings={
                        1: Pairing(BoardColor.WHITE, 15, Result.GAIN),
                        2: Pairing(BoardColor.BLACK, 2, Result.LOSS),
                        3: Pairing(BoardColor.BLACK, 16, Result.LOSS),
                        4: Pairing(BoardColor.WHITE, 5, Result.DRAW),
                        5: Pairing(BoardColor.BLACK, 11, Result.LOSS)
                    }
                ),
                9: TournamentPlayer(
                    9, 'Jessica', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1800,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 1, Result.LOSS),
                        2: Pairing(BoardColor.WHITE, 10, Result.LOSS),
                        3: Pairing(None, None, Result.HALF_POINT_BYE),
                        4: Pairing(None, 11, Result.FORFEIT_LOSS),
                        5: Pairing(None, None, Result.PAIRING_ALLOCATED_BYE),
                    }
                ),
                13: TournamentPlayer(
                    13, 'Opal', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1600,
                    pairings={
                        1: Pairing(BoardColor.BLACK, 5, Result.GAIN),
                        2: Pairing(BoardColor.WHITE, 1, Result.DRAW),
                        3: Pairing(BoardColor.BLACK, 4, Result.LOSS),
                        4: Pairing(BoardColor.BLACK, 8, Result.LOSS),
                        5: Pairing(BoardColor.WHITE, 14, Result.LOSS)
                    }
                ),
                10: TournamentPlayer(
                    10, 'Lais', '', None, PlayerGender.NONE, 0, 'FID', PlayerTitle.NONE, 1750,
                    pairings= {
                        1: Pairing(BoardColor.WHITE, 2, Result.LOSS),
                        2: Pairing(BoardColor.BLACK, 9, Result.GAIN),
                        3: Pairing(BoardColor.WHITE, 15, Result.LOSS),
                        4: Pairing(BoardColor.BLACK, 6, Result.LOSS),
                        5: Pairing(BoardColor.BLACK, 5, Result.LOSS)
                    }
                )
            }
        )

    def test_points(self):
        assert {
            player.id: player.total_points()
            for player in self.tournament.players_by_id.values()
        } == {
            2: 4, 1: 3.5, 3: 3.5, 4: 3.5, 16: 3.5, 6: 3, 5: 2.5,
            8: 2.5, 11: 2.5, 12: 2, 14: 2, 15: 2, 7: 1.5, 9: 1.5,
            13: 1.5, 10: 1
        }
    
    def test_win(self):
        assert {
            player.id: swiss.wins(player, self.tournament, max_round=6)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 3, 16: 3, 1: 2, 3: 2, 4: 2, 6: 3, 5: 2, 8: 2, 11: 2,
            12: 2, 14: 2, 15: 2, 7: 1, 9: 1, 13: 1, 10: 1
        }
    
    def test_won(self):
        assert {
            player.id: swiss.games_won(player, self.tournament, max_round=6)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 3, 16: 3, 1: 2, 3: 2, 4: 2, 6: 2, 5: 2, 8: 2, 11: 1,
            14: 2, 15: 2, 12: 0, 7: 1, 13: 1, 9: 0, 10: 1
        }
    
    def test_played_with_black(self):
        assert {
            player.id: swiss.games_played_with_black(player, self.tournament, max_round=6)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 3, 1: 2, 3: 2, 4: 2, 16: 2, 6: 2, 5: 2, 8: 2, 11: 2,
            15: 3, 14: 2, 12: 0, 7: 3, 13: 3, 9: 1, 10: 3
        }
    
    def test_won_with_black(self):
        assert {
            player.id: swiss.games_won_with_black(player, self.tournament, max_round=6)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 1, 1: 1, 3: 1, 4: 1, 16: 1, 6: 1, 5: 0, 8: 0, 11: 0,
            12: 0, 14: 1, 15: 1, 7: 0, 9: 0, 13: 1, 10: 1
        }
    
    def test_games_elected_to_play(self):
        assert {
            player.id: swiss.rounds_elected_to_play(player, self.tournament, max_round=6)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 5, 1: 5, 3: 5, 16: 5, 4: 4, 6: 5, 5: 5, 8: 5, 11: 5,
            15: 5, 12: 3, 14: 3, 7: 5, 13: 5, 9: 3, 10: 5
        }
    
    def test_progressive_scores(self):
        assert {
            player.id: swiss.progressive_scores(player, self.tournament, max_round=6)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 13, 4: 11.5, 1: 11, 3: 11, 16: 10.5, 6: 6, 8: 8.5, 11: 5.5,
            5: 5, 12: 7, 15: 7, 14: 6, 13: 7, 7: 6, 9: 2.5, 10: 4
        }
    
    def test_progressive_cut1(self):
        assert {
            player.id: swiss.progressive_scores(player, self.tournament, max_round=6, cut=1)
            for player in self.tournament.players_by_id.values()
        } == {
            2: 12, 3: 10.5, 4: 10.5, 1: 10, 16: 10, 6: 6, 8: 8, 5: 5, 11: 5,
            12: 7, 15: 7, 14: 5, 13: 6, 7: 5, 9: 2.5, 10: 4
        }