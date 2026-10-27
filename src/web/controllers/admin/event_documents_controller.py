import urllib
from collections import defaultdict
from typing import Annotated, Any, cast

import msgspec
from litestar import Request, Response, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import (
    InternalServerException,
    NotFoundException,
    ValidationException,
)
from litestar.params import Body, FromPath, FromQuery
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.response import Template
from pathvalidate import sanitize_filename

from common.exception import OptionError
from common.i18n import _
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.actions import AuthAction
from data.access_levels.client import Client
from data.event import Event
from data.input_output import DataSourceManager
from data.print_documents import (
    PrintDocument,
    PrintDocumentManager,
    PrintDocumentOptionManager,
    PrintOption,
)
from data.print_documents.documents import (
    PlayerListPrintDocument,
    QRCodePrintDocument,
)
from data.print_documents.options import TournamentsPrintOption
from data.print_documents.pdf_rendering import (
    PdfRenderers,
    PdfRenderingError,
    decode_pdf_export,
)
from data.print_documents.word_export import build_word_document, decode_word_export
from data.print_documents.options import TournamentPrintOption
from data.tournament import Tournament
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.controllers.document_pdf_source_controller import DocumentPdfSources
from web.guards import EventGuard, ActionGuard, PrintGuard
from web.session import SessionPrintLastTournaments
from web.streaming_template import StreamingHTMXTemplate


logger = get_logger()

_EXPORT_TOOLBAR_TEMPLATE = '/admin/print/_export_toolbar.html'
_WORD_MEDIA_TYPE = (
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
)


def export_toolbar_context(
    request: Request[Any, Any, Any], event: Event | None = None
) -> dict[str, Any]:
    """The context of a document viewed in the browser, which shows the export
    toolbar. The documents of an event can be exported to Word, and to PDF when
    the desktop application renders them."""
    word_export_url: str | None = None
    pdf_export_url: str | None = None
    if event is not None:
        word_export_url = request.app.route_reverse(
            'document-word', event_uniq_id=event.uniq_id
        )
        if PdfRenderers.renderer is not None:
            pdf_export_url = request.app.route_reverse(
                'document-pdf', event_uniq_id=event.uniq_id
            )
    sharly_chess_config = SharlyChessConfig()
    icons_version = sharly_chess_config.bootstrap_icons_version
    return {
        'export_toolbar': _EXPORT_TOOLBAR_TEMPLATE,
        'export_toolbar_version': sharly_chess_config.version,
        'export_toolbar_icons': (
            f'/lib/bootstrap-icons/bootstrap-icons-{icons_version}'
            '/bootstrap-icons.min.css'
        ),
        'word_export_url': word_export_url,
        'pdf_export_url': pdf_export_url,
    }


def _attachment(filename: str) -> dict[str, str]:
    return {
        'Content-Disposition': (
            f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"
        )
    }


