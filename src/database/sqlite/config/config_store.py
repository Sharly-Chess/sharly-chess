"""
All the classes of this module are basic data classes stored in the config database.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StoredConfig:
    force_edit: bool
    console_log_level: int | None
    console_color: bool
    console_show_date: bool
    console_show_level: bool
    experimental: bool
    launch_browser: bool
    federation: str | None = None
    locale: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredPlugin:
    name: str
    is_default_enabled: bool
    plugin_data: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict[str, dict[str, dict[str, Any]]]
    )


@dataclass
class StoredLocalSourceDatabase:
    name: str
    outdate_delay: str
    outdate_action: str
    updated_at: float | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])
