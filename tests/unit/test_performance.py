import gc
import weakref

from jinja2 import DictLoader
import pytest
from litestar import Litestar, get
from litestar.middleware.base import DefineMiddleware
from litestar.testing import TestClient

from web import performance
from web.settings import SharlyChessEnvironment


class TemplatePayload:
    pass


def test_performance_middleware_collects_request_scoped_timings(monkeypatch):
    log_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        performance.logger, 'info', lambda *args: log_calls.append(args)
    )

    @get('/event/example', name='example-route')
    async def handler() -> bytes:
        assert performance.current_request_performance() is not None
        performance.record_event_load(0.012)
        performance.record_sql('SELECT  *\nFROM player', 0.003)
        performance.record_template('event.html', 0.004)
        performance.record_gc(42, 0.002)
        return b'hello'

    app = Litestar(
        route_handlers=[handler],
        middleware=[DefineMiddleware(performance.PerformanceMiddleware)],
    )
    with TestClient(app) as client:
        response = client.get('/event/example')

    assert response.content == b'hello'
    assert performance.current_request_performance() is None
    assert len(log_calls) == 1
    assert log_calls[0][0].startswith('PERF route=')
    assert log_calls[0][1:5] == ('example-route', 'GET', '/event/example', 200)
    assert 'template_hot=event.html:4.0ms' in log_calls[0][-1]
    assert 'sql_hot=1x/3.0ms/3.0ms:SELECT * FROM player' in log_calls[0][-1]
    assert log_calls[0][0].find('gc=%d/%.1fms/%dobj') != -1
    message = log_calls[0][0] % log_calls[0][1:]
    assert 'response=' in message
    assert 'post_response=' in message
    assert 'gc=1/2.0ms/42obj' in message


def test_performance_middleware_ignores_static_requests(monkeypatch):
    monkeypatch.setattr(
        performance.logger,
        'info',
        lambda *args: pytest.fail('static requests must not be profiled'),
    )

    @get('/static/app.css')
    async def handler() -> str:
        assert performance.current_request_performance() is None
        return 'body {}'

    app = Litestar(
        route_handlers=[handler],
        middleware=[DefineMiddleware(performance.PerformanceMiddleware)],
    )
    with TestClient(app) as client:
        response = client.get('/static/app.css')

    assert response.status_code == 200


def test_jinja_render_releases_context_cycles(tmp_path):
    environment = SharlyChessEnvironment([tmp_path])
    template = environment.from_string(
        '{% macro render_payload() %}{{ payload }}{% endmacro %}{{ render_payload() }}'
    )
    payload = TemplatePayload()
    payload_reference = weakref.ref(payload)

    automatic_gc_enabled = gc.isenabled()
    gc.disable()
    try:
        assert template.render(payload=payload)
        del payload
        assert payload_reference() is None
    finally:
        if automatic_gc_enabled:
            gc.enable()
        gc.collect()


def test_jinja_render_preserves_cached_macro_context(tmp_path):
    environment = SharlyChessEnvironment([tmp_path])
    environment.loader = DictLoader(
        {
            'page.html': (
                "{% import 'macros.j2' as macros %}{{ macros.render(value) }}"
            ),
            'macros.j2': '{% macro render(value) %}{{ helper(value) }}{% endmacro %}',
        }
    )
    environment.globals['helper'] = str.upper
    template = environment.get_template('page.html')

    assert template.render(value='first') == 'FIRST'
    assert template.render(value='second') == 'SECOND'
