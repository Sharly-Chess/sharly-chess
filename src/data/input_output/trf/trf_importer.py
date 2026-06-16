import re
from collections import defaultdict
from datetime import datetime, date

from common.exception import ImporterError
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.input_output.tournament_importer_options import (
    TournamentImporterOption,
    FileOption,
    TournamentRatingOption,
)
from data.input_output.tournament_importers import FileTournamentImporter
from data.input_output.trf.trf_data import TrfPlayer, TrfGame, TrfTournament
from data.input_output.trf.trf_mappers import (
    TrfPlayerGender,
    TrfColor,
    TrfResult,
    TrfPlayerTitle,
    TrfEncodedType,
)
from data.input_output.trf.trf_serializer import TrfSerializer
from data.pairings.settings import ColorSeedSetting
from data.tie_breaks import TieBreak, TieBreakManager
from database.sqlite.event.event_store import (
    StoredTournament,
    StoredPlayer,
    StoredBoard,
    StoredTournamentPlayer,
    StoredPairing,
)
from plugins.manager import plugin_manager
from utils.enum import TournamentRating, Result, BoardColor, PlayerRatingType
from utils.time_control import parse_time_control_trf25
from utils.types import PlayerRating

TRF_DATE_FORMAT = '%Y/%m/%d'


class TrfTournamentImporter(FileTournamentImporter):
    @staticmethod
    def static_id() -> str:
        return 'TRF'

    @staticmethod
    def static_name() -> str:
        return _('TRF file')

    @staticmethod
    def available_options() -> list[type[TournamentImporterOption]]:
        return [
            FileOption,
            TournamentRatingOption,
        ]

    @property
    def modal_title(self) -> str:
        return _('Import TRF file')

    @property
    def accepted_file_suffixes(self) -> list[str]:
        return ['.trf', '.trfx']

    @property
    def on_file_selected_post_route_name(self) -> str | None:
        return 'tournament-import-check-trf'

    def load_stored_tournament(
        self, event: Event, stored_tournament: StoredTournament | None = None
    ) -> tuple[StoredTournament, list[StoredPlayer]]:
        (file_path, tournament_rating) = self.get_option_values()
        with open(file_path, 'r', encoding='utf-8') as file:
            trf_tournament = TrfSerializer.load(file)
        stored_tournament = self._read_trf_tournament(
            event, trf_tournament, stored_tournament
        )
        stored_tournament.rating = tournament_rating

        next_board_id = 1
        board_id_by_player_id_by_round: dict[int, dict[int, int]] = defaultdict(dict)
        stored_boards_by_round: dict[int, list[StoredBoard]] = defaultdict(list)
        stored_players: list[StoredPlayer] = []
        for trf_player in trf_tournament.players:
            player_id = trf_player.id
            try:
                self._validate_trf_player(trf_player)
            except ImporterError as exception:
                raise ImporterError(
                    _('Player [{player_id}]: {error}').format(
                        player_id=player_id,
                        error=exception,
                    )
                )
            stored_player = self._read_trf_player(
                trf_player, TournamentRating(tournament_rating), event
            )
            stored_tournament_player = StoredTournamentPlayer(
                player_id=player_id,
                pairing_number=trf_player.id,
            )
            for trf_game in trf_player.games:
                if trf_game.round > stored_tournament.rounds:
                    stored_tournament.rounds = trf_game.round
                round_nb = trf_game.round
                try:
                    self._validate_trf_game(trf_game)
                except ImporterError as exception:
                    raise ImporterError(
                        _('Player [{player_id}] - round {round}: ').format(
                            player_id=player_id,
                            round=round_nb,
                        )
                        + str(exception)
                    )
                stored_pairing, stored_board = self._read_trf_game(trf_game, player_id)
                if stored_board:
                    if player_id in board_id_by_player_id_by_round[round_nb]:
                        board_id = board_id_by_player_id_by_round[round_nb][player_id]
                    else:
                        board_id = next_board_id
                        next_board_id += 1
                        stored_board.id = board_id
                        stored_boards_by_round[round_nb].append(stored_board)
                        if trf_game.opponent_id:
                            board_id_by_player_id_by_round[round_nb][
                                trf_game.opponent_id
                            ] = board_id
                    stored_pairing.board_id = board_id
                stored_tournament_player.stored_pairings.append(stored_pairing)
            stored_players.append(stored_player)
            stored_tournament.stored_tournament_players.append(stored_tournament_player)
        stored_tournament.stored_boards_by_round = stored_boards_by_round
        if stored_boards_by_round:
            stored_tournament.rounds = max(tuple(stored_boards_by_round))
        return stored_tournament, stored_players

    def get_not_importable_features(self, event: Event) -> list[str]:
        file_path = self.get_option_values()[0]
        with open(file_path, 'r', encoding='utf-8') as file:
            tournament = TrfSerializer.load(file)
        features: list[str] = []
        if tournament.teams or tournament.deprecated_teams:
            features.append(_('Teams'))
        if tournament.individuals_point_system:
            features.append(_('162 Point system'))
        sr_method = tournament.starting_rank_method
        if sr_method and sr_method not in ['FIDON', 'NIDOF']:
            features.append(
                _('172 Starting rank method {method}').format(method=sr_method)
            )
        encoded_type = tournament.encoded_type
        if encoded_type and not TrfEncodedType.get_supported_pairing_variation(
            encoded_type
        ):
            default = TrfEncodedType.get_not_supported_default_type(encoded_type)
            features.append(
                _('192 Encoded type {type} (default: {default})').format(
                    type=encoded_type,
                    default=default,
                )
            )
        tie_breaks = tournament.standings_tie_breaks
        standard_tie_breaks = ['PTS'] + tournament.tie_breaks
        if tie_breaks and tournament.tie_breaks and tie_breaks != standard_tie_breaks:
            features.append(_('202 and 212 tie-breaks (212 used)'))
            tie_breaks = standard_tie_breaks
        if not tie_breaks:
            tie_breaks = standard_tie_breaks
        if tie_breaks:
            if tie_breaks[0] != 'PTS':
                features.append(_('212 Tie-breaks with PTS not used first'))
        if tie_breaks:
            __, unknown = self._read_tie_breaks(tie_breaks, event)
            if unknown:
                features.append(
                    _('{code} Unknown tie-breaks: {tie_breaks}').format(
                        code=212 if tournament.standings_tie_breaks else 202,
                        tie_breaks=', '.join(unknown),
                    )
                )

        if tournament.accelerated_rounds:
            features.append(_('250 Accelerated rounds'))
        if tournament.prohibited_pairings:
            features.append(_('260 Prohibited pairings'))
        if tournament.abnormal_points_assignments:
            features.append(_('299 Abnormal assignment points'))
        if any(
            federation != event.federation
            for federation in tournament.national_players_by_federation
        ):
            features.append(
                _(
                    'National rating support for other federations '
                    'than the event federation {federation}'
                ).format(federation=event.federation)
            )
        if tournament.xx_fields:
            features.append(_('XX fields'))
        if tournament.bb_fields:
            features.append(_('BB fields'))

        return features

    @classmethod
    def _read_tie_breaks(
        cls, tie_break_acronyms: list[str], event: Event
    ) -> tuple[list[TieBreak], list[str]]:
        tie_breaks: list[TieBreak] = []
        unknown_acronyms: list[str] = []
        manager = TieBreakManager(event)
        for acronym in tie_break_acronyms:
            if acronym == 'PTS':
                continue
            is_fide = not acronym.startswith('OTHER_')
            tie_break = manager.tie_break_from_trf_acronym(acronym)
            if tie_break and is_fide == tie_break.is_fide:
                tie_breaks.append(tie_break)
            else:
                unknown_acronyms.append(acronym)
        return tie_breaks, unknown_acronyms

    @staticmethod
    def _validate_trf_player(trf_player: TrfPlayer):
        try:
            TrfPlayerGender.get_core_object(trf_player.gender)
        except KeyError:
            raise ImporterError(
                _('Unknown gender [{gender}].').format(gender=trf_player.gender)
            )
        try:
            TrfPlayerTitle.get_core_object(trf_player.title)
        except KeyError:
            raise ImporterError(
                _('Unknown title [{title}].').format(title=trf_player.title)
            )
        if (
            trf_player.federation
            and trf_player.federation.upper() not in SharlyChessConfig().federations
        ):
            raise ImporterError(
                _('Unknown federation [{federation}].').format(
                    federation=trf_player.federation.upper()
                )
            )
        if trf_player.birth_date:
            try:
                datetime.strptime(trf_player.birth_date, '%Y/%m/%d')
            except ValueError:
                if not re.match(r'^\d{4}/00/00$', trf_player.birth_date):
                    raise ImporterError(
                        _('Invalid date format [{date}] (expected: {format}).').format(
                            date=trf_player.birth_date, format=_('YYYY/MM/DD')
                        )
                    )

    @staticmethod
    def _validate_trf_game(trf_game: TrfGame):
        try:
            color = TrfColor.get_core_object(trf_game.color)
        except KeyError:
            raise ImporterError(
                _('Unknown color [{color}].').format(color=trf_game.color)
            )
        try:
            result = TrfResult.get_core_object(
                trf_game.result, has_opponent=bool(trf_game.opponent_id)
            )
        except KeyError:
            raise ImporterError(
                _('Unknown result [{result}].').format(result=trf_game.result)
            )

        if trf_game.opponent_id and result.is_bye:
            raise ImporterError(
                _("Result [{result}] can't be used with an opponent.").format(
                    result=trf_game.result
                )
            )
        if not trf_game.opponent_id and not (
            result.is_bye or result == Result.NO_RESULT
        ):
            raise ImporterError(
                _("Result [{result}] can't be used without an opponent.").format(
                    result=trf_game.result
                )
            )
        if trf_game.opponent_id and not color:
            raise ImporterError(
                _("Color [{color}] can't be used with an opponent.").format(
                    color=trf_game.color
                )
            )
        if not trf_game.opponent_id and color:
            raise ImporterError(
                _("Color [{color}] can't be used without an opponent.").format(
                    color=trf_game.color
                )
            )

    @classmethod
    def _read_trf_tournament(
        cls,
        event: Event,
        trf_tournament: TrfTournament,
        stored_tournament: StoredTournament | None = None,
    ) -> StoredTournament:
        if not stored_tournament:
            stored_tournament = StoredTournament(
                id=None,
                name=trf_tournament.name,
                start_date=event.start_date,
                stop_date=event.stop_date,
            )
        stored_tournament.location = trf_tournament.city
        if trf_tournament.start_date:
            try:
                stored_tournament.start_date = datetime.strptime(
                    trf_tournament.start_date, TRF_DATE_FORMAT
                ).date()
            except ValueError:
                raise ImporterError(
                    _('Invalid date format [{date}] (expected: {format}).').format(
                        date=trf_tournament.start_date, format=_('YYYY/MM/DD')
                    )
                )
        if trf_tournament.end_date:
            try:
                stored_tournament.stop_date = datetime.strptime(
                    trf_tournament.end_date, TRF_DATE_FORMAT
                ).date()
            except ValueError:
                raise ImporterError(
                    _('Invalid date format [{date}] (expected: {format}).').format(
                        date=trf_tournament.end_date, format=_('YYYY/MM/DD')
                    )
                )
        last_date_count = 0
        last_date: date | None = None
        for round_, trf_date in enumerate(trf_tournament.round_dates, start=1):
            if not trf_date:
                continue
            try:
                round_datetime = datetime.strptime(trf_date, '%y/%m/%d')
                if round_datetime.date() == last_date:
                    last_date_count += 1
                else:
                    last_date = round_datetime.date()
                    last_date_count = 0
                round_datetime = round_datetime.replace(
                    hour=last_date_count, minute=0, second=0
                )
                stored_tournament.round_datetimes[round_] = round_datetime
            except ValueError:
                message = _(
                    'Invalid date format [{date}] (expected: {format}).'
                ).format(date=trf_date, format=_('YY/MM/DD'))
                raise ImporterError(
                    _('{string}: {value}').format(string='132', value=message)
                )
        stored_tournament.rounds = trf_tournament.num_rounds_estimation
        initial_color = trf_tournament.initial_color
        if initial_color:
            try:
                BoardColor(initial_color)
                stored_tournament.pairing_settings[ColorSeedSetting().id] = (
                    initial_color
                )
            except ValueError:
                message = _('Unknown color [{color}].').format(color=initial_color)
                raise ImporterError(
                    _('{string}: {value}').format(string='152', value=message)
                )
        sr_method = trf_tournament.starting_rank_method
        if sr_method == 'FIDON':
            stored_tournament.player_rating_type = PlayerRatingType.FIDE
        elif sr_method == 'NIDOF':
            stored_tournament.player_rating_type = PlayerRatingType.NATIONAL
        stored_tournament.pairing = TrfEncodedType.get_pairing_variation(
            trf_tournament.encoded_type
        ).id
        trf_tie_breaks = (
            trf_tournament.standings_tie_breaks or ['PTS'] + trf_tournament.tie_breaks
        )
        tie_breaks = cls._read_tie_breaks(trf_tie_breaks, event)[0]
        stored_tournament.stored_tie_breaks = [
            tie_break.to_stored_value() for tie_break in tie_breaks
        ]
        time_control = trf_tournament.time_control
        if time_control:
            try:
                parse_time_control_trf25(time_control)
                stored_tournament.time_control_trf25 = time_control
            except ValueError:
                raise ImporterError(
                    _('Invalid time control format [{time_control}].').format(
                        time_control=time_control
                    )
                )
        return stored_tournament

    @staticmethod
    def _read_trf_player(
        trf_player: TrfPlayer,
        tournament_rating: TournamentRating,
        event: Event,
    ) -> StoredPlayer:
        national_player = trf_player.national_player_by_federation.get(event.federation)
        ratings = {tr.value: PlayerRating().stored_value for tr in TournamentRating}
        ratings[tournament_rating.value] = PlayerRating(
            fide=trf_player.rating or None,
            national=getattr(national_player, 'rating', 0) or None,
        ).stored_value
        date_of_birth: date | None = None
        year_of_birth: int | None = None
        if trf_player.birth_date:
            try:
                date_of_birth = datetime.strptime(
                    trf_player.birth_date, '%Y/%m/%d'
                ).date()
            except ValueError:
                if re.match(r'^\d{4}/00/00$', trf_player.birth_date):
                    year_of_birth = int(trf_player.birth_date.split('/')[0])

        stored_player = StoredPlayer(
            id=trf_player.id,
            last_name=trf_player.name.split(',')[0].strip().upper(),
            ratings=ratings,
            first_name=(
                trf_player.name.split(',')[1].strip()
                if ',' in trf_player.name
                else None
            ),
            gender=TrfPlayerGender.get_core_object(trf_player.gender).value,
            title=TrfPlayerTitle.get_core_object(trf_player.title).value,
            fide_id=trf_player.fide_id,
            date_of_birth=date_of_birth,
            year_of_birth=year_of_birth,
            federation=trf_player.federation.upper() or 'FID',
        )
        if national_player:
            plugin_manager.hook_for_event(
                event, 'augment_stored_player_from_trf_national_player'
            )(
                stored_player=stored_player,
                trf_national_player=national_player,
            )
        return stored_player

    @staticmethod
    def _read_trf_game(
        trf_game: TrfGame, player_id: int
    ) -> tuple[StoredPairing, StoredBoard | None]:
        stored_board: StoredBoard | None = None
        result = TrfResult.get_core_object(
            trf_game.result, has_opponent=bool(trf_game.opponent_id)
        )
        color = TrfColor.get_core_object(trf_game.color)
        stored_pairing = StoredPairing(
            tournament_id=0,
            player_id=player_id,
            round_=trf_game.round,
            result=result.value,
            board_id=None,
        )
        if trf_game.opponent_id:
            stored_board = StoredBoard(
                id=None,
                white_player_id=(
                    player_id if color == BoardColor.WHITE else trf_game.opponent_id
                ),
                black_player_id=(
                    trf_game.opponent_id if color == BoardColor.WHITE else player_id
                ),
                index=0,
            )
        elif result.is_board_bye:
            stored_board = StoredBoard(
                id=None,
                white_player_id=player_id,
                black_player_id=None,
                index=0,
            )
        return stored_pairing, stored_board
