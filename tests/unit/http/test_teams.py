"""Entering teams in a team event, over HTTP."""

from collections.abc import Iterator

import pytest
from litestar.testing import TestClient

from data.pairings.variations import StandardTeamSwissVariation
from data.tournament import Tournament
from tests.unit.http.events import EventUnderTest
from utils.enum import EventType

EVENT_ID = 'test-teams-http'
TOURNAMENT_NAME = 'test-teams-http-tournament'
TEAM_SIZE = 2

EVENT = EventUnderTest(EVENT_ID, TOURNAMENT_NAME)


@pytest.fixture
def tournament() -> Iterator[Tournament]:
    EVENT.create(
        event={'event_type': EventType.TEAM},
        tournament={
            'pairing': StandardTeamSwissVariation.static_id(),
            'team_player_count': TEAM_SIZE,
            'rounds': 3,
        },
    )
    yield EVENT.tournament()
    EVENT.delete()


def create_team(http: TestClient, tournament: Tournament, **fields: str):
    return http.post(
        f'/team-create/{EVENT_ID}',
        data={'name': 'A team', 'tournament_id': str(tournament.id)} | fields,
    )


def team_names() -> list[str]:
    return [team.name for team in EVENT.tournament().teams]


@pytest.mark.unit
def test_a_team_needs_a_name(http: TestClient, tournament: Tournament):
    response = create_team(http, tournament, name='')
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert team_names() == []


@pytest.mark.unit
def test_a_team_joins_a_tournament_that_exists(
    http: TestClient, tournament: Tournament
):
    response = create_team(http, tournament, tournament_id='999')
    assert response.status_code == 200
    assert 'Unknown tournament.' in response.text
    assert team_names() == []


@pytest.mark.unit
def test_a_captain_from_outside_the_roster_is_named(
    http: TestClient, tournament: Tournament
):
    """A captain who does not play is typed in rather than chosen, so
    the name is what there is to record."""
    response = create_team(http, tournament, captain='other', captain_name=' ')
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert team_names() == []


@pytest.mark.unit
def test_a_team_the_form_accepts_joins_the_tournament(
    http: TestClient, tournament: Tournament
):
    response = create_team(http, tournament)
    assert response.status_code == 200
    assert team_names() == ['A team']
    assert next(iter(EVENT.tournament().teams)).tournament_id == tournament.id


def team_id(name: str = 'A team') -> int:
    identifier = next(team.id for team in EVENT.tournament().teams if team.name == name)
    assert identifier is not None
    return identifier


@pytest.mark.unit
def test_a_team_group_is_named_once(http: TestClient, tournament: Tournament):
    """Groups keep teams of one club apart in the pairing, so two of them
    under one name would say nothing."""
    assert (
        http.post(
            f'/team-group/add/{EVENT_ID}', data={'team_group_name': 'Clubs'}
        ).status_code
        == 200
    )
    assert [group.name for group in EVENT.tournament().event.team_groups] == ['Clubs']
    response = http.post(
        f'/team-group/add/{EVENT_ID}', data={'team_group_name': 'Clubs'}
    )
    assert response.status_code == 200
    assert 'This name is already used.' in response.text
    assert [group.name for group in EVENT.tournament().event.team_groups] == ['Clubs']


@pytest.mark.unit
def test_a_team_group_needs_a_name(http: TestClient, tournament: Tournament):
    response = http.post(f'/team-group/add/{EVENT_ID}', data={'team_group_name': ' '})
    assert response.status_code == 200
    assert 'This field is required.' in response.text
    assert list(EVENT.tournament().event.team_groups) == []


@pytest.mark.unit
def test_a_team_group_is_renamed_and_deleted(http: TestClient, tournament: Tournament):
    http.post(f'/team-group/add/{EVENT_ID}', data={'team_group_name': 'Clubs'})
    group_id = next(iter(EVENT.tournament().event.team_groups)).id
    renamed = http.patch(
        f'/team-group/update/{EVENT_ID}/{group_id}',
        data={'team_group_name': 'Schools'},
    )
    assert renamed.status_code == 200
    assert [group.name for group in EVENT.tournament().event.team_groups] == ['Schools']
    deleted = http.delete(f'/team-group/delete/{EVENT_ID}/{group_id}')
    assert deleted.status_code == 200
    assert list(EVENT.tournament().event.team_groups) == []


@pytest.mark.unit
def test_checking_a_team_in_and_out(http: TestClient, tournament: Tournament):
    """A team is checked in as a whole, and the button is the same one
    either way."""
    create_team(http, tournament)
    identifier = team_id()
    before = next(
        team for team in EVENT.tournament().teams if team.id == identifier
    ).check_in
    assert (
        http.patch(f'/team-toggle-check-in/{EVENT_ID}/{identifier}').status_code == 200
    )
    toggled = next(team for team in EVENT.tournament().teams if team.id == identifier)
    assert toggled.check_in is not before
    assert (
        http.patch(f'/team-toggle-check-in/{EVENT_ID}/{identifier}').status_code == 200
    )
    assert (
        next(
            team for team in EVENT.tournament().teams if team.id == identifier
        ).check_in
        is before
    )


