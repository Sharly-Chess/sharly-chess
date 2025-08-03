import time

from litestar.exceptions import PermissionDeniedException
from litestar.handlers import BaseRouteHandler
from litestar_htmx import HTMXRequest

from data.auth.client import Client
from data.event import Event
from data.screen import Screen
from data.tournament import Tournament
from web.utils import RequestUtils


class Guard:
    @classmethod
    def event_is_visible(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if the event of the request is not visible."""
        event: Event = RequestUtils.get_event(request)
        client: Client = RequestUtils.get_client(request)
        if not event.public:
            if not client.can_view_private_events:
                raise PermissionDeniedException(
                    'You are not allowed to view private events.'
                )
        if not event.current(now := time.time()):
            if not client.can_view_passed_coming_events:
                if event.passed(now):
                    raise PermissionDeniedException(
                        'You are not allowed to view passed events.'
                    )
                else:
                    raise PermissionDeniedException(
                        'You are not allowed to view coming events.'
                    )

    @classmethod
    def screen_is_visible(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if the screen of the request is not visible."""
        client: Client = RequestUtils.get_client(request)
        screen: Screen = RequestUtils.get_screen(request)
        if screen.public:
            if not client.can_view_public_screens:
                raise PermissionDeniedException(
                    'You are not allowed to view public screens.'
                )
        else:
            if not client.can_view_private_screens:
                raise PermissionDeniedException(
                    'You are not allowed to view private screens.'
                )

    @classmethod
    def rotator_is_visible(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if the rotator of the request is not visible."""
        client: Client = RequestUtils.get_client(request)
        rotator, screen_index, screen = RequestUtils.get_rotator(request)
        if rotator.public:
            if not client.can_view_public_screens:
                raise PermissionDeniedException(
                    'You are not allowed to view public rotators.'
                )
        else:
            if not client.can_view_private_screens:
                raise PermissionDeniedException(
                    'You are not allowed to view private rotators.'
                )

    @classmethod
    def display_controller_is_visible(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if the display controller of the request is not visible."""
        client: Client = RequestUtils.get_client(request)
        display_controller, rotator_screen_index, screen = (
            RequestUtils.get_display_controller(request)
        )
        if display_controller.public:
            if not client.can_view_public_screens:
                raise PermissionDeniedException(
                    'You are not allowed to view public display controllers.'
                )
        else:
            if not client.can_view_private_screens:
                raise PermissionDeniedException(
                    'You are not allowed to view private display controllers.'
                )

    @classmethod
    def tournament_check_in_is_open(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if the check-in of tournament of the request is not open."""
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not tournament.check_in_open:
            raise PermissionDeniedException(
                f'Check-in is not open for tournament [{tournament.uniq_id}].'
            )

    @classmethod
    def client_can_check_in(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if the check-in of tournament of the request is not allowed."""
        client: Client = RequestUtils.get_client(request)
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not client.can_check_in_players(tournament.id):
            raise PermissionDeniedException(
                f'You are not allowed to check-in players for tournament [{tournament.uniq_id}].'
            )

    @classmethod
    def tournament_is_playing(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if the tournament of the request is not playing."""
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not tournament.playing:
            raise PermissionDeniedException(
                f'Tournament [{tournament.uniq_id}] is not playing.'
            )

    @classmethod
    def tournament_record_illegal_moves_is_possible(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if recording illegal moves for the tournament of the request is not possible."""
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not tournament.record_illegal_moves:
            raise PermissionDeniedException(
                f'Recording illegal moves for tournament [{tournament.uniq_id}] is not possible.'
            )

    @classmethod
    def client_can_set_illegal_moves(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if adding/deleting illegal moves for the tournament of the request is not allowed."""
        client: Client = RequestUtils.get_client(request)
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not client.can_enter_results(tournament.id):
            raise PermissionDeniedException(
                f'You are not allowed to set illegal moves for tournament [{tournament.uniq_id}].'
            )

    @classmethod
    def client_can_enter_results(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if entering results for the tournament of the request is not allowed."""
        client: Client = RequestUtils.get_client(request)
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not client.can_enter_results(tournament.id):
            raise PermissionDeniedException(
                f'You are not allowed to enter results for tournament [{tournament.uniq_id}].'
            )

    @classmethod
    def client_can_delete_result(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if deleting the result of the request is not allowed."""
        client: Client = RequestUtils.get_client(request)
        tournament: Tournament = RequestUtils.get_tournament(request)
        if not client.can_update_results(tournament.id):
            raise PermissionDeniedException(
                f'You are not allowed to delete results for tournament [{tournament.uniq_id}].'
            )

    @classmethod
    def client_can_add_result(cls, request: HTMXRequest, _: BaseRouteHandler) -> None:
        """Raises an exception if updating the result of the request is not allowed."""
        client: Client = RequestUtils.get_client(request)
        tournament: Tournament = RequestUtils.get_tournament(request)
        round_, board, result = RequestUtils.get_round_board_result(request)
        if not board.no_result and not client.can_update_results(tournament.id):
            raise PermissionDeniedException(
                f'You are not allowed to update already entered results for tournament [{tournament.uniq_id}].'
            )
        if result not in client.imputable_results_for_tournament(
            tournament_id=tournament.id
        ):
            raise PermissionDeniedException(
                f'You are not allowed to set result [{result}] for tournament [{tournament.uniq_id}].'
            )

    @classmethod
    def client_can_view_players_tab(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if viewing the players tab is not allowed."""
        client: Client = RequestUtils.get_client(request)
        if not client.can_view_players_tab:
            raise PermissionDeniedException(
                'You are not allowed to view the players tab.'
            )

    @classmethod
    def client_can_view_pairings_tab(
        cls, request: HTMXRequest, _: BaseRouteHandler
    ) -> None:
        """Raises an exception if viewing the pairings tab is not allowed."""
        client: Client = RequestUtils.get_client(request)
        if not client.can_view_pairings_tab:
            raise PermissionDeniedException(
                'You are not allowed to view the pairings tab.'
            )
