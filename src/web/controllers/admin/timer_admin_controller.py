from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, date, timedelta
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.enums import RequestEncodingType
from litestar.exceptions import NotFoundException, ClientException
from litestar.params import Body, FromPath, FromQuery
from litestar.plugins.htmx import HTMXRequest
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.exception import FormError
from common.i18n import _, ngettext
from common.i18n.utils import by
from data.access_levels.actions import AuthAction
from data.event import Event
from data.screens.family import Family
from data.screens.manager import ScreenTypeManager
from data.screens.rotator import Rotator
from data.screens.screen import Screen
from data.screens.screen_types import ScreenType
from data.screens.timer import Timer, TimerHour
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTimer, StoredTimerHour
from utils.date_time import format_date, format_time
from utils.enum import FormAction
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard
from web.messages import Message
from web.session import SessionTimersAddOtherActive


@dataclass
class TimerUsageItem:
    field: str
    label: str
    screen_type: ScreenType | None
    other_timer: str | None
    checked: bool
    channels: list[str] = dataclass_field(default_factory=list)
    pages: int | None = None


class TimerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        timer_id: int | None = None,
        timer_hour_id: int | None = None,
        reload_event: bool = False,
    ):
        super().__init__(request, reload_event)
        assert self.admin_event is not None
        self.admin_timer: Timer | None = None
        self.admin_timer_hour: TimerHour | None = None

        if timer_id:
            try:
                self.admin_timer = self.admin_event.timers_by_id[timer_id]
            except KeyError:
                raise NotFoundException(f'Timer [{timer_id}] not found.') from None

        if timer_hour_id:
            assert self.admin_timer is not None
            try:
                self.admin_timer_hour = self.admin_timer.timer_hours_by_id[
                    timer_hour_id
                ]
            except KeyError:
                raise NotFoundException(
                    f'Hour [{timer_hour_id}] not found for timer [{self.admin_timer.name}].'
                ) from None

    def get_admin_timer(self) -> Timer:
        assert self.admin_timer is not None
        return self.admin_timer

    def get_admin_timer_hour(self) -> TimerHour:
        assert self.admin_timer_hour is not None
        return self.admin_timer_hour

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_timer': self.admin_timer,
            'admin_timer_hour': self.admin_timer_hour,
            'admin_event_tab': 'admin-event-timers-tab',
        }


