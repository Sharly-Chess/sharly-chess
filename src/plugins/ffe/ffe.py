import re

from collections import defaultdict
from datetime import datetime
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any, TYPE_CHECKING, Iterable

from dateutil.relativedelta import relativedelta
from packaging.version import Version

from common import BASE_DIR
from common.logger import print_interactive_error
from data.util import PlayerRatingType, PrintDocument, ScreenType, TournamentRating, get_plugin_data
from data.player import Player
from plugins.ffe.constants import PLUGIN_NAME, PLUGIN_VERSION
from plugins.ffe.ffe_database import FfeDatabase
from plugins.ffe.util import PlayerFFELicence
from plugins.hookspec import ExtraAdminColumn, PrintSplitOption, hookimpl, ExtraColumn

from common.i18n import _

import web.controllers.base_controller as WebContextModule
from . import migrations

from .ffe_search_controller import FfeSearchController
from ..migration import AbstractPluginMigrationManager

if TYPE_CHECKING:
    from data.tournament import Tournament

""" The FFE league names. """
ffe_leagues: dict[str, str] = {
    '': '',
    'ARA': 'Auvergne-Rhône-Alpes',
    'BFC': 'Bourgogne-Franche-Comté',
    'BRE': 'Bretagne',
    'CRS': 'Corse',
    'CVL': 'Centre-Val de Loire',
    'EST': 'Grand-Est',
    'GUA': 'Guadeloupe',
    'GUY': 'Guyane',
    'HDF': 'Hauts-de-France',
    'IDF': 'Île-de-France',
    'MAR': 'Martinique',
    'NAQ': 'Nouvelle-Aquitaine',
    'NCA': 'Nouvelle-Calédonie',
    'NOR': 'Normandie',
    'OCC': 'Occitanie',
    'PAC': "Provence-Alpes-Côte d'azur",
    'PDL': 'Pays de la Loire',
    'POL': 'Saint-Pierre-et-Miquelon',
    'REU': 'Réunion',
}

get_data = partial(get_plugin_data, PLUGIN_NAME)


class FfePluginMigrationManager(AbstractPluginMigrationManager):
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
def on_init():
    if not FfeDatabase().check():
        print_interactive_error(_('Error while updating the FFE database.'))


@hookimpl
def get_db_player_fields() -> list[str]:
    return ['RefFFE', 'AffType', 'NrFFE', 'Ligue']


@hookimpl
def augment_player_after_db_fetch(player: Player, row: dict[str, Any]):
    player.plugin_data[PLUGIN_NAME] = {
        'ffe_id': row['RefFFE'],
        'ffe_licence': PlayerFFELicence.from_papi_value(row['AffType'] or ''),
        'ffe_licence_number': row['NrFFE'] or '',
        'league': row['Ligue'] or '',
    }


@hookimpl
def player_data_for_db_write(player: Player) -> dict[str, Any]:
    pd = player.plugin_data
    return {
        'RefFFE': get_data(pd, 'ffe_id', (datetime.now() - relativedelta(years=30))),  # like Papi does :-(
        'AffType': get_data(pd, 'ffe_licence').to_papi_value if get_data(pd, 'ffe_licence') else '',
        'NrFFE': get_data(pd, 'ffe_licence_number', None),
        'Ligue': get_data(pd, 'league', ''),
    }


@hookimpl
def get_controllers() -> Iterable[type[WebContextModule.BaseController]]:
    return [
        FfeSearchController,
    ]


@hookimpl
def get_templates_path() -> Path:
    return BASE_DIR / 'src/plugins/ffe/templates'


@hookimpl
def get_base_admin_context() -> dict[str, Any]:
    return {
        'ffe_search_available': FfeDatabase().exists(),
        'ffe_leagues': ffe_leagues
    }


@hookimpl
def get_player_search_template() -> str:
    return "/ffe_search.html"


@hookimpl
def get_player_form_fields_template() -> str:
    return "/ffe_player_form_fields.html"


