from typing import Annotated, Any


from litestar import get
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template

from data.board import Board
from data.event import Event
from data.player import Player
from data.tournament import Tournament
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)


class PairingsAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request,
            event_uniq_id=event_uniq_id,
            data=data,
        )
        assert self.admin_event is not None
        self.admin_tournament: Tournament | None = None
        if self.error:
            return

        if (
            tournament_id is None
            and len(self.admin_event.tournaments_sorted_by_uniq_id) > 0
        ):
            tournament_id = self.admin_event.tournaments_sorted_by_uniq_id[0].id

        if tournament_id:
            try:
                self.admin_tournament = self.admin_event.tournaments_by_id[
                    tournament_id
                ]
            except KeyError:
                self._redirect_error(f'Tournament [{tournament_id}] not found.')
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_tournament': self.admin_tournament,
        }


class PairingsAdminController(BaseEventAdminController):
    @classmethod
    def _admin_event_pairings_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        tournament_id: int | None = None,
        round: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: PairingsAdminWebContext = PairingsAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError('admin_event not defined')
        admin_event: Event = web_context.admin_event
        admin_tournament: Tournament | None = web_context.admin_tournament
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        )

        admin_round = (
            round
            if round is not None
            else admin_tournament.current_round
            if admin_tournament is not None
            else 0
        )

        admin_boards: list[Board] = []
        admin_unpaired: list[Player] = []
        if admin_tournament is not None:
            if admin_round < admin_tournament.current_round:
                admin_tournament.calculate_points_before_round(before_round=admin_round)
                admin_boards, admin_unpaired = admin_tournament.build_boards(
                    admin_round
                )
            else:
                admin_boards, admin_unpaired = admin_tournament.build_boards()

        template_context |= {
            'admin_event_tab': 'admin-event-pairings-tab',
            'admin_event': admin_event,
            'admin_tournament': admin_tournament,
            'admin_tournament_id': web_context.value_to_form_data(admin_tournament.id)
            if admin_tournament
            else None,
            'tournament_options': web_context.get_tournament_options(),
            'admin_round': admin_round,
            'admin_boards': admin_boards,
            'admin_unpaired': admin_unpaired,
        }

        return cls._admin_event_render(template_context)

    @get(
        path=[
            '/admin/event/{event_uniq_id:str}/pairings',
            '/admin/event/{event_uniq_id:str}/pairings/{tournament_id:int}',
            '/admin/event/{event_uniq_id:str}/pairings/{tournament_id:int}/{round:int}',
        ],
        name='admin-event-pairings-tab',
        cache=1,
    )
    async def htmx_admin_pairings_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        tournament_id: int | None,
        round: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_pairings_render(
            request,
            event_uniq_id=event_uniq_id,
            tournament_id=tournament_id,
            round=round,
        )
