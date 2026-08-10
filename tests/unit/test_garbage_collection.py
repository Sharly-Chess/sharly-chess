import gc
import weakref

from litestar import Litestar, Request, get
from litestar.testing import TestClient

from web.garbage_collection import RequestGarbageCollectionMiddleware


class CyclicObject:
    reference: 'CyclicObject'


def test_request_garbage_collection_releases_request_cycles():
    object_reference: weakref.ReferenceType[CyclicObject] | None = None
    request_state: dict[str, object] | None = None

    @get('/event/example')
    async def handler(request: Request) -> str:
        nonlocal object_reference, request_state
        cyclic_object = CyclicObject()
        cyclic_object.reference = cyclic_object
        object_reference = weakref.ref(cyclic_object)
        request.state['sharly_chess_event'] = cyclic_object
        request.state['event_loader'] = object()
        request.state['framework_value'] = 'preserved'
        request_state = request.scope['state']
        return 'ok'

    app = RequestGarbageCollectionMiddleware(
        Litestar(
            route_handlers=[handler],
        )
    )
    with TestClient(app) as client:
        response = client.get('/event/example')

    assert response.status_code == 200
    assert object_reference is not None
    assert object_reference() is None
    assert request_state is not None
    assert request_state == {}
    assert gc.isenabled()


def test_request_garbage_collection_ignores_static_requests(monkeypatch):
    collect_calls: list[int] = []

    def record_collect(generation: int) -> int:
        collect_calls.append(generation)
        return 0

    monkeypatch.setattr(gc, 'collect', record_collect)

    @get('/static/app.css')
    async def handler() -> str:
        return 'body {}'

    app = RequestGarbageCollectionMiddleware(
        Litestar(
            route_handlers=[handler],
        )
    )
    with TestClient(app) as client:
        response = client.get('/static/app.css')

    assert response.status_code == 200
    assert collect_calls == []
