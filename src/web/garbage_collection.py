"""Keep cyclic garbage-collection pauses outside request processing."""

import gc
from time import perf_counter
from typing import TYPE_CHECKING

from web.performance import record_gc

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Receive, Scope, Send


class RequestGarbageCollectionMiddleware:
    """Collect request-created cycles before they reach older generations."""

    def __init__(self, app: 'ASGIApp') -> None:
        self.app = app
        self._active_requests = 0
        self._restore_automatic_collection = False

    async def __call__(self, scope: 'Scope', receive: 'Receive', send: 'Send') -> None:
        if scope['type'] != 'http' or scope.get('path', '').startswith('/static/'):
            await self.app(scope, receive, send)
            return

        if self._active_requests == 0:
            self._restore_automatic_collection = gc.isenabled()
            if self._restore_automatic_collection:
                gc.disable()
        self._active_requests += 1

        try:
            await self.app(scope, receive, send)
        finally:
            self._release_request_state(scope)
            self._active_requests -= 1
            if self._active_requests == 0 and self._restore_automatic_collection:
                start = perf_counter()
                try:
                    collected = gc.collect(0)
                finally:
                    gc.enable()
                record_gc(collected, perf_counter() - start)

    @staticmethod
    def _release_request_state(scope: 'Scope') -> None:
        state = scope.get('state')
        if state is None:
            return
        # Drop request references before collecting their cycles.
        state.clear()
