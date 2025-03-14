from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any, TYPE_CHECKING

from data.util import get_plugin_data
from packaging.version import Version

from common.i18n import _
from plugins import PLUGINS_DIR
from plugins.chessevent import migrations, PLUGIN_NAME, PLUGIN_VERSION
from plugins.chessevent.engine.chessevent_engine import ChessEventEngine
from plugins.chessevent.utils import ChessEventUtils
from plugins.hookspec import hookimpl
from plugins.utils import AbstractPluginMigrationManager, PluginEngineArgument

import web.controllers.base_controller as WebContextModule

if TYPE_CHECKING:
    from database.sqlite.event.event_store import StoredEvent
    from data.tournament import Tournament
    from database.sqlite.event.event_store import StoredTournament

get_data = partial(get_plugin_data, PLUGIN_NAME)


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
    return PLUGINS_DIR / 'chessevent' / 'templates'


@hookimpl
def on_tournament_init(tournament: 'Tournament'):
    pd = tournament.stored_tournament.plugin_data
    if not get_data(pd, 'chessevent_user_id') or not get_data(pd, 'chessevent_password'):
        tournament.event.add_debug(
            _('ChessEvent connection not defined.'), tournament=tournament
        )
    elif not get_data(pd, 'chessevent_event_id'):
        tournament.event.add_warning(_('ChessEvent event not set.'), tournament=tournament)
    elif not get_data(pd, 'chessevent_tournament_name'):
        tournament.event.add_warning(
            _('ChessEvent tournament name not set.'), tournament=tournament
        )
        

@hookimpl
def augment_event_after_db_fetch(stored_event: 'StoredEvent', row: dict[str, Any]):
    if not stored_event.plugin_data:
        stored_event.plugin_data = {}
    stored_event.plugin_data[PLUGIN_NAME] = {
        'chessevent_user_id': row.get('chessevent_user_id', None),
        'chessevent_password': row.get('chessevent_password', None),
        'chessevent_event_id': row.get('chessevent_event_id', None),
    }
    

@hookimpl
def event_data_for_db_write(stored_event: 'StoredEvent') -> dict[str, Any]:
    td = stored_event.plugin_data
    return {
        'chessevent_user_id': get_data(td, 'chessevent_user_id'),
        'chessevent_password': get_data(td, 'chessevent_password'),
        'chessevent_event_id': get_data(td, 'chessevent_event_id'),
    }
    
    
@hookimpl
def augment_tournament_after_db_fetch(stored_tournament: 'StoredTournament', row: dict[str, Any]):
    if not stored_tournament.plugin_data:
        stored_tournament.plugin_data = {}
    stored_tournament.plugin_data[PLUGIN_NAME] = {
        'chessevent_user_id': row.get('chessevent_user_id', ''),
        'chessevent_password': row.get('chessevent_password' ''),
        'chessevent_event_id': row.get('chessevent_event_id' ''),
        'chessevent_tournament_name': row['chessevent_tournament_name'],    
        'chessevent_last_download_md5': row['chessevent_last_download_md5'],
    }
    

@hookimpl
def tournament_data_for_db_write(stored_tournament: 'StoredTournament') -> dict[str, Any]:
    td = stored_tournament.plugin_data
    return {
        'chessevent_user_id': get_data(td, 'chessevent_user_id', None),
        'chessevent_password': get_data(td, 'chessevent_password', None),
        'chessevent_event_id': get_data(td, 'chessevent_event_id', None),
        'chessevent_tournament_name': get_data(td, 'chessevent_tournament_name', ''),
        'chessevent_last_download_md5': get_data(td, 'chessevent_last_download_md5', ''),
    }

                   
@hookimpl
def get_event_info_rows_template() -> str:
    return "/chessevent_event_info_rows.html"   
    
         
@hookimpl
def get_event_card_block_template() -> str:
    return "/chessevent_event_card_block.html"    

         
@hookimpl
def get_event_form_fields_template() -> str:
    return "/chessevent_event_form_fields.html"


