from typing import Annotated, Any

from litestar import delete, get, patch, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.plugins.htmx import HTMXRequest
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.player import Player
from data.team import Team
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTeam
from utils.enum import FormAction, PlayerGender
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard
from web.messages import Message
from web.session import SessionTeamsAddOtherActive
from web.utils import RequestUtils, SelectOption


class TeamAdminWebContext(BaseEventAdminWebContext):
    def __init__(self, request: HTMXRequest):
        super().__init__(request)
        self.admin_team = RequestUtils.get_optional_team(request)

    def get_admin_team(self) -> Team:
        assert self.admin_team is not None
        return self.admin_team

    @property
    def template_context(self) -> dict[str, Any]:
        event = self.get_admin_event()
        teams_by_tournament_id: dict[int | None, list[Team]] = {}
        for team in event.sorted_teams:
            teams_by_tournament_id.setdefault(team.tournament_id, []).append(team)
        for team_list in teams_by_tournament_id.values():
            team_list.sort(
                key=lambda t: (
                    t.pairing_number if t.pairing_number is not None else float('inf'),
                    t.name.lower(),
                )
            )
        sorted_tournaments: list[Tournament] = sorted(
            event.tournaments_by_id.values(), key=lambda t: (t.index, t.name)
        )
        return super().template_context | {
            'admin_event_tab': 'admin-event-teams-tab',
            'sorted_tournaments': sorted_tournaments,
            'teams_by_tournament_id': teams_by_tournament_id,
            'unassigned_teams': teams_by_tournament_id.get(None, []),
            'admin_team': self.admin_team,
        }


