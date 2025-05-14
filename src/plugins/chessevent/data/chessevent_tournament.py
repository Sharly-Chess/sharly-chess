from logging import Logger
from typing import Any

from common.logger import get_logger
from data.pairings import PairingSystem, PairingVariation
from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem
from data.pairings.variations import StandardSwissVariation, BergerRoundRobinVariation
from data.tie_breaks import tie_breaks, TieBreak
from plugins.ffe.ffe_entity import NicoisSwissVariation
from plugins.pairing_acceleration.pairing_variations import (
    HaleySwissVariation,
    ProgressiveSwissVariation,
    HaleySoftSwissVariation,
)
from plugins.utils import PluginCoreMapper
from utils.enum import TournamentRating
from plugins.chessevent.data.chessevent_field_reader import ChessEventFieldReader
from plugins.chessevent.data.chessevent_player import ChessEventPlayer
from plugins.ffe import ffe_tie_breaks

logger: Logger = get_logger()


class ChessEventPairingSystem(PluginCoreMapper[int, PairingSystem]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[int, PairingSystem]:
        return {
            1: SwissPairingSystem(),
            2: RoundRobinPairingSystem(),
        }


class ChessEventPairingVariation(PluginCoreMapper[int, PairingVariation]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[int, PairingVariation]:
        return {
            1: StandardSwissVariation(),
            2: HaleySwissVariation(),
            3: HaleySoftSwissVariation(),
            4: ProgressiveSwissVariation(),
            5: NicoisSwissVariation(),
            6: BergerRoundRobinVariation(),
        }


class ChessEventTournament:
    """A class representing all the data of a ChessEvent tournament."""

    def __init__(
        self,
        chessevent_tournament_info: dict[str, Any],
    ):
        self.players: list[ChessEventPlayer] = []
        self.check_in_started = False
        self.error = True

        reader = ChessEventFieldReader(chessevent_tournament_info)

        try:
            self.name = reader.get('name', str)
            self.type = ChessEventPairingSystem.get_core_object(reader.get('type', int))
            self.rounds = reader.get('rounds', int)
            if self.rounds not in range(25):  # the 0-value is set by default later
                raise ValueError()
            self.pairing = ChessEventPairingVariation.get_core_object(
                reader.get('pairing', int)
            )
            self.time_control = reader.get('time_control', str)
            self.location = reader.get('location', str)
            self.arbiter = reader.get('arbiter', str)
            self.start = float(reader.get('start', int))
            self.end = float(reader.get('end', int))
            self.rating = reader.get_enum(
                'rating', TournamentRating, TournamentRating.STANDARD
            )
            self.ffe_id = reader.get('ffe_id', int, '')
            self.tie_breaks = self._load_tie_breaks(chessevent_tournament_info)
            for chessevent_player_info in chessevent_tournament_info['players']:
                chessevent_player: ChessEventPlayer = ChessEventPlayer(
                    chessevent_player_info
                )
                if chessevent_player.check_in:
                    self.check_in_started = True
                if chessevent_player.error:
                    return
                self.players.append(chessevent_player)

        except KeyError:
            logger.error(
                'Field [%s] missing in the ChessEvent response', reader.last_key
            )
            return
        except TypeError:
            logger.error(
                'Invalid type [%s] for field [%s] in the ChessEvent response',
                type(chessevent_tournament_info[reader.last_key or '']).__name__,
                reader.last_key,
            )
            return
        except ValueError:
            logger.error(
                'Invalid value [%s] for field [%s] in the ChessEvent response',
                chessevent_tournament_info[reader.last_key or ''],
                reader.last_key,
            )
            return
        self.error = False

    @staticmethod
    def _load_tie_breaks(tournament_info: dict) -> list[TieBreak]:
        tie_break_by_chessevent_id = {
            1: ffe_tie_breaks.PapiStandardBuchholzTieBreak(),
            2: ffe_tie_breaks.PapiBuchholzCutBottomTieBreak(),
            3: ffe_tie_breaks.PapiMedianBuchholzTieBreak(),
            4: tie_breaks.ProgressiveScoresTieBreak(),
            5: ffe_tie_breaks.PapiPerformanceTieBreak(),
            6: ffe_tie_breaks.PapiSumOfBuchholzTieBreak(),
            7: tie_breaks.WinsTieBreak(),
            8: ffe_tie_breaks.PapiKashdanTieBreak(),
            9: tie_breaks.KoyaTieBreak(),
            10: tie_breaks.SonnebornBergerTieBreak(),
        }
        return [
            tie_break_
            for tie_break_ in [
                tie_break_by_chessevent_id.get(
                    tournament_info[f'tie_break_{index}'], None
                )
                for index in range(1, 4)
            ]
            if tie_break_ is not None
        ]

    def __str__(self) -> str:
        return '\n'.join(
            [
                f'  - Name: {self.name}',
                f'  - Type: {self.type}',
                f'  - Number of rounds: {self.rounds}',
                f'  - Paring: {self.pairing}',
                f'  - Time control: {self.time_control}',
                f'  - Location: {self.location}',
                f'  - Arbiter: {self.arbiter}',
                f'  - Dates: {self.start} - {self.end}',
            ]
            + [
                f'  - Tie-break #{index + 1} : {tie_break_.name}'
                for index, tie_break_ in enumerate(self.tie_breaks)
            ]
            + [
                f'  - Rating: {self.rating}',
                f'  - FFE qualification: {self.ffe_id}',
            ]
        )