@hookimpl
def get_event_form_data(
    event: 'Event | None'
) -> dict[str, Any]:
    if not event:
        return {
            'chessevent_user_id': '',
            'chessevent_password': '',
            'chessevent_event_id': '',
        }

    return {
        'chessevent_user_id': WebContextModule.WebContext.value_to_form_data(get_data(event.plugin_data, 'chessevent_user_id', '')),
        'chessevent_password': WebContextModule.WebContext.value_to_form_data(get_data(event.plugin_data, 'chessevent_password', '')),
        'chessevent_event_id': WebContextModule.WebContext.value_to_form_data(get_data(event.plugin_data, 'chessevent_event_id', '')),
    }   
    

@hookimpl
def get_validated_event_form_fields(
    action: str,
    event: 'Event | None',
    data: dict[str, str],
    errors: dict[str, str]
) -> dict[str, Any]:
    chessevent_user_id = WebContextModule.WebContext.form_data_to_str(
        data, 'chessevent_user_id'
    )
    chessevent_password = WebContextModule.WebContext.form_data_to_str(
        data, field := 'chessevent_password'
    )
    if chessevent_user_id and not chessevent_password:
        errors[field] = _(
            'Please enter a password for the ChessEvent connection.'
        )
    chessevent_event_id = WebContextModule.WebContext.form_data_to_str(
        data, 'chessevent_event_id'
    )
        
    # Keep data other than these two fields (such as file upload times)
    previous_data = event.plugin_data.get(PLUGIN_NAME, {}) if event else {}
                
    return {
        PLUGIN_NAME: previous_data | {
            "chessevent_user_id": chessevent_user_id,
            "chessevent_password": chessevent_password,
            "chessevent_event_id": chessevent_event_id,
        }
    }
    
    
@hookimpl
def get_tournament_card_block_template_and_data() -> tuple[str, dict[str, Any]]:
    return (
        "/chessevent_tournament_card_block.html",
        {
            "chessevent_utils": ChessEventUtils
        }
    )

@hookimpl
def get_tournament_form_fields_template() -> str:
    return "/chessevent_tournament_form_fields.html"


@hookimpl
def get_tournament_form_data(
    tournament: 'Tournament | None'
) -> dict[str, Any]:
    if not tournament:
        return {
            'chessevent_user_id': '',
            'chessevent_password': '',
            'chessevent_event_id': '',
            'chessevent_tournament_name': '',
        }

    return {
        'chessevent_user_id': WebContextModule.WebContext.value_to_form_data(get_data(tournament.plugin_data, 'chessevent_user_id', '')),
        'chessevent_password': WebContextModule.WebContext.value_to_form_data(get_data(tournament.plugin_data, 'chessevent_password', '')),
        'chessevent_event_id': WebContextModule.WebContext.value_to_form_data(get_data(tournament.plugin_data, 'chessevent_event_id', '')),
        'chessevent_tournament_name': WebContextModule.WebContext.value_to_form_data(get_data(tournament.plugin_data, 'chessevent_tournament_name', '')),
    }   
    

@hookimpl
def get_validated_tournament_form_fields(
    action: str,
    tournament: 'Tournament | None',
    data: dict[str, str],
    errors: dict[str, str]
) -> dict[str, Any]:
    
    chessevent_user_id = WebContextModule.WebContext.form_data_to_str(
        data, 'chessevent_user_id'
    )
    chessevent_password = WebContextModule.WebContext.form_data_to_str(
        data, 'chessevent_password'
    )
    chessevent_event_id = WebContextModule.WebContext.form_data_to_str(
        data, 'chessevent_event_id'
    )
    chessevent_tournament_name = WebContextModule.WebContext.form_data_to_str(
        data, 'chessevent_tournament_name'
    )
        
    # Keep data other than these two fields (such as file upload times)
    previous_data = tournament.plugin_data.get(PLUGIN_NAME, {}) if tournament else {}
                
    return {
        PLUGIN_NAME: previous_data | {
            "chessevent_user_id": chessevent_user_id,
            "chessevent_password": chessevent_password,
            "chessevent_event_id": chessevent_event_id,
            "chessevent_tournament_name": chessevent_tournament_name
        }
    }
    

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
