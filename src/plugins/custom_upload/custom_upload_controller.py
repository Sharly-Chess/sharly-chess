from typing import Annotated, Any

from litestar import get, patch, post
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from data.print_documents import PrintDocument, PrintDocumentManager
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.custom_upload import PLUGIN_NAME
from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader
from plugins.custom_upload.utils import (
    ConfiguredDocument,
    CustomUploadEventPluginData,
    CustomUploadTournamentPluginData,
    CustomUploadUtils,
    TransferProtocol,
)
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.event_documents_controller import EventDocumentsController
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard, TournamentActionGuard

type DocumentMetadata = tuple[ConfiguredDocument, type[PrintDocument] | None]


class CustomUploadAdminEventController(BaseEventAdminController):
    guards = []

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.PUBLISH_RESULTS
        )

    @staticmethod
    def _upload_results_context(
        web_context: BaseEventAdminWebContext,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        document_manager = PrintDocumentManager(event)
        documents_by_tournament: dict[int, list[DocumentMetadata]] = {}
        for tournament in event.tournaments:
            documents = CustomUploadUtils.get_tournament_plugin_data(
                tournament
            ).documents
            documents_metadata: list[DocumentMetadata] = []
            for configured_document in documents:
                try:
                    document_type: type[PrintDocument] | None = (
                        document_manager.get_type(configured_document.document_id)
                    )
                except KeyError:
                    document_type = None
                documents_metadata.append((configured_document, document_type))
            documents_by_tournament[tournament.id] = documents_metadata
        event_plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        return web_context.template_context | {
            'connection_host': event_plugin_data.ftp_host,
            'allowed_tournaments': CustomUploadAdminEventController._allowed_tournaments(
                web_context
            ),
            'documents_by_tournament': documents_by_tournament,
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
        path='/custom-upload/configuration-modal/{event_uniq_id:str}',
        name='custom-upload-event-configuration-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_event_configuration_modal(
        self, request: HTMXRequest
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        custom_upload_data = CustomUploadUtils.get_event_plugin_data(
            web_context.get_admin_event()
        )
        return HTMXTemplate(
            template_name='custom_upload_configuration_modal.html',
            context=web_context.template_context
            | {
                'data': custom_upload_data.to_form_data(),
                'transfer_protocol_options': TransferProtocol.form_options(),
                'errors': {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            trigger_event='modal_opened',
            after='settle',
        )

    # ---------------------------------------------------------------------------------
    # Tournament configuration (documents list)
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _tournament_config_context(
        web_context: TournamentAdminWebContext,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        document_manager = PrintDocumentManager(event)
        documents_display: list[dict[str, Any]] = []
        for index, configured_document in enumerate(tournament_plugin_data.documents):
            try:
                document_type = document_manager.get_type(
                    configured_document.document_id
                )
                name = _(document_type.static_name())
            except KeyError:
                name = configured_document.document_id
            documents_display.append(
                {
                    'index': index,
                    'document_id': configured_document.document_id,
                    'options': configured_document.options,
                    'name': name,
                    'target_filename': configured_document.target_filename,
                }
            )
        return web_context.template_context | {
            'data': tournament_plugin_data.to_form_data(),
            'documents_display': documents_display,
            'no_documents': not tournament_plugin_data.documents,
            'default_server_path': CustomUploadUtils.get_event_plugin_data(
                event
            ).default_server_path,
            'errors': errors or {},
        }

    def _render_tournament_config_modal(
        self,
        web_context: TournamentAdminWebContext,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        errors: dict[str, str] | None = None,
    ) -> Template:
        return HTMXTemplate(
            template_name='custom_upload_tournament_configuration_modal.html',
            context=self._tournament_config_context(
                web_context, tournament_plugin_data, errors
            ),
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            trigger_event='modal_opened',
            after='settle',
        )

    @staticmethod
    def _options_to_form_data(options: str) -> dict[str, str]:
        """Expand a stored ``id=value|id=value`` options string back into picker
        form data, so the picker can be pre-filled when editing a document."""
        form_data: dict[str, str] = {}
        if options:
            for part in options.split('|'):
                if '=' in part:
                    key, value = part.split('=', 1)
                    form_data[key] = value
        return form_data

    def _render_document_picker(
        self,
        web_context: TournamentAdminWebContext,
        tournament_plugin_data: CustomUploadTournamentPluginData,
        picker_data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        edit_index: int | None = None,
    ) -> Template:
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()
        default_data = EventDocumentsController.default_document_picker_data(
            event, tournament_ids=[tournament.id]
        )
        data = default_data | (picker_data or {})
        picker_context = EventDocumentsController.document_picker_context(
            web_context, data, auth_action=AuthAction.PUBLISH_RESULTS
        )
        return HTMXTemplate(
            template_name='custom_upload_document_picker.html',
            context=web_context.template_context
            | picker_context
            | {
                'client': web_context.client,
                'account_options': web_context.get_account_options(),
                'tournament_options': web_context.get_tournament_options(
                    picker_context['allowed_tournaments']
                ),
                'config_data': tournament_plugin_data.to_form_data(),
                'data': data,
                'edit_index': edit_index,
                'errors': errors or {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            trigger_event='modal_opened',
            after='settle',
        )

    @get(
        path='/custom-upload/configuration-modal/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-tournament-configuration-modal',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_tournament_configuration_modal(
        self,
        request: HTMXRequest,
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        tournament_custom_upload_data = CustomUploadUtils.get_tournament_plugin_data(
            tournament
        )
        return self._render_tournament_config_modal(
            web_context, tournament_custom_upload_data
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
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament_plugin_data = CustomUploadTournamentPluginData.from_form_data(data)
        return self._render_document_picker(web_context, tournament_plugin_data)

    @post(
        path='/custom-upload/edit-document/{event_uniq_id:str}/{tournament_id:int}/{document_index:int}',
        name='edit-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_edit_document(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        tournament_id: FromPath[int],
        document_index: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament_plugin_data = CustomUploadTournamentPluginData.from_form_data(data)
        if not 0 <= document_index < len(tournament_plugin_data.documents):
            return self._render_tournament_config_modal(
                web_context, tournament_plugin_data
            )
        document = tournament_plugin_data.documents[document_index]
        picker_data = {
            'document': document.document_id,
            'target_filename': document.target_filename,
        } | self._options_to_form_data(document.options)
        return self._render_document_picker(
            web_context,
            tournament_plugin_data,
            picker_data=picker_data,
            edit_index=document_index,
        )

    @post(
        path='/custom-upload/add-document-confirm/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-add-document-confirm',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_add_document_confirm(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        flat_data = WebContext.flatten_list_data(data)
        event = web_context.get_admin_event()
        tournament_plugin_data = CustomUploadTournamentPluginData.from_form_data(
            flat_data
        )
        edit_index_raw = flat_data.get('edit_index')
        edit_index = int(edit_index_raw) if edit_index_raw else None
        document_id, options_string, target_filename, errors = (
            EventDocumentsController.build_document_options(
                event, web_context.client, flat_data
            )
        )
        if errors or not document_id:
            return self._render_document_picker(
                web_context,
                tournament_plugin_data,
                picker_data=flat_data,
                errors=errors,
                edit_index=edit_index,
            )
        document = ConfiguredDocument(
            document_id=document_id,
            options=options_string,
            target_filename=target_filename,
        )
        if edit_index is not None and 0 <= edit_index < len(
            tournament_plugin_data.documents
        ):
            tournament_plugin_data.documents[edit_index] = document
        else:
            tournament_plugin_data.documents.append(document)
        return self._render_tournament_config_modal(web_context, tournament_plugin_data)

    @post(
        path='/custom-upload/cancel-add-document/{event_uniq_id:str}/{tournament_id:int}',
        name='custom-upload-cancel-add-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_cancel_add_document(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament_plugin_data = CustomUploadTournamentPluginData.from_form_data(data)
        return self._render_tournament_config_modal(web_context, tournament_plugin_data)

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
        tournament_id: FromPath[int],
        document_index: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament_plugin_data = CustomUploadTournamentPluginData.from_form_data(data)
        if 0 <= document_index < len(tournament_plugin_data.documents):
            tournament_plugin_data.documents.pop(document_index)
        return self._render_tournament_config_modal(web_context, tournament_plugin_data)

    def _update_event_configuration(
        self,
        web_context: BaseEventAdminWebContext,
        data: dict[str, str],
    ) -> Template:
        request = web_context.request
        event = web_context.get_admin_event()

        custom_upload_data = CustomUploadEventPluginData.from_form_data(data)
        event.stored_event.plugin_data[PLUGIN_NAME] = (
            custom_upload_data.to_stored_value()
        )

        with EventDatabase(event.uniq_id, True) as event_database:
            event_database.update_stored_event(event.stored_event)

        web_context = BaseEventAdminWebContext(request, reload_event=True)
        return HTMXTemplate(
            template_name='custom_upload_modal.html',
            context=self._upload_results_context(web_context),
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    @patch(
        path='/custom-upload/configuration/{event_uniq_id:str}',
        name='custom-upload-event-configuration-update',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_event_configuration_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._update_event_configuration(web_context, data)

    def _update_tournament_configuration(
        self,
        web_context: TournamentAdminWebContext,
        data: dict[str, str],
    ) -> Template:
        request = web_context.request
        event = web_context.get_admin_event()
        tournament = web_context.get_admin_tournament()

        previous_tournament_plugin_data = CustomUploadUtils.get_tournament_plugin_data(
            tournament
        )
        custom_upload_data = CustomUploadTournamentPluginData.from_form_data(
            data, previous_object=previous_tournament_plugin_data
        )
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            custom_upload_data.to_stored_value()
        )
        with EventDatabase(event.uniq_id, True) as event_database:
            event_database.update_stored_tournament(tournament.stored_tournament)

        base_web_context = BaseEventAdminWebContext(request, reload_event=True)
        return HTMXTemplate(
            template_name='custom_upload_modal.html',
            context=self._upload_results_context(base_web_context),
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
        tournament_id: FromPath[int],
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
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()

        CustomUploadUploader.schedule_upload(tournament, web_context.client)

        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/test-auth/{event_uniq_id:str}',
        name='custom-upload-test-auth',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_custom_upload_test_auth(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        ftp_host: str = WebContext.form_data_to_str(data, 'ftp_host') or ''
        ftp_username: str = WebContext.form_data_to_str(data, 'ftp_username') or ''
        ftp_password: str = WebContext.form_data_to_str(data, 'ftp_password') or ''
        default_server_path: str = (
            WebContext.form_data_to_str(data, 'default_server_path') or '/'
        )
        transfer_protocol: TransferProtocol = TransferProtocol(
            WebContext.form_data_to_str(data, 'transfer_protocol')
            or TransferProtocol.SFTP.value
        )
        transfer_port: int | None = WebContext.form_data_to_int(data, 'transfer_port')

        errors = {}
        auth_valid = False
        path_valid = False
        if NetworkMonitor.connected():
            if ftp_host and ftp_username:
                try:
                    CustomUploadUploader.test_file_transfer_connection(
                        ftp_host,
                        ftp_username,
                        ftp_password,
                        default_server_path,
                        transfer_protocol,
                        transfer_port,
                    )
                    auth_valid = True
                    path_valid = True
                except PermissionError:
                    errors['ftp_username'] = _('Invalid credentials.')
                except ConnectionError:
                    errors['ftp_host'] = _('Failed to connect to server.')
                except FileNotFoundError:
                    auth_valid = True
                    errors['default_server_path'] = _(
                        'Path does not exist or is inaccessible.'
                    )
        else:
            errors['ftp_host'] = _('No internet connection detected.')

        return HTMXTemplate(
            template_name='custom_upload_auth_fields.html',
            context=web_context.template_context
            | {
                'data': {
                    'ftp_host': data['ftp_host'],
                    'default_server_path': data['default_server_path'],
                    'ftp_username': data['ftp_username'],
                    'ftp_password': data['ftp_password'],
                    'transfer_protocol': data['transfer_protocol'],
                    'transfer_port': data['transfer_port'],
                },
                'transfer_protocol_options': TransferProtocol.form_options(),
                'ftp_password_visible': data.get('ftp_password_visible') == 'true',
                'custom_upload_auth_valid': auth_valid,
                'custom_upload_path_valid': path_valid,
                'errors': errors,
            },
        )
