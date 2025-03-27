from logging import Logger

from common.logger import get_logger
from data.util import (
    PlayerGender,
    PlayerCategory,
    PlayerRatingType,
    PlayerTitle,
)
from plugins.ffe.util import PlayerFFELicence

logger: Logger = get_logger()


class ChessEventPlayer:
    """A class representing a player information on ChessEvent."""

    @staticmethod
    def ffe_license_from_chessevent_value(value: int) -> PlayerFFELicence:
        match value:
            case 0:
                return PlayerFFELicence.NONE
            case 1:
                return PlayerFFELicence.N
            case 2:
                return PlayerFFELicence.B
            case 3:
                return PlayerFFELicence.A
            case _:
                raise ValueError(f'Unknown value: {value}')

    def __init__(
        self,
        chessevent_player_info: dict[str, bool | str | int | dict[int, float] | None],
    ):
        self.last_name: str = ''
        self.first_name: str = ''
        self.federation: str = ''
        self.fide_id: int = 0
        self.gender: PlayerGender = PlayerGender.NONE
        self.birth: float = 0.0
        self.category: PlayerCategory = PlayerCategory.NONE
        self.standard_rating: int = 0
        self.standard_rating_type: PlayerRatingType = PlayerRatingType.ESTIMATED
        self.rapid_rating: int = 0
        self.rapide_rating_type: PlayerRatingType = PlayerRatingType.ESTIMATED
        self.blitz_rating: int = 0
        self.blitz_rating_type: PlayerRatingType = PlayerRatingType.ESTIMATED
        self.title: PlayerTitle = PlayerTitle.NONE
        self.ffe_id: int = 0
        self.ffe_license: PlayerFFELicence = PlayerFFELicence.NONE
        self.ffe_license_number: str = ''
        self.ffe_league: str = ''
        self.ffe_club_id: int = 0
        self.ffe_club: str = ''
        self.email: str = ''
        self.phone: str = ''
        self.fee: float = 0.0
        self.paid: float = 0.0
        self.check_in: bool = False
        self.board: int = 0
        self.skipped_rounds: dict[int, float] = {}
        self.error = True
        key: str = ''
        try:
            self.last_name = str(chessevent_player_info[key := 'last_name'])
            self.first_name = str(chessevent_player_info[key := 'first_name'])
            self.federation = str(chessevent_player_info[key := 'federation'])
            key = 'fide_id'
            if chessevent_player_info[key]:
                self.fide_id = int(chessevent_player_info[key])
            key = 'gender'
            if chessevent_player_info[key]:
                self.gender = PlayerGender(int(chessevent_player_info[key]))
            self.birth = float(chessevent_player_info[key := 'birth'])
            self.ffe_id = int(chessevent_player_info[key := 'ffe_id'])
            self.ffe_license = self.ffe_license_from_chessevent_value(
                int(chessevent_player_info[key := 'ffe_license'])
            )
            self.ffe_license_number = str(
                chessevent_player_info[key := 'ffe_license_number']
            )
            self.ffe_league = str(chessevent_player_info[key := 'ffe_league'])
            key = 'ffe_club_id'
            if chessevent_player_info[key]:
                self.ffe_club_id = int(chessevent_player_info[key])
                if self.ffe_club_id <= 0:
                    raise ValueError
            self.ffe_club = str(chessevent_player_info[key := 'ffe_club'])
            key = 'category'
            self.category = PlayerCategory.NONE
            if chessevent_player_info[key]:
                self.category = PlayerCategory(int(chessevent_player_info[key]))
            self.standard_rating = int(chessevent_player_info[key := 'standard_rating'])
            self.standard_rating_type = PlayerRatingType(
                int(chessevent_player_info[key := 'standard_rating_type'])
            )
            self.rapid_rating = int(chessevent_player_info[key := 'rapid_rating'])
            self.rapide_rating_type = PlayerRatingType(
                int(chessevent_player_info[key := 'rapid_rating_type'])
            )
            self.blitz_rating = int(chessevent_player_info[key := 'blitz_rating'])
            self.blitz_rating_type = PlayerRatingType(
                int(chessevent_player_info[key := 'blitz_rating_type'])
            )
            self.title = PlayerTitle(int(chessevent_player_info[key := 'title']))
            self.email = str(chessevent_player_info[key := 'email'])
            self.phone = str(chessevent_player_info[key := 'phone'])
            self.fee = float(chessevent_player_info[key := 'fee'])
            self.paid = float(chessevent_player_info[key := 'paid'])
            self.check_in = bool(chessevent_player_info[key := 'check_in'])
            self.board = int(chessevent_player_info[key := 'board'])
            self.skipped_rounds: dict[int, float] = {}
            key = 'skipped_rounds'
            for round_ in chessevent_player_info[key]:
                if int(round_) in range(1, 25) and chessevent_player_info[key][
                    round_
                ] in [0.0, 0.5]:
                    self.skipped_rounds[int(round_)] = chessevent_player_info[key][
                        round_
                    ]
                else:
                    raise ValueError
        except KeyError:
            logger.error(
                'Field [%s] not found for player [%s %s]',
                key,
                self.last_name,
                self.first_name,
            )
            return
        except (TypeError, ValueError):
            logger.error(
                'Invalid value [%s] for field [%s] for player [%s %s]',
                chessevent_player_info[key],
                key,
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
