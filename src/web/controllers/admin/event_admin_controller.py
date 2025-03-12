import csv
from logging import Logger
from string import capwords
from tempfile import NamedTemporaryFile
from typing import Annotated, Any

from plugins.hookspec import ExtraColumn
from web.controllers.admin.base_event_admin_controller import BaseEventAdminController, BaseEventAdminWebContext
import xlsxwriter
from litestar import get, patch, delete, post, Response
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template, Redirect, File
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import ClientRedirect
from pyexcel_ods3 import save_data

from common import unicode_normalize
from common.i18n import _
from common.logger import get_logger
from common.papi_web_config import PapiWebConfig
from data.loader import EventLoader
from data.player import Player, Club, Federation
from data.util import PlayerGender, PlayerCategory, PrintSplit, TournamentRating, PrintDocument
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from plugins.manager import plugin_manager
from web.controllers.admin.base_admin_controller import (
    AdminWebContext,
)
from web.controllers.base_controller import BaseController
from web.controllers.base_controller import WebContext
from web.messages import Message
from web.session import SessionHandler

logger: Logger = get_logger()


class EventAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_tab_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: str | None = None,
        admin_event_tab: str | None = None,
        modal: str | None = None,
        action: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=admin_event_tab,
            data=data,
        )
        if web_context.error:
            return web_context.error
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )
        match modal:
            case None:
                pass
            case 'event':
                if data is None:
                    data = cls._prepare_event_modal_data(
                        action, request, web_context.admin_event
                    )
                    stored_event: StoredEvent = cls._admin_validate_event_update_data(
                        action, request, web_context.admin_event, data
                    )
                    errors = stored_event.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'federations': PapiWebConfig.federations,
                    'record_illegal_moves_options': cls._get_record_illegal_moves_options(
                        PapiWebConfig.default_record_illegal_moves_number
                    ),
                    'timer_color_texts': cls._get_timer_color_texts(
                        PapiWebConfig.default_timer_delays
                    ),
                    'background_images_jstree_data': cls.background_images_jstree_data(
                        data['background_image']
                    )
                    if action
                    in [
                        'update',
                        'clone',
                    ]
                    else {},
                    'modal': 'event',
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'print':
                if data is None:
                    event = web_context.admin_event
                    if len(event.tournaments_sorted_by_uniq_id) == 1:
                        tournament_id = (
                            event.tournaments_sorted_by_uniq_id[0].id
                        )
                    data = (
                        {
                            'tournament_id': WebContext.value_to_form_data(
                                tournament_id
                            ),
                            'split': WebContext.value_to_form_data(
                                PrintSplit.NO_SPLIT
                            ),
                            'document': WebContext.value_to_form_data(
                                PrintDocument.PLAYER_LIST
                            )
                        }
                    )

                template_context |= {
                    'modal': 'print',
                    'tournament_options': web_context.get_tournament_options(),
                    'split_options': web_context.get_print_split_options(),
                    'document_options': (
                        web_context.get_print_document_options()
                    ),
                    'data': data,
                    'errors': errors or {},
                }
            case _:
                raise ValueError(f'modal=[{modal}]')
        return cls._admin_event_render(template_context)

    def _admin_event(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: str | None = None,
        admin_event_tab: str | None = None,
        locale: str | None = None,
        modal: str | None = None,
        action: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        self.set_locale(request, locale)
        return self._admin_event_tab_render(
            request,
            admin_event_tab=admin_event_tab,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            modal=modal,
            action=action,
            data=data,
            errors=errors,
        )

    @get(
        path='/admin/event/{event_uniq_id:str}',
        name='admin-event',
        cache=1,
    )
    async def htmx_admin_event(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        locale: str | None,
    ) -> Template | ClientRedirect:
        return self._admin_event(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=None,
            locale=locale,
        )

    @get(
        path='/admin/event/{event_uniq_id:str}/{admin_event_tab:str}',
        name='admin-event-tab',
        cache=1,
    )
    async def htmx_admin_event_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        admin_event_tab: str,
        locale: str | None,
        admin_screens_show_family_screens: bool | None,
        admin_screens_show_details: bool | None,
        admin_families_show_details: bool | None,
        admin_rotators_show_details: bool | None,
        admin_tournaments_show_details: bool | None,
        admin_screens_show_boards: bool | None,
        admin_screens_show_input: bool | None,
        admin_screens_show_players: bool | None,
        admin_screens_show_results: bool | None,
        admin_screens_show_ranking: bool | None,
        admin_screens_show_image: bool | None,
        admin_players_sort: str | None = None,
        admin_players_filter_columns: list[str] | None = None,
        admin_players_filter_federations: list[str] | None = None,
        admin_players_filter_clubs: list[str] | None = None,
        admin_players_filter_clubs_search: str | None = None,
        admin_players_filter_genders: list[int] | None = None,
        admin_players_filter_check_ins: list[int] | None = None,
        admin_players_filter_tournaments: list[int] | None = None,
        admin_players_filter_categories: list[int] | None = None,
        admin_players_filter_name: str | None = None,
        admin_players_clear_filters: int | None = None,
    ) -> Template | ClientRedirect:
        match admin_event_tab:
            case 'config':
                pass
            case 'tournaments':
                if admin_tournaments_show_details is not None:
                    SessionHandler.set_session_admin_tournaments_show_details(
                        request, admin_tournaments_show_details
                    )
            case 'players':
                if admin_players_sort is not None:
                    SessionHandler.set_session_admin_players_sort(
                        request, admin_players_sort
                    )
                elif admin_players_filter_columns is not None:
                    SessionHandler.set_session_admin_players_filter_columns(
                        request,
                        [
                            column
                            for column in admin_players_filter_columns
                            if column  # '' must be ignored
                        ],
                    )
                elif admin_players_filter_federations is not None:
                    SessionHandler.set_session_admin_players_filter_federations(
                        request,
                        [
                            Federation.from_query_param(query_param)
                            for query_param in admin_players_filter_federations
                            if query_param  # '' must be ignored
                        ],
                    )
                elif admin_players_filter_clubs is not None:
                    SessionHandler.set_session_admin_players_filter_clubs(
                        request,
                        [
                            Club.from_query_param(query_param)
                            for query_param in admin_players_filter_clubs
                            if query_param  # '' must be ignored
                        ],
                    )
                elif admin_players_filter_genders is not None:
                    SessionHandler.set_session_admin_players_filter_genders(
                        request,
                        [
                            PlayerGender(query_param)
                            for query_param in admin_players_filter_genders
                            if query_param >= 0  # -1 must be ignored
                        ],
                    )
                elif admin_players_filter_check_ins is not None:
                    SessionHandler.set_session_admin_players_filter_check_ins(
                        request,
                        [
                            {
                                0: None,
                                1: False,
                                2: True,
                            }.get(query_param, None)
                            for query_param in admin_players_filter_check_ins
                            if query_param >= 0  # -1 must be ignored
                        ],
                    )
                elif admin_players_filter_tournaments is not None:
                    SessionHandler.set_session_admin_players_filter_tournaments(
                        request,
                        [
                            query_param
                            for query_param in admin_players_filter_tournaments
                            if query_param > 0  # 0 must be ignored
                        ],
                    )
                elif admin_players_filter_categories is not None:
                    SessionHandler.set_session_admin_players_filter_categories(
                        request,
                        [
                            PlayerCategory(query_param)
                            for query_param in admin_players_filter_categories
                            if query_param >= 0  # -1 must be ignored
                        ],
                    )
                elif admin_players_filter_name is not None:
                    SessionHandler.set_session_admin_players_filter_name(
                        request, unicode_normalize(admin_players_filter_name).lower()
                    )
                elif admin_players_filter_clubs_search is not None:
                    SessionHandler.set_session_admin_players_filter_clubs_search(
                        request, unicode_normalize(admin_players_filter_clubs_search).lower()
                    )
                elif admin_players_clear_filters:
                    SessionHandler.set_session_admin_players_filter_federations(
                        request, []
                    )
                    SessionHandler.set_session_admin_players_filter_clubs(request, [])
                    SessionHandler.set_session_admin_players_filter_genders(request, [])
                    SessionHandler.set_session_admin_players_filter_check_ins(
                        request, []
                    )
                    SessionHandler.set_session_admin_players_filter_tournaments(
                        request, []
                    )
                    SessionHandler.set_session_admin_players_filter_categories(
                        request, []
                    )
                    SessionHandler.set_session_admin_players_filter_name(request, '')
                    SessionHandler.set_session_admin_players_filter_clubs_search(request, '')
                    plugin_manager.hook.clear_player_filters(request=request)
            case 'screens':
                if admin_screens_show_family_screens is not None:
                    SessionHandler.set_session_admin_screens_show_family_screens(
                        request, admin_screens_show_family_screens
                    )
                if admin_screens_show_details is not None:
                    SessionHandler.set_session_admin_screens_show_details(
                        request, admin_screens_show_details
                    )
                screen_types: list[str] = (
                    SessionHandler.get_session_admin_screens_screen_types(request)
                )
                for screen_type, param in {
                    'boards': admin_screens_show_boards,
                    'input': admin_screens_show_input,
                    'players': admin_screens_show_players,
                    'results': admin_screens_show_results,
                    'ranking': admin_screens_show_ranking,
                    'image': admin_screens_show_image,
                }.items():
                    if param is not None:
                        if param:
                            screen_types.append(screen_type)
                        else:
                            screen_types.remove(screen_type)
                        SessionHandler.set_session_admin_screens_screen_types(
                            request, screen_types
                        )
                        continue
            case 'families':
                if admin_families_show_details is not None:
                    SessionHandler.set_session_admin_families_show_details(
                        request, admin_families_show_details
                    )
            case 'rotators':
                if admin_rotators_show_details is not None:
                    SessionHandler.set_session_admin_rotators_show_details(
                        request, admin_rotators_show_details
                    )
            case 'timers':
                pass
            case _:
                raise ValueError(f'admin_event_tab={admin_event_tab}')
        return self._admin_event(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=admin_event_tab,
            locale=locale,
        )

    @get(
        path='/admin/event-modal/{action:str}/{event_uniq_id:str}',
        name='admin-event-modal',
        cache=1,
    )
    async def htmx_admin_event_modal(
        self,
        request: HTMXRequest,
        action: str,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event(
            request,
            modal='event',
            action=action,
            event_uniq_id=event_uniq_id,
        )
        
    @get(
        path='/admin/print-modal/{event_uniq_id:str}',
        name='admin-print-modal',
    )
    async def htmx_admin_print_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: str | None = None,
    ) -> Template | ClientRedirect:
        return self._admin_event(
            request,
            modal='print',
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
        )

    def _admin_event_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        action: str,
        event_uniq_id: str | None,
    ) -> Template | ClientRedirect | Redirect:
        match action:
            case 'clone' | 'update' | 'delete':
                web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    admin_event_tab=None,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        stored_event: StoredEvent = self._admin_validate_event_update_data(
            action, request, web_context.admin_event, data
        )
        if stored_event.errors:
            return self._admin_event_tab_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='event',
                action=action,
                data=data,
                errors=stored_event.errors,
            )
        uniq_id: str = stored_event.uniq_id
        event_loader = EventLoader.get(request=request)
        match action:
            case 'update':
                rename: bool = uniq_id != web_context.admin_event.uniq_id
                if rename:
                    event_loader.clear_cache(web_context.admin_event.uniq_id)
                    try:
                        EventDatabase(web_context.admin_event.uniq_id).rename(
                            new_uniq_id=uniq_id
                        )
                    except PermissionError as ex:
                        return BaseController.redirect_error(
                            request,
                            _('Renaming the database failed: {ex}.').format(ex=ex),
                        )
                with EventDatabase(uniq_id, write=True) as event_database:
                    event_database.update_stored_event(stored_event)
                    event_database.commit()
                if rename:
                    Message.success(
                        request,
                        _(
                            'Event [{old_uniq_id}] has been renamed ([{new_uniq_id}]) and updated.'
                        ).format(
                            old_uniq_id=web_context.admin_event.uniq_id,
                            new_uniq_id=uniq_id,
                        ),
                    )
                else:
                    Message.success(
                        request,
                        _('Event [{uniq_id}] has been updated.').format(
                            uniq_id=uniq_id
                        ),
                    )
                event_loader.clear_cache(uniq_id)
                return self._admin_event_tab_render(request, event_uniq_id=uniq_id)
            case 'clone':
                EventDatabase(web_context.admin_event.uniq_id).clone(
                    new_uniq_id=uniq_id
                )
                with EventDatabase(uniq_id, write=True) as event_database:
                    event_database.update_stored_event(stored_event)
                    event_database.commit()
                Message.success(
                    request,
                    _('Event [{uniq_id}] has been created.').format(uniq_id=uniq_id),
                )
                event_loader.clear_cache(uniq_id)
                return self._admin_event_tab_render(request, event_uniq_id=uniq_id)
            case 'delete':
                try:
                    arch = EventDatabase(web_context.admin_event.uniq_id).delete()
                except PermissionError as ex:
                    return BaseController.redirect_error(
                        request, f'Archiving the database failed: {ex}'
                    )
                event_loader.clear_cache(web_context.admin_event.uniq_id)
                Message.success(
                    request,
                    _(
                        'Event [{uniq_id}] has been deleted, the database has been archived ({arch}).'
                    ).format(uniq_id=web_context.admin_event.uniq_id, arch=arch),
                )
                return self._admin_render(
                    AdminWebContext(request, data=None, admin_tab=None)
                )
            case _:
                raise ValueError(f'action=[{action}]')

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
    ) -> Template | ClientRedirect:
        return self._admin_event_update(
            request, data=data, action='clone', event_uniq_id=event_uniq_id
        )

    @delete(
        path='/admin/event-delete/{event_uniq_id:str}',
        name='admin-event-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_event_delete(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_update(
            request, data=data, action='delete', event_uniq_id=event_uniq_id
        )

    @patch(path='/admin/event-update/{event_uniq_id:str}', name='admin-event-update')
    async def htmx_admin_event_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_update(
            request, data=data, action='update', event_uniq_id=event_uniq_id
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
    ) -> Template | ClientRedirect:
        web_context: BaseEventAdminWebContext = BaseEventAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            admin_event_tab=None,
            data=data,
        )
        if web_context.error:
            return web_context.error
        errors: dict[str, str] = {}
        if data is None:
            data = {}

        tournament: Tournament | None = None
        field: str = 'tournament_id'
        try:
            tournament = web_context.admin_event.tournaments_by_id[
                WebContext.form_data_to_int(data, field)
            ]
        except (ValueError, KeyError):
            errors[field] = _('Please choose the tournament.')

        document: PrintDocument | None = None
        field = 'document'
        try:
            document = PrintDocument(
                WebContext.form_data_to_str(data, field)
            )
        except ValueError:
            errors[field] = _('Please choose the document.')

        field = 'round'
        round_: int | None = None
        try:
            round_ = WebContext.form_data_to_int(data, field, minimum=1)
        except ValueError:
            errors[field] = _('A positive integer is expected.')
        if round_ is not None:
            if tournament:
                if round_ > tournament.rounds:
                    errors[field] = _(
                        'Not part of the selected tournament ({rounds} rounds).'
                    ).format(rounds=tournament.rounds)
                elif document and (document.is_ranking or document.is_crosstable):
                    max_round = tournament.max_ranking_round
                    if max_round is not None and round_ > max_round:
                        errors[field] = _(
                            'Round not finished (last finished: {round}).'
                        ).format(round=max_round)

        if len(errors):
            return self._admin_event(
                request,
                modal='print',
                event_uniq_id=event_uniq_id,
                data=data,
                errors=errors,
            )

        # Clear the modal contents, and send an event
        return HTMXTemplate(
            template_name='common/empty_modal.html',
            re_target='#modal-wrapper',
            trigger_event="do_print",
            after="receive",
            params={
                "event_uniq_id": event_uniq_id,
                "tournament_id": tournament.id,
                "split": data['split'],
                "document": data['document'],
                "round": data['round'],
            }
        )
            
    @staticmethod
    def download_players_as_vcf(
        event_uniq_id: str,
        players: list[Player],
    ) -> Response[str]:
        """Returns a file with all the vCards of the players."""
        data: str = ''
        for player in players:
            if player.mail or player.phone:
                data += 'BEGIN:VCARD\n'
                data += 'VERSION:3.0\n'
                if player.first_name:
                    data += f'N:{capwords(player.last_name)};{player.first_name}\n'
                    data += f'FN:{player.first_name} {capwords(player.last_name)}\n'
                else:
                    data += f'N:{capwords(player.last_name)}\n'
                    data += f'FN:{capwords(player.last_name)}\n'
                data += f'ORG:{player.club}\n'
                data += f'item1.TEL:{player.phone}\n'
                data += 'item1.X-ABLabel:' + _('Personal') + '\n'
                data += f'item2.EMAIL;type=INTERNET:{player.mail}\n'
                data += 'item2.X-ABLabel:' + _('Personal') + '\n'
                data += 'CATEGORIES:' + _('Chess') + '\n'
                data += 'END:VCARD\n\n'
        return Response(
            content=data,
            media_type='text/x-vcard',
            headers={
                'Content-Disposition': f'attachment;{event_uniq_id}.vcf',
            },
        )

    datasheet_columns = [
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
        'St',
        'S',
        'Ra',
        'R',
        'Bl',
        'B',
    ]
    
    @staticmethod
    def get_players_datasheet_extra_columns() -> dict[int, ExtraColumn]:
        """Returns the extra data columns added by the plugins"""
        per_plugin_columns = plugin_manager.hook.get_extra_players_datasheet_columns()
        extra_columns = {}
        for plugin_columns in per_plugin_columns:
            for extra_column in plugin_columns:
                try:
                    index = EventAdminController.datasheet_columns.index(extra_column.at)
                    c = extra_columns.setdefault(index, [])
                    c.append(extra_column)
                except ValueError:
                    pass
        
        # The dict has keys sorted from high to low so that we can insert them in that
        # order without affecting lower indexes
        return { key: extra_columns[key] for key in reversed(sorted(extra_columns)) }
        
    @staticmethod
    def get_players_datasheet_columns() -> list[str]:
        """Returns the names of the columns used in the datasheets that can be downloaded."""
       
        header_columns = EventAdminController.datasheet_columns[:]
        
        # Add plugin columns
        extra_columns = EventAdminController.get_players_datasheet_extra_columns()
        for index, columns in extra_columns.items():
            header_columns[index:index] = [column.title for column in columns]
            
        return header_columns
            

    @staticmethod
    def get_players_datasheet_data(
        players: list[Player],
    ) -> list[list[str | int | float]]:
        """Returns the data of the datasheets that can be downloaded."""

        extra_columns = EventAdminController.get_players_datasheet_extra_columns()
        
        def augment_row(row, player):
            for index, columns in extra_columns.items():
                row[index:index] = [column.value(player) for column in columns]
            return row
                
        rows = [
            augment_row([
                player.last_name,
                player.first_name,
                player.year_of_birth,
                player.mail,
                player.phone,
                player.gender.short_name,
                player.fide_id,
                player.tournament.uniq_id,
                player.federation.name,
                player.club.name,
                player.ratings[TournamentRating.STANDARD],
                player.rating_types[TournamentRating.STANDARD].short_name,
                player.ratings[TournamentRating.RAPID],
                player.rating_types[TournamentRating.RAPID].short_name,
                player.ratings[TournamentRating.BLITZ],
                player.rating_types[TournamentRating.BLITZ].short_name,
            ], player)
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
        temp_file = NamedTemporaryFile(delete=False, mode='w', suffix='.ods')
        save_data(
            temp_file,
            cls.get_players_datasheet_columns()
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
            request, event_uniq_id=event_uniq_id, admin_event_tab=None, data=None
        )
        if web_context.error:
            return web_context.error
        players: list[Player] = [
            web_context.admin_event.players_by_id[player_id]
            for player_id in player_ids
            if player_id
        ]
        if not len(players):
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

