import re
import time
from datetime import datetime
from logging import Logger
from typing import Annotated, Any

from litestar import post, get, delete, patch
from litestar.contrib.htmx.request import HTMXRequest
from litestar.contrib.htmx.response import ClientRedirect
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK

from common.papi_web_config import PapiWebConfig
from common.i18n import _
from common.logger import get_logger
from data.loader import EventLoader
from data.timer import Timer, TimerHour
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredEvent, StoredTimer, StoredTimerHour
from web.controllers.admin.base_event_admin_controller import (
    BaseEventAdminWebContext,
    BaseEventAdminController,
)
from web.controllers.base_controller import WebContext
from web.messages import Message

logger: Logger = get_logger()


class TimerAdminWebContext(BaseEventAdminWebContext):
    def __init__(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int | None,
        timer_hour_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ]
        | None,
    ):
        super().__init__(
            request,
            data=data,
            event_uniq_id=event_uniq_id,
        )
        assert self.admin_event is not None
        self.admin_timer: Timer | None = None
        self.admin_timer_hour: TimerHour | None = None
        if self.error:
            return
        if timer_id:
            try:
                self.admin_timer = self.admin_event.timers_by_id[timer_id]
            except KeyError:
                self._redirect_error(f'Timer [{timer_id}] not found.')
                return
        if timer_hour_id:
            assert self.admin_timer is not None
            try:
                self.admin_timer_hour = self.admin_timer.timer_hours_by_id[
                    timer_hour_id
                ]
            except KeyError:
                self._redirect_error(
                    f'Hour [{timer_hour_id}] not found for timer [{self.admin_timer.uniq_id}].'
                )
                return

    @property
    def template_context(self) -> dict[str, Any]:
        return super().template_context | {
            'admin_timer': self.admin_timer,
            'admin_timer_hour': self.admin_timer_hour,
        }


