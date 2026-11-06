from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend

channels_plugin = ChannelsPlugin(
    backend=MemoryChannelsBackend(),
    arbitrary_channels_allowed=True,
)


def publish_ws_event(event: str, detail: dict[str, str] | None = None) -> None:
    """Sends an event to the open pages, which receive it as `ws:<event>`. Must
    be called from the event loop of the server. Does nothing before the server
    has started."""
    if channels_plugin._pub_queue is None:
        return
    channels_plugin.publish(
        {'event': event, 'data': {'detail': detail} if detail else ''},
        ['ws'],
    )
