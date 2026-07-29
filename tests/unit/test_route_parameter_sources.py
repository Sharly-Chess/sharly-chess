import inspect

import pytest
from litestar.params import QueryParameter

from plugins.fra_schools.fra_schools_controller import FRASchoolsController
from web.controllers.admin.family_admin_controller import FamilyAdminController
from web.controllers.admin.pairings_admin_controller import PairingsAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.admin.prize_admin_controller import PrizeAdminController
from web.controllers.admin.tournament_admin_controller import TournamentAdminController
from web.controllers.qrcode_controller import QRCodeController


@pytest.mark.unit
@pytest.mark.parametrize(
    ('controller', 'handler_name', 'parameter_name'),
    [
        (QRCodeController, 'qrcode', 'logo'),
        (PrizeAdminController, 'htmx_admin_prizes_tab', 'show_details'),
        (
            FamilyAdminController,
            'htmx_admin_event_families_tab',
            'show_details',
        ),
        (PlayerAdminController, 'htmx_admin_event_players_search', 'search'),
        (PlayerAdminController, 'htmx_admin_player_row', 'close_modal'),
        (
            PlayerAdminController,
            'htmx_admin_event_players_diff_modal',
            'tournament_id',
        ),
        (
            PairingsAdminController,
            'htmx_admin_prohibited_pairings_manual_form',
            'index',
        ),
        (
            TournamentAdminController,
            'htmx_admin_event_tournaments_tab',
            'show_details',
        ),
        (
            FRASchoolsController,
            'fra_schools_add_school_form',
            'fra_school_id',
        ),
    ],
)
def test_query_parameters_are_annotated_as_query_parameters(
    controller: type,
    handler_name: str,
    parameter_name: str,
) -> None:
    route_handler = controller.__dict__[handler_name]
    parameter = inspect.signature(route_handler.fn).parameters[parameter_name]

    assert any(
        isinstance(metadata, QueryParameter)
        for metadata in parameter.annotation.__metadata__
    )