class EventDocumentsController(BaseEventAdminController):
    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.GENERATE_DOCUMENTS),
    ]

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.GENERATE_DOCUMENTS
        )

    @classmethod
    def default_document_picker_data(
        cls,
        event: Event,
        document_id: str | None = None,
        tournament_ids: list[int] | None = None,
        _round: int | None = None,
    ) -> dict[str, str]:
        """Default form data for the document picker: default value for every
        print option, plus the selected document/round/tournament(s)."""
        print_options = PrintDocumentOptionManager(event).objects()
        return WebContext.values_dict_to_form_data(
            {option.id: option.default_value for option in print_options}
            | {
                'document': document_id or PlayerListPrintDocument.static_id(),
                'round': _round,
                'tournament': tournament_ids[0] if tournament_ids else None,
                'tournaments': tournament_ids,
            }
        )

    @classmethod
    def document_picker_context(
        cls,
        web_context: BaseEventAdminWebContext,
        data: dict[str, str],
        auth_action: AuthAction = AuthAction.GENERATE_DOCUMENTS,
    ) -> dict[str, Any]:
        """Context required to render the shared document picker fields
        (`event/_document_picker_fields.html`)."""
        event = web_context.get_admin_event()
        print_options = PrintDocumentOptionManager(event).objects()
        allowed_tournaments = web_context.client.allowed_tournaments_for_action(
            auth_action
        )
        document_ids_by_option_id: dict[str, list[str]] = defaultdict(list[str])
        containers_by_document: dict[str, list[str]] = {'': []}
        containers_by_document_and_tournament: dict[str, dict[int, list[str]]] = {}
        documents = [
            doc
            for doc in PrintDocumentManager(event).objects()
            if doc.is_available(allowed_tournaments)
        ]
        for document in documents:
            options = document.default_options()
            containers_by_document[document.id] = [
                option.container_id for option in options
            ]
            containers_by_document_and_tournament[document.id] = {
                tournament.id: [
                    option_type(event).container_id
                    for option_type in document.option_types_for_tournament(tournament)
                ]
                for tournament in allowed_tournaments
            }
            for option in options:
                document_ids_by_option_id[option.id].append(document.id)
        current_document_option_ids = []
        if document_id := data.get('document'):
            document_type = PrintDocumentManager(event).get_type(document_id)
            tournament_id = WebContext.form_data_to_int(data, 'tournament')
            tournament = (
                event.tournaments_by_id.get(tournament_id) if tournament_id else None
            )
            current_document_option_ids = [
                option_type(event).id
                for option_type in (
                    document_type.option_types_for_tournament(tournament)
                    if tournament
                    else document_type.available_options()
                )
            ]
        players_per_tournament_id = {
            tournament.id: [
                {
                    'id': tournament_player.id,
                    'full_name': tournament_player.full_name,
                }
                for tournament_player in tournament.sorted_tournament_players
            ]
            for tournament in allowed_tournaments
        }
        teams_per_tournament_id = {
            tournament.id: [
                {'id': team.id, 'name': team.name}
                for team in sorted(
                    tournament.teams,
                    key=lambda team: (
                        team.pairing_number
                        if team.pairing_number is not None
                        else float('inf'),
                        team.name.lower(),
                    ),
                )
            ]
            for tournament in allowed_tournaments
        }
        return {
            'print_options': print_options,
            'document_options': {
                document.id: document.picker_name(allowed_tournaments)
                for document in documents
            },
            'document_ids_by_option_id': document_ids_by_option_id,
            'containers_by_document': containers_by_document,
            'containers_by_document_and_tournament': (
                containers_by_document_and_tournament
            ),
            'current_document_option_ids': current_document_option_ids,
            'players_per_tournament_id': players_per_tournament_id,
            'teams_per_tournament_id': teams_per_tournament_id,
            'allowed_tournaments': allowed_tournaments,
            'data_sources': DataSourceManager().active_objects(),
        }

    @classmethod
    def _render_documents_modal(
        cls,
        web_context: BaseEventAdminWebContext,
        document_id: str | None = None,
        tournament_ids: list[int] | None = None,
        _round: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        success_message: str | None = None,
    ) -> HTMXTemplate:
        event = web_context.get_admin_event()
        allowed_tournaments = cls._allowed_tournaments(web_context)
        if len(allowed_tournaments) == 1:
            tournament_ids = [allowed_tournaments[0].id]
        if document_id is None and not PlayerListPrintDocument.is_available(
            allowed_tournaments
        ):
            document_id = QRCodePrintDocument.static_id()

        default_data = cls.default_document_picker_data(
            event,
            document_id=document_id,
            tournament_ids=tournament_ids,
            _round=_round,
        )
        data = default_data | (data or {})
        picker_context = cls.document_picker_context(web_context, data)

        template_context = picker_context | {
            'modal': 'print',
            'client': web_context.client,
            'account_options': web_context.get_account_options(),
            'tournament_options': web_context.get_tournament_options(
                picker_context['allowed_tournaments']
            ),
            'data': data,
            'success_message': success_message,
            'errors': errors or {},
        }
        return cls._admin_base_event_render(
            web_context.template_context | template_context
        )

    @get(
        path=[
            '/documents-modal/{event_uniq_id:str}',
            '/documents-modal/{event_uniq_id:str}/{tournament_id:int}',
        ],
        name='documents-modal',
    )
    async def htmx_documents_modal(
        self,
        request: HTMXRequest,
        document_id: FromQuery[str | None] = None,
        tournament_id: FromPath[int | None] = None,
        round: FromQuery[int | None] = None,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        tournament_ids = web_context.default_tournament_for_print_modal(tournament_id)
        return self._render_documents_modal(
            web_context=web_context,
            document_id=document_id,
            tournament_ids=tournament_ids,
            _round=round,
        )

    @staticmethod
    def _get_tournament_ids_from_options(
        options: list[PrintOption],
    ) -> list[int] | None:
        for option in options:
            if isinstance(option, TournamentPrintOption):
                return [option.value] if option.value is not None else None
            if isinstance(option, TournamentsPrintOption):
                return cast(list[int] | None, option.value)
        return None

    @post(
        path='/event-generate-document/{event_uniq_id:str}',
        name='event-generate-document',
    )
    async def htmx_event_generate_document(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: FromPath[str],
    ) -> Template:
        flat_data = WebContext.flatten_list_data(data)
        web_context = BaseEventAdminWebContext(request)
        client = web_context.client
        event = web_context.get_admin_event()

        errors: dict[str, str] = {}

        document_type: type[PrintDocument] | None = None
        document: PrintDocument | None = None
        field = 'document'
        try:
            document_type = PrintDocumentManager(event).get_type(
                WebContext.form_data_to_str(flat_data, field) or ''
            )
        except KeyError:
            errors[field] = _('Please choose the document.')

        if document_type:
            options: list[PrintOption] = []
            for option in document_type(client).default_options():
                value = WebContext.form_data_to_value(flat_data, option.id, option.type)
                options.append(type(option)(event, value))
            try:
                document = document_type(client, options)
                document.validate_options()
            except OptionError as error:
                errors[error.option.id] = str(error)

            if not errors:
                tournament_ids = self._get_tournament_ids_from_options(options)
                if tournament_ids:
                    SessionPrintLastTournaments(request, event).set(tournament_ids)
        if errors:
            return self._render_documents_modal(
                web_context, data=flat_data, errors=errors
            )
        assert document is not None
        # Clear the modal contents, and send an event
        return HTMXTemplate(
            template_name='common/alert.html',
            re_target='#document-success-message',
            re_swap='innerHTML',
            context={
                'type': 'success',
                'message': _(
                    'Document [{document}] has been generated in another tab.'
                ).format(document=document.tab_title),
            },
            trigger_event='do_print',
            after='receive',
            params={
                'event_uniq_id': event_uniq_id,
                'document': flat_data['document'],
                'options': {
                    option.id: flat_data[option.id]
                    for option in document.default_options()
                    if option.id in data
                },
            },
        )

    @classmethod
    def build_print_document(
        cls, client: Client, event: Event, document: str, options: str | None = None
    ) -> PrintDocument:
        """Build a print document from a document id and an
        ``id=value|id=value`` options string (list values joined by ``;``)."""
        document_type = PrintDocumentManager(event).get_type(document)
        option_data: dict[str, str] = {}
        if options:
            for option in urllib.parse.unquote(options).split('|'):
                key, raw_value = option.split('=', 1)
                option_data[key] = raw_value
        print_options: list[PrintOption] = []
        for print_option in document_type(client).default_options():
            value = WebContext.form_data_to_value(
                option_data, print_option.id, print_option.type
            )
            print_options.append(type(print_option)(event, value))
        return document_type(client, print_options)

    @get(
        path='/document-view/{event_uniq_id:str}/{document: str}',
        name='document-view',
        guards=[PrintGuard()],
    )
    async def htmx_document_view(
        self,
        request: HTMXRequest,
        document: FromPath[str],
        options: FromQuery[str | None] = None,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        print_document = self.build_print_document(
            web_context.client, event, document, options
        )
        template_context = (
            web_context.template_context
            | {
                'document': print_document,
            }
            | print_document.template_context
            | export_toolbar_context(request, event)
        )
        return StreamingHTMXTemplate(
            template_name=print_document.template_name, context=template_context
        )

    @post(
        path='/document-word/{event_uniq_id:str}',
        name='document-word',
    )
    async def document_word(self, request: HTMXRequest) -> Response[bytes]:
        """The Word file of a document, from its layout in the browser."""
        try:
            export = decode_word_export(await request.body())
        except msgspec.DecodeError as error:
            raise ValidationException(str(error)) from error
        filename = f'{sanitize_filename(export.title) or "document"}.docx'
        return Response(
            content=build_word_document(export),
            media_type=_WORD_MEDIA_TYPE,
            headers=_attachment(filename),
        )

    @post(
        path='/document-pdf/{event_uniq_id:str}',
        name='document-pdf',
    )
    async def document_pdf(self, request: HTMXRequest) -> Response[bytes]:
        """The PDF file of a document as the browser shows it, rendered by the
        desktop application."""
        renderer = PdfRenderers.renderer
        if renderer is None:
            raise NotFoundException(
                'Documents are rendered as PDF by the desktop application only.'
            )
        try:
            export = decode_pdf_export(await request.body())
        except msgspec.DecodeError as error:
            raise ValidationException(str(error)) from error
        token = DocumentPdfSources.add(export.html)
        try:
            # The web engine runs on this computer, whatever address the
            # browser reached the server at.
            server = request.scope.get('server')
            if server is None or server[1] is None:
                raise PdfRenderingError('The address of the server is unknown.')
            host, port = server
            if host in ('', '0.0.0.0', '::'):
                host = '127.0.0.1'
            elif ':' in host:
                host = f'[{host}]'
            path = request.app.route_reverse('document-pdf-source', token=token)
            content = await renderer.render(
                f'http://{host}:{port}{path}', export.margins
            )
        except PdfRenderingError as error:
            logger.error(
                'The PDF of [%s] could not be rendered: %s', export.title, error
            )
            raise InternalServerException(str(error)) from error
        finally:
            DocumentPdfSources.discard(token)
        filename = f'{sanitize_filename(export.title) or "document"}.pdf'
        return Response(
            content=content, media_type='application/pdf', headers=_attachment(filename)
        )

    @classmethod
    def build_document_options(
        cls,
        event: Event,
        client: Client,
        flat_data: dict[str, str],
    ) -> tuple[str | None, str, str, dict[str, str]]:
        """From picker form data, build ``(document_id, options_string, errors)``.

        The chosen document and its options are validated; ``options_string`` uses
        the ``id=value|id=value`` encoding consumed by :meth:`document_view`, with
        list values joined by ``;``.
        On validation failure ``errors`` is non-empty and ``options_string`` empty.
        """
        errors: dict[str, str] = {}
        document_id = WebContext.form_data_to_str(flat_data, 'document') or ''
        try:
            document_type = PrintDocumentManager(event).get_type(document_id)
        except KeyError:
            errors['document'] = _('Please choose the document.')
            return None, '', '', errors

        options: list[PrintOption] = []
        for option in document_type(client).default_options():
            value = WebContext.form_data_to_value(flat_data, option.id, option.type)
            options.append(type(option)(event, value))
        try:
            document = document_type(client, options)
            document.validate_options()
        except OptionError as error:
            errors[error.option.id] = str(error)
            return document_id, '', '', errors

        options_string = '|'.join(
            f'{option.id}={flat_data[option.id]}'
            for option in document.default_options()
            if option.id in flat_data
        )

        target_filename = (
            WebContext.form_data_to_str(flat_data, 'target_filename') or ''
        )

        return document_id, options_string, target_filename, errors

    @classmethod
    def document_view(
        cls, client: Client, event: Event, document: str, options: str | None = None
    ) -> HTMXTemplate:
        print_document = cls.build_print_document(client, event, document, options)
        template_context = {
            'document': print_document,
        } | print_document.template_context
        return HTMXTemplate(
            template_name=print_document.template_name, context=template_context
        )