@hookimpl
def get_player_form_data(
    plugin_data: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        'ffe_licence': WebContextModule.WebContext.value_to_form_data(get_data(plugin_data, 'ffe_licence', None)),
        'ffe_licence_number': WebContextModule.WebContext.value_to_form_data(
            get_data(plugin_data, 'ffe_licence_number', None)
        ),
        'ffe_id': WebContextModule.WebContext.value_to_form_data(get_data(plugin_data, 'ffe_id', None)),
        'ffe_league': WebContextModule.WebContext.value_to_form_data(get_data(plugin_data, 'league', None)),
    }   


@hookimpl
def get_validated_player_form_fields(
    action: str,
    tournament: 'Tournament',
    data: dict[str, str],
    errors: dict[str, str]
) -> dict[str, Any]:
    league: str | None = WebContextModule.WebContext.form_data_to_str(data, field := 'ffe_league')
    if league and league not in ffe_leagues:
        # should never happen, not translated.
        errors[field] = f'Invalid league value [{data[field]}].'
        data[field] = ''
    ffe_id: int | None = None

    if tournament:
        # When adding a player, the tournament may not me chosen (in this case do not test)
        try:
            ffe_id = WebContextModule.WebContext.form_data_to_int(data, field := 'ffe_id', minimum=1)
            ffe_ids = [ get_data(player.plugin_data, 'ffe_id', None) for player in tournament.players_by_id.values() ]

            if action == 'create' and ffe_id and ffe_id in ffe_ids:
                    errors[field] = _(
                        'The player with FFE ID [{ffe_id}] already plays tournament [{tournament_uniq_id}].'
                    ).format(
                        ffe_id=ffe_id,
                        tournament_uniq_id=tournament.uniq_id
                    )
        except ValueError:
            errors[field] = _('Invalid FFE ID [{ffe_id}].').format(ffe_id=data[field])
   
    ffe_licence: PlayerFFELicence = PlayerFFELicence.NONE
    try:
        ffe_licence = PlayerFFELicence(
            WebContextModule.WebContext.form_data_to_int(data, field := 'ffe_licence')
        )
    except ValueError:
        errors[field] = f'Invalid FFE licence [{data[field]}].'
    
    ffe_licence_number: str | None = WebContextModule.WebContext.form_data_to_str(
        data, field := 'ffe_licence_number'
    )
    if ffe_licence_number:
        if not re.match(r'^[A-Z]\d{5}$', ffe_licence_number):
            errors[field] = _(
                'Invalid FFE licence number [{ffe_licence_number}].'
            ).format(ffe_licence_number=data[field])
        elif tournament:
            # When adding a player, the tournament may not me chosen (in this case do not test)
            ffe_licence_numbers = [ player.plugin_data.get(PLUGIN_NAME, {}).get('ffe_licence_number', None) for player in tournament.players_by_id.values() ]
            if action == 'create' and ffe_licence_number in ffe_licence_numbers:
                errors[field] = _(
                    'The player with FFE licence number [{ffe_licence_number}] already plays tournament [{tournament_uniq_id}].'
                ).format(
                    ffe_licence_number=ffe_licence_number,
                    tournament_uniq_id=tournament.uniq_id
                )

    return {
        PLUGIN_NAME: {
            "ffe_id": ffe_id,
            "ffe_licence": ffe_licence,
            "ffe_licence_number": ffe_licence_number,
            "league": league,
        }
    }


@hookimpl
def augment_player_after_search(player: Player):
    # Try to get more information by requesting the FFE database
    if FfeDatabase().exists():
        with FfeDatabase() as ffe_database:
            if ffe_player := ffe_database.get_player_by_fide_id(player.fide_id):
                for rating_type in [
                    TournamentRating.STANDARD,
                    TournamentRating.RAPID,
                    TournamentRating.BLITZ,
                ]:
                    if player.rating_types[rating_type] == PlayerRatingType.ESTIMATED:
                        player.ratings[rating_type] = ffe_player.ratings[rating_type]
                        player.rating_types[rating_type] = ffe_player.rating_types[rating_type]
                if ffe_player.date_of_birth and player.year_of_birth == ffe_player.year_of_birth:
                    player.date_of_birth = ffe_player.date_of_birth
                player.comment = ffe_player.comment
                player.club = ffe_player.club
                player.plugin_data[PLUGIN_NAME] = {
                    "ffe_id": get_data(ffe_player.plugin_data, 'ffe_id'),
                    "ffe_licence": get_data(ffe_player.plugin_data, 'ffe_licence'),
                    "ffe_licence_number": get_data(ffe_player.plugin_data, 'ffe_licence_number'),
                    "league": get_data(ffe_player.plugin_data, 'league')
                }


