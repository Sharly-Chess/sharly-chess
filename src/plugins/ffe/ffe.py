import re

from litestar.contrib.htmx.request import HTMXRequest

from collections import Counter, defaultdict
from dataclasses import dataclass

from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, TYPE_CHECKING, Iterable

from dateutil.relativedelta import relativedelta

from common import BASE_DIR
from common.logger import print_interactive_error
from data.event import Event
from data.util import PlayerCategory, PlayerRatingType, PrintDocument, ScreenType, TournamentRating, get_plugin_data
from data.player import Player
from plugins.hookspec import ExtraAdminColumn, PrintSplitOption, hookimpl, ExtraColumn

from common.i18n import _

from web.controllers.admin.base_event_admin_controller import BaseEventAdminWebContext
import web.controllers.base_controller as WebContextModule

from .constants import PLUGIN_NAME
from .util import PlayerFFELicence
from .ffe_database import FfeDatabase
from .ffe_session_handler import FFESessionHandler
from .ffe_search_controller import FfeSearchController
from .ffe_event_controller import FfeAdminEventController

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
        FfeAdminEventController,
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
def get_base_event_admin_context(web_context: BaseEventAdminWebContext) -> dict[str, Any]:
    admin_event: Event = web_context.admin_event
    match web_context.admin_event_tab:
        case 'players':
            # The leagues that will be shown on the league select list
            players_leagues: list[str] = sorted(
                {
                    get_data(player.plugin_data, 'league')
                    for player in web_context.admin_event.players_by_id.values()
                }
            )
            
            # The leagues that will be selected on the league select list and used to filter the players
            filter_leagues: list[str] = [
                league
                for league in FFESessionHandler.get_session_admin_players_filter_leagues(
                    web_context.request
                )
                if league in players_leagues
            ]

            # The licences that will be shown on the licence select list
            players_licences: list[PlayerFFELicence] = sorted(
                {
                    get_data(player.plugin_data, 'ffe_licence')
                    for player in admin_event.players_by_id.values()
                }
            )
            # The licences that will be selected on the licence select list and used to filter the players
            filter_licences: list[PlayerFFELicence] = (
                FFESessionHandler.get_session_admin_players_filter_licences(
                    web_context.request
                )
            )
            
            league_counts: Counter[str] = Counter[str]()
            for player in web_context.admin_event.players_by_id.values():
                league_counts[get_data(player.plugin_data, 'league')] += 1
    
            licence_counts: Counter[PlayerFFELicence] = Counter[PlayerFFELicence]()
            for player in web_context.admin_event.players_by_id.values():
                licence_counts[get_data(player.plugin_data, 'ffe_licence')] += 1

            return {
                'admin_players_leagues': players_leagues,
                'admin_filter_leagues': filter_leagues,
                'admin_players_licences': players_licences,
                'admin_filter_licences': filter_licences,
                'ffe_league_counts': league_counts,
                'ffe_licence_counts': licence_counts,
                
                'admin_players_filter_leagues': FFESessionHandler.get_session_admin_players_filter_leagues(
                    web_context.request
                ),
                'admin_players_filter_licences': FFESessionHandler.get_session_admin_players_filter_licences(
                    web_context.request
                ),
        }
                
        case _:
            pass
        
        
@hookimpl
def clear_player_filters(request: HTMXRequest):
    FFESessionHandler.set_session_admin_players_filter_leagues(request, [])
    FFESessionHandler.set_session_admin_players_filter_licences(request, [])
        
        
@hookimpl
def filter_player(web_context: HTMXRequest, player: Player) -> bool:
    filter_leagues: list[str] = (
        FFESessionHandler.get_session_admin_players_filter_leagues(
            web_context.request
        )
    )
    filter_licences: list[str] = (
        FFESessionHandler.get_session_admin_players_filter_licences(
            web_context.request
        )
    )
    
    admin_players_leagues = web_context.template_context['admin_players_leagues']
    admin_players_licences = web_context.template_context['admin_players_licences']
    
    return (
        len(filter_leagues) in [0, len(admin_players_leagues)]
        or get_data(player.plugin_data, 'league') in filter_leagues
    ) and (
        len(filter_licences) in [0, len(admin_players_licences)]
        or get_data(player.plugin_data, 'ffe_licence') in filter_licences
    )


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
def set_player_default_ratings(federation: str, player: 'Player'):
    if federation != 'FRA':
        return
    
    if not player.ratings[TournamentRating.RAPID]:
        match player.category:
            case PlayerCategory.U8 | PlayerCategory.U10:
                player.ratings[TournamentRating.RAPID] = 799
            case PlayerCategory.U12 | PlayerCategory.U14:
                player.ratings[TournamentRating.RAPID] = 999
            case _:
                player.ratings[TournamentRating.RAPID] = 1199
    if not player.ratings[TournamentRating.BLITZ]:
        match player.category:
            case PlayerCategory.U8 | PlayerCategory.U10:
                player.ratings[TournamentRating.BLITZ] = 799
            case PlayerCategory.U12 | PlayerCategory.U14:
                player.ratings[TournamentRating.BLITZ] = 999
            case _:
                player.ratings[TournamentRating.BLITZ] = 1199
    if not player.ratings[TournamentRating.STANDARD]:
        match player.category:
            case (
                PlayerCategory.U8
                | PlayerCategory.U10
                | PlayerCategory.U12
                | PlayerCategory.U14
                | PlayerCategory.U16
                | PlayerCategory.U18
                | PlayerCategory.U20
            ):
                player.ratings[TournamentRating.STANDARD] = 1299
            case _:
                player.ratings[TournamentRating.STANDARD] = 1399

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