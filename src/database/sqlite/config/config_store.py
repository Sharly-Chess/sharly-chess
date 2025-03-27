"""
All the classes of this module are basic data classes stored in the config database.
"""

from dataclasses import dataclass, field


@dataclass
class StoredConfig:
    version: str
    force_edit: bool = True
    log_level: int | None = None
    launch_browser: bool | None = None
    federation: str | None = None
    locale: str | None = None
    errors: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class StoredPlugin:
    name: str
    is_enabled: bool
    errors: dict[str, str] = field(default_factory=dict[str, str])