@pytest.mark.unit
def test_a_roster_takes_the_players_chosen(http: TestClient, tournament: Tournament):
    """Players are entered into the event first and put on a roster
    afterwards, several at a time."""
    create_team(http, tournament)
    identifier = team_id()
    for name in ('First', 'Second'):
        assert (
            http.post(
                f'/player-create/{EVENT_ID}',
                data={
                    'federation': 'FRA',
                    'gender': '',
                    'title': '',
                    'team_id': str(identifier),
                    'last_name': name,
                },
            ).status_code
            == 200
        )
    roster = [
        player.last_name
        for player in EVENT.tournament().teams_by_id[identifier].players
    ]
    assert sorted(roster) == ['FIRST', 'SECOND']


@pytest.mark.unit
def test_a_roster_addition_with_nobody_chosen_adds_nobody(
    http: TestClient, tournament: Tournament
):
    """The roster modal submits whatever is ticked, and nothing ticked is
    the state it opens in."""
    create_team(http, tournament)
    identifier = team_id()
    response = http.post(
        f'/team-add-player/{EVENT_ID}/{identifier}', data={'player_id': ''}
    )
    assert response.status_code == 200
    assert list(EVENT.tournament().teams_by_id[identifier].players) == []


TEAM_COUNT = 4


@pytest.fixture
def paired(http: TestClient, tournament: Tournament) -> Iterator[Tournament]:
    """Four teams of two, checked in and paired for round one — the state
    the pairings tab is in once a team event starts."""
    for index in range(TEAM_COUNT):
        name = f'Team {index + 1}'
        assert create_team(http, tournament, name=name).status_code == 200
        identifier = team_id(name)
        for board in range(TEAM_SIZE):
            assert (
                http.post(
                    f'/player-create/{EVENT_ID}',
                    data={
                        'federation': 'FRA',
                        'gender': '',
                        'title': '',
                        'team_id': str(identifier),
                        'last_name': f'Player {index + 1}.{board + 1}',
                    },
                ).status_code
                == 200
            )
        if not EVENT.tournament().teams_by_id[identifier].check_in:
            assert (
                http.patch(f'/team-toggle-check-in/{EVENT_ID}/{identifier}').status_code
                == 200
            )
    assert (
        http.post(f'/pairings/generate/{EVENT_ID}/{tournament.id}/1').status_code == 200
    )
    yield EVENT.tournament()


@pytest.mark.unit
def test_a_team_round_is_paired_into_matches(paired: Tournament):
    """Every team plays, and each match seats one board per player of the
    smaller roster."""
    team_boards = paired.get_round_team_boards(1)
    assert len(team_boards) == TEAM_COUNT // 2
    playing = {
        team_id_
        for team_board in team_boards
        for team_id_ in (
            team_board.stored_team_board.team_a_id,
            team_board.stored_team_board.team_b_id,
        )
    }
    assert playing == {team.id for team in paired.teams}
    for team_board in team_boards:
        assert len(team_board.boards) == TEAM_SIZE


@pytest.mark.unit
@pytest.mark.parametrize('modal', ['team-absents-modal', 'absents-modal'])
def test_the_absence_modals_open_for_a_team_event(
    http: TestClient, paired: Tournament, modal: str
):
    response = http.get(f'/pairings/{modal}/{EVENT_ID}/{paired.id}/1')
    assert response.status_code == 200


@pytest.mark.unit
def test_marking_every_team_present_leaves_none_out(
    http: TestClient, paired: Tournament
):
    identifier = team_id('Team 1')
    assert (
        http.patch(f'/team-toggle-check-in/{EVENT_ID}/{identifier}').status_code == 200
    )
    assert not EVENT.tournament().teams_by_id[identifier].check_in
    response = http.post(f'/pairings/set-all-teams-present/{EVENT_ID}/{paired.id}/1')
    assert response.status_code == 200
    assert all(team.check_in for team in EVENT.tournament().teams)


@pytest.mark.unit
def test_a_team_is_given_bonus_match_points(http: TestClient, paired: Tournament):
    identifier = team_id('Team 1')
    response = http.patch(
        f'/team-point-adjustment/{EVENT_ID}/{paired.id}/1/{identifier}',
        data={'mp': '1', 'gp': '0.5', 'reason': 'Opponent arrived late'},
    )
    assert response.status_code == 200
    assert EVENT.tournament().manual_point_adjustment(identifier, 1) == (1.0, 0.5)


@pytest.mark.unit
def test_a_team_match_is_unpaired_on_its_own(http: TestClient, paired: Tournament):
    team_board = paired.get_round_team_boards(1)[0]
    response = http.delete(
        f'/team-pairing/unpair/{EVENT_ID}/{paired.id}/1/{team_board.id}'
    )
    assert response.status_code == 200
    remaining = EVENT.tournament().get_round_team_boards(1)
    assert len(remaining) == TEAM_COUNT // 2 - 1
