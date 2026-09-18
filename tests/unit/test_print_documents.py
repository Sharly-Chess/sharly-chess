"""Every print document builds, for an individual event and a team one."""

import inspect
from collections.abc import Iterator

import pytest

from data.access_levels.client import Client
from data.event import Event
from data.loader import EventLoader
from data.pairings.variations import BergerTeamRoundRobinVariation
from data.print_documents import documents
from data.print_documents.documents import PrintDocument
from data.print_documents.managers import (
    PrintDocumentManager,
    PrintPairingStyleManager,
)
from data.print_documents.options import PrintOption
from data.print_documents.place_cards.editor import PlaceCardTemplateEditor
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import (
    StoredPlayer,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, Result
from web.controllers.admin.event_documents_controller import EventDocumentsController
from web.controllers.base_controller import WebContext

EVENT_ID = 'test-print-documents'
TEAM_EVENT_ID = 'test-print-documents-teams'
TOURNAMENT_NAME = 'test-print-documents-tournament'
TEAM_COUNT = 4
TEAM_SIZE = 2

DOCUMENT_TYPES: list[type[PrintDocument]] = [
    obj
    for obj in vars(documents).values()
    if inspect.isclass(obj)
    and issubclass(obj, PrintDocument)
    and not inspect.isabstract(obj)
]


@pytest.fixture(scope='module')
def event() -> Iterator[Event]:
    TestUtils.create_event(EVENT_ID)
    TestUtils.create_tournament(EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss')
    yield EventLoader().load_event(EVENT_ID)
    EventLoader.unload_event(EVENT_ID)
    TestUtils.delete_event(EVENT_ID)


@pytest.fixture(scope='module')
def team_event() -> Iterator[Event]:
    """A team event, which the other half of the documents is printed for.
    No example event has teams, so the rosters are seeded here."""
    TestUtils.create_event(TEAM_EVENT_ID, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        TEAM_EVENT_ID,
        TOURNAMENT_NAME,
        overrides={
            'pairing': BergerTeamRoundRobinVariation.static_id(),
            'team_player_count': TEAM_SIZE,
            'rounds': TEAM_COUNT - 1,
        },
    )
    tournament_id = stored_tournament.id
    assert tournament_id is not None
    with EventDatabase(TEAM_EVENT_ID, write=True) as database:
        for team_index in range(TEAM_COUNT):
            team_id = database.add_stored_team(
                StoredTeam(
                    id=None,
                    name=f'Team {team_index + 1}',
                    tournament_id=tournament_id,
                    pairing_number=team_index + 1,
                )
            )
            for board_index in range(TEAM_SIZE):
                player_id = database.add_stored_player(
                    StoredPlayer(
                        id=None,
                        last_name=f'Player {team_index + 1}.{board_index + 1}',
                        team_id=team_id,
                        team_index=board_index,
                        check_in=True,
                    )
                )
                database.add_stored_tournament_player(
                    StoredTournamentPlayer(
                        tournament_id=tournament_id,
                        player_id=player_id,
                        pairing_number=team_index * TEAM_SIZE + board_index + 1,
                    )
                )
    loaded = EventLoader().load_event(TEAM_EVENT_ID)
    _play_first_round(loaded.tournaments_by_name[TOURNAMENT_NAME])
    with EventDatabase(TEAM_EVENT_ID, write=True) as database:
        # Round one is over, so the documents that rank on a finished
        # round have one to rank on.
        database.set_tournament_current_round(tournament_id, 2)
    EventLoader.unload_event(TEAM_EVENT_ID)
    yield EventLoader().load_event(TEAM_EVENT_ID)
    EventLoader.unload_event(TEAM_EVENT_ID)
    TestUtils.delete_event(TEAM_EVENT_ID)


def _play_first_round(tournament: Tournament) -> None:
    """The first team of each match wins every board, so the documents
    that only print a finished round have one to print."""
    with EventDatabase(TEAM_EVENT_ID, write=True) as database:
        for team_board in tournament.get_round_team_boards(1):
            team_a_id = team_board.stored_team_board.team_a_id
            if team_board.stored_team_board.team_b_id is None:
                continue
            for board in team_board.boards:
                for pairing in (
                    board.optional_white_pairing,
                    board.optional_black_pairing,
                ):
                    if pairing is None:
                        continue
                    won = pairing.tournament_player.team_id == team_a_id
                    pairing.update_result(database, Result.WIN if won else Result.LOSS)


def _case(event: Event) -> tuple[Event, dict[str, str]]:
    """An event and the option values the print controller fills in from
    the modal, which no document can default for itself."""
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    player = next(iter(tournament.players_by_id.values()))
    return event, {
        'tournament': str(tournament.id),
        'tournaments': str(tournament.id),
        'mandatory-player': str(player.id),
        'place-card-template': PlaceCardTemplateEditor.create('Cards', 'player'),
    }


@pytest.fixture(scope='module')
def individual_case(event: Event) -> tuple[Event, dict[str, str]]:
    return _case(event)


@pytest.fixture(scope='module')
def team_case(team_event: Event) -> tuple[Event, dict[str, str]]:
    return _case(team_event)


def _build(
    event: Event, document_type: type[PrintDocument], values: dict[str, str]
) -> PrintDocument:
    """Build a document the way the print controller does, from the values
    the modal holds."""
    client = Client.for_event_administrator(event)
    options: list[PrintOption] = []
    for option in document_type(client).default_options():
        value = (
            WebContext.form_data_to_value(values, option.id, option.type)
            if option.id in values
            else option.default_value
        )
        options.append(type(option)(event, value))
    return document_type(client, options)


@pytest.mark.unit
def test_every_document_can_be_reached(event: Event):
    """A document neither listed by the manager nor named by a pairing
    style cannot be printed at all."""
    reachable = set(PrintDocumentManager(event).entity_types())
    reachable |= {
        style.print_document_type for style in PrintPairingStyleManager(event).objects()
    }
    assert set(DOCUMENT_TYPES) <= reachable


@pytest.mark.unit
@pytest.mark.parametrize('case_name', ['individual_case', 'team_case'])
def test_every_offered_document_builds_its_context(
    request: pytest.FixtureRequest, case_name: str
):
    """The context is what the template reads, so a document that cannot
    build one prints nothing. Which documents an event is offered depends
    on its type and pairing system, so each case checks its own."""
    event, option_values = request.getfixturevalue(case_name)
    offered: list[str] = []
    failures: list[str] = []
    for document_type in DOCUMENT_TYPES:
        document = _build(event, document_type, option_values)
        if not document_type.is_available(document.get_allowed_tournaments()):
            continue
        offered.append(document_type.static_id())
        try:
            document.validate_options()
            assert document.tab_title
            assert isinstance(document.template_context, dict)
        except Exception as error:
            failures.append(f'{document_type.static_id()}: {error!r}')
    assert offered
    assert not failures, '\n'.join(failures)


@pytest.mark.unit
def test_options_are_read_from_the_view_url(event: Event):
    """The print tab opens the document in a new tab, carrying the modal's
    choices as one query parameter."""
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    client = Client.for_event_administrator(event)
    document = EventDocumentsController.build_print_document(
        client,
        event,
        documents.PlayerListPrintDocument.static_id(),
        f'tournament={tournament.id}',
    )
    assert document.tournament.id == tournament.id
