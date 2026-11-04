"""The websocket messages that tell the pages which check-ins and results
changed."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from litestar.channels import ChannelsPlugin

from data.board import Board
from data.tournament import Tournament
from web.controllers.admin.pairings_admin_controller import PairingsAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController


class _Channels:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def publish(self, message: dict[str, Any], channels: list[str]) -> None:
        assert channels == ['ws']
        self.messages.append(message)


def _tournament() -> Tournament:
    return cast(
        Tournament, SimpleNamespace(id=3, event=SimpleNamespace(uniq_id='open'))
    )


@pytest.mark.unit
def test_a_check_in_names_its_players() -> None:
    channels = _Channels()
    PlayerAdminController.publish_new_checkin(
        cast(ChannelsPlugin, channels), _tournament(), {12, 4}
    )
    assert channels.messages == [
        {'event': 'new-checkins|open', 'data': {'detail': {'player_ids': [4, 12]}}},
        {'event': 'new-checkins|open|3', 'data': {'detail': {'player_ids': [4, 12]}}},
    ]


@pytest.mark.unit
def test_a_check_in_of_unknown_players_names_none() -> None:
    channels = _Channels()
    PlayerAdminController.publish_new_checkin(
        cast(ChannelsPlugin, channels), _tournament(), None
    )
    assert [message['data'] for message in channels.messages] == ['', '']


@pytest.mark.unit
def test_a_result_names_its_boards_and_their_players() -> None:
    channels = _Channels()
    boards = [
        cast(
            Board, SimpleNamespace(identifier=9, white_player_id=5, black_player_id=2)
        ),
        cast(
            Board,
            SimpleNamespace(identifier=7, white_player_id=8, black_player_id=None),
        ),
    ]
    PairingsAdminController.publish_new_user_results(
        cast(ChannelsPlugin, channels), 'open', 3, 2, boards
    )
    detail = {'board_ids': [7, 9], 'player_ids': [2, 5, 8]}
    assert channels.messages == [
        {'event': 'new-user-results|open|3|2', 'data': {'detail': detail}},
        {'event': 'new-user-results|open', 'data': {'detail': detail}},
    ]
