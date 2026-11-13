"""Every print document builds, for an individual event and a team one."""

import inspect
import math
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest

from common.exception import OptionError
from common.i18n import get_locale, set_locale
from data.access_levels.client import Client
from data.account import Account
from data.board import Board
from data.columns.board_table import PairingResultColumn, WrittenResultColumn
from data.columns.column import ColumnUsage
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
from data.print_documents.options import ArbiterNormForm, PrintOption
from data.print_documents.page_layout import css_string, page_number_content
from data.print_documents.place_cards.data import PlaceCardTournament
from data.print_documents.place_cards.editor import PlaceCardTemplateEditor
from data.print_documents.place_cards.types import PairingCardType
from data.tournament import Tournament
from database.sqlite.event.event_database import EventDatabase
from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader
from plugins.custom_upload.utils import ConfiguredDocument
from database.sqlite.event.event_store import (
    StoredAccount,
    StoredPlayer,
    StoredRole,
    StoredTeam,
    StoredTournamentPlayer,
)
from tests.test_config import TestUtils
from utils.enum import EventType, PlayerRatingType, PlayerTitle, Result, RoleType
from web.controllers.admin.event_documents_controller import EventDocumentsController
from web.controllers.base_controller import WebContext

EVENT_ID = 'test-print-documents'
TEAM_EVENT_ID = 'test-print-documents-teams'
MOLTER_EVENT_ID = 'test-print-documents-molter'
PLAYING_EVENT_ID = 'test-print-documents-playing'
UNRATED_EVENT_ID = 'test-print-documents-unrated'
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


def _seed_edited_event(
    event_id: str, edit: Callable[[Tournament, EventDatabase], None]
) -> Iterator[Event]:
    """The individual event, with some of its results changed by *edit*."""
    TestUtils.create_event(event_id)
    TestUtils.create_tournament(event_id, TOURNAMENT_NAME, json_file='tec-swiss')
    original_event = EventLoader().load_event(event_id)
    with EventDatabase(event_id, write=True) as database:
        edit(original_event.tournaments_by_name[TOURNAMENT_NAME], database)
    EventLoader.unload_event(event_id)
    yield EventLoader().load_event(event_id)
    EventLoader.unload_event(event_id)
    TestUtils.delete_event(event_id)


def _played_boards(tournament: Tournament, round_: int) -> list[Board]:
    return [
        board
        for board in tournament.get_round_boards(round_)
        if board.optional_white_tournament_player is not None
        and board.black_tournament_player is not None
    ]


@pytest.fixture(scope='module')
def playing_event() -> Iterator[Event]:
    """The individual event with its last round still in play: one board
    of that round has no result yet."""

    def clear_one_result(tournament: Tournament, database: EventDatabase) -> None:
        board = _played_boards(tournament, tournament.rounds)[0]
        board.white_pairing.update_result(database, Result.NO_RESULT)
        board.black_pairing.update_result(database, Result.NO_RESULT)

    for event in _seed_edited_event(PLAYING_EVENT_ID, clear_one_result):
        assert event.tournaments_by_name[TOURNAMENT_NAME].playing
        yield event


UNRATED_RESULTS = {
    Result.WIN: Result.UNRATED_WIN,
    Result.DRAW: Result.UNRATED_DRAW,
    Result.LOSS: Result.UNRATED_LOSS,
}


@pytest.fixture(scope='module')
def unrated_event() -> Iterator[Event]:
    """The individual event with every game of its first round unrated."""

    def unrate_first_round(tournament: Tournament, database: EventDatabase) -> None:
        for board in _played_boards(tournament, 1):
            for pairing in (board.white_pairing, board.black_pairing):
                pairing.update_result(
                    database, UNRATED_RESULTS.get(pairing.result, pairing.result)
                )

    yield from _seed_edited_event(UNRATED_EVENT_ID, unrate_first_round)


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
    assert document.template_context['landscape']


@pytest.mark.unit
def test_match_sheets_of_large_matches_print_in_portrait(
    team_case: tuple[Event, dict[str, str]], monkeypatch: pytest.MonkeyPatch
):
    """Matches with more boards than a landscape page holds are printed
    on upright pages."""
    event, option_values = team_case
    monkeypatch.setattr(documents, 'LANDSCAPE_MAX_BOARDS', TEAM_SIZE - 1)
    document = _build(event, documents.MatchSheetsPrintDocument, option_values)
    assert not document.template_context['landscape']


