from functools import partial, cached_property
from typing import Any, Annotated

from litestar import get, post, patch
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Template
from litestar_htmx import HTMXRequest, HTMXTemplate

from common import SharlyChessException
from common.i18n import _, ngettext
from common.logger import get_logger
from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.utils import FFEUtils, FFE_UPLOAD_DELAY
from plugins.utils import PluginUtils
from web.controllers.admin.base_admin_controller import AdminWebContext
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)
logger = get_logger()


class FfeWebContext(AdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        tournament_id: int | None = None,
    ):
        super().__init__(request)
        event = self.get_admin_event()
        self.tournament: Tournament | None = None
        if tournament_id:
            try:
                self.tournament = event.tournaments_by_id[tournament_id]
            except KeyError:
                raise NotFoundException(f'Tournament [{tournament_id}] not found.')

    def get_tournament(self) -> Tournament:
        assert self.tournament is not None
        return self.tournament

    @cached_property
    def allowed_tournaments(self) -> list[Tournament]:
        return self.client.allowed_tournaments_for_action(AuthAction.PUBLISH_RESULTS)

    @property
    def ffe_configured_tournaments(self) -> list[Tournament]:
        ffe_configured_tournaments: list[Tournament] = []
        for tournament in self.allowed_tournaments:
            plugin_data = FFEUtils.get_tournament_plugin_data(tournament)
            if plugin_data.ffe_id and plugin_data.password:
                ffe_configured_tournaments.append(tournament)
        return ffe_configured_tournaments

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'ffe_utils': FFEUtils,
            'tournament': self.tournament,
            'allowed_tournaments': self.allowed_tournaments,
            'ffe_configured_tournaments': self.ffe_configured_tournaments,
            'FFE_UPLOAD_DELAY': FFE_UPLOAD_DELAY,
        }


