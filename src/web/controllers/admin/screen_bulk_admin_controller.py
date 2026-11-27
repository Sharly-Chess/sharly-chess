import asyncio
from dataclasses import dataclass
from typing import Annotated

from litestar import delete, get, patch
from litestar.enums import RequestEncodingType
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Body, FromPath, FromQuery
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXRequest

from common.i18n import ngettext
from data.access_levels.actions import AuthAction
from data.event import Event
from data.screens.family import Family
from data.screens.screen import Screen
from data.screens.screen_types import ScreenType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredFamily, StoredScreen
from web.admin.screens.bulk import (
    merged_form_data,
    parse_item_ids,
    shared_form_data,
)
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
)
from web.controllers.admin.family_admin_controller import (
    FamilyAdminController,
    FamilyAdminWebContext,
)
from web.controllers.admin.screen_admin_controller import (
    ScreenAdminController,
    ScreenAdminRenderer,
    ScreenAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard
from web.messages import Message


@dataclass
class BulkSelection:
    """The screens and paged screens of one type picked on the screens tab."""

    screen_type: ScreenType
    screens: list[Screen]
    families: list[Family]

    @property
    def count(self) -> int:
        return len(self.screens) + len(self.families)

    @property
    def all_paged(self) -> bool:
        return not self.screens

    @property
    def item_ids(self) -> list[str]:
        return [screen.collection_item_id for screen in self.screens] + [
            family.collection_item_id for family in self.families
        ]

    @property
    def names(self) -> list[str]:
        return [screen.name for screen in self.screens] + [
            family.display_name for family in self.families
        ]

    @property
    def items_form_data(self) -> list[dict[str, str]]:
        return [
            WebContext.values_dict_to_form_data(
                ScreenAdminRenderer.screen_form_values(screen)
            )
            for screen in self.screens
        ] + [
            WebContext.values_dict_to_form_data(
                FamilyAdminController.family_form_values(family)
            )
            for family in self.families
        ]

    @property
    def shows_board_selection(self) -> bool:
        """Whether the paged screens all choose their boards (team matches
        are never chosen board by board)."""
        return (
            self.all_paged
            and self.screen_type.supports_fixed_boards
            and not any(family.shows_team_matches for family in self.families)
        )


class ScreenBulkAdminController(BaseEventAdminController):
    """Edits or deletes several screens of one type at once."""

    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.MANAGE_SCREENS),
    ]

    @staticmethod
    def _selection(
        event: Event, screen_type_id: str, item_ids: list[str]
    ) -> BulkSelection:
        try:
            screen_ids, family_ids = parse_item_ids(item_ids)
        except ValueError:
            raise ClientException(f'Invalid screen ids {item_ids}.') from None
        try:
            screens = [event.basic_screens_by_id[screen_id] for screen_id in screen_ids]
            families = [event.families_by_id[family_id] for family_id in family_ids]
        except KeyError as error:
            raise NotFoundException(f'Screen [{error}] not found.') from None
        if not screens and not families:
            raise ClientException('No screen selected.')
        if any(screen.type != screen_type_id for screen in screens) or any(
            family.type != screen_type_id for family in families
        ):
            raise ClientException(f'Not all the screens are [{screen_type_id}].')
        return BulkSelection(
            screen_type=screens[0].screen_type if screens else families[0].screen_type,
            screens=screens,
            families=families,
        )

    @staticmethod
    def _form_item_ids(data: dict[str, str]) -> list[str]:
        return [item_id for item_id in data.get('item_ids', '').split(';') if item_id]

    @staticmethod
    def _form_changed_fields(data: dict[str, str]) -> list[str]:
        return [field for field in data.get('bulk_changed', '').split(';') if field]

    @classmethod
    def _render_bulk_modal(
        cls,
        request: HTMXRequest,
        action: str,
        screen_type_id: str,
        item_ids: list[str],
        data: dict[str, str] | None = None,
        changed_fields: list[str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template:
        web_context = ScreenAdminWebContext(request, screen_type_id=screen_type_id)
        event = web_context.get_admin_event()
        selection = cls._selection(event, screen_type_id, item_ids)
        changed_fields = changed_fields or []
        shared, mixed = shared_form_data(selection.items_form_data)
        if data is not None:
            shared |= {field: data[field] for field in changed_fields if field in data}
            for field in changed_fields:
                if field not in data:
                    shared.pop(field, None)
            mixed -= set(changed_fields)
        return cls._admin_base_event_render(
            web_context.template_context
            | {
                'admin_event_tab': 'admin-event-screens-tab',
                'modal': 'screens_bulk',
                'action': action,
                'bulk_selection': selection,
                'bulk_mixed': sorted(mixed),
                'bulk_changed': changed_fields,
                'tournament_options': web_context.screen_tournament_options(
                    selection.screen_type
                ),
                'timer_options': cls._get_timer_options(event),
                **cls._display_controller_destination_context(event),
                'ranking_crosstable_options': cls._get_ranking_crosstable_options(),
                'players_player_format_options': web_context.get_players_screen_player_format_options(),
                'players_board_format_options': web_context.get_players_screen_board_format_options(),
                'players_opponent_format_options': web_context.get_players_screen_opponent_format_options(),
                'data': shared,
                'errors': errors or {},
            }
        )

    @get(
        path='/screens-bulk-modal/{action:str}/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screens-bulk-modal',
    )
    async def htmx_admin_screens_bulk_modal(
        self,
        request: HTMXRequest,
        action: FromPath[str],
        screen_type: FromPath[str],
        item_ids: FromQuery[list[str] | None] = None,
    ) -> Template:
        if action not in ('update', 'delete'):
            raise ClientException(f'action=[{action}]')
        return self._render_bulk_modal(request, action, screen_type, item_ids or [])

    @staticmethod
    def _validated_screen(
        request: HTMXRequest,
        screen: Screen,
        data: dict[str, str],
        changed_fields: list[str],
    ) -> StoredScreen:
        return ScreenAdminController._admin_validate_screen_update_data(
            'update',
            ScreenAdminWebContext(request, screen_id=screen.id),
            merged_form_data(
                WebContext.values_dict_to_form_data(
                    ScreenAdminRenderer.screen_form_values(screen)
                ),
                data,
                changed_fields,
            ),
        )

    @staticmethod
    def _validated_family(
        request: HTMXRequest,
        family: Family,
        data: dict[str, str],
        changed_fields: list[str],
    ) -> StoredFamily:
        return FamilyAdminController._admin_validate_family_update_data(
            'update',
            FamilyAdminWebContext(request, family_id=family.id),
            merged_form_data(
                WebContext.values_dict_to_form_data(
                    FamilyAdminController.family_form_values(family)
                ),
                data,
                changed_fields,
            ),
        )

    @patch(
        path='/screens-bulk-update/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screens-bulk-update',
    )
    async def htmx_admin_screens_bulk_update(
        self,
        request: HTMXRequest,
        screen_type: FromPath[str],
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | Redirect:
        form_data = WebContext.flatten_list_data(data)
        item_ids = self._form_item_ids(form_data)
        changed_fields = self._form_changed_fields(form_data)
        event = ScreenAdminWebContext(request).get_admin_event()
        selection = self._selection(event, screen_type, item_ids)
        stored_screens: list[StoredScreen] = []
        stored_families: list[StoredFamily] = []
        errors: dict[str, str] = {}
        for screen in selection.screens:
            # The validation checks that a background image URL answers.
            stored_screen = await asyncio.to_thread(
                self._validated_screen, request, screen, form_data, changed_fields
            )
            stored_screens.append(stored_screen)
            for field, error in stored_screen.errors.items():
                errors.setdefault(field, f'{screen.name}: {error}')
        for family in selection.families:
            stored_family = self._validated_family(
                request, family, form_data, changed_fields
            )
            stored_families.append(stored_family)
            for field, error in stored_family.errors.items():
                errors.setdefault(field, f'{family.display_name}: {error}')
        display_controller_ids: list[int] | None = (
            self._read_display_controller_ids(form_data, errors, event)
            if 'display_controller_ids' in changed_fields
            else None
        )
        if errors:
            return self._render_bulk_modal(
                request,
                'update',
                screen_type,
                item_ids,
                data=form_data,
                changed_fields=changed_fields,
                errors=errors,
            )
        if changed_fields:
            with EventDatabase(event.uniq_id, write=True) as event_database:
                for stored_screen in stored_screens:
                    event_database.update_stored_screen(stored_screen)
                    assert stored_screen.id is not None
                    if display_controller_ids is not None:
                        event_database.set_stored_screen_display_controllers(
                            stored_screen.id, display_controller_ids
                        )
                for stored_family in stored_families:
                    event_database.update_stored_family(stored_family)
                    assert stored_family.id is not None
                    if display_controller_ids is not None:
                        event_database.set_stored_family_display_controllers(
                            stored_family.id, display_controller_ids
                        )
            Message.success(
                request,
                ngettext(
                    '%(num)d screen has been updated.',
                    '%(num)d screens have been updated.',
                    selection.count,
                )
                % {'num': selection.count},
            )
        return ScreenAdminRenderer._admin_event_screens_render(
            request, reload_event=True
        )

    @delete(
        path='/screens-bulk-delete/{event_uniq_id:str}/{screen_type:str}',
        name='admin-screens-bulk-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screens_bulk_delete(
        self,
        request: HTMXRequest,
        screen_type: FromPath[str],
        item_ids: FromQuery[list[str] | None] = None,
    ) -> Template | Redirect:
        event = ScreenAdminWebContext(request).get_admin_event()
        selection = self._selection(event, screen_type, item_ids or [])
        with EventDatabase(event.uniq_id, write=True) as event_database:
            for screen in selection.screens:
                event_database.delete_stored_screen(screen.id)
            for family in selection.families:
                event_database.delete_stored_family(family.id)
        Message.success(
            request,
            ngettext(
                '%(num)d screen has been deleted.',
                '%(num)d screens have been deleted.',
                selection.count,
            )
            % {'num': selection.count},
        )
        return ScreenAdminRenderer._admin_event_screens_render(
            request, reload_event=True
        )
