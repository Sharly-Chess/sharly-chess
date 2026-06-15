"""Per-request timing middleware.

Logs, for every HTTP request, where the time went: total, full-event
loading, template rendering, the number of SQLite connections opened, and
whatever is left over ("other"). Active only when ``SHARLY_PROFILE`` is set
(see :mod:`common.profiling`); otherwise it passes straight through."""

import asyncio
from time import perf_counter

from litestar.enums import ScopeType
from litestar.middleware import AbstractMiddleware
from litestar.types import Receive, Scope, Send

from common.logger import get_logger
from common.profiling import PROFILE_ENABLED, reset

logger = get_logger()

# Event-loop lag monitor: a background task sleeps for a fixed interval and
# measures how much longer than that it actually took to be woken. The
# overshoot is time the single event loop spent blocked by synchronous work
# in some handler — i.e. time during which every other request was frozen.
_LOOP_LAG_INTERVAL_S = 0.05
_LOOP_LAG_THRESHOLD_MS = 40.0


async def _monitor_loop_lag() -> None:
    while True:
        before = perf_counter()
        await asyncio.sleep(_LOOP_LAG_INTERVAL_S)
        lag_ms = (perf_counter() - before) * 1000 - _LOOP_LAG_INTERVAL_S * 1000
        if lag_ms >= _LOOP_LAG_THRESHOLD_MS:
            logger.warning('LOOP-LAG event loop blocked for ~%.0fms', lag_ms)


class ProfilingMiddleware(AbstractMiddleware):
    scopes = {ScopeType.HTTP}
    _monitor_started = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not PROFILE_ENABLED or scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        if not ProfilingMiddleware._monitor_started:
            ProfilingMiddleware._monitor_started = True
            asyncio.get_running_loop().create_task(_monitor_loop_lag())

        acc = reset()
        start = perf_counter()
        status_code: list[int | None] = [None]

        async def send_wrapper(message) -> None:
            if message['type'] == 'http.response.start':
                status_code[0] = message['status']
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            total = (perf_counter() - start) * 1000
            load_event_ms = acc.get('load_event_ms', 0.0)
            load_event_n = acc.get('load_event_n', 0)
            render_ms = acc.get('render_ms', 0.0)
            render_n = acc.get('render_n', 0)
            db_open_n = acc.get('db_open_n', 0)
            other = total - load_event_ms - render_ms

            # Any extra timed() keys (ad-hoc probes) beyond the standard ones,
            # ordered slowest first, appended so they're visible in the log.
            standard = {'load_event', 'render'}
            extras = sorted(
                (
                    (key[:-3], value, acc.get(f'{key[:-3]}_n', 0))
                    for key, value in acc.items()
                    if key.endswith('_ms') and key[:-3] not in standard
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            extras_str = ''.join(f' {name}={ms:.0f}ms(x{n})' for name, ms, n in extras)

            logger.warning(
                'PROFILE %s %s -> %s total=%.0fms load_event=%.0fms(x%d) '
                'render=%.0fms(x%d) db_opens=%d other=%.0fms%s',
                scope.get('method', '?'),
                scope.get('path', '?'),
                status_code[0],
                total,
                load_event_ms,
                load_event_n,
                render_ms,
                render_n,
                db_open_n,
                other,
                extras_str,
            )