@hookimpl
def is_tournament_participation_possible(
    tournament: 'Tournament', player: Player
) -> str | None:
    ffe_licence_number = player.plugin_data.get(PLUGIN_NAME, {}).get('ffe_licence_number', None)
    ffe_id = get_data(player.plugin_data, 'ffe_id', None)
    if (
        ffe_licence_number and any(
            get_data(player_.plugin_data, 'ffe_licence_number', None) == ffe_licence_number
            for player_ in tournament.players_by_id.values()
        )
    ):
        return _(
            'FFE licence [{ffe_licence_number}] already present in tournament [{tournament_uniq_id}].'
        ).format(
            ffe_licence_number=get_data(player.plugin_data, 'ffe_licence_number', None),
            tournament_uniq_id=tournament.uniq_id,
        )
    
    if (
        ffe_id and any(
            get_data(player_.plugin_data, 'ffe_id', None) == ffe_id
            for player_ in tournament.players_by_id.values()
        )
    ):
        # This string is not translated because the error should never happen
        return f'FFE ID [{ffe_id}] already present in tournament [{tournament.uniq_id}].'
    
    return None


@hookimpl
def get_tournament_card_block_template() -> str:
    return "/ffe_tournament_card_block.html"


def split_players_by(split_by: str, players: list[Player]):
    split_functions = {
        "ffe-league": lambda p: p.plugin_data.get(PLUGIN_NAME, {}).get('league', None),
    } 
    
    split_players = defaultdict(list)

    # Split players by group
    for player in players:
        split_players[split_functions[split_by](player)].append(player)

    # Sort by key
    split_players = {
        key: split_players[key]
        for key in sorted(split_players.keys())
    }
    
    return split_players


@hookimpl
def get_print_split_options() -> Iterable[PrintSplitOption]:
    return [
        PrintSplitOption(
            name=_('League'),
            url_name="ffe-league",
            split_fn=partial(split_players_by, "ffe-league"),
        ),
    ]


@hookimpl
def get_extra_print_view_columns(
    document: PrintDocument
) -> Iterable[ExtraColumn]:
    match document:
        case PrintDocument.PLAYER_LIST | PrintDocument.RANKING | PrintDocument.CROSSTABLE:
            return [
                ExtraColumn(
                    at="club",
                    title=_('League *** LEAGUE FOR PRINT VIEW'),
                    classes="center",
                    value=lambda player: get_data(player.plugin_data, 'league'),
                )
            ]
            
        case _:
            return []


@hookimpl
def get_extra_screen_columns(screen: ScreenType) -> Iterable[ExtraColumn]:
    match screen:
        case ScreenType.RANKING:
            return [
                ExtraColumn(
                    at="club",
                    title=_('League *** LEAGUE FOR PRINT VIEW'),
                    classes="center",
                    value=lambda player: get_data(player.plugin_data, 'league'),
                )
            ]
            
        case _:
            return []


@hookimpl
def get_extra_player_columns() -> Iterable[ExtraAdminColumn]:
    return [
        ExtraAdminColumn(
            at="club",
            header_template="/ffe_player_league_header.html",
            cell_template="/ffe_player_league_cell.html",
        ),
        ExtraAdminColumn(
            at="owed",
            header_template="/ffe_player_licence_header.html",
            cell_template="/ffe_player_licence_cell.html",
        )
    ]


@hookimpl
def get_event_migration_manager() -> AbstractPluginMigrationManager:
    return FfePluginMigrationManager()
