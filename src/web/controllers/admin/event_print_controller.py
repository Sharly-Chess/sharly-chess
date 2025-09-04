from typing import Annotated, Any

from litestar import get, post
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar_htmx import ClientRedirect

from common.i18n import _
from data.print_documents import (
    PrintDocument,
    PrintDocumentManager,
    PrintDocumentOptionManager,
)
from data.print_documents.documents import PlayerListPrintDocument
from data.tournament import Tournament
from utils.option import OptionError
from web.controllers.base_controller import WebContext
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.session import SessionHandler


class EventPrintController(BaseEventAdminController):
    @classmethod
    def _admin_print_render(
        cls,
        web_context: BaseEventAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template | ClientRedirect | Redirect:
        if web_context.error:
            return web_context.error
        return cls._admin_event_render(
            web_context.template_context | (template_context or {}),
        )

    @staticmethod
    def _print_modal_context(
        web_context: BaseEventAdminWebContext,
        document_id: str | None = None,
        tournament_id: int | None = None,
        _round: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        print_options = PrintDocumentOptionManager.objects()
        if data is None:
            event = web_context.get_admin_event()
            if len(event.tournaments_sorted_by_uniq_id) == 1:
                tournament_id = event.tournaments_sorted_by_uniq_id[0].id
            data = {
                'tournament_id': WebContext.value_to_form_data(tournament_id),
                'document': document_id or PlayerListPrintDocument.static_id(),
                'round': WebContext.value_to_form_data(_round),
            } | {
                option.id: WebContext.value_to_form_data(option.default_value)
                for option in print_options
            }
        containers_by_document: dict[str, list[str]] = {'': []} | {
            document.id: [option.container_id for option in document.default_options()]
            for document in PrintDocumentManager.objects()
        }
        current_document_option_ids = []
        if document_id := data.get('document', None):
            current_document_option_ids = [
                option.id
                for option in PrintDocumentManager.get_type(
                    document_id
                ).default_options()
            ]
        return {
            'modal': 'print',
            'tournament_options': web_context.get_tournament_options(),
            'document_options': PrintDocumentManager.options(),
            'current_document_option_ids': current_document_option_ids,
            'print_options': print_options,
            'containers_by_document': containers_by_document,
            'data': data,
            'errors': errors or {},
        }

    @get(
        path=[
            '/admin/print-modal/{event_uniq_id:str}',
            '/admin/print-modal/{event_uniq_id:str}/{document_id:str}',
            '/admin/print-modal/{event_uniq_id:str}/{document_id:str}/{tournament_id:int}',
            '/admin/print-modal/{event_uniq_id:str}/{document_id:str}/{tournament_id:int}/{round:int}',
        ],
        name='admin-print-modal',
    )
    async def htmx_admin_print_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        document_id: str | None = None,
        tournament_id: int | None = None,
        round: int | None = None,
    ) -> Template | ClientRedirect | Redirect:
        web_context = BaseEventAdminWebContext(request, event_uniq_id)
        tournament_id = web_context.default_tournament_for_print_modal(tournament_id)

        template_context = self._print_modal_context(
            web_context,
            document_id=document_id,
            tournament_id=tournament_id,
            _round=round,
        )
        return self._admin_print_render(
            web_context=web_context,
            template_context=template_context,
        )

    @post(
        path='/admin/event-print/{event_uniq_id:str}',
        name='admin-event-print',
    )
    async def htmx_admin_event_print(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect | Redirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )
        if web_context.error:
            return web_context.error

        errors: dict[str, str] = {}
        tournament: Tournament | None = None
        field = 'tournament_id'

        try:
            tournament_id = WebContext.form_data_to_int(data, field)
            if not tournament_id:
                raise ValueError('Tournament ID not supplied')
            tournament = (
                web_context.get_admin_event().tournaments_by_id[tournament_id]
                if tournament_id
                else None
            )
        except (ValueError, KeyError):
            errors[field] = _('Please choose the tournament.')

        if tournament:
            SessionHandler.set_session_admin_print_last_tournament(
                request, web_context.get_admin_event().uniq_id, tournament.id
            )

        document_type: type[PrintDocument] | None = None
        field = 'document'
        try:
            document_type = PrintDocumentManager.get_type(
                WebContext.form_data_to_str(data, field) or ''
            )
        except KeyError:
            errors[field] = _('Please choose the document.')
        if tournament and document_type:
            if error_message := document_type.validate_for_tournament(tournament):
                errors[field] = error_message
            options = []
            for option in document_type.default_options():
                value = WebContext.form_data_to_value(data, option.id, option.type)
                options.append(type(option)(value))
            document = document_type(options, tournament)
            try:
                document.validate_options()
            except OptionError as error:
                errors[error.option.id] = str(error)

        if tournament and document_type and not errors:
            # Clear the modal contents, and send an event
            return HTMXTemplate(
                template_name='common/empty_modal.html',
                re_target='#modal-wrapper',
                trigger_event='do_print',
                after='receive',
                params={
                    'event_uniq_id': event_uniq_id,
                    'tournament_id': tournament.id if tournament else None,
                    'document': data['document'],
                    'options': {
                        option.id: data[option.id]
                        for option in document_type.default_options()
                        if option.id in data
                    },
                },
            )

        template_context = self._print_modal_context(
            web_context, tournament_id=tournament_id, data=data, errors=errors
        )
        return self._admin_print_render(
            web_context=web_context,
            template_context=template_context,
        )
