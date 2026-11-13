"""The columns of the ranking screens can be hidden one by one: the rating,
the player properties, their origin (including the columns contributed by
plugins) and the tie-breaks."""

from unittest import TestCase

import pytest

from data.columns import player_table as pt
from data.columns.column import ColumnUsage
from data.columns.handlers import PlayerColumnHandler
from data.loader import EventLoader
from data.screens.manager import ScreenTypeManager
from data.screens.screen_types import RankingScreenType
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from tests.test_config import TestUtils

EVENT_ID = 'test-ranking-screen-columns-event'
TOURNAMENT_ID = 'test-ranking-screen-columns-tournament'


@pytest.mark.unit
class RankingScreenColumnsTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID)
        self.event = EventLoader().load_event(EVENT_ID)
        ranking_type = ScreenTypeManager(self.event).get_object('ranking')
        assert isinstance(ranking_type, RankingScreenType)
        self.ranking_type = ranking_type

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def test_toggles_include_plugin_columns(self) -> None:
        toggles = self.ranking_type.ranking_column_toggles(self.event)
        self.assertEqual(
            list(toggles),
            [
                'rating',
                'category',
                'gender',
                'federation',
                'ffe_league',
                'club',
                pt.FIRST_TIE_BREAK_TOGGLE_ID,
                pt.OTHER_TIE_BREAKS_TOGGLE_ID,
            ],
        )

    def test_unchecked_boxes_are_hidden(self) -> None:
        field = self.ranking_type.ranking_column_field
        data = {
            self.ranking_type.ranking_columns_marker: 'on',
            field('rating'): 'on',
            field('category'): 'on',
            field('federation'): 'on',
            field(pt.FIRST_TIE_BREAK_TOGGLE_ID): 'on',
        }
        values = self.ranking_type.read_form_data(data, {}, self.event)
        self.assertEqual(
            values['ranking_hidden_columns'],
            ['gender', 'ffe_league', 'club', pt.OTHER_TIE_BREAKS_TOGGLE_ID],
        )

    def test_form_without_the_checkboxes_hides_nothing(self) -> None:
        values = self.ranking_type.read_form_data({}, {}, self.event)
        self.assertEqual(values['ranking_hidden_columns'], [])

    def test_hidden_columns_are_stored(self) -> None:
        hidden = ['club', pt.OTHER_TIE_BREAKS_TOGGLE_ID]
        with EventDatabase(EVENT_ID, write=True) as database:
            stored = database.add_stored_screen(
                StoredScreen(
                    id=None,
                    uniq_id='ranking',
                    name=None,
                    type='ranking',
                    columns=None,
                    font_size=None,
                    menu_text=None,
                    timer_id=None,
                    ranking_hidden_columns=hidden,
                )
            )
        self.assertEqual(stored.ranking_hidden_columns, hidden)

    def test_hidden_columns_are_left_out(self) -> None:
        tournament = self.event.tournaments_by_name[TOURNAMENT_ID]
        handler = PlayerColumnHandler(self.event, ColumnUsage.SCREEN)
        all_ids = [
            column.toggle_id
            for column in handler.get_player_ranking_columns(tournament)
        ]
        hidden = ['gender', 'ffe_league', pt.OTHER_TIE_BREAKS_TOGGLE_ID]
        shown_ids = [
            column.toggle_id
            for column in handler.get_player_ranking_columns(tournament, hidden)
        ]
        self.assertEqual(
            shown_ids, [toggle for toggle in all_ids if toggle not in hidden]
        )
        self.assertIn(pt.FIRST_TIE_BREAK_TOGGLE_ID, shown_ids)
        self.assertEqual(
            shown_ids.count(None),
            all_ids.count(None),
            'the rank, title and name are always shown',
        )
