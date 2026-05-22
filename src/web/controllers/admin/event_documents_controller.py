from collections import defaultdict
from typing import Annotated

from litestar import get, post
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from web.streaming_template import StreamingHTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
import urllib

from common.exception import OptionError
from common.i18n import _
from data.access_levels.actions import AuthAction
from data.print_documents import (
    PrintDocument,
    PrintDocumentManager,
    PrintDocumentOptionManager,
    PrintOption,
)
from data.print_documents.documents import (
    PlayerListPrintDocument,
    TournamentsPrintOption,
)
from data.print_documents.options import TournamentPrintOption
from data.tournament import Tournament
from web.controllers.base_controller import WebContext
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.guards import EventGuard, ActionGuard, PrintGuard
from web.session import SessionPrintLastTournaments


class EventDocumentsController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.GENERATE_DOCUMENTS),
    ]

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.GENERATE_DOCUMENTS
        )

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
        print_options = PrintDocumentOptionManager(event).objects()
        allowed_tournaments = cls._allowed_tournaments(web_context)
        if len(allowed_tournaments) == 1:
            tournament_ids = [allowed_tournaments[0].id]

        default_data = WebContext.values_dict_to_form_data(
            {option.id: option.default_value for option in print_options}
            | {
                'document': document_id or PlayerListPrintDocument.static_id(),
                'round': _round,
                'tournament': tournament_ids[0] if tournament_ids else None,
                'tournaments': tournament_ids,
            }
        )
        data = default_data | (data or {})
        document_ids_by_option_id: dict[str, list[str]] = defaultdict(list[str])
        containers_by_document: dict[str, list[str]] = {'': []}
        allowed_tournaments = web_context.client.allowed_tournaments_for_action(
            AuthAction.GENERATE_DOCUMENTS
        )
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
            for option in options:
                document_ids_by_option_id[option.id].append(document.id)
        current_document_option_ids = []
        if document_id := data.get('document', None):
            current_document_option_ids = [
                option.id
                for option in PrintDocumentManager(event)
                .get_type(document_id)()
                .default_options()
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

        template_context = {
            'modal': 'print',
            'client': web_context.client,
            'account_options': web_context.get_account_options(),
            'tournament_options': web_context.get_tournament_options(
                allowed_tournaments
            ),
            'players_per_tournament_id': players_per_tournament_id,
            'document_ids_by_option_id': document_ids_by_option_id,
            'allowed_tournaments': allowed_tournaments,
            'document_options': {document.id: document.name for document in documents},
            'current_document_option_ids': current_document_option_ids,
            'print_options': print_options,
            'containers_by_document': containers_by_document,
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
        document_id: str | None = None,
        tournament_id: int | None = None,
        round: int | None = None,
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
                return [option.value]
            elif isinstance(option, TournamentsPrintOption):
                return option.value
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
        event_uniq_id: str,
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

    @get(
        path='/document-view/{event_uniq_id:str}/{document: str}',
        name='document-view',
        guards=[PrintGuard()],
    )
    async def htmx_document_view(
        self,
        request: HTMXRequest,
        document: str,
        options: str | None = None,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        document_type = PrintDocumentManager(event).get_type(document)
        option_data: dict[str, str] = {}
        if options:
            for option in urllib.parse.unquote(options).split('|'):
                key, raw_value = option.split('=')
                option_data[key] = raw_value
        print_options: list[PrintOption] = []
        for print_option in document_type(web_context.client).default_options():
            value = WebContext.form_data_to_value(
                option_data, print_option.id, print_option.type
            )
            print_options.append(type(print_option)(event, value))
        print_document = document_type(
            web_context.client,
            print_options,
        )

        template_context = (
            web_context.template_context
            | {
                'document': print_document,
            }
            | print_document.template_context
        )
        return StreamingHTMXTemplate(
            template_name=print_document.template_name, context=template_context
        )
