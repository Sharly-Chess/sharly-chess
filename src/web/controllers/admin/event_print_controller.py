from typing import Annotated, Any

from litestar import get, post
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
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
from web.controllers.base_controller import WebContext
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.guards import EventGuard, ActionGuard
from web.session import SessionHandler


class EventPrintController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.PRINT),
    ]

    @classmethod
    def _admin_print_render(
        cls,
        web_context: BaseEventAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {}),
        )

    @staticmethod
    def _print_modal_context(
        web_context: BaseEventAdminWebContext,
        document_id: str | None = None,
        tournament_ids: list[int] | None = None,
        _round: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        print_options = PrintDocumentOptionManager(event).objects()
        if len(event.tournaments) == 1:
            tournament_ids = list(event.tournaments_by_id)

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
        containers_by_document: dict[str, list[str]] = {'': []} | {
            document.id: [option.container_id for option in document.default_options()]
            for document in PrintDocumentManager(event).objects()
        }
        current_document_option_ids = []
        if document_id := data.get('document', None):
            current_document_option_ids = [
                option.id
                for option in PrintDocumentManager(event)
                .get_type(document_id)()
                .default_options()
            ]
        return {
            'modal': 'print',
            'tournament_options': web_context.get_tournament_options(),
            'document_options': PrintDocumentManager(event).options(),
            'current_document_option_ids': current_document_option_ids,
            'print_options': print_options,
            'containers_by_document': containers_by_document,
            'data': data,
            'errors': errors or {},
        }

    @get(
        path=[
            '/print-modal/{event_uniq_id:str}',
            '/print-modal/{event_uniq_id:str}/{tournament_id:int}',
        ],
        name='admin-print-modal',
    )
    async def htmx_admin_print_modal(
        self,
        request: HTMXRequest,
        document_id: str | None = None,
        tournament_id: int | None = None,
        round: int | None = None,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        tournament_ids = web_context.default_tournament_for_print_modal(tournament_id)

        template_context = self._print_modal_context(
            web_context,
            document_id=document_id,
            tournament_ids=tournament_ids,
            _round=round,
        )
        return self._admin_print_render(
            web_context=web_context,
            template_context=template_context,
        )

    @post(
        path='/event-print/{event_uniq_id:str}',
        name='admin-event-print',
    )
    async def htmx_admin_event_print(
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
        event = web_context.get_admin_event()

        errors: dict[str, str] = {}

        document_type: type[PrintDocument] | None = None
        field = 'document'
        try:
            document_type = PrintDocumentManager(event).get_type(
                WebContext.form_data_to_str(flat_data, field) or ''
            )
        except KeyError:
            errors[field] = _('Please choose the document.')

        tournament_ids: list[int] | None = None
        if document_type:
            options = []
            for option in document_type().default_options():
                value = WebContext.form_data_to_value(flat_data, option.id, option.type)
                options.append(type(option)(event, value))

                if isinstance(option, TournamentPrintOption):
                    tournament_id = web_context.form_data_to_int(
                        flat_data, field='tournament'
                    )
                    tournament_ids = [tournament_id] if tournament_id else []
                elif isinstance(option, TournamentsPrintOption):
                    tournament_ids = web_context.form_data_to_list_int(
                        flat_data, field='tournaments'
                    )
            try:
                document = document_type(web_context.get_admin_event(), options)
                document.validate_options()
            except OptionError as error:
                errors[error.option.id] = str(error)

            if not errors:
                if tournament_ids:
                    SessionHandler.set_session_admin_print_last_tournaments(
                        request, web_context.get_admin_event().uniq_id, tournament_ids
                    )

                    tournament = web_context.get_admin_event().tournaments_by_id[
                        tournament_ids[0]
                    ]
                    if error_message := document_type.validate_for_tournament(
                        tournament
                    ):
                        errors[field] = error_message
        if errors:
            template_context = self._print_modal_context(
                web_context, data=flat_data, errors=errors
            )
            return self._admin_print_render(
                web_context=web_context,
                template_context=template_context,
            )
        assert document_type is not None
        # Clear the modal contents, and send an event
        return HTMXTemplate(
            template_name='common/empty_modal.html',
            re_target='#modal-wrapper',
            trigger_event='do_print',
            after='receive',
            params={
                'event_uniq_id': event_uniq_id,
                'document': flat_data['document'],
                'options': {
                    option.id: flat_data[option.id]
                    for option in document_type().default_options()
                    if option.id in data
                },
            },
        )

    @get(
        path='/print-view/{event_uniq_id:str}/{document: str}',
        name='admin-print-view',
    )
    async def htmx_tournament_print_view(
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
        for print_option in document_type().default_options():
            value = WebContext.form_data_to_value(
                option_data, print_option.id, print_option.type
            )
            print_options.append(type(print_option)(event, value))
        print_document = document_type(web_context.get_admin_event(), print_options)

        template_context = (
            web_context.template_context
            | {
                'document': print_document,
            }
            | print_document.template_context
        )
        return HTMXTemplate(
            template_name=print_document.template_name, context=template_context
        )
