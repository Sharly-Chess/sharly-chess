from typing import Annotated, Any

from litestar import get, post
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect
from litestar_htmx import ClientRedirect
import urllib

from common.exception import OptionError
from common.i18n import _
from data.player import plugin_manager
from data.tournament import Tournament
from data.print_documents import (
    PrintDocument,
    PrintDocumentManager,
    PrintDocumentOptionManager,
    PrintOption,
)
from data.print_documents.documents import PlayerListPrintDocument
from data.print_documents.options import TournamentPrintOption
from plugins.hookspec import ExtraColumn
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
            data = (
                {
                    'document': document_id or PlayerListPrintDocument.static_id(),
                    'round': WebContext.value_to_form_data(_round),
                }
                | {
                    option.id: WebContext.value_to_form_data(option.default_value)
                    for option in print_options
                }
                | {
                    'tournament': WebContext.value_to_form_data(tournament_id),
                    'tournaments': WebContext.value_to_form_data(tournament_id),
                }
            )
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
            '/admin/print-modal/{event_uniq_id:str}/{tournament_id:int}',
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
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect | Redirect:
        flat_data = WebContext.flatten_list_data(data)
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=flat_data,
        )
        if web_context.error:
            return web_context.error

        errors: dict[str, str] = {}

        document_type: type[PrintDocument] | None = None
        field = 'document'
        try:
            document_type = PrintDocumentManager.get_type(
                WebContext.form_data_to_str(flat_data, field) or ''
            )
        except KeyError:
            errors[field] = _('Please choose the document.')

        tournament: Tournament | None = None
        if document_type:
            options = []
            tournament_id: int | None = None
            for option in document_type.default_options():
                value = WebContext.form_data_to_value(flat_data, option.id, option.type)
                options.append(type(option)(value))
                if isinstance(option, TournamentPrintOption):
                    assert isinstance(value, int | None)
                    tournament_id = value
            document = document_type(web_context.get_admin_event(), options)
            if tournament_id:
                tournament = web_context.get_admin_event().tournaments_by_id[
                    tournament_id
                ]
                SessionHandler.set_session_admin_print_last_tournament(
                    request, web_context.get_admin_event().uniq_id, tournament.id
                )
                if error_message := document_type.validate_for_tournament(tournament):
                    errors[field] = error_message

            try:
                document.validate_options()
            except OptionError as error:
                errors[error.option.id] = str(error)

        if document_type and not errors:
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
            web_context, tournament_id=tournament_id, data=flat_data, errors=errors
        )
        return self._admin_print_render(
            web_context=web_context,
            template_context=template_context,
        )

    @get(
        path='/admin/print-view/{event_uniq_id:str}/{document: str}',
        name='admin-print-view',
    )
    async def htmx_tournament_print_view(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        document: str,
        options: str | None = None,
    ) -> Template | ClientRedirect | Redirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        document_type = PrintDocumentManager.get_type(document)
        option_data: dict[str, str] = {}
        if options:
            for option in urllib.parse.unquote(options).split('|'):
                key, raw_value = option.split('=')
                option_data[key] = raw_value
        print_options: list[PrintOption] = []
        for print_option in document_type.default_options():
            value = WebContext.form_data_to_value(
                option_data, print_option.id, print_option.type
            )
            print_options.append(type(print_option)(value))
        print_document = document_type(web_context.get_admin_event(), print_options)

        per_plugin_columns = plugin_manager.hook.get_extra_print_view_columns(
            document=print_document
        )
        extra_columns: dict[str, list[ExtraColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                c = extra_columns.setdefault(extra_column.at, [])
                c.append(extra_column)
        per_plugin_css: list[str] = plugin_manager.hook.get_extra_print_view_css(
            document=print_document
        )
        extra_css: str = '\n'.join(per_plugin_css)

        template_context = (
            web_context.template_context
            | {
                'document': print_document,
                'extra_columns': extra_columns,
                'extra_css': extra_css,
            }
            | print_document.template_context
        )
        return HTMXTemplate(
            template_name=print_document.template_name, context=template_context
        )
