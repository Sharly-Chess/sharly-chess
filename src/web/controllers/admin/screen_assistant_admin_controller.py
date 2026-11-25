from typing import Annotated, Any

from litestar import get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException
from litestar.params import Body, FromQuery
from litestar.plugins.htmx import ClientRedirect, HTMXRequest
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK
from litestar_htmx import HTMXTemplate

from common.i18n import _
from data.access_levels.actions import AuthAction
from data.screens.assistant import (
    AssistantGoal,
    assistant_goal,
    assistant_goals,
    assistant_other_type_names,
    assistant_stages,
    assistant_summary,
    assistant_wizard,
    create_from_assistant,
)
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminController,
    BaseEventAdminWebContext,
)
from web.controllers.base_controller import WebContext
from web.guards import ActionGuard, EventGuard
from web.messages import Message
from web.session import SessionScreensTypeFilter


class ScreenAssistantAdminController(BaseEventAdminController):
    """The screen setup assistant (see ``data/screens/assistant.py``): a
    full page under the Screens tab, asking first for a goal, then the
    questions of the goal's wizard, and creating everything in one go."""

    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.MANAGE_SCREENS),
    ]

    @classmethod
    def _assistant_render(
        cls,
        request: HTMXRequest,
        goal_id: str | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        wizard_path: list[str] | None = None,
    ) -> HTMXTemplate:
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        template_context: dict[str, Any] = web_context.template_context
        # The assistant takes the place of the screens tab content.
        views = template_context['nav_tabs'].get('admin-event-views')
        if views:
            views['submenu']['admin-event-screens-tab']['template'] = (
                'screens/assistant.html'
            )
        goal: AssistantGoal | None = None
        if goal_id:
            goal = assistant_goal(event, goal_id)
            if goal is None or not goal.creatable:
                raise NotFoundException(f'Unknown assistant goal [{goal_id}].')
        template_context |= {
            'admin_event_tab': 'admin-event-screens-tab',
            'assistant_goals': assistant_goals(event),
            'assistant_other_type_names': assistant_other_type_names(event),
            'assistant_stages': assistant_stages(),
            'assistant_goal': goal,
            'errors': errors or {},
            'wizard_path': wizard_path or [],
        }
        if goal is not None:
            wizard = assistant_wizard(event, goal)
            wizard_defaults = wizard.default_data
            template_context |= {
                'wizard': wizard,
                'wizard_defaults': wizard_defaults,
                # The default values when the assistant opens.
                'data': wizard_defaults if data is None else data,
            }
        return HTMXTemplate(
            template_name='admin/event_layout.html',
            context=template_context,
        )

    @get(
        path='/screen-assistant/{event_uniq_id:str}',
        name='admin-screen-assistant',
    )
    async def htmx_admin_screen_assistant(
        self,
        request: HTMXRequest,
        goal: FromQuery[str | None] = None,
    ) -> Template:
        return self._assistant_render(request, goal_id=goal)

    @post(
        path='/screen-assistant-create/{event_uniq_id:str}',
        name='admin-screen-assistant-create',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_assistant_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        """Create what the assistant answers describe and redirect to the
        menu created, or to the screens of the goal's type."""
        form_data = WebContext.flatten_list_data(data)
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        goal_id = form_data.get('goal', '')
        goal = assistant_goal(event, goal_id)
        if goal is None or not goal.creatable:
            raise NotFoundException(f'Unknown assistant goal [{goal_id}].')
        wizard = assistant_wizard(event, goal)
        answers, wizard_path, errors = wizard.read_answers(form_data)
        if errors:
            return self._assistant_render(
                request,
                goal_id=goal_id,
                data=form_data,
                errors=errors,
                wizard_path=wizard_path,
            )
        creation = create_from_assistant(event, goal, answers)
        for created_screen_uniq_id in creation.screen_uniq_ids:
            Message.success(
                request,
                _('Screen [{screen_uniq_id}] has been created.').format(
                    screen_uniq_id=created_screen_uniq_id
                ),
            )
        for created_family_uniq_id in creation.family_uniq_ids:
            Message.success(
                request,
                _('Paged Screen [{family_uniq_id}] has been created.').format(
                    family_uniq_id=created_family_uniq_id
                ),
            )
        if creation.menu_name is not None:
            Message.success(
                request,
                _('Menu [{menu_name}] has been created.').format(
                    menu_name=creation.menu_name
                ),
            )
        if creation.channel_created:
            Message.success(
                request,
                _('Channel [{channel_name}] has been created.').format(
                    channel_name=creation.channel_name
                ),
            )
        # Asked to edit what was created, the tab opens its form too: the
        # screen or paged screen when a single one was created, else the
        # menu leading to the screens.
        edit = '&edit=1' if form_data.get('edit_after') else ''
        single_item = len(creation.screen_ids) + len(creation.family_ids) == 1
        # On to the menu created, or to the screens of the goal's type.
        if creation.menu_id is not None and not (edit and single_item):
            return ClientRedirect(
                redirect_to=request.app.route_reverse(
                    'admin-event-menus-tab', event_uniq_id=event.uniq_id
                )
                + f'?scroll_to={creation.menu_id}{edit}'
            )
        # A filter on another type would hide what was just created; the
        # filter is otherwise left alone, and the page scrolls to the
        # screen created instead.
        type_filter = SessionScreensTypeFilter(request)
        if type_filter.get() not in ('', goal.screen_type.id):
            type_filter.set('')
        scroll_to = ''
        if creation.screen_ids:
            scroll_to = f'?scroll_to={creation.screen_ids[0]}{edit}'
        elif creation.family_ids:
            scroll_to = f'?scroll_to=family-{creation.family_ids[0]}{edit}'
        return ClientRedirect(
            redirect_to=request.app.route_reverse(
                'admin-event-screens-tab', event_uniq_id=event.uniq_id
            )
            + scroll_to
        )

    @post(
        path='/screen-assistant-summary/{event_uniq_id:str}',
        name='admin-screen-assistant-summary',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_screen_assistant_summary(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str | list[str]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        """What the answers would create, shown before the Create button."""
        form_data = WebContext.flatten_list_data(data)
        web_context = BaseEventAdminWebContext(request)
        event = web_context.get_admin_event()
        goal = assistant_goal(event, form_data.get('goal', ''))
        if goal is None or not goal.creatable:
            raise NotFoundException('Unknown assistant goal.')
        wizard = assistant_wizard(event, goal)
        answers, _path, errors = wizard.read_answers(form_data)
        # On an error the Create button brings the question back; the
        # summary stays empty rather than guessing.
        summary_lines = [] if errors else assistant_summary(event, goal, answers)
        return HTMXTemplate(
            template_name='admin/screens/assistant_summary.html',
            context={'summary_lines': summary_lines},
        )
