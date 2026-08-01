from typing import Annotated, Any

from litestar import get, patch, post
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from common.logger import get_logger
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from data.event import Event
from plugins.custom_upload.custom_upload_uploader import (
    CUSTOM_UPLOAD_DELAY,
    CustomUploadUploader,
)
from plugins.custom_upload.utils import (
    ConfiguredDocument,
    CustomUploadEventPluginData,
    CustomUploadUtils,
    TransferProtocol,
)
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.event_documents_controller import EventDocumentsController
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard

logger = get_logger()


class CustomUploadAdminEventController(BaseEventAdminController):
    guards = []

    @staticmethod
    def _allowed_documents(
        web_context: BaseEventAdminWebContext, event: Event
    ) -> list[ConfiguredDocument]:
        """Documents the client is allowed to publish: event-wide documents, or
        documents targeting at least one tournament the client may publish."""
        allowed_ids = {
            tournament.id
            for tournament in web_context.client.allowed_tournaments_for_action(
                AuthAction.PUBLISH_RESULTS
            )
        }
        documents = CustomUploadUtils.get_event_plugin_data(event).documents
        allowed_documents: list[ConfiguredDocument] = []
        for document in documents:
            tournament_ids = document.tournament_ids()
            if not tournament_ids or any(
                tournament_id in allowed_ids for tournament_id in tournament_ids
            ):
                allowed_documents.append(document)
        return allowed_documents

    # ---------------------------------------------------------------------------------
    # Main modal (documents list)
    # ---------------------------------------------------------------------------------

    @staticmethod
    def _upload_results_context(
        web_context: BaseEventAdminWebContext,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        event_plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        return web_context.template_context | {
            'connection_host': event_plugin_data.ftp_host,
            'connection_default_server_path': event_plugin_data.default_server_path,
            'connection_message': CustomUploadUtils.event_connection_message(event),
            'documents': event_plugin_data.documents,
            'custom_upload_delay': CUSTOM_UPLOAD_DELAY,
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

    # ---------------------------------------------------------------------------------
    # Connection configuration
    # ---------------------------------------------------------------------------------

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
        event = web_context.get_admin_event()
        previous_plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        custom_upload_data = CustomUploadEventPluginData.from_form_data(
            data, previous_object=previous_plugin_data
        )
        CustomUploadUtils.save_event_plugin_data(event, custom_upload_data)

        reloaded_web_context = BaseEventAdminWebContext(request, reload_event=True)
        return HTMXTemplate(
            template_name='custom_upload_modal.html',
            context=self._upload_results_context(reloaded_web_context),
            re_target='#modal-wrapper',
            trigger_event='modal_opened',
            after='settle',
        )

    # ---------------------------------------------------------------------------------
    # Document picker (add / edit)
    # ---------------------------------------------------------------------------------

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
        web_context: BaseEventAdminWebContext,
        picker_data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        edit_id: str | None = None,
    ) -> Template:
        event = web_context.get_admin_event()
        allowed_tournaments = web_context.client.allowed_tournaments_for_action(
            AuthAction.PUBLISH_RESULTS
        )
        # When a single tournament is available the picker hides its tournament
        # selector, so it must be pre-selected for the document to validate.
        tournament_ids = (
            [allowed_tournaments[0].id] if len(allowed_tournaments) == 1 else None
        )
        default_data = EventDocumentsController.default_document_picker_data(
            event, tournament_ids=tournament_ids
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
                'default_server_path': CustomUploadUtils.get_event_plugin_data(
                    event
                ).default_server_path,
                'data': data,
                'edit_id': edit_id,
                'errors': errors or {},
            },
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            trigger_event='modal_opened',
            after='settle',
        )

    @get(
        path='/custom-upload/add-document/{event_uniq_id:str}',
        name='custom-upload-add-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_add_document(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_document_picker(web_context)

    @get(
        path='/custom-upload/edit-document/{event_uniq_id:str}/{document_id:str}',
        name='custom-upload-edit-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_edit_document(
        self,
        request: HTMXRequest,
        document_id: FromPath[str],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        document = CustomUploadUtils.get_document(event, document_id)
        if not document:
            return self._render_upload_modal(web_context)
        picker_data = {
            'document': document.document_id,
            'target_filename': document.target_filename,
            'server_path': document.server_path or '',
        } | self._options_to_form_data(document.options)
        return self._render_document_picker(
            web_context, picker_data=picker_data, edit_id=document.id
        )

    @staticmethod
    def _render_upload_modal(web_context: BaseEventAdminWebContext) -> Template:
        return HTMXTemplate(
            template_name='custom_upload_modal.html',
            context=CustomUploadAdminEventController._upload_results_context(
                web_context
            ),
            re_target='#modal-wrapper',
            re_swap='innerHTML',
            trigger_event='modal_opened',
            after='settle',
        )

    @post(
        path='/custom-upload/document-confirm/{event_uniq_id:str}',
        name='custom-upload-document-confirm',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_document_confirm(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        flat_data = WebContext.flatten_list_data(data)
        edit_id = flat_data.get('edit_id') or None

        document_id, options_string, target_filename, errors = (
            EventDocumentsController.build_document_options(
                event, web_context.client, flat_data
            )
        )
        if errors or not document_id:
            return self._render_document_picker(
                web_context,
                picker_data=flat_data,
                errors=errors,
                edit_id=edit_id,
            )

        server_path = CustomUploadUtils.normalize_server_path(
            WebContext.form_data_to_str(flat_data, 'server_path')
        )
        plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        existing = CustomUploadUtils.get_document(event, edit_id) if edit_id else None
        if existing:
            # The document content may have changed: reset its upload state.
            existing.document_id = document_id
            existing.options = options_string
            existing.target_filename = target_filename
            existing.server_path = server_path or None
            existing.last_upload_at = None
            existing.last_upload_attempt_at = None
            existing.upload_failure_id = None
        else:
            plugin_data.documents.append(
                ConfiguredDocument(
                    document_id=document_id,
                    options=options_string,
                    target_filename=target_filename,
                    server_path=server_path or None,
                )
            )
        CustomUploadUtils.save_event_plugin_data(event, plugin_data)

        reloaded_web_context = BaseEventAdminWebContext(request, reload_event=True)
        return self._render_upload_modal(reloaded_web_context)

    @post(
        path='/custom-upload/remove-document/{event_uniq_id:str}/{document_id:str}',
        name='custom-upload-remove-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_remove_document(
        self,
        request: HTMXRequest,
        document_id: FromPath[str],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        plugin_data.documents = [
            document for document in plugin_data.documents if document.id != document_id
        ]
        CustomUploadUtils.save_event_plugin_data(event, plugin_data)

        reloaded_web_context = BaseEventAdminWebContext(request, reload_event=True)
        return self._render_upload_results(reloaded_web_context)

    # ---------------------------------------------------------------------------------
    # Upload
    # ---------------------------------------------------------------------------------

    @post(
        path='/custom-upload/upload/{event_uniq_id:str}',
        name='custom-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload(self, request: HTMXRequest) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        CustomUploadUploader.upload_event_documents(
            event, self._allowed_documents(web_context, event), web_context.client
        )
        return self._render_upload_results(web_context)

    @post(
        path='/custom-upload/upload-document/{event_uniq_id:str}/{document_id:str}',
        name='custom-upload-document',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_document(
        self,
        request: HTMXRequest,
        document_id: FromPath[str],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        document = CustomUploadUtils.get_document(event, document_id)
        if document:
            CustomUploadUploader.schedule_upload(event, document, web_context.client)
        return self._render_upload_results(web_context)

    # ---------------------------------------------------------------------------------
    # Auto-upload
    # ---------------------------------------------------------------------------------

    def _apply_auto_upload(
        self,
        web_context: BaseEventAdminWebContext,
        event: Event,
        documents: list[ConfiguredDocument],
    ):
        """Schedule or cancel the automatic upload of documents after their
        auto-upload flag changed."""
        for document in documents:
            if document.auto_upload:
                if CustomUploadUploader.should_schedule_document_upload(
                    event, document
                ):
                    CustomUploadUploader.schedule_upload(
                        event, document, web_context.client
                    )
            else:
                CustomUploadUploader.remove_scheduled_upload(event.uniq_id, document.id)

    @patch(
        path='/custom-upload/document-auto-upload/{event_uniq_id:str}/{document_id:str}',
        name='custom-upload-document-auto-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_document_auto_upload(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        document_id: FromPath[str],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        document = CustomUploadUtils.get_document(event, document_id)
        if document:
            document.auto_upload = WebContext.form_data_to_bool(
                data, f'auto_upload_{document_id}'
            )
            CustomUploadUtils.save_event_plugin_data(
                event, CustomUploadUtils.get_event_plugin_data(event)
            )
            self._apply_auto_upload(web_context, event, [document])
        reloaded_web_context = BaseEventAdminWebContext(request, reload_event=True)
        return self._render_upload_results(reloaded_web_context)

    @patch(
        path='/custom-upload/auto-upload/{event_uniq_id:str}',
        name='custom-upload-auto-upload',
        guards=[EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_admin_custom_upload_auto_upload(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        enabled = WebContext.form_data_to_bool(data, 'auto_upload_all')
        plugin_data = CustomUploadUtils.get_event_plugin_data(event)
        for document in plugin_data.documents:
            document.auto_upload = enabled
        CustomUploadUtils.save_event_plugin_data(event, plugin_data)
        self._apply_auto_upload(web_context, event, plugin_data.documents)
        reloaded_web_context = BaseEventAdminWebContext(request, reload_event=True)
        return self._render_upload_results(reloaded_web_context)

    # ---------------------------------------------------------------------------------
    # Connection test
    # ---------------------------------------------------------------------------------

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
        plugin_data: CustomUploadEventPluginData = (
            CustomUploadEventPluginData.from_form_data(data)
        )
        ftp_host: str = plugin_data.ftp_host or ''
        ftp_username: str = plugin_data.ftp_username or ''
        ftp_password: str = plugin_data.ftp_password or ''
        default_server_path: str = plugin_data.default_server_path or ''
        transfer_protocol: TransferProtocol = plugin_data.transfer_protocol
        transfer_port: int = plugin_data.transfer_port or transfer_protocol.default_port

        errors = {}
        auth_valid = False
        path_valid = False
        if NetworkMonitor.connected():
            if ftp_host and ftp_username:
                log_message: str | None = None
                try:
                    logger.info(
                        'Attempting connection to [%s:********@%s:%d/%s] via [%s]...',
                        ftp_username,
                        ftp_host,
                        transfer_port,
                        default_server_path,
                        transfer_protocol.name,
                    )
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
                    logger.info('Connection succeeded.')
                except PermissionError as error:
                    message = _('Invalid credentials.')
                    errors['ftp_username'] = message
                    errors['ftp_password'] = message
                    log_message = str(error)
                except ConnectionError as error:
                    message = _('Failed to connect to server.')
                    errors['ftp_host'] = message
                    errors['transfer_protocol'] = message
                    errors['transfer_port'] = message
                    log_message = str(error)
                except FileNotFoundError as error:
                    auth_valid = True
                    message = _('Path does not exist or is inaccessible.')
                    errors['default_server_path'] = message
                    log_message = str(error)
                if log_message:
                    logger.warning(
                        'Connection test to [%s:%d/%s] via [%s] failed: %s.',
                        ftp_host,
                        transfer_port,
                        default_server_path,
                        transfer_protocol.name,
                        log_message,
                    )
        else:
            message: str = _('No internet connection detected.')
            errors['ftp_host'] = message
            errors['transfer_protocol'] = message
            errors['transfer_port'] = message
            logger.warning(message)

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