class TeamAdminController(BaseEventAdminController):
    guards = [
        EventGuard(),
        ActionGuard(AuthAction.VIEW_TOURNAMENTS_TAB),
    ]

    @classmethod
    def _admin_event_teams_render(
        cls,
        web_context: TeamAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {})
        )

    @staticmethod
    def _team_modal_context(
        web_context: TeamAdminWebContext,
        action: FormAction,
        data: dict[str, str],
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        tournament_options: dict[str, str] = {'': _('— Unassigned —')}
        for tournament in sorted(
            event.tournaments_by_id.values(), key=lambda t: (t.index, t.name)
        ):
            tournament_options[str(tournament.id)] = tournament.name
        return {
            'modal': 'team',
            'action': action,
            'tournament_options': tournament_options,
            'add_other_active': SessionTeamsAddOtherActive(web_context.request).get(),
            'data': data,
            'errors': errors or {},
        }

    @staticmethod
    def _team_form_data_from_team(team: Team) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'name': team.name,
                'tournament_id': team.tournament_id or '',
            }
        )

    # -------------------------------------------------------------------------
    # Tab
    # -------------------------------------------------------------------------

    @get(
        path='/event/{event_uniq_id:str}/teams',
        name='admin-event-teams-tab',
    )
    async def htmx_admin_event_teams_tab(self, request: HTMXRequest) -> Template:
        return self._admin_event_teams_render(TeamAdminWebContext(request))

    # -------------------------------------------------------------------------
    # Modals
    # -------------------------------------------------------------------------

    @get(
        path='/team-modal/create/{event_uniq_id:str}',
        name='admin-team-create-modal',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_create_modal(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        tournament_id_q = request.query_params.get('tournament_id') or ''
        if not tournament_id_q and len(event.tournaments_by_id) == 1:
            tournament_id_q = str(next(iter(event.tournaments_by_id)))
        data = WebContext.values_dict_to_form_data(
            {
                'name': '',
                'tournament_id': tournament_id_q,
            }
        )
        return self._admin_event_teams_render(
            web_context,
            self._team_modal_context(web_context, FormAction.CREATE, data),
        )

    @get(
        path='/team-modal/update/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-update-modal',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_update_modal(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        team = web_context.get_admin_team()
        return self._admin_event_teams_render(
            web_context,
            self._team_modal_context(
                web_context,
                FormAction.UPDATE,
                self._team_form_data_from_team(team),
            ),
        )

    @get(
        path='/team-modal/delete/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-delete-modal',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_delete_modal(self, request: HTMXRequest) -> Template:
        return self._admin_event_teams_render(
            TeamAdminWebContext(request), {'modal': 'team_delete'}
        )

    # -------------------------------------------------------------------------
    # Roster
    # -------------------------------------------------------------------------

    @classmethod
    def _team_roster_modal_context(
        cls,
        web_context: TeamAdminWebContext,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        roster_ids = {p.id for p in team.players}
        available_players: list[Player] = sorted(
            (
                player
                for player in event.players_by_id.values()
                if player.id not in roster_ids and player.stored_player.team_id is None
            ),
            key=lambda p: (p.last_name.lower(), p.first_name.lower()),
        )
        player_options: dict[str, SelectOption] = {}
        for p in available_players:
            rating = p.event_default_rating_and_type
            bracket_parts: list[str] = []
            if rating.value:
                bracket_parts.append(str(rating))
            if p.category and p.category.name and p.category.name != '-':
                bracket_parts.append(p.category.name)
            if p.gender != PlayerGender.NONE:
                bracket_parts.append(p.gender.short_name)
            name = p.full_name
            if bracket_parts:
                name += ' (' + ' • '.join(bracket_parts) + ')'
            club_name = p.club.name if p.club else ''
            search_terms = ' '.join(
                term
                for term in (p.full_name, club_name, str(rating.value or ''))
                if term
            )
            player_options[str(p.id)] = SelectOption(
                name=name,
                subtitle=club_name or None,
                search=search_terms,
            )
        return {
            'modal': 'team_roster',
            'available_players': available_players,
            'player_options': player_options,
        }

    @get(
        path='/team-roster-modal/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-roster-modal',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_roster_modal(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        return self._admin_event_teams_render(
            web_context, self._team_roster_modal_context(web_context)
        )

    @post(
        path='/team-add-player/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-add-player',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_add_player(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        player_ids = WebContext.form_data_to_list_int(data, 'player_id')
        valid_players: list[Player] = [
            event.players_by_id[pid] for pid in player_ids if pid in event.players_by_id
        ]
        if not valid_players:
            Message.warning(request, _('Please select at least one player.'))
            return self._admin_event_teams_render(
                web_context, self._team_roster_modal_context(web_context)
            )
        with EventDatabase(event.uniq_id, True) as database:
            for player in valid_players:
                team.add_player(player, database)
        return self._admin_event_teams_render(
            web_context, self._team_roster_modal_context(web_context)
        )

    @delete(
        path=('/team-remove-player/{event_uniq_id:str}/{team_id:int}/{player_id:int}'),
        name='admin-team-remove-player',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_team_remove_player(
        self, request: HTMXRequest, player_id: int
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        player = event.players_by_id.get(player_id)
        if player is not None:
            with EventDatabase(event.uniq_id, True) as database:
                team.remove_player(player, database)
        return self._admin_event_teams_render(
            web_context, self._team_roster_modal_context(web_context)
        )

    # -------------------------------------------------------------------------
    # Lineups
    # -------------------------------------------------------------------------

    @classmethod
    def _team_lineups_modal_context(
        cls, web_context: TeamAdminWebContext
    ) -> dict[str, Any]:
        team = web_context.get_admin_team()
        tournament = team.tournament
        editable_rounds: list[int] = []
        if tournament is not None:
            first_editable = max(1, tournament.last_paired_round + 1)
            editable_rounds = list(range(first_editable, tournament.rounds + 1))
        rounds_data: list[dict[str, Any]] = []
        for round_ in editable_rounds:
            lineup_ids = [p.id for p in team.effective_round_lineup(round_)]
            rounds_data.append(
                {
                    'round': round_,
                    'has_override': team.has_explicit_round_lineup(round_),
                    'selected_ids': lineup_ids,
                    'ordered_players': [
                        *team.effective_round_lineup(round_),
                        *(p for p in team.players if p.id not in set(lineup_ids)),
                    ],
                }
            )
        default_round = 0
        if tournament is not None and editable_rounds:
            current = tournament.current_round or 1
            default_round = (
                current if current in editable_rounds else editable_rounds[0]
            )
        return {
            'modal': 'team_lineups',
            'rounds_data': rounds_data,
            'default_round': default_round,
        }

    @get(
        path='/team-lineups-modal/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-lineups-modal',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_lineups_modal(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        return self._admin_event_teams_render(
            web_context, self._team_lineups_modal_context(web_context)
        )

    @patch(
        path=('/team-lineup/{event_uniq_id:str}/{team_id:int}/{round_:int}'),
        name='admin-team-lineup-save',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_lineup_save(
        self,
        request: HTMXRequest,
        round_: int,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        tournament = team.tournament
        if tournament is None or round_ <= tournament.last_paired_round:
            Message.warning(request, _('This round cannot be edited.'))
            return self._admin_event_teams_render(
                web_context, self._team_lineups_modal_context(web_context)
            )
        ordered_ids = data.get('player_ids', []) or []
        roster_ids = {p.id for p in team.players}
        filtered_ids = [pid for pid in ordered_ids if pid in roster_ids]
        with EventDatabase(event.uniq_id, True) as database:
            if not filtered_ids:
                team.delete_round_lineup(round_, database)
            else:
                team.set_round_lineup(round_, filtered_ids, database)
        return self._admin_event_teams_render(
            web_context, self._team_lineups_modal_context(web_context)
        )

    @patch(
        path='/teams-reassign/{event_uniq_id:str}',
        name='admin-teams-reassign',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_teams_reassign(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        """Apply the cross-tournament drag-drop state.

        Each form item is encoded as ``team_id:tournament_id_or_empty``.
        Items appear in DOM order; within a tournament the position becomes
        the team's pairing_number (1-based). Teams that are already paired
        in their current tournament are not allowed to move — such
        attempts are silently ignored."""
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        raw_assignments = data.get('assignment', []) or []
        by_tournament: dict[int | None, list[int]] = {}
        for raw in raw_assignments:
            team_id_str, _, tid_str = raw.partition(':')
            try:
                team_id = int(team_id_str)
            except ValueError:
                continue
            tournament_id: int | None
            if tid_str:
                try:
                    tournament_id = int(tid_str)
                except ValueError:
                    continue
                if tournament_id not in event.tournaments_by_id:
                    continue
            else:
                tournament_id = None
            by_tournament.setdefault(tournament_id, []).append(team_id)
        with EventDatabase(event.uniq_id, True) as database:
            for tournament_id, team_ids in by_tournament.items():
                for index, team_id in enumerate(team_ids, start=1):
                    team = event.teams_by_id.get(team_id)
                    if team is None:
                        continue
                    if team.is_paired and team.tournament_id != tournament_id:
                        continue
                    if team.tournament_id != tournament_id:
                        team.set_tournament(tournament_id, database)
                    if team.pairing_number != index:
                        team.set_pairing_number(index, database)
        return self._admin_event_teams_render(web_context)

    @patch(
        path='/team-reorder-players/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-reorder-players',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_reorder_players(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        ordered_ids = data.get('player_ids', []) or []
        with EventDatabase(event.uniq_id, True) as database:
            team.reorder_players(list(ordered_ids), database)
        return self._admin_event_teams_render(
            web_context, self._team_roster_modal_context(web_context)
        )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    @staticmethod
    def _read_team_form_data(
        data: dict[str, str],
        web_context: TeamAdminWebContext,
        action: FormAction,
    ) -> tuple[StoredTeam | None, dict[str, str]]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}

        name = (WebContext.form_data_to_str(data, field := 'name') or '').strip()
        if not name:
            errors[field] = _('This field is required.')
        else:
            used_names = [t.name for t in event.teams]
            if action == FormAction.UPDATE:
                used_names.remove(web_context.get_admin_team().name)
            if name in used_names:
                errors[field] = _('This name is already used.')

        tournament_id: int | None = None
        raw_tournament_id = WebContext.form_data_to_str(data, field := 'tournament_id')
        if raw_tournament_id:
            try:
                tournament_id = int(raw_tournament_id)
            except ValueError:
                errors[field] = f'Invalid tournament id [{raw_tournament_id}].'
            else:
                if tournament_id not in event.tournaments_by_id:
                    errors[field] = _('Unknown tournament.')
                    tournament_id = None

        if errors:
            return None, errors

        existing = web_context.admin_team
        stored_team = StoredTeam(
            id=existing.id if existing and action == FormAction.UPDATE else None,
            name=name,
            tournament_id=tournament_id,
            pairing_number=(
                existing.pairing_number
                if existing and action == FormAction.UPDATE
                else None
            ),
        )
        return stored_team, errors

    @post(
        path='/team-create/{event_uniq_id:str}',
        name='admin-team-create',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        add_other = WebContext.resolve_add_other(
            data, SessionTeamsAddOtherActive(request)
        )

        stored_team, errors = self._read_team_form_data(
            data, web_context, FormAction.CREATE
        )
        if not stored_team:
            return self._admin_event_teams_render(
                web_context,
                self._team_modal_context(web_context, FormAction.CREATE, data, errors),
            )
        event = web_context.get_admin_event()
        team = event.add_team(stored_team)
        Message.success(
            request,
            _('Team [{team}] has been created.').format(team=team.name),
        )
        if add_other:
            next_data = WebContext.values_dict_to_form_data(
                {
                    'name': '',
                    'tournament_id': stored_team.tournament_id or '',
                }
            )
            modal_context = self._team_modal_context(
                web_context, FormAction.CREATE, next_data
            )
            modal_context['previous_team'] = team
            return self._admin_event_teams_render(web_context, modal_context)
        return self._admin_event_teams_render(web_context)

    @patch(
        path='/team-update/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-update',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        stored_team, errors = self._read_team_form_data(
            data, web_context, FormAction.UPDATE
        )
        if not stored_team:
            return self._admin_event_teams_render(
                web_context,
                self._team_modal_context(web_context, FormAction.UPDATE, data, errors),
            )
        team = web_context.get_admin_team()
        team.stored_team.name = stored_team.name
        team.stored_team.tournament_id = stored_team.tournament_id
        event = web_context.get_admin_event()
        with EventDatabase(event.uniq_id, True) as database:
            team.update(database)
        event.clear_team_cache()
        for tournament in event.tournaments:
            tournament.clear_team_cache()
        Message.success(
            request,
            _('Team [{team}] has been updated.').format(team=team.name),
        )
        return self._admin_event_teams_render(web_context)

    @delete(
        path='/team-delete/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-delete',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_team_delete(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        team_name = team.name
        event.delete_team(team)
        Message.success(
            request,
            _('Team [{team}] has been deleted.').format(team=team_name),
        )
        return self._admin_event_teams_render(web_context)