@pytest.mark.unit
def test_team_pairings_list_the_matches_of_a_team_paired_system(
    team_case: tuple[Event, dict[str, str]],
):
    """Teams paired against each other get the round's matches on one
    list, each with its board score."""
    event, option_values = team_case
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(event, documents.TeamPairingsPrintDocument, option_values)
    assert documents.TeamPairingsPrintDocument.is_available([tournament])
    team_boards = document.template_context['team_boards']
    assert {tb.id for tb in team_boards} == {
        tb.id for tb in tournament.get_round_team_boards(1)
    }
    assert all(
        tb.game_score_display != '-' for tb in team_boards if tb.team_b is not None
    )


@pytest.mark.unit
def test_team_pairings_are_not_offered_to_a_flat_team_system(
    molter_case: tuple[Event, dict[str, str]],
):
    """Flat boards seated from a fixed table have no team matches to list."""
    event, _option_values = molter_case
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    assert not documents.TeamPairingsPrintDocument.is_available([tournament])


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


@pytest.mark.unit
def test_pairing_cards_carry_their_round(event: Event):
    """Pairing cards can print the round they were made for, next to the
    tournament's name."""
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    pairings = PairingCardType.pairings(tournament, 2)
    assert pairings
    assert {pairing.round for pairing in pairings} == {2}


@pytest.mark.unit
def test_place_cards_date_the_tournament_from_its_start(
    event: Event, monkeypatch: pytest.MonkeyPatch
):
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    monkeypatch.setattr(
        tournament.stored_tournament,
        'start_date',
        tournament.stop_date - timedelta(days=40),
    )
    place_card_tournament = PlaceCardTournament(tournament)
    assert place_card_tournament.start.day == tournament.start_date.day
    assert place_card_tournament.start.month == tournament.start_date.month
    assert place_card_tournament.start.year == tournament.start_date.year


def _certificates(event: Event) -> list[dict[str, Any]]:
    """Checks the certificate of every FIDE-rated player against the
    intermediate ratings computed round by round from the rated games, and
    returns what each certificate prints."""
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    certificates: list[dict[str, Any]] = []
    for tournament_player in tournament.tournament_players:
        if tournament_player.rating_used_by_fide.type != PlayerRatingType.FIDE:
            continue
        k_factor, _estimated = tournament_player.fide_rating_coefficient
        starting_rating = tournament_player.rating_used_by_fide.value
        ratings_by_round: dict[int, int] = {}
        performance_diff = 0.0
        for round_, pairing in tournament_player.pairings_by_round.items():
            if not pairing.played or pairing.result.is_unrated:
                continue
            rating_change = pairing.fide_rating_change(k_factor)
            if rating_change.delta is None:
                continue
            performance_diff += pairing.result.point_value - rating_change.expected
            ratings_by_round[round_] = starting_rating + math.floor(
                round(k_factor * performance_diff, 2) + 0.5
            )
        if not ratings_by_round:
            continue
        peak_rating = max(ratings_by_round.values())
        peak_round = min(
            round_
            for round_, rating in ratings_by_round.items()
            if rating == peak_rating
        )
        document = _build(
            event,
            documents.RatingAchievementCertificatePrintDocument,
            {
                'tournament': str(tournament.id),
                'mandatory-player': str(tournament_player.id),
            },
        )
        document.validate_options()
        context = document.template_context
        assert context['at_round'] == peak_round
        assert context['intermediate_rating'] == peak_rating
        assert {round_ for round_, _pairing, _change in context['games']} <= set(
            range(1, peak_round + 1)
        )
        certificates.append(context)
    return certificates


@pytest.mark.unit
def test_rating_certificate_stops_at_the_peak_rating(event: Event):
    """The certificate states the highest intermediate rating the player
    reached, after the earliest round it was reached, adding K times the
    difference between the score and the expected score of the rated games
    played until then."""
    assert _certificates(event)


@pytest.mark.unit
def test_rating_certificate_counts_the_round_in_play(playing_event: Event):
    """The games of a round still in play count for the certificate as soon
    as their result is entered."""
    tournament = playing_event.tournaments_by_name[TOURNAMENT_NAME]
    assert tournament.rounds in {
        certificate['at_round'] for certificate in _certificates(playing_event)
    }


@pytest.mark.unit
def test_rating_certificate_leaves_out_the_unrated_games(unrated_event: Event):
    """An unrated game is listed as not rated, and its result does not
    count for the intermediate rating."""
    unrated_games = [
        rating_change
        for certificate in _certificates(unrated_event)
        for round_, _pairing, rating_change in certificate['games']
        if round_ == 1
    ]
    assert unrated_games
    assert all(rating_change.delta is None for rating_change in unrated_games)


