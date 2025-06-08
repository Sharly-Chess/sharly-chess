"""
All the classes of this module are basic data classes stored in the config database.
"""

from dataclasses import dataclass, field


@dataclass
class StoredConfig:
    force_edit: bool = True
    console_log_level: int | None = None
    console_color: bool | None = None
    console_show_date: bool | None = None
    console_show_level: bool | None = None
    experimental: bool | None = None
    launch_browser: bool | None = None
    federation: str | None = None
    locale: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredPlugin:
    name: str
    is_enabled: bool
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredLocalSourceDatabase:
    name: str
    outdate_delay: str
    outdate_action: str
    updated_at: float | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])
