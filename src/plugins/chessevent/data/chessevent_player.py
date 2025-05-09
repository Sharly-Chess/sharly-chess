from logging import Logger
from typing import Any

from common.logger import get_logger
from plugins.utils import PluginCoreMapper
from utils.enum import (
    PlayerGender,
    PlayerCategory,
    PlayerRatingType,
    PlayerTitle,
)
from plugins.chessevent.data.chessevent_field_reader import ChessEventFieldReader
from plugins.ffe.util import PlayerFFELicence

logger: Logger = get_logger()


class ChessEventFFELicence(PluginCoreMapper[int, PlayerFFELicence]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[int, PlayerFFELicence]:
        return {
            0: PlayerFFELicence.NONE,
            1: PlayerFFELicence.N,
            2: PlayerFFELicence.B,
            3: PlayerFFELicence.A,
        }


class ChessEventRatingType(PluginCoreMapper[int, PlayerRatingType]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[int, PlayerRatingType]:
        return {
            1: PlayerRatingType.NATIONAL,
            2: PlayerRatingType.ESTIMATED,
            3: PlayerRatingType.FIDE,
        }


class ChessEventTitle(PluginCoreMapper[int, PlayerTitle]):
    @staticmethod
    def _core_object_by_plugin_value() -> dict[int, PlayerTitle]:
        return {
            0: PlayerTitle.NONE,
            1: PlayerTitle.WOMAN_FIDE_MASTER,
            2: PlayerTitle.FIDE_MASTER,
            3: PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            4: PlayerTitle.INTERNATIONAL_MASTER,
            5: PlayerTitle.WOMAN_GRANDMASTER,
            6: PlayerTitle.GRANDMASTER,
        }


class ChessEventPlayer:
    """A class representing a player information on ChessEvent."""

    def __init__(
        self,
        chessevent_player_info: dict[str, Any],
    ):
        self.error = True
        reader = ChessEventFieldReader(chessevent_player_info)

        try:
            self.last_name = reader.get('last_name', str)
            self.first_name = reader.get('first_name', str)
            self.federation = reader.get('federation', str)
            self.fide_id = reader.get('fide_id', int, 0)
            self.gender = reader.get_enum('gender', PlayerGender, PlayerGender.NONE)
            self.birth = float(reader.get('birth', int))

            self.ffe_id = reader.get('ffe_id', int)
            self.ffe_license = ChessEventFFELicence.get_core_object(
                reader.get('ffe_license', int)
            )
            self.ffe_license_number = reader.get('ffe_license_number', str)
            self.ffe_league = reader.get('ffe_league', str)
            self.ffe_club_id = reader.get('ffe_club_id', int, 0)
            self.ffe_club = reader.get('ffe_club', str, '')

            self.category = reader.get_enum(
                'category', PlayerCategory, PlayerCategory.NONE
            )
            self.standard_rating = reader.get('standard_rating', int)
            self.standard_rating_type = ChessEventRatingType.get_core_object(
                reader.get('standard_rating_type', int)
            )
            self.rapid_rating = reader.get('rapid_rating', int)
            self.rapide_rating_type = ChessEventRatingType.get_core_object(
                reader.get('rapid_rating_type', int)
            )
            self.blitz_rating = reader.get('blitz_rating', int)
            self.blitz_rating_type = ChessEventRatingType.get_core_object(
                reader.get('blitz_rating_type', int)
            )
            self.title = ChessEventTitle.get_core_object(reader.get('title', int))

            self.email = reader.get('email', str)
            self.phone = reader.get('phone', str)
            self.fee = float(reader.get('fee', (int, float)))
            self.paid = float(reader.get('paid', (int, float)))
            self.check_in = bool(reader.get('check_in', (bool, int)))
            self.board = reader.get('board', int)

            self.skipped_rounds: dict[int, float] = {}
            skipped = reader.get('skipped_rounds', dict, {})
            for round_, val in skipped.items():
                if int(round_) in range(1, 25) and val in [0.0, 0.5]:
                    self.skipped_rounds[int(round_)] = val
                else:
                    raise ValueError

        except KeyError:
            logger.error(
                'Field [%s] not found for player [%s %s]',
                reader.last_key,
                self.last_name,
                self.first_name,
            )
            return
        except (TypeError, ValueError):
            logger.error(
                'Invalid value [%s] for field [%s] for player [%s %s]',
                chessevent_player_info[reader.last_key or ''],
                reader.last_key,
                self.last_name,
                self.first_name,
            )
            return

        self.error = False

    def __str__(self) -> str:
        return '\n'.join(
            [
                f'  - Name: {self.last_name} {self.first_name}',
                f'  - Title / FFE ID / FIDE ID: {self.title} / {self.ffe_id} / {self.fide_id}',
                f'  - FFE Licence / Licence number / Category / Gender: '
                f'{self.ffe_license} / {self.ffe_license_number} / {self.category} / {self.gender}',
                f'  - Birth date: {self.birth}',
                f'  - Standard rating / rapid / blitz: {self.standard_rating}{self.standard_rating_type} '
                f'/ {self.rapid_rating}{self.rapide_rating_type} / {self.blitz_rating}{self.blitz_rating_type}',
                f'  - Federation / League / Club: '
                f'{self.federation} / {self.ffe_league} / {self.ffe_club_id} {self.ffe_club}',
                f'  - Mail / Phone: {self.email} / {self.phone}',
                f'  - Owed / Paid / Check-in: {self.fee} / {self.paid} / {self.check_in}',
                f'  - Fixed board / Rounds : {self.board} / {self.skipped_rounds}',
            ]
        )
