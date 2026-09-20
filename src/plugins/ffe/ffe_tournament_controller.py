import asyncio
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from litestar import post, get
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath
from litestar.response import Template, File
from litestar_htmx import HTMXRequest, ClientRedirect, HTMXTemplate

from common.exception import SharlyChessException
from common.i18n import _, get_locale, set_locale
from common.logger import get_logger
from common.network import NetworkMonitor
from data.access_levels.actions import AuthAction
from data.tournament import Tournament
from plugins import ffe
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.ffe_background_uploader import FfeBackgroundUploader
from plugins.ffe.ffe_session import FFESession
from plugins.ffe.ffe_team_session import FFETeamSession, SiteOption
from plugins.ffe.utils import FFEUtils, FfeTournamentPluginData
from plugins.utils import PluginUtils
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
)
from web.controllers.admin.tournament_admin_controller import TournamentAdminWebContext
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard, TournamentActionGuard
from web.messages import Message
import contextlib

logger = get_logger()
get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)


class FfeTournamentController(BaseEventAdminController):
    """Controller for all the FFE endpoints used on the tournaments page."""

    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.VIEW_TOURNAMENTS_TAB),
    ]

    @staticmethod
    def _test_auth(ffe_id: int, ffe_password: str, locale: str) -> bool | None:
        """Check the FFE credentials. Runs in a worker thread, hence the locale
        which is thread-local."""
        set_locale(locale)
        return FFESession(tournament=None).test_auth(
            ffe_id=ffe_id, ffe_password=ffe_password
        )

    @post(
        path='/ffe/test-auth/{event_uniq_id:str}',
        name='ffe-test-auth',
    )
    async def htmx_ffe_test_auth(
        self,
        event_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        ffe_auth_valid: bool | None = None

        if NetworkMonitor.connected():
            ffe_id: int = 0
            with contextlib.suppress(ValueError):
                ffe_id = WebContext.form_data_to_int(data, 'ffe_id') or 0
            ffe_password: str = WebContext.form_data_to_str(data, 'ffe_password') or ''

            if ffe_id and ffe_password:
                ffe_auth_valid = await asyncio.to_thread(
                    self._test_auth, ffe_id, ffe_password, get_locale()
                )

        errors = {}
        # Compare to False, None means 'unable to check'
        if ffe_auth_valid is False:
            errors['ffe_id'] = _('Invalid FFE certification number or password.')
            errors['ffe_password'] = _('Invalid FFE certification number or password.')

        return HTMXTemplate(
            template_name='ffe_tournament_ffe_auth_fields.html',
            context={
                'data': {
                    'ffe_id': data['ffe_id'],
                    'ffe_password': data['ffe_password'],
                },
                'ffe_auth_valid': ffe_auth_valid is True,
                'ffe_password_visible': data['ffe_password_visible'] == 'true',
                'event_uniq_id': event_uniq_id,
                'errors': errors,
            },
        )

    @staticmethod
    def _team_lists(
        login: str,
        password: str,
        competition_id: int,
        division_id: int | None,
        locale: str,
    ) -> tuple[bool | None, list[SiteOption] | None, list[SiteOption] | None]:
        """Log in with a group account and list the divisions of the
        competition, plus the groups of *division_id*. Runs in a worker
        thread, hence the locale which is thread-local."""
        set_locale(locale)
        session = FFETeamSession(tournament=None)
        logged_in = session.login(login, password)
        if not logged_in:
            return logged_in, None, None
        divisions = session.list_divisions(competition_id)
        groups: list[SiteOption] | None = None
        if divisions and division_id in {division.id for division in divisions}:
            groups = session.list_groups(competition_id, division_id)
        return True, divisions, groups

    @post(
        path='/ffe/team-auth/{event_uniq_id:str}',
        name='ffe-team-auth',
    )
    async def htmx_ffe_team_auth(
        self,
        request: HTMXRequest,
        event_uniq_id: FromPath[str],
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        """Re-render the team-module connection fields with the divisions
        and groups the site lists for the credentials and rule set in the
        form."""
        from data.rule_sets import RuleSetManager

        web_context = TournamentAdminWebContext(request, tournament_id=None)
        event = web_context.get_admin_event()
        login = WebContext.form_data_to_str(data, 'ffe_team_login') or ''
        password = WebContext.form_data_to_str(data, 'ffe_team_password') or ''
        division_choice = WebContext.form_data_to_str(data, 'ffe_team_division') or ''
        group_choice = WebContext.form_data_to_str(data, 'ffe_team_group') or ''
        division_hint = (
            WebContext.form_data_to_str(data, 'ffe_team_division_hint') or ''
        )
        competition_id: int | None = None
        rule_set_id = WebContext.form_data_to_str(data, 'rule_set') or ''
        if rule_set_id:
            with contextlib.suppress(KeyError):
                competition_id = FFEUtils.rule_set_team_competition_id(
                    RuleSetManager(event).get_type(rule_set_id)({})
                )

        auth_valid: bool | None = None
        divisions: list[SiteOption] | None = None
        groups: list[SiteOption] | None = None
        message: str | None = None
        errors: dict[str, str] = {}
        division_id, _division_name = FfeTournamentPluginData._split_site_choice(
            division_choice
        )
        if login and password and competition_id:
            if NetworkMonitor.connected():
                auth_valid, divisions, groups = await asyncio.to_thread(
                    self._team_lists,
                    login,
                    password,
                    competition_id,
                    division_id,
                    get_locale(),
                )
                if auth_valid is None:
                    message = _('FFE website could not be reached.')
            else:
                message = _('No internet connection.')
        if auth_valid is False:
            errors['ffe_team_login'] = _('Invalid FFE group account or password.')
            errors['ffe_team_password'] = _('Invalid FFE group account or password.')
        if divisions is not None:
            assert competition_id is not None
            division_ids = {division.id for division in divisions}
            if division_id not in division_ids:
                # Not chosen yet (or gone): the phase of the rule set
                # names the division to offer first.
                division_choice = next(
                    (
                        FfeTournamentPluginData.site_choice(d.id, d.name)
                        for d in divisions
                        if d.name == division_hint
                    ),
                    '',
                )
                group_choice = ''
                new_division_id, _name = FfeTournamentPluginData._split_site_choice(
                    division_choice
                )
                if new_division_id is not None:
                    _valid, _divisions, groups = await asyncio.to_thread(
                        self._team_lists,
                        login,
                        password,
                        competition_id,
                        new_division_id,
                        get_locale(),
                    )
        if groups is not None:
            group_id, _group_name = FfeTournamentPluginData._split_site_choice(
                group_choice
            )
            if group_id not in {group.id for group in groups}:
                group_choice = ''

        return HTMXTemplate(
            template_name='ffe_tournament_team_auth_fields.html',
            context={
                'data': {
                    'ffe_team_login': login,
                    'ffe_team_password': password,
                    'ffe_team_division': division_choice,
                    'ffe_team_group': group_choice,
                },
                'errors': errors,
                'ffe_team_divisions': divisions,
                'ffe_team_groups': groups,
                'ffe_team_auth_valid': auth_valid is True and bool(group_choice),
                'ffe_team_password_visible': data.get('ffe_team_password_visible')
                == 'true',
                'ffe_team_message': message,
                'event_uniq_id': event_uniq_id,
            },
        )

    @post(
        path='/ffe/make-visible/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-make-visible',
        guards=[TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_ffe_make_visible(
        self,
        request: HTMXRequest,
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        FfeBackgroundUploader.upload_tournament(
            tournament.event.uniq_id, tournament.id, set_visible=True
        )
        if FFEUtils.get_tournament_plugin_data(tournament).upload_failure_id:
            Message.error(
                request,
                _(
                    'Tournament visibility could not be set, consult '
                    'Menu > Data Transfer > FFE for more details.'
                ),
            )
        else:
            Message.success(request, _('Tournament is now visible on the FFE website.'))

        return self.render_messages(request)

    @post(
        path='/ffe/upload-tournament/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-upload-single-tournament',
        guards=[TournamentActionGuard(AuthAction.PUBLISH_RESULTS)],
    )
    async def htmx_ffe_upload_tournament(
        self,
        request: HTMXRequest,
        tournament_id: FromPath[int],
    ) -> Template:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        FfeBackgroundUploader.upload_tournament(tournament.event.uniq_id, tournament.id)
        if FFEUtils.get_tournament_plugin_data(tournament).upload_failure_id:
            Message.error(
                request,
                _(
                    'Tournament upload failed, consult Menu > '
                    'Data Transfer > FFE for more details.'
                ),
            )
        else:
            Message.success(request, _('Tournament successfully uploaded.'))

        return self.render_messages(request)

    @staticmethod
    def tournament_fees_file(tournament: Tournament) -> Path:
        return (
            ffe.TMP_DIR / 'fees' / tournament.event.uniq_id / f'{tournament.name}.html'
        )

    @classmethod
    def _extract_fees(cls, tournament: Tournament, locale: str) -> str | None:
        """Download the fees of *tournament* and write them to their file.
        Runs in a worker thread, hence the locale which is thread-local."""
        set_locale(locale)
        html = FFESession(tournament).get_fees()
        if html:
            fees_file = cls.tournament_fees_file(tournament)
            fees_file.parent.mkdir(parents=True, exist_ok=True)
            fees_file.write_text(html)
        return html

    @get(
        path='/ffe/extract-fees/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-extract-fees',
        guards=[TournamentActionGuard(AuthAction.DOWNLOAD_FEES)],
    )
    async def htmx_ffe_extract_fees(
        self,
        request: HTMXRequest,
        event_uniq_id: FromPath[str],
        tournament_id: FromPath[int],
    ) -> Template | ClientRedirect:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        try:
            if await asyncio.to_thread(self._extract_fees, tournament, get_locale()):
                url: str = request.app.route_reverse(
                    'ffe-download-fees',
                    event_uniq_id=event_uniq_id,
                    tournament_id=tournament_id,
                )
                logger.debug(
                    'Fees written to [%s], redirecting to [%s].',
                    self.tournament_fees_file(tournament),
                    url,
                )
                response: ClientRedirect = ClientRedirect(redirect_to=url)
                # cf https://github.com/bigskysoftware/htmx/issues/3189
                response.set_header('HX-Trigger', 'download_ready')
                return response
            Message.info(request, _('Tournament exempt from registration fees.'))
        except SharlyChessException as e:
            Message.error(request, str(e))
        return self.render_messages(request)

    @get(
        path='/ffe/download-fees/{event_uniq_id:str}/{tournament_id:int}',
        name='ffe-download-fees',
        guards=[TournamentActionGuard(AuthAction.DOWNLOAD_FEES)],
    )
    async def ffe_download_fees(
        self,
        request: HTMXRequest,
        event_uniq_id: FromPath[str],
        tournament_id: FromPath[int],
    ) -> Template | File:
        web_context = TournamentAdminWebContext(request, tournament_id)
        tournament = web_context.get_admin_tournament()
        file: Path = self.tournament_fees_file(tournament)
        return File(
            path=file,
            filename=f'{event_uniq_id}-{tournament.name}-fees.html',
        )
