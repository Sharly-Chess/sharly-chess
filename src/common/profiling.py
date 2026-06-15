"""Lightweight per-request profiling accumulator.

Enabled by setting the environment variable ``SHARLY_PROFILE`` to a truthy
value (``1``/``true``/``yes``/``on``). When disabled every hook here is a
cheap no-op, so the instrumentation can stay in the code.

The accumulator is a plain dict held in a :class:`~contextvars.ContextVar`.
It is reset at the start of each request (by the profiling middleware) and
mutated in place by the instrumentation points (event loading, template
rendering, database connection opening). Storing a *mutable dict* and
mutating it in place — rather than reassigning the ContextVar — means the
counters survive Litestar dispatching a sync handler onto a worker thread
(the copied context still references the same dict)."""

import os
from contextvars import ContextVar
from time import perf_counter

PROFILE_ENABLED: bool = os.environ.get('SHARLY_PROFILE', '').lower() in (
    '1',
    'true',
    'yes',
    'on',
)

_acc: ContextVar[dict | None] = ContextVar('sharly_profile_acc', default=None)


def reset() -> dict:
    """Starts a fresh accumulator for the current request and returns it."""
    acc: dict = {}
    _acc.set(acc)
    return acc


def add_ms(key: str, ms: float) -> None:
    """Adds an elapsed-time sample (in milliseconds) under ``key``, also
    counting how many samples were recorded."""
    if not PROFILE_ENABLED:
        return
    acc = _acc.get()
    if acc is None:
        return
    acc[f'{key}_ms'] = acc.get(f'{key}_ms', 0.0) + ms
    acc[f'{key}_n'] = acc.get(f'{key}_n', 0) + 1


def incr(key: str, count: int = 1) -> None:
    """Increments the ``key`` counter (no timing)."""
    if not PROFILE_ENABLED:
        return
    acc = _acc.get()
    if acc is None:
        return
    acc[f'{key}_n'] = acc.get(f'{key}_n', 0) + count


class timed:
    """Context manager that records the wall time of its block under ``key``."""

    __slots__ = ('key', '_start')

    def __init__(self, key: str):
        self.key = key
        self._start = 0.0

    def __enter__(self) -> 'timed':
        if PROFILE_ENABLED:
            self._start = perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        if PROFILE_ENABLED:
            add_ms(self.key, (perf_counter() - self._start) * 1000)
