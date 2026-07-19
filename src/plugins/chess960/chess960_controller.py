from typing import Annotated, Any

from litestar import get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.screen import Screen
from database.sqlite.event.event_database import EventDatabase
from plugins.chess960 import PLUGIN_NAME
from plugins.chess960.utils import (
    Chess960ScreenPluginData,
    Chess960Set,
    is_valid_position_number,
    random_position_number,
)
from web.controllers.admin.base_admin_controller import AdminWebContext
from web.controllers.admin.base_event_admin_controller import BaseEventAdminController
from web.guards import ActionGuard, EventGuard


class Chess960WebContext(AdminWebContext):
    def __init__(self, request: HTMXRequest, screen_uniq_id: str):
        super().__init__(request)
        self.event = self.get_admin_event()
        self.screen_uniq_id = screen_uniq_id
        screen = self.event.screens_by_uniq_id.get(screen_uniq_id)
        if screen is None or screen.stored_screen is None:
            raise NotFoundException(f'Screen [{screen_uniq_id}] not found.')
        self.screen: Screen = screen

    def load_data(self) -> Chess960ScreenPluginData:
        assert self.screen.stored_screen is not None
        data = Chess960ScreenPluginData.from_stored_value(
            self.screen.stored_screen.plugin_data.get(PLUGIN_NAME, {})
        )
        # Drop sets whose tournament no longer exists so they disappear from
        # the modal (and are cleaned from storage on the next save).
        data.sets = [
            chess960_set
            for chess960_set in data.sets
            if chess960_set.tournament_id in self.event.tournaments_by_id
        ]
        return data

    def save_data(self, data: Chess960ScreenPluginData) -> None:
        assert self.screen.stored_screen is not None
        self.screen.stored_screen.plugin_data[PLUGIN_NAME] = data.to_stored_value()
        with EventDatabase(self.event.uniq_id, write=True) as database:
            database.update_stored_screen(self.screen.stored_screen)

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'chess960_screen': self.screen,
            'chess960_screen_uniq_id': self.screen_uniq_id,
            'chess960_tournaments': self.event.tournaments,
        }