class TimerAdminController(BaseEventAdminController):
    # Litestar declares `guards` on `Controller` as an instance variable, so
    # it cannot be narrowed to a class variable here.
    guards = [  # noqa: RUF012
        EventGuard(),
        ActionGuard(AuthAction.MANAGE_SCREENS),
    ]

    @classmethod
    def _admin_event_timers_render(
        cls,
        web_context: TimerAdminWebContext,
        template_context: dict[str, Any] | None = None,
    ) -> Template:
        return cls._admin_base_event_render(
            web_context.template_context | (template_context or {})
        )

    @get(
        path='/event/{event_uniq_id:str}/timers',
        name='admin-event-timers-tab',
    )
    async def htmx_admin_event_timers_tab(self, request: HTMXRequest) -> Template:
        return self._admin_event_timers_render(TimerAdminWebContext(request))

    # -------------------------------------------------------------------------
    # Default timers
    # -------------------------------------------------------------------------

    @classmethod
    def _default_timers_modal_context(
        cls,
        web_context: TimerAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        stored_event = web_context.get_admin_event().stored_event
        if data is None:
            delays = stored_event.timer_delays
            data = {}
            for i in range(1, 4):
                data |= WebContext.values_dict_to_form_data({f'delay_{i}': delays[i]})
        return {
            'modal': 'default-timers',
            'errors': errors or {},
            'data': data,
        }

    @get(
        path='/default-timers-modal/{event_uniq_id:str}',
        name='admin-default-timers-modal',
    )
    async def htmx_admin_default_timers_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = TimerAdminWebContext(request)
        return self._admin_event_timers_render(
            web_context, self._default_timers_modal_context(web_context)
        )

    @patch(
        path='/default-timers-update/{event_uniq_id:str}',
        name='default-timers-update',
    )
    async def htmx_admin_default_timers_update(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request)
        event = web_context.get_admin_event()

        errors: dict[str, str] = {}
        stored_event = event.stored_event

        timer_delays: dict[int, int | None] = dict.fromkeys(range(1, 4))
        for i in range(1, 4):
            field = f'delay_{i}'
            try:
                timer_delays[i] = WebContext.form_data_to_int(data, field, minimum=0)
            except ValueError:
                errors[field] = _(
                    'Invalid delay [{delay}] (positive integer or 0 expected).'
                ).format(delay=data[field])

        if errors:
            return self._admin_event_timers_render(
                web_context,
                self._default_timers_modal_context(web_context, data, errors),
            )

        stored_event.timer_delays = timer_delays

        with EventDatabase(event.uniq_id, write=True) as event_database:
            event_database.update_stored_event(stored_event)
        web_context = TimerAdminWebContext(request, reload_event=True)
        return self._admin_event_timers_render(web_context)

    # -------------------------------------------------------------------------
    # Timer
    # -------------------------------------------------------------------------

    @classmethod
    def _timer_form_modal_context(
        cls,
        web_context: TimerAdminWebContext,
        action: FormAction,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        usage_sections = cls._timer_usage_sections(
            event,
            web_context.get_admin_timer() if action == FormAction.UPDATE else None,
            data,
        )
        if data is None:
            delays: dict[int, int | None]
            if action == FormAction.CREATE:
                name = event.get_unused_timer_name()
                delays = dict.fromkeys(range(1, 4))
            else:
                stored_timer = web_context.get_admin_timer().stored_timer
                delays = stored_timer.delays
                if action == FormAction.CLONE:
                    name = event.get_unused_timer_name(stored_timer.name)
                else:
                    name = stored_timer.name
            data = {'name': WebContext.value_to_form_data(name)}
            for i in range(1, 4):
                data |= WebContext.values_dict_to_form_data({f'delay_{i}': delays[i]})
        return {
            'modal': 'timer',
            'action': action,
            'data': data,
            'errors': errors or {},
            'usage_sections': usage_sections,
        }

    @staticmethod
    def _read_timer_form_data(
        web_context: TimerAdminWebContext,
        action: FormAction,
        data: dict[str, str],
    ) -> tuple[StoredTimer | None, dict[str, str]]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        colors: dict[int, str | None] = (
            dict.fromkeys(range(1, 4))
            if action == FormAction.CREATE
            else dict(web_context.get_admin_timer().stored_timer.colors)
        )
        delays: dict[int, int | None] = dict.fromkeys(range(1, 4))
        name = WebContext.form_data_to_str(data, field := 'name') or ''
        if not name:
            errors[field] = _('This field is required.')
        else:
            used_names = list(event.timers_by_name.keys())
            if action == FormAction.UPDATE:
                used_names.remove(web_context.get_admin_timer().name)
            if name in used_names:
                errors[field] = _('This name is already used.')

        for i in range(1, 4):
            field = f'delay_{i}'
            try:
                delays[i] = WebContext.form_data_to_int(data, field, minimum=0)
            except ValueError:
                errors[field] = _(
                    'Invalid delay [{delay}] (positive integer or 0 expected).'
                ).format(delay=data[field])
        if errors:
            return None, errors
        return StoredTimer(
            id=None,
            name=name,
            colors=colors,
            delays=delays,
            errors=errors,
        ), {}

    @get(
        path='/timer-modal/create/{event_uniq_id:str}',
        name='admin-timer-create-modal',
    )
    async def htmx_admin_timer_create_modal(
        self,
        request: HTMXRequest,
    ) -> Template:
        web_context = TimerAdminWebContext(request)
        return self._admin_event_timers_render(
            web_context,
            self._timer_form_modal_context(web_context, FormAction.CREATE),
        )

    @get(
        path='/timer-modal/update/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-update-modal',
    )
    async def htmx_admin_timer_update_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            self._timer_form_modal_context(web_context, FormAction.UPDATE),
        )

    @get(
        path='/timer-modal/clone/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-clone-modal',
    )
    async def htmx_admin_timer_clone_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            self._timer_form_modal_context(web_context, FormAction.CLONE),
        )

    @get(
        path='/timer-modal/delete/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-delete-modal',
    )
    async def htmx_admin_timer_delete_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            {'modal': 'timer_delete'},
        )

    @get(
        path='/timer-hours-modal/clear/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hours-clear-modal',
    )
    async def htmx_admin_timer_hours_clear_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            {'modal': 'timer_hours_clear'},
        )

    @post(path='/timer-create/{event_uniq_id:str}', name='admin-timer-create')
    async def htmx_admin_timer_create(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request)
        stored_timer, errors = self._read_timer_form_data(
            web_context, FormAction.CREATE, data
        )
        if not stored_timer:
            return self._admin_event_timers_render(
                web_context,
                self._timer_form_modal_context(
                    web_context, FormAction.CREATE, data, errors
                ),
            )
        event = web_context.get_admin_event()
        timer = event.create_timer(stored_timer)
        self._apply_timer_usage(event, timer, data)
        web_context.admin_timer = timer
        message = _('Timer [{timer}] has been created.').format(timer=timer.name)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context(message)
        )

    @post(
        path='/timer-create-from-schedule/{event_uniq_id:str}/{tournament_id:int}',
        name='admin-timer-create-from-schedule',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_create_from_schedule(
        self,
        request: HTMXRequest,
        tournament_id: FromPath[int],
    ) -> Template:
        """Creates a timer named after the tournament, with a round hour for each
        scheduled round."""
        web_context = TimerAdminWebContext(request)
        event = web_context.get_admin_event()
        tournament = event.tournaments_by_id.get(tournament_id)
        if tournament is None:
            raise NotFoundException(f'Tournament [{tournament_id}] not found.')
        timer = event.create_timer(
            StoredTimer(
                id=None,
                name=event.get_unused_timer_name(tournament.name),
                colors=dict.fromkeys(range(1, 4)),
                delays=dict.fromkeys(range(1, 4)),
            )
        )
        timer.copy_schedule(
            tournament,
            [
                schedule_round.round
                for schedule_round in timer.schedule_rounds(tournament)
            ],
        )
        web_context.admin_timer = timer
        message = _('Timer [{timer}] has been created.').format(timer=timer.name)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context(message)
        )

    @post(
        path='/timer-clone/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-clone',
    )
    async def htmx_admin_timer_clone(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        stored_timer, errors = self._read_timer_form_data(
            web_context, FormAction.CLONE, data
        )
        if not stored_timer:
            return self._admin_event_timers_render(
                web_context,
                self._timer_form_modal_context(
                    web_context, FormAction.CLONE, data, errors
                ),
            )
        event = web_context.get_admin_event()
        cloned_timer = web_context.get_admin_timer()
        stored_timer.stored_timer_hours = [
            replace(timer_hour.stored_timer_hour, id=None)
            for timer_hour in cloned_timer.sorted_timer_hours
        ]
        timer = event.create_timer(stored_timer)
        self._apply_timer_usage(event, timer, data)
        web_context.admin_timer = timer
        message = _('Timer [{timer}] has been created.').format(timer=timer.name)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context(message)
        )

    @patch(
        path='/timer-update/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-update',
    )
    async def htmx_admin_timer_update(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        stored_timer, errors = self._read_timer_form_data(
            web_context, FormAction.UPDATE, data
        )
        if not stored_timer:
            return self._admin_event_timers_render(
                web_context,
                self._timer_form_modal_context(
                    web_context, FormAction.UPDATE, data, errors
                ),
            )
        timer = web_context.get_admin_timer()
        timer.update(stored_timer)
        self._apply_timer_usage(web_context.get_admin_event(), timer, data)
        message = _('Timer [{timer}] has been updated.').format(timer=timer.name)
        Message.success(request, message)
        return self._admin_event_timers_render(
            TimerAdminWebContext(request, reload_event=True)
        )

    @delete(
        path='/timer-delete/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_delete(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        event = web_context.get_admin_event()
        timer = web_context.get_admin_timer()
        event.delete_timer(timer)
        Message.success(
            request,
            _('Timer [{timer}] has been deleted.').format(timer=timer.name),
        )
        return self._admin_event_timers_render(web_context)

    # -------------------------------------------------------------------------
    # Quick countdown
    # -------------------------------------------------------------------------

    QUICK_MINUTES = (5, 10, 15, 30)

    @staticmethod
    def _quick_default_timer_ids(event: Event) -> list[int]:
        shown = [
            timer.id
            for timer in event.timers
            if timer.screens or timer.families or timer.rotators
        ]
        return shown or [timer.id for timer in event.timers]

    @classmethod
    def _quick_countdown_modal_context(
        cls,
        web_context: TimerAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        event = web_context.get_admin_event()
        if data is None:
            data = {'label': _('Next round'), 'minutes': '5'} | {
                f'timer_{timer_id}': 'on'
                for timer_id in cls._quick_default_timer_ids(event)
            }
            if not event.timers:
                data['new_timer'] = 'on'
        return {
            'modal': 'timer_quick',
            'data': data,
            'errors': errors or {},
            'quick_minutes': cls.QUICK_MINUTES,
            'quick_timers': sorted(event.timers, key=by('name')),
        }

    @get(
        path='/timer-quick-modal/{event_uniq_id:str}',
        name='admin-timer-quick-modal',
    )
    async def htmx_admin_timer_quick_modal(self, request: HTMXRequest) -> Template:
        web_context = TimerAdminWebContext(request)
        return self._admin_event_timers_render(
            web_context, self._quick_countdown_modal_context(web_context)
        )

    @staticmethod
    def _quick_countdown_time(
        data: dict[str, str], errors: dict[str, str]
    ) -> datetime | None:
        now = datetime.now()
        at = (data.get('at') or '').strip()
        if at:
            try:
                at_time = datetime.strptime(at, '%H:%M').time()
            except ValueError:
                errors['at'] = _('Invalid time [{time}].').format(time=at)
                return None
            triggered_at = datetime.combine(now.date(), at_time)
            if triggered_at <= now:
                errors['at'] = _('This time has already passed.')
                return None
            return triggered_at
        try:
            minutes = WebContext.form_data_to_int(data, 'minutes', minimum=1)
        except ValueError:
            minutes = None
        if minutes is None:
            errors['minutes'] = _('Choose when the countdown ends.')
            return None
        start = now.replace(second=0, microsecond=0)
        if start < now:
            start += timedelta(minutes=1)
        return start + timedelta(minutes=minutes)

    @post(
        path='/timer-quick/{event_uniq_id:str}',
        name='admin-timer-quick',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_quick(
        self,
        request: HTMXRequest,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        """Adds a moment, a few minutes from now, to the chosen timers, and to a
        new timer if asked, whose screens are chosen next."""
        web_context = TimerAdminWebContext(request)
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        label = WebContext.form_data_to_str(data, 'label') or ''
        if not label:
            errors['label'] = _('This field is required.')
        triggered_at = self._quick_countdown_time(data, errors)
        timers = [
            timer
            for timer in event.timers
            if WebContext.form_data_to_bool(data, f'timer_{timer.id}')
        ]
        new_timer = WebContext.form_data_to_bool(data, 'new_timer')
        if not timers and not new_timer:
            errors['timers'] = _('Choose at least one timer.')
        if errors:
            return self._admin_event_timers_render(
                web_context,
                self._quick_countdown_modal_context(web_context, data, errors),
            )
        assert triggered_at is not None
        created_timer: Timer | None = None
        if new_timer:
            created_timer = event.create_timer(
                StoredTimer(
                    id=None,
                    name=event.get_unused_timer_name(),
                    colors=dict.fromkeys(range(1, 4)),
                    delays=dict.fromkeys(range(1, 4)),
                )
            )
            timers.append(created_timer)
        added: list[str] = []
        taken: list[str] = []
        for timer in timers:
            if any(hour.triggered_at == triggered_at for hour in timer.timer_hours):
                taken.append(timer.name)
                continue
            timer.add_timer_hour(
                StoredTimerHour(
                    id=None,
                    timer_id=timer.id,
                    triggered_at=triggered_at,
                    label=label,
                )
            )
            added.append(timer.name)
        if added:
            Message.success(
                request,
                _('Countdown to [{label}] at {time} added to {timers}.').format(
                    label=label,
                    time=format_time(triggered_at),
                    timers=', '.join(f'[{name}]' for name in added),
                ),
            )
        if taken:
            Message.warning(
                request,
                _('Another hour is already set at {time} on {timers}.').format(
                    time=format_time(triggered_at),
                    timers=', '.join(f'[{name}]' for name in taken),
                ),
            )
        if created_timer is not None:
            web_context.admin_timer = created_timer
            return self._admin_event_timers_render(
                web_context, self._timer_usage_modal_context(web_context)
            )
        return self._admin_event_timers_render(web_context)

    # -------------------------------------------------------------------------
    # Timer usage
    # -------------------------------------------------------------------------

    @staticmethod
    def _timer_usage_items(
        event: Event,
    ) -> list[tuple[str, Screen | Family | Rotator]]:
        return (
            [(f'screen_{screen.id}', screen) for screen in event.sorted_basic_screens]
            + [(f'family_{family.id}', family) for family in event.sorted_families]
            + [(f'rotator_{rotator.id}', rotator) for rotator in event.sorted_rotators]
        )

    @classmethod
    def _timer_usage_sections(
        cls,
        event: Event,
        timer: Timer | None,
        data: dict[str, str] | None = None,
    ) -> list[tuple[str, list[tuple[ScreenType | None, list[TimerUsageItem]]]]]:
        """The screens, multi-screens and rotators of the event, grouped for the
        checkboxes that choose those showing the timer: checked as in `data`
        when the form is shown again, as they are otherwise."""
        items_by_kind: dict[str, list[TimerUsageItem]] = {
            'screen': [],
            'family': [],
            'rotator': [],
        }
        for field, item in cls._timer_usage_items(event):
            kind = field.split('_')[0]
            on_timer = (
                timer is not None
                and item.timer is not None
                and item.timer.id == timer.id
            )
            items_by_kind[kind].append(
                TimerUsageItem(
                    field=field,
                    label=item.display_name if isinstance(item, Family) else item.name,
                    screen_type=None if isinstance(item, Rotator) else item.screen_type,
                    other_timer=(
                        item.timer.name if item.timer and not on_timer else None
                    ),
                    checked=(
                        WebContext.form_data_to_bool(data, field)
                        if data is not None
                        else on_timer
                    ),
                    channels=[
                        display_controller.name
                        for display_controller in item.display_controllers
                    ],
                    pages=(
                        len(item.screens_by_uniq_id)
                        if isinstance(item, Family)
                        else None
                    ),
                )
            )
        screens = items_by_kind['screen'] + items_by_kind['family']
        sections: list[
            tuple[str, list[tuple[ScreenType | None, list[TimerUsageItem]]]]
        ] = [
            (
                _('Screens'),
                [
                    (
                        screen_type,
                        sorted(
                            [
                                item
                                for item in screens
                                if item.screen_type == screen_type
                            ],
                            key=by('label'),
                        ),
                    )
                    for screen_type in ScreenTypeManager(event).objects()
                ],
            ),
            (_('Rotators'), [(None, items_by_kind['rotator'])]),
        ]
        return [
            (
                title,
                [(screen_type, items) for screen_type, items in groups if items],
            )
            for title, groups in sections
            if any(items for _screen_type, items in groups)
        ]

    @classmethod
    def _apply_timer_usage(
        cls, event: Event, timer: Timer, data: dict[str, str]
    ) -> None:
        """Shows the timer on the checked screens, multi-screens and rotators,
        and takes it off the unchecked ones that showed it."""
        for field, item in cls._timer_usage_items(event):
            on_timer = item.timer is not None and item.timer.id == timer.id
            if WebContext.form_data_to_bool(data, field):
                if not on_timer:
                    item.set_timer(timer.id)
            elif on_timer:
                item.set_timer(None)

    @classmethod
    def _timer_usage_modal_context(
        cls, web_context: TimerAdminWebContext
    ) -> dict[str, Any]:
        return {
            'modal': 'timer_usage',
            'usage_sections': cls._timer_usage_sections(
                web_context.get_admin_event(), web_context.get_admin_timer()
            ),
        }

    @get(
        path='/timer-usage-modal/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-usage-modal',
    )
    async def htmx_admin_timer_usage_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context, self._timer_usage_modal_context(web_context)
        )

    @patch(
        path='/timer-usage-update/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-usage-update',
    )
    async def htmx_admin_timer_usage_update(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        timer = web_context.get_admin_timer()
        self._apply_timer_usage(web_context.get_admin_event(), timer, data)
        Message.success(
            request,
            _('The screens of timer [{timer}] have been updated.').format(
                timer=timer.name
            ),
        )
        return self._admin_event_timers_render(
            TimerAdminWebContext(request, reload_event=True)
        )

    # -------------------------------------------------------------------------
    # Timer Hour
    # -------------------------------------------------------------------------

    @classmethod
    def _timer_hour_form_modal_context(
        cls,
        web_context: TimerAdminWebContext,
        action: FormAction,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
        success_message: str | None = None,
    ) -> dict[str, Any]:
        timer = web_context.get_admin_timer()
        if data is None:
            round_: int | None
            label: str | None
            if action == FormAction.CREATE:
                round_ = timer.next_round
                label = None
                triggered_at = timer.free_hour_time(datetime.now())
                text_before: str | None = ''
                text_after: str | None = ''
            else:
                hour = web_context.get_admin_timer_hour()
                label = hour.label
                if action == FormAction.CLONE:
                    round_ = None if hour.round is None else timer.next_round
                else:
                    round_ = hour.round
                triggered_at = hour.triggered_at
                text_before = hour.stored_timer_hour.text_before
                text_after = hour.stored_timer_hour.text_after
            data = WebContext.values_dict_to_form_data(
                {
                    'hour_kind': 'other' if round_ is None else 'round',
                    'hour_round': round_,
                    'hour_label': label,
                    'triggered_at': triggered_at,
                    'text_before': text_before,
                    'text_after': text_after,
                }
            )
        request = web_context.request
        return {
            'modal': 'timer_hour_form',
            'action': action,
            'data': data,
            'default_texts': {
                'round': TimerHour.default_texts('__round__', None),
                'round_label': TimerHour.default_texts('__round__', '__label__'),
                'other': TimerHour.default_texts(None, '__label__'),
            },
            'errors': errors or {},
            'success_message': success_message,
            'add_other_active': SessionTimersAddOtherActive(request).get(),
        }

    @staticmethod
    def _timer_hours_modal_context(
        success_message: str | None = None,
    ) -> dict[str, Any]:
        return {
            'modal': 'timer_hours',
            'success_message': success_message,
        }

    @get(
        path='/timer-hours-modal/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hours-modal',
    )
    async def htmx_admin_timer_hours_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        return self._admin_event_timers_render(
            TimerAdminWebContext(request, timer_id),
            self._timer_hours_modal_context(),
        )

    @get(
        path='/timer-hour-modal/create/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hour-create-modal',
    )
    async def htmx_admin_timer_hour_create_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            self._timer_hour_form_modal_context(web_context, FormAction.CREATE),
        )

    @get(
        path=(
            '/timer-hour-modal/update/{event_uniq_id:str}/'
            '{timer_id:int}/{timer_hour_id:int}'
        ),
        name='admin-timer-hour-update-modal',
    )
    async def htmx_admin_timer_hour_update_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        timer_hour_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        return self._admin_event_timers_render(
            web_context,
            self._timer_hour_form_modal_context(web_context, FormAction.UPDATE),
        )

    @get(
        path=(
            '/timer-hour-modal/clone/{event_uniq_id:str}/'
            '{timer_id:int}/{timer_hour_id:int}'
        ),
        name='admin-timer-hour-clone-modal',
    )
    async def htmx_admin_timer_hour_clone_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        timer_hour_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        return self._admin_event_timers_render(
            web_context,
            self._timer_hour_form_modal_context(web_context, FormAction.CLONE),
        )

    @staticmethod
    def _read_timer_hour_form_data(
        web_context: TimerAdminWebContext,
        action: FormAction,
        data: dict[str, str],
    ) -> tuple[StoredTimerHour | None, dict[str, str]]:
        timer = web_context.get_admin_timer()
        errors: dict[str, str] = {}
        is_round = data.get('hour_kind') != 'other'
        round_: int | None = None
        label = WebContext.form_data_to_str(data, 'hour_label') or None
        if is_round:
            try:
                round_ = WebContext.form_data_to_int(data, 'hour_round', minimum=1)
            except ValueError:
                errors['hour_round'] = _('Invalid round [{round}].').format(
                    round=data.get('hour_round')
                )
            else:
                if round_ is None:
                    errors['hour_round'] = _('This field is required.')
        elif not label:
            errors['hour_label'] = _('This field is required.')
        triggered_at: datetime | None = None
        field = 'triggered_at'
        try:
            triggered_at = WebContext.form_data_to_datetime(data, field)
            if not triggered_at:
                errors[field] = _('This field is required.')
            else:
                used_datetimes = [
                    timer_hour.triggered_at for timer_hour in timer.timer_hours
                ]
                if action == FormAction.UPDATE:
                    used_datetimes.remove(
                        web_context.get_admin_timer_hour().triggered_at
                    )
                if triggered_at in used_datetimes:
                    errors[field] = _('There already is an hour defined at this time.')
                if not timer.first_date <= triggered_at.date() <= timer.last_date:
                    errors[field] = _('Choose a date from {first} to {last}.').format(
                        first=timer.first_date_str, last=timer.last_date_str
                    )
        except FormError as e:
            errors[field] = str(e)
        text_before = WebContext.form_data_to_str(data, 'text_before')
        text_after = WebContext.form_data_to_str(data, 'text_after')
        if errors:
            return None, errors
        assert triggered_at is not None
        return StoredTimerHour(
            id=None,
            timer_id=timer.id,
            triggered_at=triggered_at,
            round=round_,
            label=label,
            text_before=text_before,
            text_after=text_after,
        ), {}

    @post(
        path='/timer-hour/create/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hour-create',
    )
    async def htmx_admin_timer_hour_create(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        add_other = WebContext.resolve_add_other(
            data, SessionTimersAddOtherActive(request)
        )
        stored_timer_hour, errors = self._read_timer_hour_form_data(
            web_context, FormAction.CREATE, data
        )
        if not stored_timer_hour:
            return self._admin_event_timers_render(
                web_context,
                self._timer_hour_form_modal_context(
                    web_context, FormAction.CREATE, data, errors
                ),
            )
        timer = web_context.get_admin_timer()
        timer_hour = timer.add_timer_hour(stored_timer_hour)
        message = _('Hour [{hour}] has been created.').format(hour=timer_hour.name)
        if add_other:
            template_context = self._timer_hour_form_modal_context(
                web_context, FormAction.CREATE, success_message=message
            )
        else:
            template_context = self._timer_hours_modal_context(message)
        return self._admin_event_timers_render(web_context, template_context)

    @staticmethod
    def _schedule_tournaments(event: Event) -> list[Tournament]:
        return [
            tournament
            for tournament in event.sorted_tournaments
            if tournament.has_schedule
        ]

    @classmethod
    def _timer_hours_copy_modal_context(
        cls, web_context: TimerAdminWebContext, tournament_id: int | None
    ) -> dict[str, Any]:
        tournaments = cls._schedule_tournaments(web_context.get_admin_event())
        tournament = next(
            (t for t in tournaments if t.id == tournament_id),
            tournaments[0] if tournaments else None,
        )
        return {
            'modal': 'timer_hours_copy',
            'schedule_tournaments': tournaments,
            'schedule_tournament': tournament,
            'schedule_rounds': (
                web_context.get_admin_timer().schedule_rounds(tournament)
                if tournament
                else []
            ),
        }

    @get(
        path='/timer-hours-copy-modal/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hours-copy-modal',
    )
    async def htmx_admin_timer_hours_copy_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        tournament_id: FromQuery[int | None] = None,
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            self._timer_hours_copy_modal_context(web_context, tournament_id),
        )

    @post(
        path='/timer-hours/copy/{event_uniq_id:str}/{timer_id:int}/{tournament_id:int}',
        name='admin-timer-hours-copy',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_hours_copy(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        tournament_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        """Adds or moves the round hours of the checked rounds of a tournament's
        schedule."""
        web_context = TimerAdminWebContext(request, timer_id)
        tournament = web_context.get_admin_event().tournaments_by_id.get(tournament_id)
        if tournament is None:
            raise NotFoundException(f'Tournament [{tournament_id}] not found.')
        rounds = [
            int(field.removeprefix('round_'))
            for field in data
            if field.startswith('round_')
            and field.removeprefix('round_').isdigit()
            and WebContext.form_data_to_bool(data, field)
        ]
        added, moved = web_context.get_admin_timer().copy_schedule(tournament, rounds)
        messages = []
        if added:
            messages.append(
                ngettext('{count} hour added.', '{count} hours added.', added).format(
                    count=added
                )
            )
        if moved:
            messages.append(
                ngettext('{count} hour moved.', '{count} hours moved.', moved).format(
                    count=moved
                )
            )
        message = ' '.join(messages) or _('The hours already follow the schedule.')
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context(message)
        )

    @patch(
        path='/timer-hours/update-date/{event_uniq_id:str}/{timer_id:int}/{iso_date:str}',
        name='admin-timer-hours-update-date',
    )
    async def htmx_admin_timer_hours_update_date(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        iso_date: FromPath[str],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        timer = web_context.get_admin_timer()
        previous_date = date.fromisoformat(iso_date)
        new_date = WebContext.form_data_to_date(data, 'date')
        if not new_date:
            raise ClientException('Missing date field.')

        timer.update_timer_hours_date(previous_date, new_date)
        warning_message = ''
        previous_date_hours = timer.timer_hours_by_date_str.get(
            format_date(previous_date), []
        )
        if previous_date_hours:
            warning_message = ngettext(
                '{count} hour could not be moved (time conflict).',
                '{count} hours could not be moved (time conflict).',
                len(previous_date_hours),
            ).format(count=len(previous_date_hours))
        return self._admin_event_timers_render(
            web_context,
            self._timer_hours_modal_context()
            | {
                'warning_message': warning_message,
            },
        )

    @patch(
        path='/timer-hour/update/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-update',
    )
    async def htmx_admin_timer_hour_update(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        timer_hour_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        stored_timer_hour, errors = self._read_timer_hour_form_data(
            web_context, FormAction.UPDATE, data
        )
        if not stored_timer_hour:
            return self._admin_event_timers_render(
                web_context,
                self._timer_hour_form_modal_context(
                    web_context, FormAction.UPDATE, data, errors
                ),
            )
        timer_hour = web_context.get_admin_timer_hour()
        timer_hour.update(stored_timer_hour)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context()
        )

    POSTPONE_MINUTES = (5, 10, 15, 30)

    @classmethod
    def _timer_hour_postpone_modal_context(
        cls,
        web_context: TimerAdminWebContext,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        timer_hour = web_context.get_admin_timer_hour()
        later_hours = web_context.get_admin_timer().later_hours_of_the_day(timer_hour)
        if data is None:
            data = {'minutes': '15', 'later_hours': 'on' if later_hours else ''}
        return {
            'modal': 'timer_hour_postpone',
            'data': data,
            'errors': errors or {},
            'postpone_minutes': cls.POSTPONE_MINUTES,
            'later_hours': later_hours,
        }

    @get(
        path=(
            '/timer-hour-postpone-modal/{event_uniq_id:str}/'
            '{timer_id:int}/{timer_hour_id:int}'
        ),
        name='admin-timer-hour-postpone-modal',
    )
    async def htmx_admin_timer_hour_postpone_modal(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        timer_hour_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        return self._admin_event_timers_render(
            web_context, self._timer_hour_postpone_modal_context(web_context)
        )

    @patch(
        path='/timer-hour/postpone/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-postpone',
    )
    async def htmx_admin_timer_hour_postpone(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        timer_hour_id: FromPath[int],
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        timer = web_context.get_admin_timer()
        timer_hour = web_context.get_admin_timer_hour()
        errors: dict[str, str] = {}
        field = (
            'other_minutes' if (data.get('other_minutes') or '').strip() else 'minutes'
        )
        try:
            minutes = WebContext.form_data_to_int(data, field, minimum=1)
        except ValueError:
            minutes = None
        if minutes is None:
            errors[field] = _('Enter a number of minutes.')
        with_later_hours = WebContext.form_data_to_bool(data, 'later_hours')
        if minutes is not None:
            conflicts = timer.postpone_conflicts(timer_hour, minutes, with_later_hours)
            if conflicts:
                errors[field] = _('[{hour}] already takes that time.').format(
                    hour=conflicts[0].name
                )
        if errors:
            return self._admin_event_timers_render(
                web_context,
                self._timer_hour_postpone_modal_context(web_context, data, errors),
            )
        assert minutes is not None
        moved = timer.postpone(timer_hour, minutes, with_later_hours)
        message = ngettext(
            '{count} hour postponed by {minutes} min.',
            '{count} hours postponed by {minutes} min.',
            moved,
        ).format(count=moved, minutes=minutes)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context(message)
        )

    @delete(
        path='/timer-hour/delete/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_hour_delete(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
        timer_hour_id: FromPath[int],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        web_context.get_admin_timer().delete_timer_hour(timer_hour_id)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context()
        )

    @delete(
        path='/timer-hours/clear/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hours-clear',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_hours_clear(
        self,
        request: HTMXRequest,
        timer_id: FromPath[int],
    ) -> Template:
        """Delete all timer hours for a timer in one shot."""
        web_context = TimerAdminWebContext(request, timer_id)
        web_context.get_admin_timer().delete_all_timer_hours()
        message = _('All hours have been cleared.')
        web_context = TimerAdminWebContext(request, timer_id, reload_event=True)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context(message)
        )