@pytest.mark.unit
@pytest.mark.parametrize('result', list(Result))
def test_every_result_has_a_crosstable_symbol(result: Result):
    assert isinstance(result.to_crosstable, str)


@pytest.mark.unit
def test_uploaded_document_has_no_export_toolbar(event: Event):
    """The export toolbar is for the documents viewed in the browser: a
    document uploaded to a server is the document alone."""
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    document = ConfiguredDocument(
        document_id=documents.PlayerListPrintDocument.static_id(),
        options=f'tournament={tournament.id}',
    )
    file, _ = CustomUploadUploader._generate_document_in_memory(
        event, document, Client.for_event_administrator(event)
    )
    html = file.getvalue().decode()
    assert next(iter(tournament.players_by_id.values())).last_name in html
    assert 'document-export-toolbar' not in html


ARBITERS_EVENT_ID = 'test-print-documents-arbiters'


@pytest.fixture(scope='module')
def arbiters_event() -> Iterator[Event]:
    """The individual event, refereed by a chief arbiter and an arbiter."""
    TestUtils.create_event(ARBITERS_EVENT_ID)
    TestUtils.create_tournament(
        ARBITERS_EVENT_ID, TOURNAMENT_NAME, json_file='tec-swiss'
    )
    event = EventLoader().load_event(ARBITERS_EVENT_ID)
    tournament_id = event.tournaments_by_name[TOURNAMENT_NAME].id
    for role_type, first_name in (
        (RoleType.CHIEF_ARBITER, 'Chief'),
        (RoleType.ARBITER, 'Candidate'),
    ):
        event.create_account(
            StoredAccount(
                id=None,
                active=True,
                first_name=first_name,
                last_name='Arbiter',
                stored_roles=[
                    StoredRole(
                        account_id=None,
                        role=role_type.value,
                        tournament_ids=[tournament_id],
                    )
                ],
            )
        )
    EventLoader.unload_event(ARBITERS_EVENT_ID)
    yield EventLoader().load_event(ARBITERS_EVENT_ID)
    EventLoader.unload_event(ARBITERS_EVENT_ID)
    TestUtils.delete_event(ARBITERS_EVENT_ID)


def _account(event: Event, first_name: str) -> Account:
    return next(
        account
        for account in event.sorted_active_user_accounts
        if account.first_name == first_name
    )


def _arbiter_norm_report(event: Event, **values: str) -> dict[str, Any]:
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(
        event,
        documents.ArbiterNormReportPrintDocument,
        {'tournaments': str(tournament.id)} | values,
    )
    assert documents.ArbiterNormReportPrintDocument.is_available(
        document.get_allowed_tournaments()
    )
    document.validate_options()
    return document.template_context


@pytest.mark.unit
@pytest.mark.parametrize('form', list(ArbiterNormForm))
def test_arbiter_norm_report_describes_the_tournament(
    arbiters_event: Event, form: ArbiterNormForm
):
    """The report counts every player, the FIDE-rated ones, their
    federations and the players holding a title above CM and WCM."""
    tournament = arbiters_event.tournaments_by_name[TOURNAMENT_NAME]
    candidate = _account(arbiters_event, 'Candidate')
    context = _arbiter_norm_report(
        arbiters_event,
        **{
            'arbiter-norm-form': form.value,
            'arbiter-norm-candidate': str(candidate.id),
        },
    )
    assert context['form'] == form
    players = list(tournament.tournament_players)
    assert context['candidate'] == candidate
    assert context['players_count'] == len(players)
    assert context['fide_rated_players_count'] == sum(
        1
        for player in players
        if player.rating_used_by_fide.type == PlayerRatingType.FIDE
    )
    assert context['federations_count'] == len(
        {str(player.federation) for player in players if str(player.federation)}
    )
    not_titles = {PlayerTitle.CANDIDATE_MASTER, PlayerTitle.WOMAN_CANDIDATE_MASTER}
    assert context['titled_players_count'] == sum(
        1 for player in players if player.held_titles - not_titles
    )
    assert context['rounds'] == str(tournament.rounds)


@pytest.mark.unit
def test_arbiter_norm_report_names_the_system_in_english(arbiters_event: Event):
    """FIDE forms are in English, whatever the language of the interface."""
    candidate = _account(arbiters_event, 'Candidate')
    previous_locale = get_locale()
    set_locale('fr')
    try:
        context = _arbiter_norm_report(
            arbiters_event,
            **{'arbiter-norm-candidate': str(candidate.id)},
        )
        assert get_locale() == 'fr'
    finally:
        set_locale(previous_locale)
    assert context['system'] == 'Swiss'


