"""Low-overhead, request-scoped performance instrumentation.

The counters live in a :class:`contextvars.ContextVar`, so concurrent requests
and background tasks cannot mix their measurements.  Database and template
code record data only while an HTTP request profile is active.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter, process_time
from typing import TYPE_CHECKING, Any

from common.logger import get_logger

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Message, Receive, Scope, Send


logger = get_logger()


@dataclass(slots=True)
class QueryPerformance:
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0


@dataclass(slots=True)
class RequestPerformance:
    sql_count: int = 0
    sql_seconds: float = 0.0
    event_load_count: int = 0
    event_load_seconds: float = 0.0
    template_count: int = 0
    template_seconds: float = 0.0
    gc_count: int = 0
    gc_seconds: float = 0.0
    gc_collected: int = 0
    response_bytes: int = 0
    response_seconds: float | None = None
    queries: dict[str, QueryPerformance] = field(default_factory=dict)
    templates: dict[str, float] = field(default_factory=dict)


_current_request: ContextVar[RequestPerformance | None] = ContextVar(
    'sharly_chess_request_performance', default=None
)


def current_request_performance() -> RequestPerformance | None:
    return _current_request.get()


def record_sql(query: str, seconds: float) -> None:
    profile = current_request_performance()
    if profile is None:
        return
    normalized_query = ' '.join(query.split())
    query_profile = profile.queries.setdefault(normalized_query, QueryPerformance())
    query_profile.count += 1
    query_profile.total_seconds += seconds
    query_profile.max_seconds = max(query_profile.max_seconds, seconds)
    profile.sql_count += 1
    profile.sql_seconds += seconds


def record_event_load(seconds: float) -> None:
    profile = current_request_performance()
    if profile is None:
        return
    profile.event_load_count += 1
    profile.event_load_seconds += seconds


def record_template(template_name: str | None, seconds: float) -> None:
    profile = current_request_performance()
    if profile is None:
        return
    name = template_name or '<string>'
    profile.template_count += 1
    profile.template_seconds += seconds
    profile.templates[name] = profile.templates.get(name, 0.0) + seconds


def record_gc(collected: int, seconds: float) -> None:
    profile = current_request_performance()
    if profile is None:
        return
    profile.gc_count += 1
    profile.gc_seconds += seconds
    profile.gc_collected += collected


class PerformanceMiddleware:
    """Log one timing breakdown for every non-static HTTP request."""

    def __init__(self, app: 'ASGIApp') -> None:
        self.app = app

    async def __call__(self, scope: 'Scope', receive: 'Receive', send: 'Send') -> None:
        if scope['type'] != 'http' or scope.get('path', '').startswith('/static/'):
            await self.app(scope, receive, send)
            return

        profile = RequestPerformance()
        token = _current_request.set(profile)
        start_wall = perf_counter()
        start_cpu = process_time()
        status_code = 500

        async def send_with_measurement(message: 'Message') -> None:
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = message['status']
            elif message['type'] == 'http.response.body':
                profile.response_bytes += len(message.get('body', b''))
            await send(message)
            if (
                message['type'] == 'http.response.body'
                and not message.get('more_body', False)
                and profile.response_seconds is None
            ):
                # The client has received the complete response. Middleware
                # cleanup (notably request GC) can continue after this point.
                profile.response_seconds = perf_counter() - start_wall

        try:
            await self.app(scope, receive, send_with_measurement)
        finally:
            wall_seconds = perf_counter() - start_wall
            cpu_seconds = process_time() - start_cpu
            _current_request.reset(token)
            self._log_profile(scope, profile, status_code, wall_seconds, cpu_seconds)

    @staticmethod
    def _log_profile(
        scope: 'Scope',
        profile: RequestPerformance,
        status_code: int,
        wall_seconds: float,
        cpu_seconds: float,
    ) -> None:
        route_handler: Any = scope.get('route_handler')
        route_name = getattr(route_handler, 'name', None) or '<unmatched>'
        response_seconds = profile.response_seconds or wall_seconds
        post_response_seconds = max(0.0, wall_seconds - response_seconds)
        # Event loading contains its SQLite time; the other categories are separate.
        # The remainder covers guards, controller/context work, sessions and ASGI
        # until the final response body is sent. Post-response work is shown
        # separately so deferred GC is not mistaken for client-visible latency.
        other_seconds = max(
            0.0,
            response_seconds - profile.event_load_seconds - profile.template_seconds,
        )
        logger.info(
            'PERF route=%s method=%s path=%s status=%d total=%.1fms '
            'response=%.1fms post_response=%.1fms cpu=%.1fms '
            'event_load=%d/%.1fms sql=%d/%.1fms template=%d/%.1fms '
            'gc=%d/%.1fms/%dobj other=%.1fms bytes=%d%s',
            route_name,
            scope.get('method', '?'),
            scope.get('path', '?'),
            status_code,
            wall_seconds * 1000,
            response_seconds * 1000,
            post_response_seconds * 1000,
            cpu_seconds * 1000,
            profile.event_load_count,
            profile.event_load_seconds * 1000,
            profile.sql_count,
            profile.sql_seconds * 1000,
            profile.template_count,
            profile.template_seconds * 1000,
            profile.gc_count,
            profile.gc_seconds * 1000,
            profile.gc_collected,
            other_seconds * 1000,
            profile.response_bytes,
            PerformanceMiddleware._hotspot_summary(profile),
        )

    @staticmethod
    def _hotspot_summary(profile: RequestPerformance) -> str:
        parts: list[str] = []
        if profile.templates:
            name, seconds = max(profile.templates.items(), key=lambda item: item[1])
            parts.append(f'template_hot={name}:{seconds * 1000:.1f}ms')
        if profile.queries:
            query, stats = max(
                profile.queries.items(), key=lambda item: item[1].total_seconds
            )
            if len(query) > 120:
                query = query[:117] + '...'
            parts.append(
                f'sql_hot={stats.count}x/{stats.total_seconds * 1000:.1f}ms/'
                f'{stats.max_seconds * 1000:.1f}ms:{query}'
            )
        return f' {" ".join(parts)}' if parts else ''