class TimerAdminController(BaseEventAdminController):
    @staticmethod
    def _admin_validate_timer_update_data(
        action: str,
        web_context: TimerAdminWebContext,
        data: dict[str, str] | None = None,
    ) -> StoredTimer:
        assert web_context.admin_event is not None
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        field = 'uniq_id'
        uniq_id: str | None = WebContext.form_data_to_str(data, field)
        colors: dict[int, str | None] = {i: None for i in range(1, 4)}
        color_checkboxes: dict[int, bool | None] = {i: None for i in range(1, 4)}
        delays: dict[int, int | None] = {i: None for i in range(1, 4)}
        if action in [
            'delete',
        ]:
            pass
        else:
            if not uniq_id:
                errors[field] = _('Please enter the timer ID.')
            else:
                match action:
                    case 'create' | 'clone':
                        assert web_context.admin_event is not None
                        if uniq_id in web_context.admin_event.timers_by_uniq_id:
                            errors[field] = _(
                                'Timer [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case 'update':
                        assert web_context.admin_timer is not None
                        if (
                            uniq_id != web_context.admin_timer.uniq_id
                            and uniq_id in web_context.admin_event.timers_by_uniq_id
                        ):
                            errors[field] = _(
                                'Timer [{uniq_id}] already exists.'
                            ).format(uniq_id=uniq_id)
                    case _:
                        raise ValueError(f'action=[{action}]')
        match action:
            case 'update' | 'create' | 'clone':
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
            case 'delete':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
            
        assert web_context.admin_timer is not None
        assert uniq_id is not None
        return StoredTimer(
            id=web_context.admin_timer.id
            if action
            not in [
                'create',
                'clone',
            ]
            else None,
            uniq_id=uniq_id,
            colors=colors,
            delays=delays,
            errors=errors,
        )

    @staticmethod
    def _admin_validate_timer_hour_update_data(
        web_context: TimerAdminWebContext,
        previous_valid_timer_hour: TimerHour | None,
        data: dict[str, str] | None = None,
    ) -> StoredTimerHour:
        errors: dict[str, str] = {}
        if data is None:
            data = {}
        uniq_id: str | None = WebContext.form_data_to_str(data, 'uniq_id')
        if not uniq_id:
            errors['uniq_id'] = _('Please enter the round number or the hour ID.')
        time_str: str | None = WebContext.form_data_to_str(data, 'time_str')
        date_str: str | None = WebContext.form_data_to_str(data, 'date_str')
        if not time_str:
            errors['time_str'] = _('Please enter the time.')
        else:
            matches = re.match(
                '^(?P<hour>[0-9]{1,2}):(?P<minute>[0-9]{1,2})$', time_str
            )
            if not matches:
                errors['time_str'] = _('Please enter a valid time.')
        if not previous_valid_timer_hour and not date_str:
            errors['date_str'] = _('Please enter the date of the first hour.')
        elif date_str:
            if not re.match(
                '^#?(?P<year>[0-9]{4})-(?P<month>[0-9]{1,2})-(?P<day>[0-9]{1,2})$',
                date_str,
            ):
                errors['date_str'] = _('Please enter a valid date.')
        if 'time_str' not in errors and 'date_str' not in errors:
            datetime_str: str
            if date_str:
                datetime_str = f'{date_str} {time_str}'
            else:
                assert previous_valid_timer_hour
                datetime_str = f'{previous_valid_timer_hour.date_str} {time_str}'
            try:
                timestamp: int = int(
                    time.mktime(
                        datetime.strptime(datetime_str, '%Y-%m-%d %H:%M').timetuple()
                    )
                )
                if (
                    previous_valid_timer_hour and previous_valid_timer_hour.timestamp
                    and timestamp <= previous_valid_timer_hour.timestamp
                ):
                    errors['time_str'] = _(
                        'Invalid hour [{hour}] (before previous hour [{previous_hour}]).'
                    ).format(
                        hour=datetime_str,
                        previous_hour=previous_valid_timer_hour.datetime_str,
                    )
                    if date_str:
                        errors['date_str'] = errors['time_str']
            except ValueError:
                errors['time_str'] = _('Please enter valid date and time.')
                if date_str:
                    errors['date_str'] = errors['time_str']
                    
        assert web_context.admin_timer is not None
        assert web_context.admin_timer_hour is not None
        assert uniq_id is not None
        if (
            uniq_id != web_context.admin_timer_hour.uniq_id
            and uniq_id in web_context.admin_timer.timer_hour_uniq_ids
        ):
            errors['uniq_id'] = _('Hour [{uniq_id}] already exists.').format(
                uniq_id=uniq_id
            )
        text_before: str | None = WebContext.form_data_to_str(data, 'text_before')
        text_after: str | None = WebContext.form_data_to_str(data, 'text_after')
        try:
            round_: int = int(uniq_id)
            if round_ <= 0:
                errors['uniq_id'] = _('Round numbers must be positive integers.')
        except (TypeError, ValueError, AssertionError):
            if not text_before:
                errors['text_before'] = _(
                    'Please enter the text to display before the hour (mandatory except for rounds).'
                )
            if not text_after:
                errors['text_after'] = _(
                    'Please enter the text to display after the hour (mandatory except for rounds).'
                )
        
        assert web_context.admin_timer and web_context.admin_timer.id is not None
        return StoredTimerHour(
            id=web_context.admin_timer_hour.id,
            order=web_context.admin_timer_hour.order,
            timer_id=web_context.admin_timer.id,
            uniq_id=uniq_id,
            date_str=date_str,
            time_str=time_str,
            text_before=text_before,
            text_after=text_after,
            errors=errors,
        )

    @classmethod
    def _admin_event_timers_render(
        cls,
        request: HTMXRequest,
        event_uniq_id: str,
        modal: str | None = None,
        action: str | None = None,
        timer_id: int | None = None,
        timer_hour_id: int | None = None,
        data: dict[str, str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> Template | ClientRedirect:
        web_context: TimerAdminWebContext = TimerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            timer_id=timer_id,
            timer_hour_id=timer_hour_id,
            data=data,
        )
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError("admin_event not defined")
        template_context: dict[str, Any] = cls._get_admin_event_render_context(
            web_context
        ) | {
            'admin_event_tab': 'admin-event-timers-tab',
        }
        
        match modal:
            case None:
                pass
            case 'default-timers':
                stored_event: StoredEvent = web_context.admin_event.stored_event
                if data is None:
                    assert stored_event.timer_colors is not None
                    assert stored_event.timer_delays is not None
                    colors = stored_event.timer_colors
                    delays = stored_event.timer_delays
                    data = (
                        {
                            f'color_{i}': WebContext.value_to_form_data(colors[i])
                            for i in range(1, 4)
                        }
                        | {
                            f'color_{i}_checkbox': WebContext.value_to_form_data(colors[i] is None)
                            for i in range(1, 4)
                        }
                        | {
                            f'delay_{i}': WebContext.value_to_form_data(delays[i])
                            for i in range(1, 4)
                        }
                    )

                template_context |= {
                    'timer_color_texts': cls._get_timer_color_texts(
                        PapiWebConfig.default_timer_delays
                    ),
                    'modal': 'default-timers',
                    'errors': errors or {},
                    'data': data,
                }
            case 'timer':
                if data is None:
                    uniq_id: str | None = None
                    colors = {i: None for i in range(1, 4)}
                    delays = {i: None for i in range(1, 4)}
                    match action:
                        case 'update':
                            assert web_context.admin_timer is not None
                            uniq_id = web_context.admin_timer.stored_timer.uniq_id
                        case 'create':
                            uniq_id = web_context.admin_event.get_unused_timer_uniq_id()
                        case 'clone':
                            assert web_context.admin_timer is not None
                            uniq_id = web_context.admin_event.get_unused_timer_uniq_id(
                                web_context.admin_timer.stored_timer.uniq_id
                            )
                        case 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    match action:
                        case 'update' | 'clone':
                            assert web_context.admin_timer is not None
                            assert web_context.admin_timer.stored_timer is not None
                            assert web_context.admin_timer.stored_timer.colors is not None
                            assert web_context.admin_timer.stored_timer.delays is not None
                            colors = web_context.admin_timer.stored_timer.colors
                            delays = web_context.admin_timer.stored_timer.delays
                        case 'create' | 'delete':
                            pass
                        case _:
                            raise ValueError(f'action=[{action}]')
                    data = (
                        {
                            'uniq_id': WebContext.value_to_form_data(uniq_id),
                        }
                        | {
                            f'color_{i}': WebContext.value_to_form_data(colors[i])
                            for i in range(1, 4)
                        }
                        | {
                            f'color_{i}_checkbox': WebContext.value_to_form_data(
                                colors[i] is None
                            )
                            for i in range(1, 4)
                        }
                        | {
                            f'delay_{i}': WebContext.value_to_form_data(delays[i])
                            for i in range(1, 4)
                        }
                    )
                    stored_timer: StoredTimer = cls._admin_validate_timer_update_data(
                        action, web_context, data
                    )
                    errors = stored_timer.errors
                if errors is None:
                    errors = {}
                template_context |= {
                    'timer_color_texts': cls._get_timer_color_texts(
                        web_context.admin_event.timer_delays
                    ),
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
            case 'timer_hours':
                assert web_context.admin_timer is not None
                if data is None:
                    if web_context.admin_timer_hour:
                        data = {
                            'uniq_id': WebContext.value_to_form_data(
                                web_context.admin_timer_hour.stored_timer_hour.uniq_id
                            ),
                            'date_str': WebContext.value_to_form_data(
                                web_context.admin_timer_hour.stored_timer_hour.date_str
                            ),
                            'time_str': WebContext.value_to_form_data(
                                web_context.admin_timer_hour.stored_timer_hour.time_str
                            ),
                            'text_before': WebContext.value_to_form_data(
                                web_context.admin_timer_hour.stored_timer_hour.text_before
                            ),
                            'text_after': WebContext.value_to_form_data(
                                web_context.admin_timer_hour.stored_timer_hour.text_after
                            ),
                        }
                        stored_timer_hour = cls._admin_validate_timer_hour_update_data(
                            web_context,
                            web_context.admin_timer.get_previous_timer_hour(
                                web_context.admin_timer_hour
                            ),
                            data,
                        )
                        errors = stored_timer_hour.errors
                    else:
                        data = {}
                if errors is None:
                    errors = {}
                template_context |= {
                    'modal': modal,
                    'action': action,
                    'data': data,
                    'errors': errors,
                }
        return cls._admin_event_render(template_context)

    @get(
        path='/admin/event/{event_uniq_id:str}/timers',
        name='admin-event-timers-tab',
        cache=1,
    )
    async def htmx_admin_event_timers_tab(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
        )

    @get(
        path='/admin/default-timers-modal/{event_uniq_id:str}',
        name='admin-default-timers-modal',
        cache=1,
    )
    async def htmx_admin_default_timers_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='default-timers',
            action=None,
            timer_id=None,
        )

    @patch(
        path='/admin/default-timers-update/{event_uniq_id:str}',
        name='default-timers-update'
    )
    async def htmx_admin_default_timers_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        web_context: TimerAdminWebContext = TimerAdminWebContext(
            request,
            event_uniq_id=event_uniq_id,
            timer_id=None,
            timer_hour_id=None,
            data=data,
        )

        assert web_context.admin_event is not None

        errors: dict[str, str] = {}
        stored_event: StoredEvent = web_context.admin_event.stored_event

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
                timer_delays[i] = WebContext.form_data_to_int(
                    data, field, minimum=1
                )
            except ValueError:
                errors[field] = _(
                    'Invalid delay [{delay}] (positive integer expected).'
                ).format(delay=data[field])

        if errors:
            return self._admin_event_timers_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='default-timers',
                action=None,
                timer_id=None,
                data=data,
                errors=errors,
            )

        stored_event.timer_colors=timer_colors
        stored_event.timer_delays=timer_delays

        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            event_database.update_stored_event(stored_event)
            event_database.commit()

        return self._admin_event_timers_render(
            request, event_uniq_id=event_uniq_id
        )

    @get(
        path='/admin/timer-modal/create/{event_uniq_id:str}',
        name='admin-timer-create-modal',
        cache=1,
    )
    async def htmx_admin_timer_create_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
    ) -> Template | ClientRedirect:
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='timer',
            action='create',
            timer_id=None,
        )

    @get(
        path='/admin/timer-modal/{action:str}/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-modal',
        cache=1,
    )
    async def htmx_admin_timer_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        timer_id: int | None,
    ) -> Template | ClientRedirect:
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='timer',
            action=action,
            timer_id=timer_id,
        )

    def _admin_timer_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        action: str,
        timer_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        match action:
            case 'update' | 'delete' | 'clone' | 'create':
                web_context: TimerAdminWebContext = TimerAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    timer_id=timer_id,
                    timer_hour_id=None,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError("admin_event not defined")
        stored_timer: StoredTimer | None = self._admin_validate_timer_update_data(
            action, web_context, data
        )
        assert stored_timer is not None
        if stored_timer.errors:
            return self._admin_event_timers_render(
                request,
                event_uniq_id=event_uniq_id,
                modal='timer',
                action=action,
                timer_id=timer_id,
                data=data,
                errors=stored_timer.errors,
            )
        event_loader: EventLoader = EventLoader.get(request=request)
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'create':
                    stored_timer = event_database.add_stored_timer(stored_timer)
                    assert stored_timer and stored_timer.id is not None
                    stored_timer_hour: StoredTimerHour = (
                        event_database.add_stored_timer_hour(
                            stored_timer.id, set_datetime=True
                        )
                    )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Timer [{timer_uniq_id}] has been created.').format(
                            timer_uniq_id=stored_timer.uniq_id
                        ),
                    )
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_timers_render(
                        request,
                        event_uniq_id=event_uniq_id,
                        modal='timer_hours',
                        timer_id=stored_timer.id,
                        timer_hour_id=stored_timer_hour.id,
                    )
                case 'update':
                    assert web_context.admin_timer and web_context.admin_timer.id is not None
                    stored_timer = event_database.update_stored_timer(stored_timer)
                    assert stored_timer and stored_timer.id is not None
                    Message.success(
                        request,
                        _('Timer [{timer_uniq_id}] has been updated.').format(
                            timer_uniq_id=stored_timer.uniq_id
                        ),
                    )
                    if not web_context.admin_timer.timer_hours_by_id:
                        stored_timer_hour = (
                            event_database.add_stored_timer_hour(
                                web_context.admin_timer.id, set_datetime=True
                            )
                        )
                        event_database.commit()
                        event_loader.clear_cache(event_uniq_id)
                        return self._admin_event_timers_render(
                            request,
                            event_uniq_id=event_uniq_id,
                            modal='timer_hours',
                            timer_id=stored_timer.id,
                            timer_hour_id=stored_timer_hour.id,
                        )
                    else:
                        event_database.commit()
                        event_loader.clear_cache(event_uniq_id)
                        for (
                            timer_hour
                        ) in web_context.admin_timer.timer_hours_sorted_by_order:
                            if timer_hour.error:
                                return self._admin_event_timers_render(
                                    request,
                                    event_uniq_id=event_uniq_id,
                                    modal='timer_hours',
                                    timer_id=stored_timer.id,
                                    timer_hour_id=timer_hour.id,
                                )
                        return self._admin_event_timers_render(
                            request, event_uniq_id=event_uniq_id
                        )
                case 'delete':
                    assert web_context.admin_timer is not None
                    assert web_context.admin_timer.id is not None
                    event_database.delete_stored_timer(web_context.admin_timer.id)
                    event_database.commit()
                    Message.success(
                        request,
                        _('Timer [{timer_uniq_id}] has been deleted.').format(
                            timer_uniq_id=web_context.admin_timer.uniq_id
                        ),
                    )
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_timers_render(
                        request, event_uniq_id=event_uniq_id
                    )
                case 'clone':
                    if web_context.admin_timer is None:
                        raise RuntimeError(f'{web_context.admin_timer=} for [{action=}]')
                    stored_timer = event_database.add_stored_timer(stored_timer)
                    assert stored_timer is not None and stored_timer.id is not None
                    for (
                        timer_hour
                    ) in web_context.admin_timer.timer_hours_sorted_by_order:
                        assert timer_hour.id is not None
                        event_database.clone_stored_timer_hour(
                            timer_hour.id, stored_timer.id
                        )
                    event_database.commit()
                    Message.success(
                        request,
                        _('Timer [{timer_uniq_id}] has been created.').format(
                            timer_uniq_id=stored_timer.uniq_id
                        ),
                    )
                    event_loader.clear_cache(event_uniq_id)
                    return self._admin_event_timers_render(
                        request,
                        event_uniq_id=event_uniq_id,
                        modal='timer_hours',
                        timer_id=stored_timer.id,
                    )
                case _:
                    raise ValueError(f'action=[{action}]')

    @post(path='/admin/timer-create/{event_uniq_id:str}', name='admin-timer-create')
    async def htmx_admin_timer_create(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='create',
            timer_id=None,
            data=data,
        )

    @post(
        path='/admin/timer-clone/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-clone',
    )
    async def htmx_admin_timer_clone(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='clone',
            timer_id=timer_id,
            data=data,
        )

    @patch(
        path='/admin/timer-update/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-update',
    )
    async def htmx_admin_timer_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            timer_id=timer_id,
            data=data,
        )

    @delete(
        path='/admin/timer-delete/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int | None,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            timer_id=timer_id,
            data=data,
        )

    @get(
        path='/admin/timer-hours-modal/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hours-modal',
        cache=1,
    )
    async def htmx_admin_timer_hours_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='timer_hours',
            timer_id=timer_id,
            timer_hour_id=None,
        )

    @get(
        path='/admin/timer-hours-hour-modal/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hours-hour-modal',
        cache=1,
    )
    async def htmx_admin_timer_hours_hour_modal(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        timer_hour_id: int,
    ) -> Template | ClientRedirect:
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='timer_hours',
            timer_id=timer_id,
            timer_hour_id=timer_hour_id,
        )

    def _admin_timer_hours_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        timer_hour_id: int | None,
        action: str,
        data: Annotated[
            dict[str, Any],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        match action:
            case 'delete' | 'clone' | 'update' | 'add' | 'reorder':
                web_context: TimerAdminWebContext = TimerAdminWebContext(
                    request,
                    event_uniq_id=event_uniq_id,
                    timer_id=timer_id,
                    timer_hour_id=timer_hour_id,
                    data=data,
                )
            case _:
                raise ValueError(f'action=[{action}]')
        if web_context.error:
            return web_context.error
        if web_context.admin_event is None:
            raise RuntimeError("admin_event not defined")
        event_loader: EventLoader = EventLoader.get(request=request)
        match action:
            case 'delete':
                assert web_context.admin_timer is not None
                if len(web_context.admin_timer.timer_hours_by_id) <= 1:
                    return self.redirect_error(
                        request, 'The last hour of timer can not be deleted.'
                    )
            case 'update' | 'clone' | 'add' | 'reorder':
                pass
            case _:
                raise ValueError(f'action=[{action}]')
        next_timer_hour_id: int | None = None
        with EventDatabase(
            web_context.admin_event.uniq_id, write=True
        ) as event_database:
            match action:
                case 'update':
                    assert web_context.admin_timer is not None
                    assert web_context.admin_timer_hour is not None
                    stored_timer_hour: StoredTimerHour = (
                        self._admin_validate_timer_hour_update_data(
                            web_context,
                            web_context.admin_timer.get_previous_timer_hour(
                                web_context.admin_timer_hour
                            ),
                            data,
                        )
                    )
                    if stored_timer_hour.errors:
                        return self._admin_event_timers_render(
                            request,
                            event_uniq_id=event_uniq_id,
                            modal='timer_hours',
                            timer_id=timer_id,
                            timer_hour_id=timer_hour_id,
                            data=data,
                            errors=stored_timer_hour.errors,
                        )
                    event_database.update_stored_timer_hour(stored_timer_hour)
                case 'delete':
                    assert web_context.admin_timer and web_context.admin_timer.id is not None
                    assert web_context.admin_timer_hour and web_context.admin_timer_hour.id is not None
                    event_database.delete_stored_timer_hour(
                        web_context.admin_timer_hour.id, web_context.admin_timer.id
                    )
                case 'clone':
                    assert web_context.admin_timer is not None
                    assert web_context.admin_timer_hour is not None
                    assert web_context.admin_timer_hour.id is not None
                    stored_timer_hour = event_database.clone_stored_timer_hour(
                        web_context.admin_timer_hour.id
                    )
                    next_timer_hour_id = stored_timer_hour.id
                case 'add':
                    assert web_context.admin_timer and web_context.admin_timer.id is not None
                    stored_timer_hour = event_database.add_stored_timer_hour(
                        web_context.admin_timer.id
                    )
                    next_timer_hour_id = stored_timer_hour.id
                case 'reorder':
                    event_database.reorder_stored_timer_hours(data['item'])
                case _:
                    raise ValueError(f'action=[{action}]')
            event_database.commit()
        event_loader.clear_cache(event_uniq_id)
        return self._admin_event_timers_render(
            request,
            event_uniq_id=event_uniq_id,
            modal='timer_hours',
            timer_id=timer_id,
            timer_hour_id=next_timer_hour_id,
        )

    @post(
        path='/admin/timer-hour-add/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-hour-add',
    )
    async def htmx_admin_timer_hour_add(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        data: Annotated[
            dict[str, str],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_hours_update(
            request,
            event_uniq_id=event_uniq_id,
            action='add',
            timer_id=timer_id,
            timer_hour_id=None,
            data=data,
        )

    @post(
        path='/admin/timer-hour-clone/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-clone',
    )
    async def htmx_admin_timer_hour_clone(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        timer_hour_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_hours_update(
            request,
            event_uniq_id=event_uniq_id,
            action='clone',
            timer_id=timer_id,
            timer_hour_id=timer_hour_id,
            data=data,
        )

    @patch(
        path='/admin/timer-hour-update/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-update',
    )
    async def htmx_admin_timer_hour_update(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        timer_hour_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_hours_update(
            request,
            event_uniq_id=event_uniq_id,
            action='update',
            timer_id=timer_id,
            timer_hour_id=timer_hour_id,
            data=data,
        )

    @delete(
        path='/admin/timer-hour-delete/{event_uniq_id:str}/{timer_id:int}/{timer_hour_id:int}',
        name='admin-timer-hour-delete',
        status_code=HTTP_200_OK,
    )
    async def htmx_admin_timer_hour_delete(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        timer_hour_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_hours_update(
            request,
            event_uniq_id=event_uniq_id,
            action='delete',
            timer_id=timer_id,
            timer_hour_id=timer_hour_id,
            data=data,
        )

    @patch(
        path='/admin/timer-reorder-hours/{event_uniq_id:str}/{timer_id:int}',
        name='admin-timer-reorder-hours',
    )
    async def htmx_admin_timer_reorder_hours(
        self,
        request: HTMXRequest,
        event_uniq_id: str,
        timer_id: int,
        data: Annotated[
            dict[str, str | list[int]],
            Body(media_type=RequestEncodingType.URL_ENCODED),
        ],
    ) -> Template | ClientRedirect:
        return self._admin_timer_hours_update(
            request,
            event_uniq_id=event_uniq_id,
            action='reorder',
            timer_id=timer_id,
            timer_hour_id=None,
            data=data,
        )
