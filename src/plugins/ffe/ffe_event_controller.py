from functools import partial
from threading import Thread
from typing import Annotated, Any
from litestar import get, post
from litestar.response import Template
from litestar_htmx import HTMXRequest, ClientRedirect, HTMXTemplate, Reswap
from litestar.enums import RequestEncodingType
from litestar.params import Body

from common import format_timestamp_date_time
from common.i18n import _
from common.network import NetworkMonitor
from data.event import Event
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.ffe_session_handler import FFESessionHandler
from plugins.ffe.utils import FFEUtils, PlayerFFELicence
from plugins.utils import PluginUtils
from utils.enum import NeedsUpload
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.player_admin_controller import PlayerAdminController

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

SUCCESS = 0
INFO = 1
ERROR = 2
SETTINGS_ERROR = 3


class FfeUploadStatus:
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message

    def __str__(self) -> str:
        return self.message


class FfeAdminEventController(BaseEventAdminController):
    uploading: bool = False

    @get(
        path='/ffe/event/{event_uniq_id:str}/players',
        name='ffe-admin-event-players-tab',
        cache=1,
    )
    async def htmx_ffe_event_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_players_filter_leagues: list[str] | None = None,
        admin_players_filter_licences: list[int] | None = None,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        if admin_players_filter_leagues is not None:
            FFESessionHandler.set_session_admin_players_filter_leagues(
                request,
                [
                    league
                    for league in admin_players_filter_leagues
                    if league  # '' must be ignored
                ],
            )
        elif admin_players_filter_licences is not None:
            FFESessionHandler.set_session_admin_players_filter_licences(
                request,
                [
                    PlayerFFELicence(query_param)
                    for query_param in admin_players_filter_licences
                    if query_param >= 0  # -1 must be ignored
                ],
            )
        PlayerAdminController.set_players_search_results(request, event_uniq_id)
        return PlayerAdminController._admin_event_players_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @post(
        path='/ffe/test-auth',
        name='ffe-test-auth',
    )
    async def htmx_ffe_test_auth(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        ffe_auth_valid: bool | None = None

        if NetworkMonitor.connected():
            ffe_id = data['ffe_id']
            ffe_password = data['ffe_password']

            if ffe_id and ffe_password:
                ffe_auth_valid = FFESession(tournament=None, debug=False).test_auth(
                    ffe_id=ffe_id, ffe_password=ffe_password
                )

        errors = {}
        # Compare to False, None means 'unable to check'
        if ffe_auth_valid is False:
            errors['ffe_id'] = _('Invalid FFE ID or password.')
            errors['ffe_password'] = _('Invalid FFE ID or password.')

        return HTMXTemplate(
            template_name='ffe_tournament_ffe_auth_fields.html',
            context={
                'data': {
                    'ffe_id': data['ffe_id'],
                    'ffe_password': data['ffe_password'],
                },
                'ffe_auth_valid': ffe_auth_valid is True,
                'ffe_password_visible': data['ffe_password_visible'] == 'true',
                'errors': errors,
            },
        )

    upload_status_messages: dict[str, FfeUploadStatus] = {}

    @classmethod
    def result_id(cls, tournament: Tournament) -> str:
        return f'{tournament.event.uniq_id}:{tournament.id}'

    @classmethod
    def print_success(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadStatus(
            SUCCESS, message
        )

    @classmethod
    def print_error(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadStatus(
            ERROR, message
        )

    @classmethod
    def print_info(cls, tournament: Tournament, message: str) -> None:
        cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadStatus(
            INFO, message
        )

    @classmethod
    def get_updated_upload_results(cls, admin_event: Event) -> list[Tournament]:
        tournaments: list[Tournament] = []
        for tournament in admin_event.tournaments_by_id.values():
            result_id = cls.result_id(tournament)
            result = (
                cls.upload_status_messages[result_id]
                if result_id in cls.upload_status_messages
                else None
            )

            # Clear the message if it is a SETTINGS_ERROR, and refresh it here...
            if result and result.status == SETTINGS_ERROR:
                result.message = ''
            if not cls.check_id_and_password(tournament):
                cls.upload_status_messages[result_id] = FfeUploadStatus(
                    SETTINGS_ERROR,
                    _('FFE ID and password not defined for tournament').format(
                        tournament_uniq_id=tournament.uniq_id
                    ),
                )
                pass
            elif not tournament.file:
                cls.upload_status_messages[result_id] = FfeUploadStatus(
                    SETTINGS_ERROR,
                    _('Papi file not defined for tournament').format(
                        tournament_uniq_id=tournament.uniq_id
                    ),
                )
            elif not tournament.file_exists:
                cls.upload_status_messages[result_id] = FfeUploadStatus(
                    SETTINGS_ERROR,
                    _('Papi file not found [{file}]').format(
                        file=tournament.file, tournament_uniq_id=tournament.uniq_id
                    ),
                )
            else:
                tournaments.append(tournament)
        return tournaments

    @get(
        path='/ffe/ffe-upload-modal/{event_uniq_id:str}',
        name='ffe-upload-modal',
    )
    async def htmx_admin_ffe_upload_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        self.get_updated_upload_results(web_context.admin_event)

        return HTMXTemplate(
            template_name='/ffe_upload_modal.html',
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': self.result_id,
                'upload_status_messages': self.upload_status_messages,
                'ffe_utils': FFEUtils,
            },
        )

    @staticmethod
    def check_id_and_password(tournament: Tournament) -> bool:
        pd = tournament.plugin_data
        ffe_id = get_data(pd, 'ffe_id')
        ffe_password = get_data(pd, 'ffe_password')
        if not ffe_id or not ffe_password:
            print(
                _('FFE ID not defined for tournament [{tournament_uniq_id}].').format(
                    tournament_uniq_id=tournament.uniq_id
                )
            )
            return False
        return True

    @classmethod
    def ffe_last_upload(cls, tournament: Tournament) -> float:
        return get_data(tournament.plugin_data, 'ffe_last_upload', 0.0)

    @classmethod
    def ffe_upload_needed(cls, tournament: Tournament) -> NeedsUpload:
        try:
            ffe_last_upload = cls.ffe_last_upload(tournament)
            if ffe_last_upload > tournament.file_modified_timestamp:
                # Last version already uploaded
                return NeedsUpload.NO_CHANGE
            return NeedsUpload.YES
        except FileNotFoundError:
            return NeedsUpload.NO_CHANGE

    @classmethod
    def upload_event(cls, admin_event: Event) -> None:
        if cls.uploading:
            return
        cls.uploading = True

        tournaments = cls.get_updated_upload_results(admin_event)
        updated_tournaments: list[Tournament] = []
        for tournament in tournaments:
            needs_upload: NeedsUpload = cls.ffe_upload_needed(tournament)
            match needs_upload:
                case NeedsUpload.YES:
                    updated_tournaments.append(tournament)
                case NeedsUpload.NO_CHANGE:
                    cls.upload_status_messages[cls.result_id(tournament)] = (
                        FfeUploadStatus(
                            INFO,
                            _('Papi file not modified since last upload').format(
                                last_upload=format_timestamp_date_time(
                                    cls.ffe_last_upload(tournament)
                                )
                            ),
                        )
                    )
                    pass

        if not updated_tournaments:
            cls.uploading = False
            return

        for tournament in updated_tournaments:
            cls.upload_status_messages[cls.result_id(tournament)] = FfeUploadStatus(
                INFO,
                _('Uploading tournament...').format(
                    tournament_uniq_id=tournament.uniq_id
                ),
            )

        def _upload_tournaments(cls: FfeAdminEventController) -> None:
            try:
                for tournament in updated_tournaments:
                    FFESession(
                        tournament,
                        debug=False,
                        print_error=partial(
                            FfeAdminEventController.print_error, tournament
                        ),
                        print_info=partial(
                            FfeAdminEventController.print_info, tournament
                        ),
                        print_success=partial(
                            FfeAdminEventController.print_success, tournament
                        ),
                    ).upload(set_visible=False)
            finally:
                cls.uploading = False

        uploader = Thread(target=_upload_tournaments, args=(cls,))
        uploader.start()

    @get(
        path='/ffe/ffe-upload-results/{event_uniq_id:str}',
        name='ffe-upload-results',
    )
    async def htmx_admin_ffe_upload_results(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | Reswap:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        return HTMXTemplate(
            template_name='/ffe_upload_results.html',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': self.result_id,
                'upload_status_messages': self.upload_status_messages,
                'ffe_utils': FFEUtils,
            },
        )

    @post(
        path='/ffe/ffe-upload/{event_uniq_id:str}',
        name='ffe-upload',
    )
    async def htmx_admin_ffe_upload(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | Reswap:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error

        admin_event = web_context.admin_event
        assert admin_event is not None
        self.upload_event(admin_event)

        return HTMXTemplate(
            template_name='/ffe_upload_results.html',
            context=web_context.template_context
            | {
                'format_timestamp_date_time': format_timestamp_date_time,
                'result_id': self.result_id,
                'upload_status_messages': self.upload_status_messages,
                'ffe_utils': FFEUtils,
            },
        )
