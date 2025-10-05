import json
import time
import zoneinfo
from datetime import datetime, timedelta

from requests import JSONDecodeError
from text_unidecode import unidecode

from common.exception import (
    OptionError,
    DictReaderException,
    SharlyChessException,
    ImporterError,
)
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.input_output import TournamentImporter
from data.input_output.dict_reader import dict_to_dataclass
from data.input_output.tournament_importer_options import TournamentImporterOption
from data.player import PlayerRating
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredTournamentPlayer,
    StoredPairing,
)
from plugins import ffe
from plugins.chessevent import PLUGIN_NAME, TMP_DIR
from plugins.chessevent.chessevent_session import (
    ChessEventSession,
    ChessEventTournamentRequestData,
)
from plugins.chessevent.chessevent_status import (
    SuccessChessEventStatus,
    ChessEventStatus,
    UnexpectedErrorChessEventStatus,
)
from plugins.chessevent.exceptions import ChessEventStatusError
from plugins.chessevent.tournament_importer.data import (
    ChessEventTournament,
    ChessEventPlayer,
)
from plugins.chessevent.tournament_importer import options
from plugins.chessevent.tournament_importer.mappers import (
    ChessEventPairingVariation,
    ChessEventTieBreak,
    ChessEventFFELicence,
    ChessEventTitle,
    ChessEventRatingType,
)
from plugins.chessevent.utils import get_data
from plugins.ffe.ffe import FfePlugin
from plugins.ffe.utils import FfePlayerPluginData
from utils.enum import TournamentRating, Result

paris_tz = zoneinfo.ZoneInfo('Europe/Paris')
epoch = datetime(1970, 1, 1, tzinfo=zoneinfo.ZoneInfo('UTC'))


