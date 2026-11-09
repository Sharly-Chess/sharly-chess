from collections.abc import Mapping

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
