from typing import Any, Annotated

from litestar import get, post, patch
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from data.access_levels.actions import AuthAction
from data.print_documents import PrintDocumentManager
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader
from plugins.custom_upload.utils import CustomUploadUtils
from utils.date_time import format_datetime
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import EventGuard, ActionGuard, TournamentActionGuard


class CustomUploadAdminEventController(BaseEventAdminController):
    guards = []

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.PUBLISH_RESULTS
        )

    @classmethod
    def _upload_results_context(
        cls, web_context: BaseEventAdminWebContext
    ) -> dict[str, Any]:
        tournaments = web_context.get_admin_event().tournaments
        # TODO: load document URLs for *each* tournament instead of an arbitrary one
        document_urls = None
        for tournament in tournaments:
            document_urls = CustomUploadUtils.get_tournament_plugin_data(
                tournament
            ).document_urls
        document_types = []
        if document_urls is not None and len(document_urls) > 0:
            # TODO: refactor logic to be cleaner
            for document_url in document_urls:
                document_id = document_url.split('/')[-1].split('?')[0]
                document_type = PrintDocumentManager(
                    web_context.get_admin_event()
                ).get_type(document_id)
                document_types.append(document_type)
        return web_context.template_context | {
            'format_datetime': format_datetime,
            'allowed_tournaments': cls._allowed_tournaments(web_context),
            'documents': document_types,
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

    @classmethod
    def _render_upload_results(cls, web_context: BaseEventAdminWebContext) -> Template:
        return HTMXTemplate(
            template_name='/custom_upload_results.html',
            context=cls._upload_results_context(web_context),
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
        path='/custom-upload/documents-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='change-tournament-documents-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_change_documents_modal(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        custom_upload_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        return HTMXTemplate(
            template_name='change_tournament_documents_modal.html',
            context=web_context.template_context
            | {
                'enumerate': enumerate,
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
        tournament = web_context.get_admin_tournament()
        custom_upload_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        custom_upload_data.document_urls.append('')
        return HTMXTemplate(
            template_name='change_tournament_documents_modal.html',
            context=web_context.template_context
            | {
                'enumerate': enumerate,
                'data': custom_upload_data.to_form_data(),
                'errors': {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            after='settle',
        )

    def _update_document(
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
                    errors[name] = (
                        "There should be no more than one unescaped '?' character"
                    )
                    continue
                document_id = value.split('/')[-1].split('?')[0]
                try:
                    document_manager.get_type(document_id)
                except KeyError:
                    errors[name] = 'No document type is matching input'
                    continue
                updated_document_urls.append(value)

        if len(errors) > 0:
            document_urls = ';'.join(data.values())
            return HTMXTemplate(
                template_name='change_tournament_documents_modal.html',
                context=web_context.template_context
                | {
                    'enumerate': enumerate,
                    'data': {'document_urls': document_urls},
                    'errors': errors,
                },
                re_target='#modal-wrapper',
                re_swap='innerHTML',
                after='settle',
            )

        custom_upload_data = CustomUploadUtils.get_tournament_plugin_data(tournament)
        custom_upload_data.document_urls = updated_document_urls
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
        path='/custom-upload/documents-update/{event_uniq_id:str}/{tournament_id:int}',
        name='change-documents-update',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_change_documents_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        return self._update_document(web_context, data)

    @post(
        path='/custom-upload/upload/{event_uniq_id:str}',
        name='custom-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)

        # TODO: upload event to custom location

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

        CustomUploadUploader.schedule_upload(tournament, True)

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
        # TODO: Check if FTP connection is working

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
                'custom_upload_auth_valid': False,
                'errors': [],
            },
        )