class FfeUploadController(BaseEventAdminController):
    """Controller for all the endpoints sent from the FFE upload modal."""

    guards = [EventGuard(), ActionGuard(AuthAction.PUBLISH_RESULTS)]

    @classmethod
    def _render_ffe_upload_modal(
        cls,
        web_context: FfeWebContext,
        message: str | None = None,
        message_type: str | None = None,
    ) -> HTMXTemplate:
        template_context = web_context.template_context
        template_context |= {
            'message': message,
            'message_type': message_type,
        }
        return cls._render_modal('/ffe_upload_modal.html', template_context)

    @get(
        path='/ffe/upload-modal/{event_uniq_id:str}',
        name='ffe-upload-modal',
    )
    async def htmx_ffe_upload_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        return self._render_ffe_upload_modal(FfeWebContext(request))

    @classmethod
    def _render_ffe_rules_upload_modal(
        cls,
        web_context: FfeWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> HTMXTemplate:
        if data is None:
            data = WebContext.values_dict_to_form_data(
                {'all_tournaments': True}
                | {
                    f'tournament_{tournament.id}': True
                    for tournament in web_context.ffe_configured_tournaments
                }
            )
        template_context = web_context.template_context
        template_context |= {
            'data': data,
            'errors': errors or {},
        }
        return cls._render_modal('/ffe_rules_upload_modal.html', template_context)

    @get(
        path='/ffe/rules-upload-modal/{event_uniq_id:str}',
        name='ffe-rules-upload-modal',
    )
    async def htmx_ffe_rules_upload_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        return self._render_ffe_rules_upload_modal(FfeWebContext(request))

    @classmethod
    def _render_upload_results(cls, web_context: FfeWebContext) -> HTMXTemplate:
        return HTMXTemplate(
            template_name='/ffe_upload_results.html',
            context=web_context.template_context,
            re_swap='outerHTML',
            re_target='#upload-results',
        )

    @get(
        path='/ffe/upload-results/{event_uniq_id:str}',
        name='ffe-upload-results',
    )
    async def htmx_admin_ffe_upload_results(self, request: HTMXRequest) -> Template:
        return self._render_upload_results(FfeWebContext(request))

    @post(
        path='/ffe/ffe-upload/{event_uniq_id:str}',
        name='ffe-upload',
    )
    async def htmx_admin_ffe_upload(self, request: HTMXRequest) -> Template:
        web_context = FfeWebContext(request)
        FfeBackgroundUploader.upload_event_tournaments(web_context.allowed_tournaments)
        return self._render_upload_results(web_context)

    @post(
        path='/ffe/upload-modal/upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-modal-upload-tournament',
    )
    async def htmx_ffe_modal_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = FfeWebContext(request, tournament_id)
        tournament = web_context.get_tournament()

        FfeBackgroundUploader.schedule_upload(tournament, True)

        return self._render_upload_results(web_context)

    @post(
        path='/ffe/upload-modal/make-visible/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-modal-make-visible',
    )
    async def htmx_ffe_modal_make_visible(
        self,
        request: HTMXRequest,
        tournament_id: int,
    ) -> Template:
        web_context = FfeWebContext(request, tournament_id)
        tournament = web_context.get_tournament()
        FfeBackgroundUploader.upload_tournament(
            tournament.event.uniq_id, tournament.id, set_visible=True
        )
        message_type: str | None = None
        if FFEUtils.get_tournament_plugin_data(tournament).upload_failure_id:
            message = _('Tournament visibility could not be set.')
            message_type = 'error'
        else:
            message = _('Tournament is now visible on the FFE website.')

        return self._render_ffe_upload_modal(web_context, message, message_type)

    @post(
        path='/ffe/upload-modal/upload-rules/{event_uniq_id:str}',
        name='ffe-modal-upload-rules',
    )
    async def htmx_ffe_modal_upload_rules(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, Any], Body(media_type=RequestEncodingType.MULTI_PART)
        ],
    ) -> Template:
        web_context = FfeWebContext(request)
        normalized_data = await WebContext.normalize_multipart_data(data)
        rules_file = WebContext.form_data_to_path(normalized_data, 'rules_file')
        error_tournament_names: list[str] = []
        if not rules_file or rules_file.suffix != '.pdf':
            if rules_file:
                message = _(
                    'Invalid file extension [{extension}] (expected: {expected}).'
                ).format(
                    extension=rules_file.suffix,
                    expected='.pdf',
                )
                rules_file.unlink(missing_ok=True)
            else:
                message = _('Please select a file.')
            return self._render_ffe_rules_upload_modal(
                web_context, normalized_data, {'rules_file': message}
            )

        for tournament in web_context.ffe_configured_tournaments:
            if not WebContext.form_data_to_path(
                normalized_data, f'tournament_{tournament.id}'
            ):
                continue
            try:
                FFESession(tournament).upload_rules(rules_file)
            except SharlyChessException as error:
                logger.exception(
                    '%sError when uploading rules to the FFE website: %s',
                    tournament.log_prefix,
                    error,
                )
                error_tournament_names.append(tournament.name)
        message_type: str | None = None
        if len(error_tournament_names) == 0:
            message = _('Rules successfully uploaded.')
        else:
            message = ngettext(
                'Rules upload failed for tournament [{tournaments}].',
                'Rules upload failed for tournaments [{tournaments}].',
                len(error_tournament_names),
            ).format(tournaments=', '.join(error_tournament_names))
            message += ' ' + _('Consult the logs for more details.')
            message_type = 'error'
        rules_file.unlink(missing_ok=True)
        return self._render_ffe_upload_modal(web_context, message, message_type)

    @patch(
        path='/ffe/update-event-auto-upload/{event_uniq_id:str}',
        name='ffe-update-event-auto-upload',
    )
    async def htmx_ffe_update_event_auto_upload(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = FfeWebContext(request)
        event = web_context.get_admin_event()
        plugin_data = FFEUtils.get_event_plugin_data(event)
        plugin_data.auto_upload = WebContext.form_data_to_bool(data, 'auto_upload')
        FFEUtils.update_event_plugin_data(event, plugin_data)
        for tournament in event.tournaments:
            if not FFEUtils.get_tournament_plugin_data(tournament).auto_upload:
                continue
            if plugin_data.auto_upload:
                if FfeBackgroundUploader.ffe_upload_needed(tournament):
                    FfeBackgroundUploader.schedule_upload(tournament)
            else:
                FfeBackgroundUploader.remove_scheduled_upload(tournament)
        return self._render_upload_results(web_context)

    @patch(
        path='/ffe/update-tournament-auto-upload/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-update-tournament-auto-upload',
    )
    async def htmx_ffe_update_tournament_auto_upload(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> HTMXTemplate:
        web_context = FfeWebContext(request, tournament_id)
        tournament = web_context.get_tournament()

        plugin_data = FFEUtils.get_tournament_plugin_data(tournament)
        plugin_data.auto_upload = WebContext.form_data_to_bool(
            data, f'tournament_auto_upload_{tournament.id}'
        )
        FFEUtils.update_tournament_plugin_data(tournament, plugin_data)
        if plugin_data.auto_upload:
            if FfeBackgroundUploader.ffe_upload_needed(tournament):
                FfeBackgroundUploader.schedule_upload(tournament)
        else:
            FfeBackgroundUploader.remove_scheduled_upload(tournament)
        return HTMXTemplate(
            template_name='/ffe_tournament_statuses.html',
            context=web_context.template_context,
            re_target=f'#tournament-upload-statuses-{tournament.id}',
            re_swap='innerHTML',
        )
