from pathlib import Path
from types import ModuleType

from packaging.version import Version

from common import BASE_DIR
from plugins.chessevent import migrations, PLUGIN_NAME, PLUGIN_VERSION
from plugins.chessevent.engine.chessevent_engine import ChessEventEngine
from plugins.hookspec import hookimpl
from plugins.utils import AbstractPluginMigrationManager, PluginEngineArgument


class ChessEventPluginMigrationManager(AbstractPluginMigrationManager):
    @property
    def plugin_name(self) -> str:
        return PLUGIN_NAME

    @property
    def latest_plugin_version(self) -> Version:
        return PLUGIN_VERSION

    @property
    def base_module(self) -> ModuleType:
        return migrations


@hookimpl
def get_templates_path() -> Path:
    return BASE_DIR / 'src/plugins/chessevent/templates'


@hookimpl
def get_tournament_card_block_template() -> str:
    return "/chessevent_tournament_card_block.html"


@hookimpl
def get_event_migration_manager() -> AbstractPluginMigrationManager:
    return ChessEventPluginMigrationManager()


@hookimpl
def get_engine_argument() -> PluginEngineArgument:
    return PluginEngineArgument(
        'c',
        'chessevent',
        'download Papi files from Chess Event',
        ChessEventEngine,
    )
