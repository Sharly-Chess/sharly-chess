from typing import Annotated, Any

from litestar import delete, get, patch, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.plugins.htmx import HTMXRequest
from litestar.response import Template
from litestar_htmx import HTMXTemplate
from litestar.status_codes import HTTP_200_OK

from common.i18n import _, ngettext
from common.sharly_chess_config import SharlyChessConfig
from data.access_levels.actions import AuthAction
from data.board import Board
from data.event import Event
from data.player import Player
from data.team import RosterFullError, Team, TeamGroup
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTeam
from utils.enum import FormAction, PlayerGender, Result, TeamByeType, TeamSortMode
from data.access_levels.client import Client
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard, SetByeGuard
from web.messages import Message
from web.session import SessionTeamsAddOtherActive, SessionTeamsShowDetails
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
            'show_details': SessionTeamsShowDetails(self.request).get(),
            'team_sort_modes': list(TeamSortMode),
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
        tournament_options: dict[str, str | SelectOption] = {
            '': _('— Unassigned —'),
        }
        for tournament in sorted(
            event.tournaments_by_id.values(), key=lambda t: (t.index, t.name)
        ):
            # Tournaments that no longer accept teams (fixed-table
            # systems once paired) stay listed but unselectable, except
            # as the team's current assignment.
            if not tournament.can_add_teams and not (
                web_context.admin_team is not None
                and web_context.admin_team.tournament_id == tournament.id
            ):
                tournament_options[str(tournament.id)] = SelectOption(
                    name=tournament.name,
                    disabled=True,
                    tooltip=_(
                        'This tournament has already been paired; '
                        'teams can no longer be added.'
                    ),
                    subtitle=_('Pairings started'),
                )
            else:
                tournament_options[str(tournament.id)] = tournament.name
        # A team already paired can't change tournament — moving it would
        # orphan its boards.
        tournament_locked = (
            action == FormAction.UPDATE
            and web_context.admin_team is not None
            and web_context.admin_team.has_been_paired
        )
        # Nested dicts render as <optgroup> sections — select2's native
        # way of visually separating the roster from the free-text option.
        captain_options: dict[str, Any] = {'': '-'}
        if action == FormAction.UPDATE and web_context.admin_team is not None:
            players = {
                str(player.id): player.full_name
                for player in web_context.admin_team.players
            }
            if players:
                captain_options[_('Players')] = players
        captain_options[_('Other')] = {'other': _('Non-playing captain…')}
        if 'federation' not in data:
            # New teams default to the event's federation.
            data = data | {'federation': event.federation or ''}
        return {
            'modal': 'team',
            'action': action,
            'tournament_options': tournament_options,
            'tournament_locked': tournament_locked,
            'captain_options': captain_options,
            'federation_options': (
                {'': '-'} | TeamAdminController._get_federation_options()
            ),
            'team_group_options': TeamAdminController._team_group_options(event),
            'show_team_group_form': False,
            'add_other_active': SessionTeamsAddOtherActive(web_context.request).get(),
            'data': data,
            'errors': errors or {},
        }

    @staticmethod
    def _team_group_options(event: Event) -> dict[str, SelectOption]:
        """Existing event team groups for the picker, each labelled with
        how many teams already use it (so reuse is obvious)."""
        counts = event.team_group_team_counts()
        options: dict[str, SelectOption] = {'': SelectOption('-')}
        for group in sorted(event.team_groups, key=lambda g: g.name.lower()):
            label = group.name
            if group.id in counts:
                label += f' ({counts[group.id]})'
            options[str(group.id)] = SelectOption(label, search=group.name)
        return options

    @staticmethod
    def _team_form_data_from_team(team: Team) -> dict[str, str]:
        if team.captain is not None:
            captain = str(team.captain.id)
        elif team.stored_team.captain_name:
            captain = 'other'
        else:
            captain = ''
        return WebContext.values_dict_to_form_data(
            {
                'name': team.name,
                'tournament_id': team.tournament_id or '',
                'group_id': team.group_id or '',
                'federation': team.federation,
                'captain': captain,
                'captain_name': team.stored_team.captain_name or '',
            }
        )

    # -------------------------------------------------------------------------
    # Tab
    # -------------------------------------------------------------------------

    @get(
        path='/event/{event_uniq_id:str}/teams',
        name='admin-event-teams-tab',
    )
    async def htmx_admin_event_teams_tab(
        self,
        request: HTMXRequest,
        show_details: bool | None,
    ) -> Template:
        if show_details is not None:
            SessionTeamsShowDetails(request).set(show_details)
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
    # Team groups (reusable, event-level — picked in the team modal)
    # -------------------------------------------------------------------------

    @classmethod
    def _render_team_group_fields(
        cls,
        web_context: TeamAdminWebContext,
        action: FormAction = FormAction.CREATE,
        group: TeamGroup | None = None,
        show_form: bool = False,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> HTMXTemplate:
        event = web_context.get_admin_event()
        show_delete_button = (
            action == FormAction.UPDATE
            and group is not None
            and group.id not in event.team_group_team_counts()
        )
        context = web_context.template_context | {
            'team_group_options': cls._team_group_options(event),
            'show_team_group_form': show_form or bool(errors),
            'team_group_action': action,
            'team_group': group,
            'show_team_group_delete_button': show_delete_button,
            'data': data or {},
            'errors': errors or {},
        }
        return HTMXTemplate(
            template_name='/admin/teams/team_group_fields.html',
            context=context,
            re_target='#team-group-container',
            re_swap='outerHTML',
        )

    @staticmethod
    def _validate_team_group_name(
        event: Event, name: str, ignore_group_id: int | None = None
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not name:
            errors['team_group_name'] = _('This field is required.')
        elif any(
            group.name.lower() == name.lower() and group.id != ignore_group_id
            for group in event.team_groups
        ):
            errors['team_group_name'] = _('This name is already used.')
        return errors

    @get(
        path='/team-group/add-form/{event_uniq_id:str}',
        name='admin-team-group-add-form',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_group_add_form(
        self, request: HTMXRequest, group_id: str = ''
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        return self._render_team_group_fields(
            web_context,
            FormAction.CREATE,
            show_form=True,
            data={'team_group_name': '', 'group_id': group_id},
        )

    @get(
        path='/team-group/update-form/{event_uniq_id:str}',
        name='admin-team-group-update-form',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_group_update_form(
        self, request: HTMXRequest, group_id: int
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        group = web_context.get_admin_event().team_groups_by_id.get(group_id)
        if group is None:
            raise NotFoundException(f'Unknown group [{group_id}].')
        return self._render_team_group_fields(
            web_context,
            FormAction.UPDATE,
            group=group,
            show_form=True,
            data={'team_group_name': group.name, 'group_id': str(group_id)},
        )

    @post(
        path='/team-group/add/{event_uniq_id:str}',
        name='admin-team-group-add',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_group_add(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        name = (data.get('team_group_name') or '').strip()
        errors = self._validate_team_group_name(event, name)
        if not errors:
            group = event.add_team_group(name)
            return self._render_team_group_fields(
                web_context,
                data={'team_group_name': '', 'group_id': str(group.id)},
            )
        return self._render_team_group_fields(
            web_context, FormAction.CREATE, show_form=True, data=data, errors=errors
        )

    @patch(
        path='/team-group/update/{event_uniq_id:str}/{group_id:int}',
        name='admin-team-group-update',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_group_update(
        self,
        request: HTMXRequest,
        group_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        group = event.team_groups_by_id.get(group_id)
        if group is None:
            raise NotFoundException(f'Unknown group [{group_id}].')
        name = (data.get('team_group_name') or '').strip()
        errors = self._validate_team_group_name(event, name, ignore_group_id=group_id)
        if not errors:
            event.update_team_group(group_id, name)
            return self._render_team_group_fields(
                web_context,
                data={'team_group_name': name, 'group_id': str(group_id)},
            )
        return self._render_team_group_fields(
            web_context,
            FormAction.UPDATE,
            group=group,
            show_form=True,
            data=data,
            errors=errors,
        )

    @delete(
        path='/team-group/delete/{event_uniq_id:str}/{group_id:int}',
        name='admin-team-group-delete',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_team_group_delete(
        self, request: HTMXRequest, group_id: int
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        web_context.get_admin_event().delete_team_group(group_id)
        return self._render_team_group_fields(
            web_context, data={'team_group_name': '', 'group_id': ''}
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
        tournament = team.tournament
        roster_max_size = tournament.rule_set_roster_max_size if tournament else None
        return {
            'modal': 'team_roster',
            'available_players': available_players,
            'player_options': player_options,
            'roster_max_size': roster_max_size,
            'roster_at_cap': (
                roster_max_size is not None and len(team.players) >= roster_max_size
            ),
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

    @get(
        path='/team-record-modal/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-record-modal',
        guards=[ActionGuard(AuthAction.UPDATE_PLAYERS_HISTORY)],
    )
    async def htmx_admin_team_record_modal(self, request: HTMXRequest) -> Template:
        return self._render_team_record_modal(TeamAdminWebContext(request))

    @patch(
        path='/records/check-in-team/{event_uniq_id:str}/{team_id:int}',
        name='records-check-in-team',
        guards=[ActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_records_check_in_team(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        team = web_context.get_admin_team()
        tournament = team.tournament
        if tournament is not None:
            tournament.check_in_team(team, not team.check_in)
        return self._render_team_record_modal(web_context)

    @patch(
        path='/team-set-bye/{event_uniq_id:str}/{team_id:int}/{round:int}',
        name='admin-team-set-bye',
        guards=[SetByeGuard()],
    )
    async def htmx_team_set_bye(
        self,
        request: HTMXRequest,
        team_id: int,
        round: int,
        result: int,
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        team = web_context.get_admin_team()
        tournament = team.tournament
        if tournament is None or not tournament.pairing_system.show_unpaired_team_modal:
            raise NotFoundException(
                'Team byes are not available for this pairing system.'
            )
        bye_type = {
            Result.NO_RESULT: None,
            Result.ZERO_POINT_BYE: TeamByeType.ZPB,
            Result.HALF_POINT_BYE: TeamByeType.HPB,
            Result.FULL_POINT_BYE: TeamByeType.FPB,
        }.get(Result(result))
        with EventDatabase(team.event.uniq_id, write=True) as db:
            team.set_round_bye(round, bye_type, db)
        return self._render_team_record_modal(web_context)

    @classmethod
    def _render_team_record_modal(cls, web_context: TeamAdminWebContext) -> Template:
        team = web_context.get_admin_team()
        tournament = team.tournament
        rounds = tournament.rounds if tournament else 0
        data = {
            f'round_{round_}_result': WebContext.value_to_form_data(
                cls._team_round_result_value(team, round_).value
            )
            for round_ in range(1, rounds + 1)
        }
        return cls._admin_event_teams_render(
            web_context,
            {
                'modal': 'team-record',
                'get_team_bye_options': cls._get_team_bye_options,
                'data': data,
            },
        )

    @staticmethod
    def _team_round_result_value(team: Team, round_: int) -> 'Result':
        bye = team.round_bye_type(round_)
        if bye is None:
            return Result.NO_RESULT
        return {
            TeamByeType.ZPB: Result.ZERO_POINT_BYE,
            TeamByeType.HPB: Result.HALF_POINT_BYE,
            TeamByeType.FPB: Result.FULL_POINT_BYE,
            TeamByeType.PAB: Result.PAIRING_ALLOCATED_BYE,
        }.get(bye, Result.NO_RESULT)

    @staticmethod
    def _get_team_bye_options(
        client: 'Client', team: Team, round_: int
    ) -> dict[str, SelectOption]:
        tournament = team.tournament
        assert tournament is not None
        hpb_msg: str | None = None
        fpb_msg: str | None = None
        if not client.can_set_half_point_bye(tournament.id):
            hpb_msg = _('You are not allowed to set Half-Point Byes.')
        if not client.can_set_full_point_bye(tournament.id):
            fpb_msg = _('You are not allowed to set Full-Point Byes.')
        if round_ > tournament.rounds - tournament.last_rounds_no_byes:
            msg = ngettext(
                "Byes can't be set for the last round of the tournament.",
                "Byes can't be set for the last {rounds} rounds of the tournament.",
                tournament.last_rounds_no_byes,
            ).format(rounds=tournament.last_rounds_no_byes)
            hpb_msg = msg
            fpb_msg = msg
        options: dict[Result, SelectOption] = {
            Result.NO_RESULT: SelectOption('-'),
            Result.ZERO_POINT_BYE: SelectOption(_('Zero-Point Bye')),
            Result.HALF_POINT_BYE: SelectOption(
                _('Half-Point Bye'),
                tooltip=hpb_msg,
                disabled=bool(hpb_msg),
            ),
            Result.FULL_POINT_BYE: SelectOption(
                _('Full-Point Bye (deprecated)'),
                tooltip=fpb_msg,
                disabled=bool(fpb_msg),
                classes='' if fpb_msg else 'text-danger',
            ),
        }
        return {str(result.value): option for result, option in options.items()}

    @post(
        path='/team-add-player/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-add-player',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_add_player(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        flat_data = WebContext.flatten_list_data(data)
        player_ids = WebContext.form_data_to_list_int(flat_data, 'player_id')
        valid_players: list[Player] = [
            event.players_by_id[pid] for pid in player_ids if pid in event.players_by_id
        ]
        if not valid_players:
            Message.warning(request, _('Please select at least one player.'))
            return self._admin_event_teams_render(
                web_context, self._team_roster_modal_context(web_context)
            )
        tournament = team.tournament
        max_size = tournament.rule_set_roster_max_size if tournament else None
        if max_size is not None:
            remaining = max_size - len(team.players)
            if remaining <= 0:
                Message.warning(
                    request,
                    _('Roster is full ({max} players max for this rule set).').format(
                        max=max_size
                    ),
                )
                return self._admin_event_teams_render(
                    web_context, self._team_roster_modal_context(web_context)
                )
            if len(valid_players) > remaining:
                valid_players = valid_players[:remaining]
                Message.warning(
                    request,
                    _(
                        'Only {n} more player(s) can be added '
                        '({max} max for this rule set).'
                    ).format(n=remaining, max=max_size),
                )
        with EventDatabase(event.uniq_id, True) as database:
            for player in valid_players:
                try:
                    team.add_player(player, database)
                except RosterFullError as err:
                    Message.warning(
                        request,
                        _(
                            'Roster is full ({max} players max for this rule set).'
                        ).format(max=err.max_size),
                    )
                    break
            self._resort_team_tournament(team, database)
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
                self._resort_team_tournament(team, database)
        return self._admin_event_teams_render(
            web_context, self._team_roster_modal_context(web_context)
        )

    @patch(
        path='/team-toggle-check-in/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-toggle-check-in',
        guards=[ActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_admin_team_toggle_check_in(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        tournament = web_context.get_admin_team().tournament
        team = web_context.get_admin_team()
        if tournament is not None:
            tournament.check_in_team(team, not team.check_in)
        return self._admin_event_teams_render(web_context)

    @get(
        path='/team-check-in-modal/{event_uniq_id:str}',
        name='admin-team-check-in-modal',
        guards=[ActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_admin_team_check_in_modal(self, request: HTMXRequest) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team_tournaments = [
            t for t in event.tournaments_by_id.values() if t.is_team_tournament
        ]
        return self._admin_event_teams_render(
            web_context,
            {
                'modal': 'team-check-in',
                'team_tournaments': team_tournaments,
            },
        )

    @post(
        path='/team-check-in-reset/{event_uniq_id:str}/{tournament_id:int}/{present:int}',
        name='admin-team-check-in-reset',
        guards=[ActionGuard(AuthAction.CHECK_IN_PLAYERS)],
    )
    async def htmx_admin_team_check_in_reset(
        self, request: HTMXRequest, tournament_id: int, present: int
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        tournament = event.tournaments_by_id.get(tournament_id)
        if tournament is not None and tournament.is_team_tournament:
            tournament.check_in_all_teams(bool(present))
        team_tournaments = [
            t for t in event.tournaments_by_id.values() if t.is_team_tournament
        ]
        return self._admin_event_teams_render(
            web_context,
            {
                'modal': 'team-check-in',
                'team_tournaments': team_tournaments,
            },
        )

    # -------------------------------------------------------------------------
    # Lineups
    # -------------------------------------------------------------------------

    @classmethod
    def _team_lineups_modal_context(
        cls,
        web_context: TeamAdminWebContext,
        requested_round: int | None = None,
    ) -> dict[str, Any]:
        team = web_context.get_admin_team()
        tournament = team.tournament
        editable_rounds: list[int] = []
        team_player_count = 0
        color_pattern = ''
        warn_lineup_order = False
        if tournament is not None:
            warn_lineup_order = tournament.warn_lineup_order
            first_editable = max(1, tournament.last_paired_round + 1)
            rounds_set = set(range(first_editable, tournament.rounds + 1))
            # Include the current round even if already paired — paired
            # rounds get reconciled to existing boards on save.
            if (
                tournament.current_round
                and 1 <= tournament.current_round <= tournament.rounds
            ):
                rounds_set.add(tournament.current_round)
            # Also include an explicitly requested past round (e.g.
            # opened from the pairings tab pencil).
            if (
                requested_round is not None
                and 1 <= requested_round <= tournament.rounds
            ):
                rounds_set.add(requested_round)
            editable_rounds = sorted(rounds_set)
            team_player_count = tournament.team_player_count or 0
            color_pattern = tournament.color_pattern or ''
        elif team.players:
            # Team not yet assigned to a tournament: edit a single base
            # lineup (round 1), the roster standing in for the board count.
            # It becomes round 1's lineup once the team is assigned.
            editable_rounds = [1]
            team_player_count = len(team.players)
        rounds_data: list[dict[str, Any]] = []
        for round_ in editable_rounds:
            slots = team.effective_round_slots(round_, board_count=team_player_count)
            slot_player_ids: set[int] = {p.id for p in slots if p is not None}
            bench = [p for p in team.players if p.id not in slot_player_ids]
            rounds_data.append(
                {
                    'round': round_,
                    'has_override': team.has_explicit_round_lineup(round_),
                    'slots': slots,
                    'bench': bench,
                    'out_of_order': team.lineup_out_of_roster_order(round_),
                }
            )
        default_round = 0
        if editable_rounds:
            if tournament is not None:
                current = tournament.current_round or 1
                default_round = (
                    current if current in editable_rounds else editable_rounds[0]
                )
            else:
                default_round = editable_rounds[0]
        if requested_round is not None and requested_round in editable_rounds:
            default_round = requested_round
        return {
            'modal': 'team_lineups',
            'rounds_data': rounds_data,
            'default_round': default_round,
            'team_player_count': team_player_count,
            'color_pattern': color_pattern,
            'roster_players': team.players if editable_rounds else [],
            'warn_lineup_order': warn_lineup_order,
        }

    @get(
        path='/team-lineups-modal/{event_uniq_id:str}/{team_id:int}',
        name='admin-team-lineups-modal',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_lineups_modal(
        self, request: HTMXRequest, round: int | None = None
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        return self._admin_event_teams_render(
            web_context,
            self._team_lineups_modal_context(web_context, requested_round=round),
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
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        team = web_context.get_admin_team()
        tournament = team.tournament
        if tournament is not None:
            n = tournament.team_player_count or 0
            valid_round = 1 <= round_ <= tournament.rounds
        else:
            # Unassigned team: only the round-1 base lineup is editable,
            # the roster standing in for the board count.
            n = len(team.players)
            valid_round = round_ == 1 and bool(team.players)
        if not valid_round:
            Message.warning(request, _('This round cannot be edited.'))
            return self._admin_event_teams_render(
                web_context,
                self._team_lineups_modal_context(web_context, requested_round=round_),
            )
        roster_ids = {p.id for p in team.players}
        slot_values: list[int | None] = []
        for i in range(n):
            raw = data.get(f'slot_{i}', '')
            raw = raw[0] if isinstance(raw, list) else raw
            try:
                pid = int(raw) if raw else None
            except ValueError:
                pid = None
            slot_values.append(pid if pid in roster_ids else None)
        is_paired_round = (
            tournament is not None and round_ <= tournament.last_paired_round
        )
        if is_paired_round:
            self._reconcile_paired_round_lineup(
                event, tournament, team, round_, slot_values
            )
        else:
            with EventDatabase(event.uniq_id, True) as database:
                if all(v is None for v in slot_values):
                    team.delete_round_lineup(round_, database)
                else:
                    team.set_round_lineup(round_, slot_values, database)
                # The line-up-average sort mode keys off the round 1
                # line-up, so re-sort once it changes (self-guards for
                # the other modes and once a round is paired).
                if tournament is not None:
                    tournament.resort_teams(database)
        return self._admin_event_teams_render(
            web_context,
            self._team_lineups_modal_context(web_context, requested_round=round_),
        )

    @classmethod
    def _reconcile_paired_round_lineup(
        cls,
        event: 'Event',
        tournament: Tournament,
        team: Team,
        round_: int,
        new_slot_values: list[int | None],
    ) -> None:
        """Apply *new_slot_values* to ``team``'s lineup at *round_* when
        the round is already paired. For each slot whose player changed,
        punch the old player off the corresponding individual board, then
        fill in the new one — reusing the inline-edit helpers so
        pairings/results stay consistent. Players bumped off the lineup
        lose their pairing for the round."""
        from web.controllers.admin.pairings_admin_controller import (
            PairingsAdminController,
        )

        if not tournament.pairing_system.paired_by_team:
            cls._reconcile_flat_round_lineup(
                event, tournament, team, round_, new_slot_values
            )
            return

        # Find the team's team_board for this round (skip byes/EXEMPT —
        # those have no opponent and don't need slot reconciliation).
        team_board = next(
            (
                tb
                for tb in tournament.get_round_team_boards(round_)
                if (
                    tb.stored_team_board.team_a_id == team.id
                    or tb.stored_team_board.team_b_id == team.id
                )
                and tb.stored_team_board.team_b_id is not None
            ),
            None,
        )
        if team_board is None:
            # Team has a bye / no real match this round — just persist
            # the lineup; no boards to reconcile.
            with EventDatabase(event.uniq_id, write=True) as database:
                if all(v is None for v in new_slot_values):
                    team.delete_round_lineup(round_, database)
                else:
                    team.set_round_lineup(round_, new_slot_values, database)
            return

        old_slots = [
            p.id if p is not None else None for p in team.effective_round_slots(round_)
        ]
        boards_by_index = {board.index: board for board in team_board.boards}

        # Two-pass: vacate every slot that changes, then fill. Avoids
        # collisions when two players swap within the team's lineup.
        to_punch: list[tuple[int, int]] = []  # (slot, old_player_id)
        to_fill: list[tuple[int, int]] = []  # (slot, new_player_id)
        for i, old_pid in enumerate(old_slots):
            new_pid = new_slot_values[i] if i < len(new_slot_values) else None
            if old_pid == new_pid:
                continue
            if old_pid is not None:
                to_punch.append((i, old_pid))
            if new_pid is not None:
                to_fill.append((i, new_pid))

        for slot, old_pid in to_punch:
            board = boards_by_index.get(slot)
            if board is None:
                continue
            PairingsAdminController._punch_lineup_hole_for_team(
                event, tournament, board, team_board, team, old_pid
            )
        for slot, new_pid in to_fill:
            board = boards_by_index.get(slot)
            if board is None:
                continue
            new_tp = tournament.tournament_players_by_id.get(new_pid)
            if new_tp is None:
                continue
            physical_side = (
                'white'
                if PairingsAdminController._team_owning_side(
                    tournament, team_board, slot, 'W'
                )
                == team
                else 'black'
            )
            PairingsAdminController._fill_lineup_hole(
                event, tournament, board, team_board, team, physical_side, new_tp
            )

    @staticmethod
    def _reconcile_flat_round_lineup(
        event: 'Event',
        tournament: Tournament,
        team: Team,
        round_: int,
        new_slot_values: list[int | None],
    ) -> None:
        """Flat (fixed-table) counterpart of the paired-round lineup
        reconciliation: boards are plain rows with no team_board
        envelope, and the board index is global rather than the team
        slot. A changed slot is located through the outgoing player's
        board when there is one, and through the pairing table's
        ``round_seats`` mapping otherwise (slot was already a hole).
        A replacement takes the seat with the board's result cleared;
        an emptied slot leaves a forfeit hole."""
        from data.pairings.fixed_table import FixedTablePairingEngine

        old_slots = [
            p.id if p is not None else None for p in team.effective_round_slots(round_)
        ]
        round_boards = tournament.get_round_boards(round_)
        boards_by_index = {board.index: board for board in round_boards}
        board_side_by_player: dict[int, tuple['Board', str]] = {}
        for board in round_boards:
            if board.stored_board.white_player_id is not None:
                board_side_by_player[board.stored_board.white_player_id] = (
                    board,
                    'white',
                )
            if board.stored_board.black_player_id is not None:
                board_side_by_player[board.stored_board.black_player_id] = (
                    board,
                    'black',
                )
        engine = tournament.pairing_variation.engine
        table_seats = (
            engine.round_seats(tournament, round_)
            if isinstance(engine, FixedTablePairingEngine)
            else {}
        )

        def _hole_seat(slot: int) -> tuple['Board', str] | None:
            """The board seat the table assigns to this team slot,
            provided that seat is currently a hole (don't stomp an
            occupied seat; honors boards whose colours were permuted
            by checking the opposite side)."""
            table_seat = table_seats.get((team.id, slot))
            if table_seat is None:
                return None
            board = boards_by_index.get(table_seat[0])
            if board is None:
                return None
            side = table_seat[1]
            w_id = board.stored_board.white_player_id
            b_id = board.stored_board.black_player_id
            if side == 'white':
                if w_id is None:
                    return board, 'white'
                if b_id is None:
                    return board, 'black'
            else:
                if b_id is None:
                    return board, 'black'
                if w_id is None:
                    return board, 'white'
            return None

        changes = [
            (
                i,
                old_pid,
                new_slot_values[i] if i < len(new_slot_values) else None,
            )
            for i, old_pid in enumerate(old_slots)
            if old_pid != (new_slot_values[i] if i < len(new_slot_values) else None)
        ]
        with EventDatabase(event.uniq_id, write=True) as database:
            if all(v is None for v in new_slot_values):
                team.delete_round_lineup(round_, database)
            else:
                team.set_round_lineup(round_, new_slot_values, database)
            for slot, old_pid, new_pid in changes:
                seat = board_side_by_player.get(old_pid) if old_pid else None
                if seat is None:
                    seat = _hole_seat(slot)
                if seat is None:
                    continue
                board, side = seat
                old_tp = tournament.tournament_players_by_id.get(old_pid)
                if old_tp is not None:
                    old_pairing = old_tp.pairings_by_round[round_]
                    old_pairing.stored_pairing.result = Result.NO_RESULT.value
                    old_pairing.stored_pairing.board_id = None
                    old_pairing.stored_pairing.effective_points = None
                    old_pairing.stored_pairing.illegal_moves = 0
                    old_pairing.update(database)
                opp_id = (
                    board.stored_board.black_player_id
                    if side == 'white'
                    else board.stored_board.white_player_id
                )
                opp_pairing = None
                if opp_id is not None:
                    opp_tp = tournament.tournament_players_by_id.get(opp_id)
                    if opp_tp is not None:
                        opp_pairing = opp_tp.pairings_by_round[round_]
                new_tp = (
                    tournament.tournament_players_by_id.get(new_pid)
                    if new_pid is not None
                    else None
                )
                if new_tp is not None:
                    board.replace_player(new_tp, side)  # type: ignore[arg-type]
                    new_pairing = new_tp.pairings_by_round[round_]
                    new_pairing.stored_pairing.result = Result.NO_RESULT.value
                    new_pairing.stored_pairing.board_id = board.identifier
                    new_pairing.stored_pairing.effective_points = None
                    new_pairing.stored_pairing.illegal_moves = 0
                    new_pairing.update(database)
                    if opp_pairing is not None:
                        opp_pairing.stored_pairing.result = Result.NO_RESULT.value
                        opp_pairing.stored_pairing.effective_points = None
                        opp_pairing.stored_pairing.illegal_moves = 0
                        opp_pairing.update(database)
                else:
                    if side == 'white':
                        board.stored_board.white_player_id = None
                        board._white_player_ref = None
                    else:
                        board.stored_board.black_player_id = None
                        board._black_player_ref = None
                    # The opposing player loses their opponent — score
                    # the hole as a forfeit win, like lineup holes
                    # punched at pairing time.
                    if opp_pairing is not None:
                        opp_pairing.stored_pairing.result = Result.FORFEIT_WIN.value
                        opp_pairing.stored_pairing.effective_points = None
                        opp_pairing.stored_pairing.illegal_moves = 0
                        opp_pairing.update(database)
                database.update_stored_board(board.stored_board)
                board.set_last_result_update(Result.NO_RESULT, database)

    @patch(
        path='/team-sort-mode/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-team-sort-mode',
        guards=[ActionGuard(AuthAction.UPDATE_TOURNAMENTS)],
    )
    async def htmx_admin_team_sort_mode(
        self,
        request: HTMXRequest,
        tournament_id: int,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TeamAdminWebContext(request)
        event = web_context.get_admin_event()
        tournament = event.tournaments_by_id.get(tournament_id)
        if tournament is None or tournament.team_sort_mode_locked:
            return self._admin_event_teams_render(web_context)
        # The button lives inside ``#teams-form``, so HTMX also
        # serialises its repeated ``assignment`` inputs — flatten the
        # list-valued body before reading the single mode field.
        flat_data = WebContext.flatten_list_data(data)
        try:
            mode = TeamSortMode(
                WebContext.form_data_to_str(flat_data, 'team_sort_mode') or ''
            )
        except ValueError:
            return self._admin_event_teams_render(web_context)
        with EventDatabase(event.uniq_id, True) as database:
            tournament.stored_tournament.team_sort_mode = mode.value
            # Switching to RANDOM means a fresh shuffle: drop the
            # existing pairing numbers so every team is a newcomer.
            if mode == TeamSortMode.RANDOM:
                for team in tournament.teams:
                    if team.pairing_number is not None:
                        team.set_pairing_number(None, database)
            database.update_stored_tournament(tournament.stored_tournament)
            tournament.resort_teams(database)
        return self._admin_event_teams_render(web_context)

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
        in their current tournament are not allowed to move, and teams
        cannot be dropped into a tournament whose pairing system refuses
        team additions once paired — such attempts are silently
        ignored."""
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
                    if team.has_been_paired and team.tournament_id != tournament_id:
                        continue
                    if team.tournament_id != tournament_id:
                        target = (
                            event.tournaments_by_id.get(tournament_id)
                            if tournament_id is not None
                            else None
                        )
                        if target is not None and not target.can_add_teams:
                            continue
                        team.set_tournament(tournament_id, database)
                        # A team joining a tournament with paired rounds
                        # is zero-point-byed for them, like late-added
                        # players.
                        team.give_byes_for_paired_rounds(database)
                    if team.pairing_number != index:
                        team.set_pairing_number(index, database)
            # An auto-sort tournament re-orders itself regardless of the
            # drag order (e.g. a team dragged into it from elsewhere).
            for tournament_id in by_tournament:
                if tournament_id is None:
                    continue
                tournament = event.tournaments_by_id.get(tournament_id)
                if tournament is not None:
                    tournament.resort_teams(database)
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
            # Roster order can change the round-1 lineup average.
            self._resort_team_tournament(team, database)
        return self._admin_event_teams_render(
            web_context, self._team_roster_modal_context(web_context)
        )

    @staticmethod
    def _resort_team_tournament(team: Team, database: EventDatabase) -> None:
        """Re-apply the team's tournament auto-sort after a roster
        change. No-op when the team isn't assigned to a tournament."""
        tournament = team.tournament
        if tournament is not None:
            tournament.resort_teams(database)

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

        if tournament_id is not None and 'tournament_id' not in errors:
            is_new_assignment = (
                action == FormAction.CREATE
                or tournament_id != web_context.get_admin_team().tournament_id
            )
            if (
                is_new_assignment
                and not event.tournaments_by_id[tournament_id].can_add_teams
            ):
                errors['tournament_id'] = _(
                    'This tournament has already been paired; '
                    'teams can no longer be added.'
                )

        if action == FormAction.UPDATE:
            existing_team = web_context.get_admin_team()
            if existing_team.has_been_paired:
                # The tournament field is disabled for paired teams, so it
                # submits nothing — preserve the current tournament. Only
                # a (bypassed) explicit different value is an error.
                if (
                    tournament_id is not None
                    and tournament_id != existing_team.tournament_id
                ):
                    errors['tournament_id'] = _(
                        'This team has already been paired; its tournament cannot be changed.'
                    )
                else:
                    tournament_id = existing_team.tournament_id

        group_id: int | None = None
        raw_group_id = WebContext.form_data_to_str(data, field := 'group_id')
        if raw_group_id:
            try:
                group_id = int(raw_group_id)
            except ValueError:
                errors[field] = f'Invalid group id [{raw_group_id}].'
            else:
                if group_id not in event.team_groups_by_id:
                    errors[field] = _('Unknown group.')
                    group_id = None

        # Captain: a roster player (by id), a non-playing captain
        # ('other' + free-typed name), or none.
        captain_id: int | None = None
        captain_name: str | None = None
        raw_captain = WebContext.form_data_to_str(data, field := 'captain') or ''
        if raw_captain == 'other':
            captain_name = (
                WebContext.form_data_to_str(data, 'captain_name') or ''
            ).strip() or None
            if captain_name is None:
                errors['captain_name'] = _('This field is required.')
        elif raw_captain:
            try:
                captain_id = int(raw_captain)
            except ValueError:
                errors[field] = f'Invalid captain id [{raw_captain}].'
            else:
                existing = web_context.admin_team
                roster_ids = (
                    {p.id for p in existing.players}
                    if existing and action == FormAction.UPDATE
                    else set()
                )
                if captain_id not in roster_ids:
                    errors[field] = _('The captain must belong to the team roster.')
                    captain_id = None

        if errors:
            return None, errors

        federation: str | None = None
        raw_federation = WebContext.form_data_to_str(data, field := 'federation')
        if raw_federation:
            if raw_federation not in SharlyChessConfig().federations:
                errors[field] = _('Unknown federation.')
            else:
                federation = raw_federation

        existing = web_context.admin_team
        stored_team = StoredTeam(
            id=existing.id if existing and action == FormAction.UPDATE else None,
            name=name,
            tournament_id=tournament_id,
            group_id=group_id,
            captain_id=captain_id,
            captain_name=captain_name,
            federation=federation,
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
        with EventDatabase(event.uniq_id, True) as database:
            team.give_byes_for_paired_rounds(database)
            self._resort_team_tournament(team, database)
        Message.success(
            request,
            _('Team [{team}] has been created.').format(team=team.name),
        )
        if add_other:
            next_data = WebContext.values_dict_to_form_data(
                {
                    'name': '',
                    'tournament_id': stored_team.tournament_id or '',
                    'group_id': stored_team.group_id or '',
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
        tournament_changed = team.stored_team.tournament_id != stored_team.tournament_id
        # The team leaves this tournament when it changes — renumber what's left.
        old_tournament = team.tournament if tournament_changed else None
        # A team moving tournaments takes a fresh pairing number on the new side
        # (its old one belongs to the old tournament and could collide).
        if tournament_changed:
            team.stored_team.pairing_number = None
        team.stored_team.name = stored_team.name
        team.stored_team.tournament_id = stored_team.tournament_id
        team.stored_team.group_id = stored_team.group_id
        team.stored_team.captain_id = stored_team.captain_id
        team.stored_team.captain_name = stored_team.captain_name
        team.stored_team.federation = stored_team.federation
        event = web_context.get_admin_event()
        with EventDatabase(event.uniq_id, True) as database:
            team.update(database)
        event.clear_team_cache()
        for tournament in event.tournaments:
            tournament.clear_team_cache()
        with EventDatabase(event.uniq_id, True) as database:
            if tournament_changed:
                team.give_byes_for_paired_rounds(database)
            self._resort_team_tournament(team, database)
            if old_tournament is not None:
                old_tournament.resort_teams(database)
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
        tournament = team.tournament
        event.delete_team(team)
        # Close the gap left in the pairing numbers of the old tournament.
        if tournament is not None:
            with EventDatabase(event.uniq_id, True) as database:
                tournament.resort_teams(database)
        Message.success(
            request,
            _('Team [{team}] has been deleted.').format(team=team_name),
        )
        return self._admin_event_teams_render(web_context)