class ChessEventTournamentImporter(TournamentImporter):
    @staticmethod
    def static_id() -> str:
        return PLUGIN_NAME

    @staticmethod
    def static_name() -> str:
        return _('ChessEvent')

    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [
            options.ChessEventEventOption,
            options.ChessEventUserOption,
            options.ChessEventPasswordOption,
            options.ChessEventTournamentOption,
        ]

    @property
    def modal_title(self) -> str:
        return _('Import from ChessEvent')

    @property
    def doc_url(self) -> str | None:
        return 'chessevent'

    def _on_status_error_raised(
        self, error: ChessEventStatusError, tournament: Tournament | None
    ):
        """Executed when an ChessEventStatusError is raised."""

    def _on_standard_error_raised(
        self, error: SharlyChessException, tournament: Tournament | None
    ):
        """Executed when a SharlyChessException is raised."""

    def _resolve_request_data(self, event: Event) -> ChessEventTournamentRequestData:
        event_id, user_id, password, tournament_name = self.get_option_values()
        if not user_id:
            user_id = get_data(event.plugin_data, 'chessevent_user_id')
        if not password:
            password = get_data(event.plugin_data, 'chessevent_password')
        if not event_id:
            event_id = get_data(event.plugin_data, 'chessevent_event_id')
        return ChessEventTournamentRequestData(
            event_id=event_id,
            user_id=user_id,
            password=password,
            tournament_name=tournament_name,
        )

    @staticmethod
    def _get_chessevent_tournament(
        request_data: ChessEventTournamentRequestData,
    ) -> ChessEventTournament:
        chessevent_data = ChessEventSession().read_tournament_data(request_data)
        try:
            chessevent_tournament = dict_to_dataclass(
                ChessEventTournament, json.loads(chessevent_data)
            )
        except (UnicodeDecodeError, JSONDecodeError, DictReaderException) as error:
            error_output = TMP_DIR / 'invalid-chessevent-data.json'
            with open(error_output, 'w', encoding='utf-8') as f:
                f.write(chessevent_data)
            raise SharlyChessException(
                'Error while reading ChessEvent data '
                f'(saved to file [{error_output}]): {error}'
            )
        return chessevent_tournament

    def validate_options(
        self,
        event: Event | None = None,
    ):
        assert event is not None
        (
            user_option,
            password_option,
            event_option,
            tournament_option,
        ) = self.options
        if not user_option.value and not get_data(
            event.plugin_data, 'chessevent_user_id'
        ):
            raise OptionError(_('A value is expected.'), user_option)
        if not password_option.value and not get_data(
            event.plugin_data, 'chessevent_password'
        ):
            raise OptionError(_('A value is expected.'), password_option)
        if not event_option.value and not get_data(
            event.plugin_data, 'chessevent_event_id'
        ):
            raise OptionError(_('A value is expected.'), event_option)
        if not tournament_option.value:
            raise OptionError(_('A value is expected.'), tournament_option)

    def load_tournament(
        self,
        event: Event,
        tournament: Tournament | None = None,
    ) -> Tournament:
        try:
            return super().load_tournament(event, tournament)
        except ChessEventStatusError as error:
            self._on_status_error_raised(error, tournament)
            raise ImporterError(str(error))
        except SharlyChessException as error:
            self._on_standard_error_raised(error, tournament)
            raise error

    def load_stored_tournament(
        self, event: Event, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        request_data = self._resolve_request_data(event)
        tournament = self._get_chessevent_tournament(request_data)
        stored_tournament = self._read_chessevent_tournament(
            tournament, stored_tournament
        )
        stored_tournament.plugin_data[PLUGIN_NAME] = {
            'chessevent_event_id': request_data.event_id,
            'chessevent_user_id': request_data.user_id,
            'chessevent_password': request_data.password,
            'chessevent_tournament_name': request_data.tournament_name,
            'chessevent_last_sync': time.time(),
            'chessevent_status': SuccessChessEventStatus().id,
        }
        stored_players = [
            self._read_chessevent_player(player, player_id)
            for player_id, player in enumerate(tournament.players)
        ]
        return stored_tournament, stored_players

    @staticmethod
    def _read_chessevent_tournament(
        tournament: ChessEventTournament,
        stored_tournament: StoredTournament | None = None,
    ) -> StoredTournament:
        if not stored_tournament:
            stored_tournament = StoredTournament(id=None, name=tournament.name)
        stored_tournament.rounds = tournament.rounds
        try:
            stored_tournament.pairing = ChessEventPairingVariation.get_core_object(
                tournament.pairing
            ).id
        except KeyError:
            raise SharlyChessException(
                f'Unknown value [{tournament.pairing}] for field [pairing].'
            )
        stored_tournament.location = tournament.location
        stored_tournament.rating = tournament.rating
        stored_tournament.tie_breaks = []
        for tie_break in (
            tournament.tie_break_1,
            tournament.tie_break_2,
            tournament.tie_break_3,
        ):
            if not tie_break:
                continue
            try:
                stored_tournament.tie_breaks.append(
                    ChessEventTieBreak.get_core_object(tie_break).to_dict()
                )
            except KeyError:
                raise SharlyChessException(
                    f'Unknown value for tie break [{tie_break}].'
                )

        if ffe.PLUGIN_NAME not in stored_tournament.plugin_data:
            stored_tournament.plugin_data[ffe.PLUGIN_NAME] = {}
        if not stored_tournament.plugin_data[ffe.PLUGIN_NAME].get('ffe_id', None):
            stored_tournament.plugin_data[ffe.PLUGIN_NAME]['ffe_id'] = tournament.ffe_id
        # Check-in not yet opened if no player has checked in,
        # opened if some players have, but closed if all players have
        stored_tournament.check_in_open = any(
            player.check_in for player in tournament.players
        ) and not all(player.check_in for player in tournament.players)
        return stored_tournament

    @classmethod
    def _read_chessevent_player(
        cls, player: ChessEventPlayer, player_id: int
    ) -> StoredPlayer:
        def unknown_exception(field: str) -> SharlyChessException:
            return SharlyChessException(
                f'Player [{player.last_name} {player.first_name}]: '
                f'Unknown value [{getattr(player, field)}] for field [{field}].'
            )

        try:
            title = ChessEventTitle.get_core_object(player.title)
        except KeyError:
            raise unknown_exception('title')
        if player.federation not in SharlyChessConfig.federations:
            raise unknown_exception('federation')
        try:
            standard_rating_type = ChessEventRatingType.get_core_object(
                player.standard_rating_type
            )
        except KeyError:
            raise unknown_exception('standard_rating_type')
        try:
            rapid_rating_type = ChessEventRatingType.get_core_object(
                player.rapid_rating_type
            )
        except KeyError:
            raise unknown_exception('rapid_rating_type')
        try:
            blitz_rating_type = ChessEventRatingType.get_core_object(
                player.blitz_rating_type
            )
        except KeyError:
            raise unknown_exception('blitz_rating_type')

        ratings = {
            TournamentRating.STANDARD.value: PlayerRating(
                value=player.standard_rating,
                type=standard_rating_type,
            ).stored_value,
            TournamentRating.RAPID.value: PlayerRating(
                value=player.rapid_rating,
                type=rapid_rating_type,
            ).stored_value,
            TournamentRating.BLITZ.value: PlayerRating(
                value=player.blitz_rating,
                type=blitz_rating_type,
            ).stored_value,
        }
        try:
            ffe_licence = ChessEventFFELicence.get_core_object(player.ffe_license)
        except KeyError:
            raise unknown_exception('ffe_license')
        if player.ffe_league and player.ffe_league not in FfePlugin.FFE_LEAGUES:
            raise unknown_exception('ffe_league')
        ffe_plugin_data = FfePlayerPluginData(
            player.ffe_id,
            ffe_licence,
            player.ffe_license_number or None,
            player.ffe_league or None,
        )

        return StoredPlayer(
            id=player_id,
            last_name=unidecode(player.last_name).upper(),
            first_name=unidecode(player.first_name).title(),
            date_of_birth=(epoch + timedelta(seconds=float(player.birth))).astimezone(
                paris_tz
            ),
            gender=player.gender.value,
            mail=player.email,
            phone=player.phone,
            comment=None,
            owed=float(player.fee),
            paid=float(player.paid),
            title=title,
            ratings=ratings,
            fide_id=player.fide_id or None,
            federation=player.federation,
            club=player.ffe_club,
            fixed=player.board or None,
            check_in=bool(player.check_in),
            plugin_data={ffe.PLUGIN_NAME: ffe_plugin_data.to_stored_value()},
            stored_tournament_player=StoredTournamentPlayer(
                player_id=player_id,
                stored_pairings=cls._get_pairings(player, player_id),
            ),
        )

    @staticmethod
    def _get_pairings(
        player: ChessEventPlayer,
        player_id: int,
    ) -> list[StoredPairing]:
        stored_pairings: list[StoredPairing] = []
        for round_, result_value in player.skipped_rounds.items():
            if result_value == 0:
                result = Result.ZERO_POINT_BYE
            elif result_value == 0.5:
                result = Result.HALF_POINT_BYE
            else:
                raise ValueError
            stored_pairings.append(
                StoredPairing(
                    tournament_id=0,
                    player_id=player_id,
                    round_=round_,
                    result=result,
                    board_id=None,
                )
            )
        return stored_pairings


class ChessEventSyncTournamentImporter(ChessEventTournamentImporter):
    @staticmethod
    def _save_tournament_chessevent_status(
        status: ChessEventStatus, tournament: Tournament | None
    ):
        if not tournament:
            return
        with EventDatabase(tournament.event.uniq_id, True) as database:
            database.execute(
                'UPDATE `tournament` SET `chessevent_status` = ? WHERE `id` = ?',
                (status.id, tournament.id),
            )

    def _on_status_error_raised(
        self, error: ChessEventStatusError, tournament: Tournament | None
    ):
        self._save_tournament_chessevent_status(error.status, tournament)

    def _on_standard_error_raised(
        self, error: SharlyChessException, tournament: Tournament | None
    ):
        self._save_tournament_chessevent_status(
            UnexpectedErrorChessEventStatus(), tournament
        )
