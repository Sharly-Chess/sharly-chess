"""Every print document builds, for an individual event and a team one."""

import inspect
from collections.abc import Iterator

import pytest

from data.access_levels.client import Client
from data.event import Event
from data.loader import EventLoader
from data.pairings.molter import StandardMolterVariation
from data.pairings.variations import BergerTeamRoundRobinVariation
from data.print_documents import documents
from data.print_documents.documents import PrintDocument
from data.print_documents.managers import (
    PrintDocumentManager,
    PrintPairingStyleManager,
)
from data.print_documents import options
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
MOLTER_EVENT_ID = 'test-print-documents-molter'
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


def _seed_team_event(event_id: str, pairing: str, rounds: int) -> Iterator[Event]:
    """A team event with its first round paired and played, so the
    documents that only print a finished round have one to print. No
    example event has teams, so the rosters are seeded here."""
    TestUtils.create_event(event_id, overrides={'event_type': EventType.TEAM})
    stored_tournament = TestUtils.create_tournament(
        event_id,
        TOURNAMENT_NAME,
        overrides={
            'pairing': pairing,
            'team_player_count': TEAM_SIZE,
            'rounds': rounds,
            'current_round': 1,
        },
    )
    tournament_id = stored_tournament.id
    assert tournament_id is not None
    with EventDatabase(event_id, write=True) as database:
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
    event = EventLoader().load_event(event_id)
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    assert tournament.generate_round_pairings(1) == ''
    _play_first_round(event_id, tournament)
    with EventDatabase(event_id, write=True) as database:
        database.set_tournament_current_round(tournament_id, 2)
    EventLoader.unload_event(event_id)
    yield EventLoader().load_event(event_id)
    EventLoader.unload_event(event_id)
    TestUtils.delete_event(event_id)


@pytest.fixture(scope='module')
def team_event() -> Iterator[Event]:
    """A team event, which the other half of the documents is printed for."""
    yield from _seed_team_event(
        TEAM_EVENT_ID, BergerTeamRoundRobinVariation.static_id(), TEAM_COUNT - 1
    )


@pytest.fixture(scope='module')
def molter_event() -> Iterator[Event]:
    """A team event whose system seats flat boards from a fixed table,
    with no team matches to sheet."""
    yield from _seed_team_event(MOLTER_EVENT_ID, StandardMolterVariation.static_id(), 3)


def _play_first_round(event_id: str, tournament: Tournament) -> None:
    """White wins every board, so the documents that only print a
    finished round have one to print."""
    with EventDatabase(event_id, write=True) as database:
        for board in tournament.get_round_boards(1):
            if (
                board.optional_white_tournament_player is None
                or board.black_tournament_player is None
            ):
                continue
            board.white_pairing.update_result(database, Result.WIN)
            board.black_pairing.update_result(database, Result.LOSS)


def _case(event: Event) -> tuple[Event, dict[str, str]]:
    """An event and the option values the print controller fills in from
    the modal, which no document can default for itself."""
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    player = next(iter(tournament.players_by_id.values()))
    return event, {
        'tournament': str(tournament.id),
        'tournaments': str(tournament.id),
        'round': '1',
        'mandatory-player': str(player.id),
        'place-card-template': PlaceCardTemplateEditor.create('Cards', 'player'),
    }


@pytest.fixture(scope='module')
def individual_case(event: Event) -> tuple[Event, dict[str, str]]:
    return _case(event)


@pytest.fixture(scope='module')
def team_case(team_event: Event) -> tuple[Event, dict[str, str]]:
    return _case(team_event)


@pytest.fixture(scope='module')
def molter_case(molter_event: Event) -> tuple[Event, dict[str, str]]:
    return _case(molter_event)


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
@pytest.mark.parametrize('case_name', ['individual_case', 'team_case', 'molter_case'])
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


@pytest.mark.unit
def test_match_sheets_sheet_the_matches_of_a_team_paired_system(
    team_case: tuple[Event, dict[str, str]],
):
    """Teams paired against each other get one sheet per match, chosen
    from the match selection and signed by the arbiter."""
    event, option_values = team_case
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(event, documents.MatchSheetsPrintDocument, option_values)
    assert documents.MatchSheetsPrintDocument.option_types_for_tournament(
        tournament
    ) == [
        options.TournamentPrintOption,
        options.RoundPrintOption,
        options.MatchSheetSelectionPrintOption,
        options.MatchSheetArbiterPrintOption,
    ]
    assert document.template_name == '/admin/print/match_sheets.html'
    assert document.template_context['team_boards']


@pytest.mark.unit
def test_match_sheets_print_the_pairings_of_a_flat_team_system(
    molter_case: tuple[Event, dict[str, str]],
):
    """Flat boards seated from a fixed table have no match to sheet: the
    document is the pairings one, with the pairings options (style, board
    order, federation) in place of the match selection."""
    event, option_values = molter_case
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(event, documents.MatchSheetsPrintDocument, option_values)
    assert (
        documents.MatchSheetsPrintDocument.option_types_for_tournament(tournament)
        == documents.PairingPrintDocument.available_options()
    )
    pairings = _build(event, documents.PairingPrintDocument, option_values)
    assert document.template_name == pairings.template_name
    assert document.title == pairings.title
    assert [board.id for board in document.template_context['boards']] == [
        board.id for board in pairings.template_context['boards']
    ]
