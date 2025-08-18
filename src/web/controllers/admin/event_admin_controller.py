import csv
from tempfile import NamedTemporaryFile
from typing import Annotated, Any, Iterable

import xlsxwriter

from litestar import get, patch, post, Response, delete
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect, File
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import ClientRedirect
from pyexcel_ods3 import save_data

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.display_controller import DisplayController
from data.loader import EventLoader
from data.player import Player
from data.print_documents import (
    PrintDocument,
    PrintDocumentManager,
    PrintDocumentOptionManager,
)
from data.print_documents.documents import PlayerListPrintDocument
from data.rotator import Rotator
from data.screen import Screen
from plugins.ffe.utils import FFEUtils
from utils.enum import TournamentRating, ScreenType
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from plugins.hookspec import ExtraColumn
from plugins.manager import plugin_manager
from utils.option import OptionError
from web.controllers.base_controller import BaseController
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.urls import (
    admin_event_pairings_url,
    admin_event_players_url,
    admin_event_tournaments_url,
    admin_event_config_url,
    admin_url,
)


class EventAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_config_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None = None,
        modal: str | None = None,
        action: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )

        plugin_event_info_rows = plugin_manager.hook.get_event_info_rows_template()
        template_context |= {
            'admin_event_tab': 'admin-event-config-tab',
            'ffe_utils': FFEUtils,
            'plugin_event_info_rows': plugin_event_info_rows,
            'event_uniq_ids': EventLoader.all_event_ids(),
        }

        match modal:
            case None:
                pass
            case 'event':
                if action is None:
                    raise RuntimeError('action not defined')
                if data is None:
                    data = cls._prepare_event_modal_data(
                        action, request, web_context.admin_event
                    )

                plugin_form_fields_templates = (
                    plugin_manager.hook.get_event_form_fields_template() or []
                )
                template_context |= {
                    'federation_options': cls._get_federation_options(None),
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        SharlyChessConfig.default_record_illegal_moves_number
                    ),
                    'timer_color_texts': cls._get_timer_color_texts(
                        SharlyChessConfig.default_timer_delays
                    ),
                    'background_images_jstree_data': cls.background_images_jstree_data(
                        data['background_image']
                    )
                    if action
                    in [
                        'update',
                        'clone',
                    ]
                    and 'background_image' in data
                    else {},
                    'modal': 'event',
                    'plugin_form_fields_templates': plugin_form_fields_templates,
                    'action': action,
                    'data': data,
                    'errors': errors or {},
                }
            case 'print':
                print_options = PrintDocumentOptionManager.objects()
                if data is None:
                    event = web_context.admin_event
                    if len(event.tournaments_sorted_by_uniq_id) == 1:
                        tournament_id = event.tournaments_sorted_by_uniq_id[0].id
                    data = {
                        'tournament_id': WebContext.value_to_form_data(tournament_id),
                        'document': PlayerListPrintDocument.static_id(),
                    } | {
                        option.id: WebContext.value_to_form_data(option.default_value)
                        for option in print_options
                    }
                containers_by_document: dict[str, list[str]] = {'': []} | {
                    document.id: [
                        option.container_id for option in document.default_options()
                    ]
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
                template_context |= {
                    'modal': 'print',
                    'tournament_options': web_context.get_tournament_options(),
                    'document_options': PrintDocumentManager.options(),
                    'current_document_option_ids': current_document_option_ids,
                    'print_options': print_options,
                    'containers_by_document': containers_by_document,
                    'data': data,
                    'errors': errors or {},
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}',
        name='admin-event',
    )
    async def htmx_admin_event(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | Redirect | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            data=None,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        started_tournaments: list[Tournament] = [
            tournament
            for tournament in web_context.admin_event.tournaments_by_uniq_id.values()
            if tournament.started
        ]
        if len(started_tournaments) > 0 and web_context.client.can_view_pairings_tab:
            return Redirect(
                admin_event_pairings_url(
                    request, web_context.admin_event.uniq_id, started_tournaments[0].id
                )
            )
        if (
            web_context.admin_event.player_count
            and web_context.client.can_view_players_tab
        ):
            return Redirect(
                admin_event_players_url(request, web_context.admin_event.uniq_id)
            )
        if (
            web_context.admin_event.tournaments_by_uniq_id
            and web_context.client.can_view_tournaments_tab
        ):
            return Redirect(
                admin_event_tournaments_url(request, web_context.admin_event.uniq_id)
            )

        # Search for screens
        if web_context.client.can_view_public_screens:
            screens_by_screen_type_sorted_by_uniq_id: dict[ScreenType, list[Screen]]
            if web_context.client.can_view_private_screens:
                screens_by_screen_type_sorted_by_uniq_id = (
                    web_context.admin_event.screens_by_screen_type_sorted_by_uniq_id
                )
            else:
                screens_by_screen_type_sorted_by_uniq_id = web_context.admin_event.public_screens_by_screen_type_sorted_by_uniq_id
            for screen_type in ScreenType.screen_types():
                if screens_by_screen_type_sorted_by_uniq_id[screen_type]:
                    return Redirect(
                        path=request.app.route_reverse(
                            f'admin-event-{screen_type.value}-screens-tab',
                            event_uniq_id=event_uniq_id,
                        )
                    )
        # Search for rotators
        if web_context.client.can_view_public_screens:
            rotators: list[Rotator]
            if web_context.client.can_view_private_screens:
                rotators = web_context.admin_event.rotators_sorted_by_uniq_id
            else:
                rotators = web_context.admin_event.public_rotators_sorted_by_uniq_id
            if rotators:
                return Redirect(
                    path=request.app.route_reverse(
                        'admin-event-rotators-tab', event_uniq_id=event_uniq_id
                    )
                )
        # search for display controllers
        if web_context.client.can_view_public_screens:
            display_controllers: list[DisplayController]
            if web_context.client.can_view_private_screens:
                display_controllers = (
                    web_context.admin_event.display_controllers_sorted_by_uniq_id
                )
            else:
                display_controllers = (
                    web_context.admin_event.public_display_controllers_sorted_by_uniq_id
                )
            if display_controllers:
                return Redirect(
                    path=request.app.route_reverse(
                        'admin-event-displayer_controllers-tab',
                        event_uniq_id=event_uniq_id,
                    )
                )

        if web_context.client.can_view_event_basic_config:
            return Redirect(
                admin_event_config_url(request, web_context.admin_event.uniq_id)
            )

        # default display with no tab selected
        return self._admin_event_render(
            self._get_admin_event_render_context(web_context)
        )

    @get(
        path='/admin/event/{event_uniq_id:str}/config',
        name='admin-event-config-tab',
    )
    async def htmx_admin_event_config_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_config_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/event-modal/{action:str}/{event_uniq_id:str}',
        name='admin-event-modal',
    )
    async def htmx_admin_event_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_config_render(
            request,
            modal='event',
            action=action,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/event-delete-modal/{event_uniq_id:str}',
        name='admin-event-delete-modal',
        cache=1,
    )
    async def htmx_admin_event_delete_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        web_context = BaseEventAdminWebContext(request, event_uniq_id)
        return self._admin_event_render(
            web_context.template_context | {'modal': 'event-delete'}
        )

    @get(
        path='/admin/print-modal/{event_uniq_id:str}',
        name='admin-print-modal',
    )
    async def htmx_admin_print_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None = None,
    ) -> Template | ClientRedirect:
        return self._admin_event_config_render(
            request,
            modal='print',
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
        )

    @post(
        path='/admin/event-clone/{event_uniq_id:str}',
        name='admin-event-clone',
    )
    async def htmx_admin_event_clone(
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
        stored_event: StoredEvent = self._admin_validate_event_update_data(
            'clone', web_context, web_context.admin_event, data
        )
        if stored_event.errors:
            assert event_uniq_id is not None
            return self._admin_event_config_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='event',
                action='clone',
                data=data,
                errors=stored_event.errors,
            )
        uniq_id: str = stored_event.uniq_id
        event = web_context.get_admin_event()
        EventDatabase(event.uniq_id).clone(new_uniq_id=uniq_id)
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            if 'with_players' not in data:
                event_database.delete_all_stored_players()
            event_database.commit()
        Message.success(
            request,
            _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id),
        )
        return self._admin_event_config_render(request, event_uniq_id=uniq_id)

    @delete(
        path='/admin/event-delete/{event_uniq_id:str}',
        name='admin-event-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_event_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect | Redirect:
        web_context = BaseEventAdminWebContext(request, event_uniq_id)
        if web_context.error:
            return web_context.error
        event = web_context.get_admin_event()
        try:
            arch = EventDatabase(event.uniq_id).delete()
        except PermissionError as ex:
            return BaseController.redirect_error(
                request, f'Archiving the database failed: {ex}'
            )
        Message.success(
            request,
            _(
                'Event [{uniq_id}] has been deleted, the database has been archived ({arch}).'
            ).format(uniq_id=event.uniq_id, arch=arch),
        )
        return ClientRedirect(redirect_to=admin_url(request))

    @patch(path='/admin/event-update/{event_uniq_id:str}', name='admin-event-update')
    async def htmx_admin_event_update(
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
        stored_event: StoredEvent = self._admin_validate_event_update_data(
            'update', web_context, web_context.admin_event, data
        )
        if stored_event.errors:
            assert event_uniq_id is not None
            return self._admin_event_config_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='event',
                action='update',
                data=data,
                errors=stored_event.errors,
            )
        uniq_id = stored_event.uniq_id
        with EventDatabase(uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
            event_database.commit()
        Message.success(
            request,
            _('Event [{uniq_id}] has been updated.').format(uniq_id=uniq_id),
        )
        return self._admin_event_config_render(request, event_uniq_id=uniq_id)

    @patch(
        path='/admin/event-uniq-id-update/{event_uniq_id:str}',
        name='admin-event-uniq-id-update',
    )
    async def htmx_admin_event_uniq_id_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect | Redirect:
        web_context = BaseEventAdminWebContext(request, event_uniq_id, data)
        event = web_context.get_admin_event()
        new_uniq_id = WebContext.form_data_to_str(data, 'uniq_id')
        if (
            not new_uniq_id
            or not EventLoader.id_regex.match(new_uniq_id)
            or (
                new_uniq_id != event.uniq_id
                and new_uniq_id in EventLoader.all_event_ids()
            )
        ):
            # No precise error (validated in JS)
            return self.redirect_error(
                request, f'Invalid event uniq ID [{new_uniq_id}].'
            )
        if new_uniq_id != event_uniq_id:
            try:
                EventDatabase(event.uniq_id).rename(new_uniq_id)
            except PermissionError as ex:
                return self.redirect_error(
                    request,
                    _('Renaming the database failed: {ex}.').format(ex=ex),
                )
            Message.success(
                request,
                _(
                    'Event unique ID has been renamed from '
                    '[{old_uniq_id}] to [{new_uniq_id}].'
                ).format(
                    old_uniq_id=event.uniq_id,
                    new_uniq_id=new_uniq_id,
                ),
            )
        return self._admin_event_config_render(request, new_uniq_id)

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
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        errors: dict[str, str] = {}

        tournament: Tournament | None = None
        field = 'tournament_id'

        try:
            tournament_id = WebContext.form_data_to_int(data, field)
            if not tournament_id:
                raise ValueError('Tournament ID not supplied')
            tournament = web_context.admin_event.tournaments_by_id[tournament_id]
        except (ValueError, KeyError):
            errors[field] = _('Please choose the tournament.')

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
        return self._admin_event_config_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='print',
            data=data,
            errors=errors,
        )

    @staticmethod
    def download_players_as_vcf(
        event_uniq_id: str,
        players: list[Player],
    ) -> Response[str]:
        """Returns a file with all the vCards of the players."""
        data: str = ''
        for player in players:
            if not (player.mail or player.phone):
                continue
            data += 'BEGIN:VCARD\nVERSION:3.0\n'
            if player.first_name:
                data += (
                    f'N:{player.last_name.title()};{player.first_name}\n'
                    f'FN:{player.first_name} {player.last_name.title()}\n'
                )
            else:
                data += f'N:{player.last_name.title()}\nFN:{player.last_name.title()}\n'
            data += (
                f'ORG:{player.club}\n'
                f'item1.TEL:{player.phone}\n'
                f'item1.X-ABLabel:{_("Personal")}\n'
                f'item2.EMAIL;type=INTERNET:{player.mail}\n'
                f'item2.X-ABLabel:{_("Personal")}\n'
                f'CATEGORIES:{_("Chess")}\n'
                'END:VCARD\n\n'
            )
        return Response(
            content=data,
            media_type='text/x-vcard',
            headers={
                'Content-Disposition': f'attachment;{event_uniq_id}.vcf',
            },
        )

    DATASHEET_COLUMNS = [
        'last_name',
        'first_name',
        'yob',
        'mail',
        'phone',
        'gender',
        'fide_id',
        'tournament',
        'federation',
        'club',
        'owed',
        'paid',
        'comment',
        'St',
        'S',
        'Ra',
        'R',
        'Bl',
        'B',
    ]

    @classmethod
    def get_players_datasheet_extra_columns(cls) -> dict[int, list[ExtraColumn]]:
        """Returns the extra data columns added by the plugins"""
        per_plugin_columns: list[Iterable[ExtraColumn]] = (
            plugin_manager.hook.get_extra_players_datasheet_columns()
        )
        extra_columns: dict[int, list[ExtraColumn]] = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                try:
                    index = cls.DATASHEET_COLUMNS.index(extra_column.at)
                    c = extra_columns.setdefault(index, [])
                    c.append(extra_column)
                except ValueError:
                    pass

        # The dict has keys sorted from high to low so that we can insert them in that
        # order without affecting lower indexes
        return {key: extra_columns[key] for key in reversed(sorted(extra_columns))}

    @classmethod
    def get_players_datasheet_columns(cls) -> list[str]:
        """Returns the names of the columns used in the datasheets that can be downloaded."""

        header_columns = cls.DATASHEET_COLUMNS[:]

        # Add plugin columns
        extra_columns = EventAdminController.get_players_datasheet_extra_columns()
        for index, columns in extra_columns.items():
            header_columns[index:index] = [column.title for column in columns]

        return header_columns

    @classmethod
    def get_players_datasheet_data(
        cls,
        players: list[Player],
    ) -> list[list[str | int | float]]:
        """Returns the data of the datasheets that can be downloaded."""

        extra_columns = cls.get_players_datasheet_extra_columns()

        def augment_row(row, player):
            for index, columns in extra_columns.items():
                row[index:index] = [column.value(player) for column in columns]
            return row

        rows = [
            augment_row(
                [
                    player.last_name,
                    player.first_name,
                    player.year_of_birth,
                    player.mail or '',
                    player.phone or '',
                    player.gender.short_name,
                    player.fide_id or '',
                    player.tournament.uniq_id if player.tournament else '',
                    player.federation.name,
                    player.club.name if player.club else '',
                    player.owed,
                    player.paid,
                    player.comment,
                    player.get_rating(TournamentRating.STANDARD).value,
                    player.get_rating(TournamentRating.STANDARD).type.short_name,
                    player.get_rating(TournamentRating.RAPID).value,
                    player.get_rating(TournamentRating.RAPID).type.short_name,
                    player.get_rating(TournamentRating.BLITZ).value,
                    player.get_rating(TournamentRating.BLITZ).type.short_name,
                ],
                player,
            )
            for player in players
        ]
        return rows

    @classmethod
    def download_players_as_xlsx(
        cls,
        event_uniq_id: str,
        players: list[Player],
    ) -> File:
        """Returns a file with all the information of the players in an XLSX format."""
        temp_file = NamedTemporaryFile(delete=False, mode='wb', suffix='.xlsx')
        workbook = xlsxwriter.Workbook(temp_file)
        worksheet = workbook.add_worksheet()
        columns = cls.get_players_datasheet_columns()
        data = cls.get_players_datasheet_data(players)
        worksheet.add_table(
            0,
            0,
            len(data),
            len(columns) - 1,
            options={
                'columns': [{'header': column} for column in columns],
                'data': data,
            },
        )
        worksheet.autofit()
        workbook.close()
        return File(path=temp_file.name, filename=f'{event_uniq_id}.xlsx')

    @classmethod
    def download_players_as_csv(
        cls,
        event_uniq_id: str,
        players: list[Player],
    ) -> File:
        """Returns a file with all the information of the players in a CSV format (comma-separated)."""
        temp_file = NamedTemporaryFile(
            delete=False, mode='w', suffix='.csv', newline=''
        )
        writer = csv.writer(temp_file)
        writer.writerow(cls.get_players_datasheet_columns())
        writer.writerows(cls.get_players_datasheet_data(players))
        return File(path=temp_file.name, filename=f'{event_uniq_id}.csv')

    @classmethod
    def download_players_as_ods(
        cls,
        event_uniq_id: str,
        players: list[Player],
    ) -> File:
        """Returns a file with all the information of the players in an ODS format."""
        temp_file = NamedTemporaryFile(delete=False, mode='w+b', suffix='.ods')
        save_data(
            temp_file,
            [cls.get_players_datasheet_columns()]
            + cls.get_players_datasheet_data(players),
        )
        return File(path=temp_file.name, filename=f'{event_uniq_id}.ods')

    @get(
        path='/admin/download-event-players/{event_uniq_id:str}',
        name='admin-download-event-players',
    )
    async def htmx_admin_event_download_players(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        download_format: str | None = None,
        player_ids: list[int] | None = None,
    ) -> ClientRedirect | Response[str] | File:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request, event_uniq_id=event_uniq_id, data=None
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        players: list[Player] = [
            web_context.admin_event.players_by_id[player_id]
            for player_id in player_ids or []
            if player_id
        ]
        if not players:
            players = web_context.admin_event.players_sorted_by_name
        match download_format:
            case 'vcf':
                return self.download_players_as_vcf(
                    web_context.admin_event.uniq_id, players
                )
            case 'csv':
                return self.download_players_as_csv(
                    web_context.admin_event.uniq_id, players
                )
            case 'xlsx':
                return self.download_players_as_xlsx(
                    web_context.admin_event.uniq_id, players
                )
            case 'ods':
                return self.download_players_as_ods(
                    web_context.admin_event.uniq_id, players
                )
            case _:
                raise ValueError(f'download_format={download_format}')
