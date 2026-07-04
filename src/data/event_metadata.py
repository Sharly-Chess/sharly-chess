from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

from common.i18n import _
from database.sqlite.event.event_store import BaseStoredEvent
from plugins.manager import plugin_manager
from plugins.utils import Plugin
from utils.enum import EventType


@dataclass
class EventMetadata(BaseStoredEvent):
    """Class containing the metadata of an event required
    for display on the event selection pages."""

    start_date: date = field(default_factory=date.today)
    stop_date: date = field(default_factory=date.today)
    tournament_count: int = 0
    player_count: int = 0
    team_count: int = 0
    timer_count: int = 0
    screen_count: int = 0
    family_count: int = 0
    rotator_count: int = 0

    @property
    def is_team_event(self) -> bool:
        return self.event_type == EventType.TEAM

    @property
    def plugins(self) -> list[Plugin]:
        return [
            plugin_manager.plugins_by_id[plugin_id]
            for plugin_id in self.enabled_plugins
        ]

    @cached_property
    def are_all_plugins_enabled(self) -> bool:
        return all(plugin.is_enabled for plugin in self.plugins)

    @property
    def plugins_tooltip_message(self) -> str:
        tooltip_message = '<div class="mt-1"></div>'
        for plugin in self.plugins:
            classes = 'text-center mb-1'
            styles = 'line-height: 1.1;'
            if not plugin.is_enabled:
                classes += ' tooltip-danger fw-bold'
                content = _('{plugin} (disabled)').format(plugin=plugin.name)
            else:
                content = plugin.name
            tooltip_message += (
                f'<div class="{classes}" style="{styles}">{content}</div>'
            )
        return tooltip_message