@pytest.mark.unit
def test_arbiter_norm_report_is_signed_by_the_chosen_signee_only(
    arbiters_event: Event,
):
    """The signee fields stay blank unless a signee is chosen, even when the
    tournament has a chief arbiter."""
    candidate = _account(arbiters_event, 'Candidate')
    context = _arbiter_norm_report(
        arbiters_event,
        **{'arbiter-norm-candidate': str(candidate.id)},
    )
    assert context['signee'] is None
    assert context['signee_position'] == ''
    chief_arbiter = _account(arbiters_event, 'Chief')
    context = _arbiter_norm_report(
        arbiters_event,
        **{
            'arbiter-norm-candidate': str(candidate.id),
            'arbiter-norm-signee': str(chief_arbiter.id),
        },
    )
    assert context['signee'] == chief_arbiter
    assert context['signee_position'] == 'Chief Arbiter'


@pytest.mark.unit
def test_arbiter_norm_report_requires_a_candidate(arbiters_event: Event):
    tournament = arbiters_event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(
        arbiters_event,
        documents.ArbiterNormReportPrintDocument,
        {'tournaments': str(tournament.id)},
    )
    with pytest.raises(OptionError):
        document.validate_options()


def _pairings(event: Event, **values: str) -> documents.BoardPairingPrintDocument:
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(
        event,
        documents.BoardPairingPrintDocument,
        {'tournament': str(tournament.id), 'round': '1', **values},
    )
    assert isinstance(document, documents.BoardPairingPrintDocument)
    return document


@pytest.mark.unit
def test_pairings_are_mirrored_around_the_result(event: Event):
    roles = [column.print_role for column in _pairings(event).board_columns]
    result = next(
        index for index, role in enumerate(roles) if role.startswith('result')
    )
    assert roles[0] == 'board'
    assert roles[1] == 'points'
    assert roles[-1] == 'points'
    assert 'name' in roles[:result]
    assert 'name' in roles[result + 1 :]
    assert 'points' not in roles[2:-1]


@pytest.mark.unit
def test_pairings_leave_space_for_the_results_when_asked(event: Event):
    compact = _pairings(event)
    spaced = _pairings(event, **{'result-space': 'on'})
    assert PairingResultColumn in [type(column) for column in compact.board_columns]
    assert WrittenResultColumn in [type(column) for column in spaced.board_columns]
    assert compact.table_classes == ''
    assert spaced.table_classes == 'result-space'


@pytest.mark.unit
def test_pairings_show_a_dash_until_the_result_is_known(playing_event: Event):
    tournament = playing_event.tournaments_by_name[TOURNAMENT_NAME]
    document = _build(
        playing_event,
        documents.BoardPairingPrintDocument,
        {'tournament': str(tournament.id), 'round': str(tournament.rounds)},
    )
    assert isinstance(document, documents.BoardPairingPrintDocument)
    column = PairingResultColumn(ColumnUsage.PRINT)
    cells = {column.get_cell_content(board) for board in document.boards}
    assert '–' in cells
    assert cells - {'–'}


@pytest.mark.unit
def test_pairings_print_the_title_columns_only_when_a_player_has_a_title(
    event: Event,
):
    document = _pairings(event)
    has_titles = any(
        player.display_title
        for board in document.boards
        for player in (
            board.optional_white_tournament_player,
            board.black_tournament_player,
        )
        if player is not None
    )
    printed = any(column.print_role == 'title' for column in document.board_columns)
    assert printed == has_titles


@pytest.mark.unit
def test_pages_have_a_footer_except_the_cards(event: Event):
    tournament = event.tournaments_by_name[TOURNAMENT_NAME]
    values = {'tournament': str(tournament.id), 'round': '1'}
    pairings = _build(event, documents.BoardPairingPrintDocument, values)
    footer = pairings.page_footer_css
    assert footer is not None
    assert 'counter(page)' in footer
    assert 'counter(pages)' in footer
    for document_type in (
        documents.PlaceCardPrintDocument,
        documents.QRCodePrintDocument,
    ):
        assert _build(event, document_type, values).page_footer_css is None


@pytest.mark.unit
def test_css_strings_escape_quotes_and_backslashes():
    assert css_string('Open "A" \\ 2026') == '"Open \\000022A\\000022 \\00005c 2026"'
    assert page_number_content() == ('"Page " counter(page) " of " counter(pages)')
