import re
from typing import Any, Annotated

from litestar import get, post, patch
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from data.print_documents import PrintDocumentManager
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader
from plugins.custom_upload.utils import (
    CustomUploadUtils,
    CustomUploadTournamentPluginData,
)
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard


class CustomUploadAdminEventController(BaseEventAdminController):
    guards = []

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.PUBLISH_RESULTS
        )

    @staticmethod
    def _extract_document_id(document_url: str) -> str:
        return re.findall(r'([\w-]*)[^/]*$', document_url)[0]

    @staticmethod
    def _upload_results_context(
        web_context: BaseEventAdminWebContext,
    ) -> dict[str, Any]:
        tournaments = web_context.get_admin_event().tournaments
        document_types_by_tournament = {}
        for tournament in tournaments:
            document_urls = CustomUploadUtils.get_tournament_plugin_data(
                tournament
            ).document_urls
            document_types = []
            for document_url in document_urls:
                document_id = CustomUploadAdminEventController._extract_document_id(
                    document_url
                )
                document_type = PrintDocumentManager(
                    web_context.get_admin_event()
                ).get_type(document_id)
                document_types.append(document_type)
            document_types_by_tournament[tournament.id] = document_types
        return web_context.template_context | {
            'allowed_tournaments': CustomUploadAdminEventController._allowed_tournaments(
                web_context
            ),
            'documents_by_tournament': document_types_by_tournament,
        }

    @get(
        path='/custom-upload/modal/{event_uniq_id:str}',
        name='custom-upload-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return HTMXTemplate(
            template_name='custom_upload_modal.html',
            context=self._upload_results_context(web_context),
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @staticmethod
    def _render_upload_results(web_context: BaseEventAdminWebContext) -> Template:
        return HTMXTemplate(
            template_name='custom_upload_results.html',
            context=CustomUploadAdminEventController._upload_results_context(
                web_context
            ),
        )

    @get(
        path='/custom-upload/upload-results/{event_uniq_id:str}',
        name='custom-upload-results',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_results(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_upload_results(web_context)

    @get(
        path='/custom-upload/configuration-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-tournament-configuration-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_tournament_configuration_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        custom_upload_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        return HTMXTemplate(
            template_name='custom_upload_tournament_configuration_modal.html',
            context=web_context.template_context
            | {
                'data': custom_upload_data.to_form_data(),
                'errors': {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            trigger_event='modal_opened',
            after='settle',
        )

    @post(
        path='/custom-upload/add-document/{event_uniq_id:str}/{tournament_id:int}',
        name='add-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_add_document(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        custom_upload_data = CustomUploadTournamentPluginData.from_form_data(data)
        custom_upload_data.document_urls.append('')
        return HTMXTemplate(
            template_name='custom_upload_tournament_configuration_modal.html',
            context=web_context.template_context
            | {
                'data': custom_upload_data.to_form_data(),
                'errors': {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            after='settle',
        )

    @post(
        path='/custom-upload/remove-document/{event_uniq_id:str}/{tournament_id:int}/{document_index:int}',
        name='remove-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_remove_document(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        tournament_id: int,
        document_index: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        custom_upload_data = CustomUploadTournamentPluginData.from_form_data(data)
        custom_upload_data.document_urls.pop(document_index)
        return HTMXTemplate(
            template_name='change_tournament_documents_modal.html',
            context=web_context.template_context
            | {
                'data': custom_upload_data.to_form_data(),
                'errors': {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            after='settle',
        )

    def _update_tournament_configuration(
        self,
        web_context: TournamentAdminWebContext,
        data: dict[str, str],
    ) -> Template:
        request = web_context.request
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()

        updated_document_urls = []
        errors = {}
        document_manager = PrintDocumentManager(web_context.get_admin_event())

        for name, value in data.items():
            if name.startswith('document_url'):
                if value.count('?') > 1:
                    errors[name] = _(
                        "There should be no more than one unescaped '?' character"
                    )
                    continue
                document_id = CustomUploadAdminEventController._extract_document_id(
                    value
                )
                try:
                    document_manager.get_type(document_id)
                except KeyError:
                    errors[name] = _('No document type is matching input.')
                    continue
                updated_document_urls.append(value)

        if len(errors) > 0:
            return HTMXTemplate(
                template_name='custom_upload_tournament_configuration_modal.html',
                context=web_context.template_context
                | {
                    'data': data,
                    'errors': errors,
                },
                re_target='#modal-wrapper',
                re_swap='innerHTML',
                after='settle',
            )

        custom_upload_data = CustomUploadTournamentPluginData.from_form_data(data)
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            custom_upload_data.to_stored_value()
        )
        with EventDatabase(event.uniq_id, True) as event_database:
            event_database.update_stored_tournament(tournament.stored_tournament)

        web_context = BaseEventAdminWebContext(request, reload_event=True)
        return HTMXTemplate(
            template_name='custom_upload_modal.html',
            context=self._upload_results_context(web_context),
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @patch(
        path='/custom-upload/configuration/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-tournament-configuration-update',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_tournament_configuration_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        return self._update_tournament_configuration(web_context, data)

    @post(
        path='/custom-upload/upload/{event_uniq_id:str}',
        name='custom-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        CustomUploadUploader.upload_event_tournaments(
            self._allowed_tournaments(web_context), web_context.client
        )
        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-tournament',
        guards=[EventGuard(), TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()

        CustomUploadUploader.schedule_upload(tournament, web_context.client)

        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/test-auth',
        name='custom-upload-test-auth',
    )
    async def htmx_custom_upload_test_auth(
        self,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        ftp_auth_valid: bool | None = None

        ftp_host: str | None = WebContext.form_data_to_str(data, 'ftp_host', '')
        ftp_username: str | None = WebContext.form_data_to_str(data, 'ftp_username', '')
        ftp_password: str | None = WebContext.form_data_to_str(data, 'ftp_password', '')

        if NetworkMonitor.connected():
            ftp_auth_valid = False
            if ftp_host and ftp_username:
                ftp_auth_valid = CustomUploadUploader.test_ftp(
                    ftp_host, ftp_username, ftp_password or ''
                )

        errors = {}
        if ftp_auth_valid is False:
            errors['ftp_host'] = _('Failed to connect to server.')

        return HTMXTemplate(
            template_name='custom_upload_tournament_auth_fields.html',
            context={
                'data': {
                    'ftp_host': data['ftp_host'],
                    'server_path': data['server_path'],
                    'ftp_username': data['ftp_username'],
                    'ftp_password': data['ftp_password'],
                },
                'ftp_password_visible': data['ftp_password_visible'] == 'true',
                'custom_upload_auth_valid': ftp_auth_valid is True,
                'errors': errors,
            },
        )
