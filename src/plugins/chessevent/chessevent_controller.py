from litestar import get, patch
from litestar.response import Template
from litestar_htmx import HTMXRequest

from common import SharlyChessException
from common.exception import ImporterError
from common.i18n import _, ngettext
from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from plugins.chessevent.tournament_importer.importer import (
    ChessEventTournamentImporter,
    ChessEventSyncTournamentImporter,
)
from plugins.chessevent.tournament_importer.options import (
    ChessEventEventOption,
    ChessEventUserOption,
    ChessEventPasswordOption,
    ChessEventTournamentOption,
)
from plugins.chessevent.utils import ChessEventUtils
from utils.date_time import format_datetime
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.guards import EventGuard, TournamentActionGuard

logger = get_logger()


class ChessEventController(BaseEventAdminController):
    guards = [
        EventGuard(),
        TournamentActionGuard(AuthAction.UPDATE_PLAYERS),
    ]

    @staticmethod
    def _allowed_tournaments(web_context: BaseEventAdminWebContext) -> list[Tournament]:
        return web_context.client.allowed_tournaments_for_action(
            AuthAction.UPDATE_PLAYERS
        )

    @classmethod
    def _render_chessevent_sync_modal(
        cls,
        web_context: BaseEventAdminWebContext,
        allow_sync: bool,
        tournament: Tournament | None = None,
        message: str | None = None,
        message_type: str | None = None,
    ):
        template_context = {
            'chessevent_utils': ChessEventUtils,
            'format_datetime': format_datetime,
            'chessevent_importer': ChessEventTournamentImporter(),
            'tournament': tournament,
            'allow_sync': allow_sync,
            'message': message,
            'message_type': message_type,
            'allowed_tournaments': cls._allowed_tournaments(web_context),
        }
        return cls._render_modal(
            '/chessevent_sync_modal.html',
            web_context.template_context | template_context,
        )

    @get(
        path='/chessevent/sync-modal/{event_uniq_id:str}',
        name='chessevent-sync-modal',
    )
    async def chessevent_sync_modal(
        self,
        request: HTMXRequest,
        allow_sync: bool = False,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        return self._render_chessevent_sync_modal(web_context, allow_sync)

    @staticmethod
    def _sync_tournament_with_chessevent(tournament: Tournament) -> bool | None:
        status = ChessEventUtils.resolve_tournament_status(tournament)
        if status.sync_disabled_message:
            return None
        importer = ChessEventSyncTournamentImporter(
            [
                ChessEventEventOption(ChessEventUtils.resolve_event_id(tournament)),
                ChessEventUserOption(ChessEventUtils.resolve_user_id(tournament)),
                ChessEventPasswordOption(ChessEventUtils.resolve_password(tournament)),
                ChessEventTournamentOption(
                    ChessEventUtils.resolve_tournament_name(tournament)
                ),
            ]
        )
        try:
            importer.load_tournament(tournament.event, tournament)
            return True
        except ImporterError:
            """Already said in the status."""
        except SharlyChessException as error:
            logger.error(
                'An error occurred while synchronizing '
                'the tournament [%s] with ChessEvent:\n%s',
                tournament.name,
                error,
            )
        return False

    @patch(
        path='/chessevent/sync-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='chessevent-sync-tournament',
    )
    async def chessevent_sync_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        result = self._sync_tournament_with_chessevent(tournament)
        if result:
            message = _('Tournament [{tournament}] successfully synchronized.')
        else:
            message = _('Synchronization failed for tournament [{tournament}].')

        web_context = TournamentAdminWebContext(
            request, tournament_id, reload_event=True
        )
        return self._render_chessevent_sync_modal(
            web_context,
            allow_sync=True,
            tournament=web_context.get_admin_tournament(),
            message=message.format(tournament=tournament.name),
            message_type='success' if result else 'error',
        )

    @patch(
        path='/chessevent/sync-all-tournaments/{event_uniq_id:str}',
        name='chessevent-sync-all-tournaments',
    )
    async def chessevent_sync_all_tournaments(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = BaseEventAdminWebContext(request)
        allowed_tournaments = self._allowed_tournaments(web_context)
        results = [
            self._sync_tournament_with_chessevent(tournament)
            for tournament in allowed_tournaments
        ]
        message_parts: list[str] = []
        message_type = 'info'
        if success_count := results.count(True):
            message_type = 'success'
            message_parts.append(
                ngettext(
                    '{count} tournament successfully synchronized',
                    '{count} tournament successfully synchronized',
                    success_count,
                ).format(count=success_count)
            )
        if ignored_count := results.count(None):
            message_parts.append(
                ngettext(
                    '{count} tournament ignored',
                    '{count} tournaments ignored',
                    ignored_count,
                ).format(count=ignored_count)
            )
        if error_count := results.count(False):
            message_type = 'error'
            message_parts.append(
                ngettext(
                    'Synchronisation failed for {count} tournament',
                    'Synchronisation failed for {count} tournaments',
                    error_count,
                ).format(count=error_count)
            )
        web_context = BaseEventAdminWebContext(request, reload_event=True)
        return self._render_chessevent_sync_modal(
            web_context,
            allow_sync=True,
            message=', '.join(message_parts) + '.',
            message_type=message_type,
        )
