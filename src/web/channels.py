import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend

channels_plugin = ChannelsPlugin(
    backend=MemoryChannelsBackend(),
    arbitrary_channels_allowed=True,
)

APP_CHANNEL: str = 'ws'
"""The channel of the events concerning the whole application, which every
page of the administration receives."""


def event_channel(event_uniq_id: str) -> str:
    """The channel of the events concerning one event, which only the pages of
    that event receive."""
    return f'event:{event_uniq_id}'


def publish_ws_event(
    event: str,
    detail: Mapping[str, object] | None = None,
    event_uniq_id: str | None = None,
) -> None:
    """Sends an event to the open pages, which receive it as `ws:<event>`: the
    pages of the event *event_uniq_id* when given, every page otherwise. Must be
    called from the event loop of the server. Does nothing before the server has
    started."""
    if channels_plugin._pub_queue is None:
        return
    channels_plugin.publish(
        {'event': event, 'data': {'detail': detail} if detail else ''},
        [event_channel(event_uniq_id) if event_uniq_id else APP_CHANNEL],
    )


# The changes written to an event are announced to its screens once the code
# that wrote them has run, unless that code announced them itself with a more
# precise event: `tournament-changed|<event>` names the tournaments whose data
# changed, `screens-changed|<event>` tells that the setup of the screens or what
# they show beyond the data of the tournaments changed.
_server_loop: asyncio.AbstractEventLoop | None = None
_started_at: datetime = datetime.now()
_screens_changed_at: dict[str, datetime] = {}
_changed_tournament_ids: defaultdict[str, set[int]] = defaultdict(set)
_changed_screens: set[str] = set()
_announced_tournament_ids: defaultdict[str, set[int]] = defaultdict(set)
_announced_screens: set[str] = set()
_flush_scheduled: bool = False


def bind_server_loop() -> None:
    """Remembers the event loop of the server, from which the changes are
    announced. Called when the server starts."""
    global _server_loop
    _server_loop = asyncio.get_running_loop()


def screens_changed_at(event_uniq_id: str) -> datetime:
    """When the setup of the screens of the event *event_uniq_id* last changed,
    or what they show beyond the data of the tournaments. Not kept from one run
    of the server to the next: every screen is drawn again after a restart."""
    return _screens_changed_at.get(event_uniq_id, _started_at)


def _on_server_loop(callback: Callable[[], None]) -> None:
    if _server_loop is None or _server_loop.is_closed():
        return
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None
    if running_loop is _server_loop:
        callback()
    else:
        _server_loop.call_soon_threadsafe(callback)


def _schedule_flush() -> None:
    global _flush_scheduled
    if not _flush_scheduled and _server_loop is not None:
        _flush_scheduled = True
        _server_loop.call_soon(_flush_changes)


def _flush_changes() -> None:
    global _flush_scheduled
    _flush_scheduled = False
    changes = {
        event_uniq_id: sorted(tournament_ids - _announced_tournament_ids[event_uniq_id])
        for event_uniq_id, tournament_ids in _changed_tournament_ids.items()
    }
    screens = _changed_screens - _announced_screens
    _changed_tournament_ids.clear()
    _changed_screens.clear()
    _announced_tournament_ids.clear()
    _announced_screens.clear()
    if channels_plugin._pub_queue is None:
        return
    for event_uniq_id, tournament_ids in changes.items():
        if tournament_ids:
            channels_plugin.publish(
                {
                    'event': f'tournament-changed|{event_uniq_id}',
                    'data': {'detail': {'tournament_ids': tournament_ids}},
                },
                [event_channel(event_uniq_id)],
            )
    for event_uniq_id in screens:
        channels_plugin.publish(
            {'event': f'screens-changed|{event_uniq_id}', 'data': ''},
            [event_channel(event_uniq_id)],
        )


def notify_changes(
    event_uniq_id: str, tournament_ids: Iterable[int], screens: bool
) -> None:
    """Records the changes written to the event *event_uniq_id*: to the data of
    the tournaments *tournament_ids*, and to the screens when *screens*. May be
    called from any thread."""
    tournament_ids = set(tournament_ids)
    if screens:
        _screens_changed_at[event_uniq_id] = datetime.now()

    def record() -> None:
        _changed_tournament_ids[event_uniq_id].update(tournament_ids)
        if screens:
            _changed_screens.add(event_uniq_id)
        _schedule_flush()

    if tournament_ids or screens:
        _on_server_loop(record)


def mark_tournament_change_announced(event_uniq_id: str, tournament_id: int) -> None:
    """Records that the change being written to the data of a tournament has
    been announced by an event of its own. May be called from any thread."""

    def record() -> None:
        _announced_tournament_ids[event_uniq_id].add(tournament_id)
        _schedule_flush()

    _on_server_loop(record)


def mark_screens_change_announced(event_uniq_id: str) -> None:
    """Records that the change being written to the screens of an event has
    been announced by an event of its own. May be called from any thread."""

    def record() -> None:
        _announced_screens.add(event_uniq_id)
        _schedule_flush()

    _on_server_loop(record)