class Chess960Controller(BaseEventAdminController):
    guards = [EventGuard(), ActionGuard(AuthAction.MANAGE_SCREENS)]

    @classmethod
    def _render_list(
        cls, web_context: Chess960WebContext, message: str | None = None
    ) -> HTMXTemplate:
        data = web_context.load_data()
        sets = []
        for index, chess960_set in enumerate(data.sets):
            tournament = web_context.event.tournaments_by_id.get(
                chess960_set.tournament_id
            )
            sets.append(
                {
                    'index': index,
                    'tournament_name': tournament.name
                    if tournament
                    else _('(unknown tournament)'),
                    'summary': ', '.join(
                        _('Round {round}: {number}').format(round=round_, number=number)
                        for round_, number in sorted(chess960_set.positions.items())
                    )
                    or _('No positions set.'),
                }
            )
        template_context = web_context.template_context | {
            'chess960_mode': 'list',
            'chess960_sets': sets,
            'chess960_message': message,
        }
        return cls._render_modal('/chess960_modal.html', template_context)

    @classmethod
    def _render_form(
        cls,
        web_context: Chess960WebContext,
        set_index: int | None,
        tournament_id: int | None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> HTMXTemplate:
        plugin_data = web_context.load_data()
        if data is None:
            data = {}
            if set_index is not None and 0 <= set_index < len(plugin_data.sets):
                chess960_set = plugin_data.sets[set_index]
                if tournament_id is None:
                    tournament_id = chess960_set.tournament_id
                if tournament_id == chess960_set.tournament_id:
                    data = {
                        f'pos_{round_}': str(number)
                        for round_, number in chess960_set.positions.items()
                    }
        tournaments = list(web_context.event.tournaments)
        if tournament_id is None and tournaments:
            tournament_id = tournaments[0].id
        tournament = (
            web_context.event.tournaments_by_id.get(tournament_id)
            if tournament_id is not None
            else None
        )
        rounds = list(range(1, tournament.rounds + 1)) if tournament else []
        template_context = web_context.template_context | {
            'chess960_mode': 'form',
            'chess960_set_index': set_index,
            'chess960_tournament_id': tournament_id,
            'chess960_rounds': rounds,
            'data': data,
            'errors': errors or {},
        }
        return cls._render_modal('/chess960_modal.html', template_context)

    @get(path='/chess960/modal/{event_uniq_id:str}', name='chess960-modal')
    async def htmx_chess960_modal(
        self,
        request: HTMXRequest,
        screen_uniq_id: str,
        mode: str | None = None,
        set_index: int | None = None,
        tournament_id: int | None = None,
    ) -> Template:
        web_context = Chess960WebContext(request, screen_uniq_id)
        if mode == 'form':
            return self._render_form(web_context, set_index, tournament_id)
        return self._render_list(web_context)

    @post(path='/chess960/set-save/{event_uniq_id:str}', name='chess960-set-save')
    async def htmx_chess960_set_save(
        self,
        request: HTMXRequest,
        screen_uniq_id: str,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        set_index: int | None = None,
    ) -> Template:
        web_context = Chess960WebContext(request, screen_uniq_id)
        errors: dict[str, str] = {}
        try:
            tournament_id = int(data.get('tournament_id', ''))
        except ValueError:
            tournament_id = None
        if tournament_id not in web_context.event.tournaments_by_id:
            errors['tournament_id'] = _('Please choose a tournament.')
        positions: dict[int, int] = {}
        for key, value in data.items():
            if not key.startswith('pos_'):
                continue
            raw = (value or '').strip()
            if not raw:
                continue
            round_ = int(key[len('pos_') :])
            try:
                number = int(raw)
            except ValueError:
                errors[key] = _('Enter a position number from 0 to 959.')
                continue
            if not is_valid_position_number(number):
                errors[key] = _('Enter a position number from 0 to 959.')
                continue
            positions[round_] = number
        if errors:
            return self._render_form(
                web_context, set_index, tournament_id, data=data, errors=errors
            )
        assert tournament_id is not None
        plugin_data = web_context.load_data()
        chess960_set = Chess960Set(tournament_id=tournament_id, positions=positions)
        if set_index is not None and 0 <= set_index < len(plugin_data.sets):
            plugin_data.sets[set_index] = chess960_set
        else:
            plugin_data.sets.append(chess960_set)
        web_context.save_data(plugin_data)
        return self._render_list(web_context, message=_('Set saved.'))

    @post(path='/chess960/set-delete/{event_uniq_id:str}', name='chess960-set-delete')
    async def htmx_chess960_set_delete(
        self,
        request: HTMXRequest,
        screen_uniq_id: str,
        set_index: int,
    ) -> Template:
        web_context = Chess960WebContext(request, screen_uniq_id)
        plugin_data = web_context.load_data()
        if 0 <= set_index < len(plugin_data.sets):
            del plugin_data.sets[set_index]
            web_context.save_data(plugin_data)
        return self._render_list(web_context, message=_('Set removed.'))

    @post(path='/chess960/randomize/{event_uniq_id:str}', name='chess960-randomize')
    async def htmx_chess960_randomize(
        self,
        request: HTMXRequest,
        screen_uniq_id: str,
        round_: int,
        data: Annotated[
            dict[str, str], Body(media_type=RequestEncodingType.URL_ENCODED)
        ],
        set_index: int | None = None,
    ) -> Template:
        web_context = Chess960WebContext(request, screen_uniq_id)
        data = dict(data)
        data[f'pos_{round_}'] = str(random_position_number())
        try:
            tournament_id = int(data.get('tournament_id', ''))
        except ValueError:
            tournament_id = None
        return self._render_form(web_context, set_index, tournament_id, data=data)
