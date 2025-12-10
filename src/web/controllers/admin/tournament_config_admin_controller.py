from dataclasses import replace
from logging import Logger
from typing import Annotated, Any

from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.event import Event

from litestar import get, patch
from litestar.plugins.htmx import HTMXRequest, HTMXTemplate
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from common.i18n import (
    _,
)

from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent
from plugins.manager import plugin_manager
from utils.enum import PlayerRatingType, Result
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard
from web.messages import Message

logger: Logger = get_logger()


class TournamentConfigAdminController(BaseEventAdminController):
    guards = [EventGuard(), ActionGuard(AuthAction.MANAGE_EVENTS)]

    @classmethod
    def _prepare_modal_data(
        cls,
        request: HTMXRequest,
        admin_event: Event,
    ) -> dict[str, Any]:
        stored_event = admin_event.stored_event

        return WebContext.values_dict_to_form_data(
            {
                'player_rating_type': stored_event.player_rating_type,
                'location': stored_event.location,
                'record_illegal_moves': stored_event.record_illegal_moves,
                'rules': stored_event.rules,
                'override_unrated_rapid_blitz': stored_event.override_unrated_rapid_blitz,
                'three_points_for_a_win': stored_event.three_points_for_a_win,
                'pab_value': stored_event.pab_value,
            }
        )

    @classmethod
    def _read_form_data(
        cls,
        admin_event: Event,
        data: dict[str, str] | None = None,
    ) -> tuple[StoredEvent | None, dict[str, str]]:
        if data is None:
            data = {}
        errors: dict[str, str] = {}

        location = WebContext.form_data_to_str(data, 'location')
        player_rating_type: int = (
            WebContext.form_data_to_int(data, 'player_rating_type')
            or PlayerRatingType.FIDE.value
        )

        record_illegal_moves = cls._admin_validate_record_illegal_moves_update_data(
            data, errors
        )
        rules = cls._admin_validate_rules_update_data(data, errors)
        override_unrated_rapid_blitz = WebContext.form_data_to_bool(
            data, 'override_unrated_rapid_blitz'
        )
        three_points_for_a_win = WebContext.form_data_to_bool(
            data, 'three_points_for_a_win'
        )
        pab_value = WebContext.form_data_to_int(data, 'pab_value') or Result.WIN.value

        if errors:
            return None, errors

        stored_event = replace(
            admin_event.stored_event,
            location=location,
            player_rating_type=player_rating_type,
            record_illegal_moves=record_illegal_moves,
            rules=rules,
            override_unrated_rapid_blitz=override_unrated_rapid_blitz,
            three_points_for_a_win=three_points_for_a_win,
            pab_value=pab_value,
        )
        return stored_event, errors

    def _modal_context(
        self,
        event: Event,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            'modal': 'tournaments_config',
            'data': data,
            'player_rating_type_options': {
                str(PlayerRatingType.FIDE.value): _('FIDE'),
                str(PlayerRatingType.NATIONAL.value): _(
                    'National *** NAME FOR RATING TYPE NATIONAL'
                ),
            },
            'three_points_for_a_win_options': {
                str(Result.WIN.value): _('Win'),
                str(Result.DRAW.value): _('Draw'),
                str(Result.LOSS.value): _('Loss'),
            },
            'plugin_templates': plugin_manager.hook_for_event(
                event, 'get_tournament_config_template'
            )(),
            'errors': errors or {},
        }

    @get(
        path='/tournament-config-modal/{event_uniq_id:str}',
        name='admin-tournament-config-modal',
    )
    async def htmx_admin_tournament_config_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        data = self._prepare_modal_data(request, web_context.get_admin_event())
        template_context = self._modal_context(event, data)

        return self._admin_base_event_render(
            web_context.template_context | template_context,
        )

    @patch(
        path='/tournament-update-config/{event_uniq_id:str}',
        name='admin-tournament-update-config',
        guards=[ActionGuard(AuthAction.UPDATE_EVENT)],
    )
    async def htmx_admin_tournament_update_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        stored_event, errors = self._read_form_data(web_context.get_admin_event(), data)
        if not stored_event:
            template_context = self._modal_context(event, data, errors=errors)
            return self._admin_base_event_render(
                web_context.template_context | template_context,
            )

        uniq_id = stored_event.uniq_id
        with EventDatabase(uniq_id, write=True) as database:
            database.update_stored_event(stored_event)

        Message.success(
            request,
            _('Tournament defaults have been updated.').format(uniq_id=uniq_id),
        )

        return HTMXTemplate(
            template_name='common/empty_modal_and_messages.html',
            context={'messages': Message.messages(request)},
            re_target='#modal-wrapper',
            trigger_event='close_modal',
            after='settle',
        )
