"""
All the classes of this module are basic data classes stored in the config database.
"""

from dataclasses import dataclass, field

from data.auth.exec_mode import ExecMode


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
    default_mode: int = ExecMode.STAND_ALONE.value
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
