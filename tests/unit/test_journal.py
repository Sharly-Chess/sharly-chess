"""The journal of an event: what was done, when and by whom."""

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

import pytest

from data import journal
from data.event import Event
from data.journal import (
    Actor,
    Author,
    AuthorKind,
    Source,
    SourceKind,
    JournalAction,
    JournalCategory,
    UnjournaledWriteError,
    acting_as,
    author_label,
    check_journal_scope,
    end_journal_scope,
    identity_key,
    not_journaled,
    load_journal,
    load_journal_filter_options,
    parse_identity_key,
    start_journal_scope,
)
from data.loader import EventLoader
from data.snapshot import SnapshotReason, write_snapshot
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredAccount
from tests.test_config import TestUtils
from utils.enum import Result

EVENT_ID = 'test-journal-event'
TOURNAMENT_ID = 'test-journal-tournament'


@pytest.mark.unit
class JournalTestCase(TestCase):
    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    @property
    def tournament(self):
        # The tournament keeps only a weak reference to its event.
        self._event: Event = EventLoader().load_event(EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def _played_board(self):
        return next(
            board
            for board in self.tournament.get_round_boards(1)
            if board.black_tournament_player is not None and board.result == Result.WIN
        )

    def test_a_changed_result_is_recorded_with_the_former_one(self):
        board = self._played_board()
        white = board.white_tournament_player.full_name
        board.tournament.add_result(board, Result.DRAW)

        [entry] = load_journal(EVENT_ID)
        self.assertEqual(entry.action, JournalAction.RESULT_CHANGED)
        self.assertEqual(entry.category, JournalCategory.RESULTS)
        self.assertEqual(entry.round, 1)
        self.assertEqual(entry.board_id, board.id)
        self.assertEqual(entry.tournament_name, TOURNAMENT_ID)
        self.assertIn(white, entry.sentence)
        self.assertIn('1-0', entry.sentence)
        self.assertIn('½-½', entry.sentence)

    def test_a_cleared_then_entered_result_gives_two_entries(self):
        board = self._played_board()
        board.tournament.delete_result(board)
        board = next(b for b in self.tournament.get_round_boards(1) if b.id == board.id)
        board.tournament.add_result(board, Result.LOSS)

        actions = [entry.action for entry in load_journal(EVENT_ID)]
        self.assertEqual(
            actions, [JournalAction.RESULT_ENTERED, JournalAction.RESULT_CLEARED]
        )

    def test_an_unchanged_result_is_not_recorded(self):
        board = self._played_board()
        board.tournament.add_result(board, Result.WIN)

        self.assertEqual(load_journal(EVENT_ID), [])

    def test_the_author_is_kept_by_name(self):
        board = self._played_board()
        with acting_as(
            Actor(
                Author(AuthorKind.ACCOUNT, 42),
                Source(SourceKind.NETWORK, host='10.0.0.5'),
            )
        ):
            board.tournament.add_result(board, Result.DRAW)

        [entry] = load_journal(EVENT_ID)
        self.assertEqual(entry.author, Author(AuthorKind.ACCOUNT, 42))
        self.assertEqual(entry.source.kind, SourceKind.NETWORK)
        self.assertEqual(entry.host, '10.0.0.5')

    def test_without_an_author_the_application_acted(self):
        board = self._played_board()
        board.tournament.add_result(board, Result.DRAW)

        [entry] = load_journal(EVENT_ID)
        self.assertIsNone(entry.author)
        self.assertEqual(entry.source.kind, SourceKind.APPLICATION)

    def test_an_entry_goes_with_the_write_it_is_part_of(self):
        with pytest.raises(RuntimeError), EventDatabase(EVENT_ID, write=True):
            journal.record(EVENT_ID, JournalAction.TIE_BREAKS_CHANGED)
            raise RuntimeError

        self.assertEqual(load_journal(EVENT_ID), [])

        with EventDatabase(EVENT_ID, write=True):
            journal.record(EVENT_ID, JournalAction.TIE_BREAKS_CHANGED)

        self.assertEqual(len(load_journal(EVENT_ID)), 1)

    def test_a_suppressed_journal_records_nothing(self):
        board = self._played_board()
        with not_journaled('a test'):
            board.tournament.add_result(board, Result.DRAW)

        self.assertEqual(load_journal(EVENT_ID), [])

    def test_a_note_reads_as_its_text(self):
        journal.record(EVENT_ID, JournalAction.NOTE, text='Appeal on board 3')

        [entry] = load_journal(EVENT_ID)
        self.assertTrue(entry.is_note)
        self.assertEqual(entry.text, 'Appeal on board 3')

    def test_an_unknown_action_reads_as_its_text(self):
        journal.record(EVENT_ID, 'some_plugin_action', text='Uploaded somewhere')

        [entry] = load_journal(EVENT_ID)
        self.assertIsNone(entry.action)
        self.assertEqual(entry.sentence, 'Uploaded somewhere')

    def test_a_missing_value_does_not_break_the_sentence(self):
        journal.record(EVENT_ID, JournalAction.RESULT_CHANGED, data={'board': 3})

        [entry] = load_journal(EVENT_ID)
        self.assertIn('?', entry.sentence)


UNPAIRED_EVENT_ID = 'test-journal-unpaired-event'


@pytest.mark.unit
class JournalActionsTestCase(TestCase):
    """The actions journaled by the tournament, the event and the backups."""

    def setUp(self) -> None:
        TestUtils.create_event(UNPAIRED_EVENT_ID)
        TestUtils.create_tournament(
            UNPAIRED_EVENT_ID,
            TOURNAMENT_ID,
            json_file='tec-swiss-unpaired',
            overrides={'record_illegal_moves': 2},
        )

    def tearDown(self) -> None:
        TestUtils.delete_event(UNPAIRED_EVENT_ID)

    @property
    def tournament(self):
        EventLoader.unload_event(UNPAIRED_EVENT_ID)
        self._event: Event = EventLoader().load_event(UNPAIRED_EVENT_ID)
        return self._event.tournaments_by_name[TOURNAMENT_ID]

    def actions(self) -> list[JournalAction | None]:
        return [entry.action for entry in load_journal(UNPAIRED_EVENT_ID)]

    def test_a_bye_given_then_removed(self):
        tournament = self.tournament
        player = tournament.sorted_tournament_players[0]
        tournament.set_player_byes(player, {1: Result.HALF_POINT_BYE})
        tournament = self.tournament
        player = tournament.tournament_players_by_id[player.id]
        tournament.set_player_byes(player, {1: Result.NO_RESULT})

        removed, given = load_journal(UNPAIRED_EVENT_ID)
        self.assertEqual(given.action, JournalAction.BYE_SET)
        self.assertEqual(removed.action, JournalAction.BYE_REMOVED)
        self.assertIn(player.full_name, removed.sentence)
        self.assertEqual(removed.player_id, player.id)
        self.assertEqual(removed.round, 1)

    def test_a_check_in_is_journaled_only_when_it_changes(self):
        tournament = self.tournament
        player = tournament.sorted_tournament_players[0]
        tournament.check_in_player(player, not player.check_in)
        tournament.check_in_player(player, player.check_in)

        self.assertEqual(len(load_journal(UNPAIRED_EVENT_ID)), 1)

    def test_pairing_and_publishing_a_round(self):
        tournament = self.tournament
        self.assertEqual(tournament.generate_round_pairings(1), '')
        self.tournament.set_published_round(1)
        self.tournament.set_published_round(0)

        self.assertEqual(
            self.actions(),
            [
                JournalAction.ROUND_UNPUBLISHED,
                JournalAction.ROUND_PUBLISHED,
                JournalAction.ROUND_PAIRED,
            ],
        )

    def test_swapped_colours_name_the_new_white(self):
        self.tournament.generate_round_pairings(1)
        board = next(
            board
            for board in self.tournament.get_round_boards(1)
            if board.black_tournament_player is not None
        )
        black = board.black_tournament_player.full_name
        board.permute_colors()

        entry = load_journal(UNPAIRED_EVENT_ID)[0]
        self.assertEqual(entry.action, JournalAction.COLOURS_SWAPPED)
        self.assertEqual(entry.stored.data['white'], black)

    def test_a_renamed_player_keeps_the_old_name(self):
        event = self.tournament.event
        player = self.tournament.sorted_tournament_players[0]
        old_name = player.full_name
        stored_player = replace(player.stored_player, last_name='RENAMED')
        event.update_player(player, stored_player)

        [entry] = load_journal(UNPAIRED_EVENT_ID)
        self.assertEqual(entry.action, JournalAction.PLAYER_RENAMED)
        self.assertIn(old_name, entry.sentence)
        self.assertIn('RENAMED', entry.sentence)

    def test_a_deleted_player_is_still_named(self):
        event = self.tournament.event
        player = self.tournament.sorted_tournament_players[0]
        name = player.full_name
        event.delete_player(player)

        [entry] = load_journal(UNPAIRED_EVENT_ID)
        self.assertEqual(entry.action, JournalAction.PLAYER_DELETED)
        self.assertIn(name, entry.sentence)

    def test_a_penalty_is_journaled_with_its_reason(self):
        tournament = self.tournament
        player = tournament.sorted_tournament_players[0]
        with EventDatabase(UNPAIRED_EVENT_ID, write=True) as database:
            tournament.point_adjustments.set_manual_for_player(
                player.id, 1, -1.0, 'Phone rang', database
            )
            tournament.point_adjustments.set_manual_for_player(
                player.id, 1, -1.0, 'Phone rang', database
            )

        [entry] = load_journal(UNPAIRED_EVENT_ID)
        self.assertEqual(entry.action, JournalAction.POINT_ADJUSTMENT)
        self.assertIn('-1', entry.sentence)
        self.assertEqual(entry.text, 'Phone rang')

    def test_an_illegal_move_names_the_player_and_the_count(self):
        tournament = self.tournament
        tournament.generate_round_pairings(1)
        tournament = self.tournament
        player = next(
            player
            for player in tournament.sorted_tournament_players
            if not player.pairings[1].unpaired
        )
        tournament.store_illegal_move(player)

        entry = load_journal(UNPAIRED_EVENT_ID)[0]
        self.assertEqual(entry.action, JournalAction.ILLEGAL_MOVE_ADDED)
        self.assertIn(player.full_name, entry.sentence)
        self.assertEqual(entry.stored.data['count'], 1)

    def test_leaving_fide_mode(self):
        self.tournament.leave_fide_mode()

        self.assertEqual(self.actions(), [JournalAction.FIDE_MODE_LEFT])

    def test_pairing_settings_changed_only_when_they_change(self):
        tournament = self.tournament
        settings = dict(tournament.stored_pairing_settings)
        tournament.update_pairing_settings(settings)
        self.assertEqual(self.actions(), [])

        tournament.update_pairing_settings(settings | {'test': 1})
        self.assertEqual(self.actions(), [JournalAction.PAIRING_SETTINGS_CHANGED])

    def test_a_staff_account_and_its_access(self):
        event = self.tournament.event
        account = event.create_account(
            StoredAccount(id=None, active=True, first_name='Jane', last_name='ARBITER')
        )

        actions = self.actions()
        self.assertEqual(actions[0], JournalAction.ACCOUNT_CREATED)
        self.assertIn('ARBITER', load_journal(UNPAIRED_EVENT_ID)[0].sentence)
        event.delete_account(account)
        self.assertEqual(self.actions()[0], JournalAction.ACCOUNT_DELETED)

    def test_a_restored_backup_rewinds_the_journal_and_says_so(self):
        snapshot = write_snapshot(UNPAIRED_EVENT_ID, SnapshotReason.MANUAL)
        self.tournament.generate_round_pairings(1)

        snapshot.restore_in_place()

        self.assertEqual(self.actions(), [JournalAction.SNAPSHOT_RESTORED])

    def test_an_imported_tournament_journals_nothing_of_its_own(self):
        self.assertEqual(load_journal(UNPAIRED_EVENT_ID), [])


@pytest.mark.unit
class JournalReadingTestCase(TestCase):
    """The journal grows with the event, so it is read only by its page, and
    only as much of it as the page shows."""

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')
        EventLoader.unload_event(EVENT_ID)
        self._event: Event = EventLoader().load_event(EVENT_ID)
        self.tournament = self._event.tournaments_by_name[TOURNAMENT_ID]
        with acting_as(
            Actor(
                Author(AuthorKind.ACCOUNT, 7),
                Source(SourceKind.SCREEN, 'Result entry', '10.0.0.5'),
            )
        ):
            for round_ in range(1, 4):
                self.tournament.record(JournalAction.ROUND_PAIRED, round_)
        journal.record(EVENT_ID, JournalAction.NOTE, text='A remark')

    def tearDown(self) -> None:
        TestUtils.delete_event(EVENT_ID)

    def test_opening_an_event_does_not_read_the_journal(self):
        queries: list[str] = []
        execute = EventDatabase.execute

        def recording_execute(database, query, params=()):
            queries.append(query)
            return execute(database, query, params)

        EventLoader.unload_event(EVENT_ID)
        with patch.object(EventDatabase, 'execute', recording_execute):
            EventLoader().load_event(EVENT_ID)

        self.assertTrue(queries)
        self.assertFalse([query for query in queries if '`journal`' in query])

    def test_the_filters_and_the_limit_are_applied_by_the_database(self):
        rounds = load_journal(EVENT_ID, category=JournalCategory.PAIRINGS, limit=2)
        self.assertEqual([entry.round for entry in rounds], [3, 2])

        notes = load_journal(EVENT_ID, category=JournalCategory.NOTES)
        self.assertEqual([entry.text for entry in notes], ['A remark'])

        by_jane = load_journal(EVENT_ID, author=('account', 7, None))
        self.assertEqual(len(by_jane), 3)

        from_the_screen = load_journal(
            EVENT_ID, source=('screen', 'Result entry', None)
        )
        self.assertEqual(len(from_the_screen), 3)
        by_nobody = load_journal(EVENT_ID, author=(None, None, None))
        self.assertEqual([entry.text for entry in by_nobody], ['A remark'])

        of_the_tournament = load_journal(EVENT_ID, tournament_id=self.tournament.id)
        self.assertEqual(len(of_the_tournament), 3)

    def test_the_filters_offer_only_what_the_journal_holds(self):
        options = load_journal_filter_options(EVENT_ID)

        self.assertTrue(options.has_entries)
        self.assertEqual(options.tournament_names, {self.tournament.id: TOURNAMENT_ID})
        self.assertEqual(
            options.categories, [JournalCategory.PAIRINGS, JournalCategory.NOTES]
        )
        self.assertIn(('account', 7, None), options.authors)
        self.assertIn((None, None, None), options.authors)
        self.assertIn(('screen', 'Result entry', None), options.sources)
        self.assertIn(('application', None, None), options.sources)

    def test_an_account_is_named_as_it_is_called_now(self):
        author = Author(AuthorKind.ACCOUNT, 7)
        self.assertEqual(author_label(author, 'Jane SMITH'), 'Jane SMITH')
        self.assertEqual(author_label(None), '—')

    def test_a_deleted_account_is_named_by_the_entry_of_its_deletion(self):
        event = self.tournament.event
        account = event.create_account(
            StoredAccount(id=None, active=True, first_name='Jane', last_name='GONE')
        )
        event.delete_account(account)

        with EventDatabase(EVENT_ID) as database:
            names = database.load_journal_deleted_account_names()
        self.assertEqual(names, {account.id: account.full_name})

    def test_an_author_key_reads_back(self):
        actor = ('account', 7, 'Jane Arbiter')
        self.assertEqual(parse_identity_key(identity_key(actor)), actor)
        self.assertIsNone(parse_identity_key('not json'))


@pytest.mark.unit
class JournalCheckTestCase(TestCase):
    """An operation that changes the event journals it, or says why not."""

    def setUp(self) -> None:
        TestUtils.create_event(EVENT_ID)
        TestUtils.create_tournament(EVENT_ID, TOURNAMENT_ID, json_file='tec-swiss')

    def tearDown(self) -> None:
        end_journal_scope()
        TestUtils.delete_event(EVENT_ID)

    def _rename_tournament(self, name: str) -> None:
        with EventDatabase(EVENT_ID, write=True) as database:
            database.execute('UPDATE `tournament` SET `name` = ?', (name,))

    def test_every_action_has_a_category_and_a_sentence(self):
        for action in JournalAction:
            self.assertIsInstance(action.category, JournalCategory)
            self.assertIsInstance(action.sentence({}), str)

    def test_a_change_left_out_of_the_journal_is_refused(self):
        scope = start_journal_scope('test')
        self._rename_tournament('Renamed')

        self.assertEqual(
            scope.unjournaled_writes(), {EVENT_ID: {('tournament', 'name')}}
        )
        with pytest.raises(UnjournaledWriteError):
            check_journal_scope(scope)

    def test_a_journaled_change_passes(self):
        scope = start_journal_scope('test')
        self._rename_tournament('Renamed')
        journal.record(EVENT_ID, JournalAction.TOURNAMENT_RENAMED)

        check_journal_scope(scope)

    def test_a_change_said_not_to_be_journaled_passes(self):
        scope = start_journal_scope('test')
        with not_journaled('a test'):
            self._rename_tournament('Renamed')

        check_journal_scope(scope)

    def test_a_value_written_again_is_no_change(self):
        with EventDatabase(EVENT_ID) as database:
            database.execute('SELECT `name` FROM `tournament`')
            name = database.fetchone()['name']
        scope = start_journal_scope('test')
        self._rename_tournament(name)

        check_journal_scope(scope)

    def test_bookkeeping_columns_need_no_entry(self):
        scope = start_journal_scope('test')
        with EventDatabase(EVENT_ID, write=True) as database:
            database.execute("UPDATE `info` SET `plugin_data` = '{}'")

        check_journal_scope(scope)
