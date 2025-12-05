from copy import copy
from datetime import datetime
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.exceptions import NotFoundException
from litestar.plugins.htmx import HTMXRequest
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.exception import FormError
from common.sharly_chess_config import SharlyChessConfig
from common.i18n import _
from data.access_levels.actions import AuthAction
from data.timer import Timer, TimerHour
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredTimer, StoredTimerHour
from utils.enum import FormAction
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.guards import EventGuard, ActionGuard
from web.messages import Message
from web.session import SessionHandler


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
                raise NotFoundException(f'Timer [{timer_id}] not found.')

        if timer_hour_id:
            assert self.admin_timer is not None
            try:
                self.admin_timer_hour = self.admin_timer.timer_hours_by_id[
                    timer_hour_id
                ]
            except KeyError:
                raise NotFoundException(
                    f'Hour [{timer_hour_id}] not found for timer [{self.admin_timer.name}].'
                )

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
    guards = [
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
            colors = stored_event.timer_colors
            delays = stored_event.timer_delays
            data = {}
            for i in range(1, 4):
                data |= WebContext.values_dict_to_form_data(
                    {
                        f'color_{i}': colors[i],
                        f'color_{i}_checkbox': colors[i] is None,
                        f'delay_{i}': delays[i],
                    }
                )
        return {
            'timer_color_texts': cls._get_timer_color_texts(
                SharlyChessConfig.default_timer_delays
            ),
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

        timer_colors: dict[int, str | None] = {i: None for i in range(1, 4)}
        timer_delays: dict[int, int | None] = {i: None for i in range(1, 4)}
        for i in range(1, 4):
            field = f'color_{i}'
            if not WebContext.form_data_to_bool(data, field + '_checkbox'):
                try:
                    timer_colors[i] = WebContext.form_data_to_rgb(data, field)
                except ValueError:
                    errors[field] = _(
                        'Invalid color [{color}] ([#RRGGBB] expected).'
                    ).format(color={data[field]})
            field = f'delay_{i}'
            try:
                timer_delays[i] = WebContext.form_data_to_int(data, field, minimum=1)
            except ValueError:
                errors[field] = _(
                    'Invalid delay [{delay}] (positive integer expected).'
                ).format(delay=data[field])

        if errors:
            return self._admin_event_timers_render(
                web_context,
                self._default_timers_modal_context(web_context, data, errors),
            )

        stored_event.timer_colors = timer_colors
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
        if data is None:
            colors: dict[int, str | None]
            delays: dict[int, int | None]
            if action == FormAction.CREATE:
                name = event.get_unused_timer_name()
                colors = {i: None for i in range(1, 4)}
                delays = {i: None for i in range(1, 4)}
            else:
                stored_timer = web_context.get_admin_timer().stored_timer
                colors = stored_timer.colors
                delays = stored_timer.delays
                if action == FormAction.CLONE:
                    name = event.get_unused_timer_name(stored_timer.name)
                else:
                    name = stored_timer.name
            data = {'name': WebContext.value_to_form_data(name)}
            for i in range(1, 4):
                data |= WebContext.values_dict_to_form_data(
                    {
                        f'color_{i}': colors[i],
                        f'color_{i}_checkbox': colors[i] is None,
                        f'delay_{i}': delays[i],
                    }
                )
        return {
            'timer_color_texts': cls._get_timer_color_texts(event.timer_delays),
            'modal': 'timer',
            'action': action,
            'data': data,
            'errors': errors or {},
        }

    @staticmethod
    def _read_timer_form_data(
        web_context: TimerAdminWebContext,
        action: FormAction,
        data: dict[str, str],
    ) -> tuple[StoredTimer | None, dict[str, str]]:
        event = web_context.get_admin_event()
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        colors: dict[int, str | None] = {i: None for i in range(1, 4)}
        color_checkboxes: dict[int, bool | None] = {i: None for i in range(1, 4)}
        delays: dict[int, int | None] = {i: None for i in range(1, 4)}
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
            field = f'color_{i}'
            color_checkboxes[i] = WebContext.form_data_to_bool(
                data, field + '_checkbox'
            )
            if not color_checkboxes[i]:
                try:
                    colors[i] = WebContext.form_data_to_rgb(data, field)
                except ValueError:
                    errors[field] = _(
                        'Invalid color [{color}] ([#RRGGBB] expected).'
                    ).format(color={data[field]})
            field = f'delay_{i}'
            try:
                delays[i] = WebContext.form_data_to_int(data, field, minimum=1)
            except ValueError:
                errors[field] = _(
                    'Invalid delay [{delay}] (positive integer expected).'
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
        timer_id: int,
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
        timer_id: int,
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
        timer_id: int,
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        return self._admin_event_timers_render(
            web_context,
            {'modal': 'timer_delete'},
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
        web_context.admin_timer = timer
        message = _('Timer [{timer}] has been created.').format(timer=timer.name)
        return self._admin_event_timers_render(
            web_context,
            self._timer_hour_form_modal_context(
                web_context, FormAction.CREATE, success_message=message
            ),
        )

    @post(
        path='/timer-clone/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-clone',
    )
    async def htmx_admin_timer_clone(
        self,
        request: HTMXRequest,
        timer_id: int,
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
        stored_timer.stored_timer_hours = copy(
            cloned_timer.stored_timer.stored_timer_hours
        )
        web_context.admin_timer = event.create_timer(stored_timer)
        return self._admin_event_timers_render(
            web_context,
            self._timer_hours_modal_context(_('Timer [{timer}] has been created.')),
        )

    @patch(
        path='/timer-update/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-update',
    )
    async def htmx_admin_timer_update(
        self,
        request: HTMXRequest,
        timer_id: int,
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
        message = _('Timer [{timer}] has been updated.').format(timer=timer.name)
        Message.success(request, message)
        return self._admin_event_timers_render(web_context)

    @delete(
        path='/timer-delete/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_delete(
        self,
        request: HTMXRequest,
        timer_id: int,
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
        event = web_context.get_admin_event()
        timer = web_context.get_admin_timer()
        if data is None:
            if action == FormAction.CREATE:
                uniq_id = str(timer.next_round)
                if timer.timer_hours:
                    triggered_at = timer.sorted_timer_hours[-1].triggered_at
                else:
                    triggered_at = datetime.combine(
                        event.start_date, datetime.min.time()
                    )
                text_before: str | None = ''
                text_after: str | None = ''
            else:
                hour = web_context.get_admin_timer_hour()
                if action == FormAction.CLONE:
                    if hour.uniq_id.isdigit():
                        uniq_id = str(timer.next_round)
                    else:
                        uniq_id = timer.get_unused_hour_name(hour.uniq_id)
                else:
                    uniq_id = hour.uniq_id
                triggered_at = hour.triggered_at
                text_before = hour.stored_timer_hour.text_before
                text_after = hour.stored_timer_hour.text_after
            data = WebContext.values_dict_to_form_data(
                {
                    'uniq_id': uniq_id,
                    'triggered_at': triggered_at,
                    'text_before': text_before,
                    'text_after': text_after,
                }
            )
        return {
            'modal': 'timer_hour_form',
            'action': action,
            'data': data,
            'errors': errors or {},
            'success_message': success_message,
            'add_other_active': (
                SessionHandler.get_session_admin_timer_add_other_active(
                    web_context.request
                )
            ),
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
        timer_id: int,
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
        timer_id: int,
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
        timer_id: int,
        timer_hour_id: int,
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
        timer_id: int,
        timer_hour_id: int,
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
        event = web_context.get_admin_event()
        timer = web_context.get_admin_timer()
        errors: dict[str, str] = {}
        uniq_id = WebContext.form_data_to_str(data, field := 'uniq_id') or ''
        if not uniq_id:
            errors[field] = _('This field is required.')
        else:
            uniq_ids = timer.timer_hour_uniq_ids
            if action == FormAction.UPDATE:
                uniq_ids.remove(web_context.get_admin_timer_hour().uniq_id)
            if uniq_id in uniq_ids:
                if uniq_id.isdigit():
                    errors[field] = _(
                        'There already is an hour for round #{round}.'
                    ).format(round=int(uniq_id))
                else:
                    errors[field] = _('Hour [{hour}] already exists.').format(
                        hour=uniq_id
                    )
            if uniq_id.isdigit():
                if int(uniq_id) == 0:
                    errors[field] = _('Round #0 is forbidden.')
                uniq_id = str(int(uniq_id))
        triggered_at: datetime | None = None
        try:
            triggered_at = WebContext.form_data_to_datetime(
                data, field := 'triggered_at'
            )
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
                if not event.start_date <= triggered_at.date() <= event.stop_date:
                    errors[field] = _(
                        'Time outside of event time range ({range}).'
                    ).format(range=event.date_range_str)
        except FormError as e:
            errors[field] = str(e)
        text_before = WebContext.form_data_to_str(data, field := 'text_before')
        if not uniq_id.isdigit() and not text_before:
            errors[field] = _('This field is required (except for rounds).')
        text_after = WebContext.form_data_to_str(data, field := 'text_after')
        if not uniq_id.isdigit() and not text_after:
            errors[field] = _('This field is required (except for rounds).')
        if errors:
            return None, errors
        assert triggered_at is not None
        return StoredTimerHour(
            id=None,
            timer_id=timer.id,
            uniq_id=uniq_id,
            triggered_at=triggered_at,
            text_before=text_before,
            text_after=text_after,
            errors=errors,
        ), {}

    @post(
        path='/timer-hour/create/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hour-create',
    )
    async def htmx_admin_timer_hour_create(
        self,
        request: HTMXRequest,
        timer_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id)
        SessionHandler.set_session_admin_timer_add_other_active(
            request, 'add_other' in data
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
        if 'add_other' in data:
            template_context = self._timer_hour_form_modal_context(
                web_context, FormAction.CREATE, success_message=message
            )
        else:
            template_context = self._timer_hours_modal_context(message)
        return self._admin_event_timers_render(web_context, template_context)

    @patch(
        path='/timer-hour/update/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-update',
    )
    async def htmx_admin_timer_hour_update(
        self,
        request: HTMXRequest,
        timer_id: int,
        timer_hour_id: int,
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

    @delete(
        path='/timer-hour/delete/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_hour_delete(
        self,
        request: HTMXRequest,
        timer_id: int,
        timer_hour_id: int,
    ) -> Template:
        web_context = TimerAdminWebContext(request, timer_id, timer_hour_id)
        web_context.get_admin_timer().delete_timer_hour(timer_hour_id)
        return self._admin_event_timers_render(
            web_context, self._timer_hours_modal_context()
        )
