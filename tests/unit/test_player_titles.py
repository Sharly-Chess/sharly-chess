"""`Player.strongest_title` and `Player.display_title` — the open/women
title split. `strongest_title` is the single most prestigious title (used
for imports/exports/sorting/logic); `display_title` is the human-readable
string that shows the women title alongside the open one unless the open
title outranks it on the combined FIDE ladder."""

import pytest

from common import SharlyChessException
from data.board import PlayerRatingType
from data.columns.player_datasheet import TitleColumn, WomenTitleColumn
from data.event import Event
from database.sqlite.event.event_store import StoredEvent, StoredPlayer
from utils.enum import PlayerTitle, TitleNorm


def _player(title: str = '', women_title: str = ''):
    event = Event(
        StoredEvent(
            uniq_id='title-test',
            name='Title test',
            federation='FRA',
            player_rating_type=PlayerRatingType.FIDE.value,
            enabled_plugins=[],
            stored_players=[
                StoredPlayer(id=1, last_name='X', title=title, women_title=women_title)
            ],
        )
    )
    return event.players_by_id[1]


class TestStrongestTitle:
    def test_open_only(self):
        assert _player(title='FM').strongest_title == PlayerTitle.FIDE_MASTER

    def test_women_only(self):
        assert (
            _player(women_title='WIM').strongest_title
            == PlayerTitle.WOMAN_INTERNATIONAL_MASTER
        )

    def test_both_returns_higher_rank(self):
        # sort_index ranks FM (5) above WIM (4).
        assert (
            _player(title='FM', women_title='WIM').strongest_title
            == PlayerTitle.FIDE_MASTER
        )

    def test_none(self):
        assert _player().strongest_title == PlayerTitle.NONE


class TestDisplayTitle:
    def test_open_only(self):
        assert _player(title='GM').display_title == PlayerTitle.GRANDMASTER.short_name

    def test_women_only(self):
        assert (
            _player(women_title='WGM').display_title
            == PlayerTitle.WOMAN_GRANDMASTER.short_name
        )

    def test_gm_hides_wgm(self):
        assert (
            _player(title='GM', women_title='WGM').display_title
            == PlayerTitle.GRANDMASTER.short_name
        )

    def test_im_hides_wim(self):
        assert (
            _player(title='IM', women_title='WIM').display_title
            == PlayerTitle.INTERNATIONAL_MASTER.short_name
        )

    def test_fm_and_wim_shown_together(self):
        # FM does not supersede WIM (same FIDE tier) — both shown, because
        # a WIM confers benefits (e.g. tournament entry) an FM does not.
        expected = (
            f'{PlayerTitle.FIDE_MASTER.short_name}'
            f'/{PlayerTitle.WOMAN_INTERNATIONAL_MASTER.short_name}'
        )
        assert _player(title='FM', women_title='WIM').display_title == expected

    def test_cm_and_wim_shown_together(self):
        # WIM outranks CM, so it is never hidden.
        expected = (
            f'{PlayerTitle.CANDIDATE_MASTER.short_name}'
            f'/{PlayerTitle.WOMAN_INTERNATIONAL_MASTER.short_name}'
        )
        assert _player(title='CM', women_title='WIM').display_title == expected

    def test_none_is_empty(self):
        assert _player().display_title == ''


class TestTitleOnNormLadder:
    """`Player.title_on_norm_ladder` — open and women titles are separate
    ladders, so a women norm is measured against the women title and an open
    norm against the open title. This is what lets a player who holds only a
    women title (or only an open one) be evaluated correctly for norms."""

    def test_fm_woman_has_no_women_ladder_title(self):
        # FM, no women title: women norms see NONE (so WIM/WGM are still
        # ahead of her), open norms see FM.
        player = _player(title='FM')
        assert player.title_on_norm_ladder(TitleNorm.WIM) == PlayerTitle.NONE
        assert player.title_on_norm_ladder(TitleNorm.WGM) == PlayerTitle.NONE
        assert player.title_on_norm_ladder(TitleNorm.IM) == PlayerTitle.FIDE_MASTER
        assert player.title_on_norm_ladder(TitleNorm.GM) == PlayerTitle.FIDE_MASTER

    def test_wgm_woman_has_no_open_ladder_title(self):
        # WGM, no open title: women norms see WGM, open norms see NONE.
        player = _player(women_title='WGM')
        assert (
            player.title_on_norm_ladder(TitleNorm.WIM) == PlayerTitle.WOMAN_GRANDMASTER
        )
        assert player.title_on_norm_ladder(TitleNorm.IM) == PlayerTitle.NONE

    def test_dual_titled_uses_each_ladder(self):
        # IM + WIM: women norms see WIM, open norms see IM.
        player = _player(title='IM', women_title='WIM')
        assert (
            player.title_on_norm_ladder(TitleNorm.WIM)
            == PlayerTitle.WOMAN_INTERNATIONAL_MASTER
        )
        assert (
            player.title_on_norm_ladder(TitleNorm.IM)
            == PlayerTitle.INTERNATIONAL_MASTER
        )


class TestDatasheetTitleColumns:
    """The open-title datasheet column accepts a women title and routes it to
    the women field instead of rejecting it; the women-title column still only
    accepts women titles."""

    def test_open_column_sets_open_title(self):
        stored = StoredPlayer(id=1)
        TitleColumn()._augment_stored_player(stored, 'IM')
        assert stored.title == 'IM'
        assert stored.women_title == ''

    def test_open_column_routes_women_title_to_women_field(self):
        stored = StoredPlayer(id=1)
        TitleColumn()._augment_stored_player(stored, 'WIM')
        assert stored.title == ''
        assert stored.women_title == 'WIM'

    def test_open_column_rejects_unknown_value(self):
        with pytest.raises(SharlyChessException):
            TitleColumn()._augment_stored_player(StoredPlayer(id=1), 'ZZ')

    def test_women_column_sets_women_title(self):
        stored = StoredPlayer(id=1)
        WomenTitleColumn()._augment_stored_player(stored, 'WGM')
        assert stored.women_title == 'WGM'

    def test_women_column_rejects_open_title(self):
        with pytest.raises(SharlyChessException):
            WomenTitleColumn()._augment_stored_player(StoredPlayer(id=1), 'IM')


class TestFideTier:
    def test_open_outranks_lower_women(self):
        assert (
            PlayerTitle.GRANDMASTER.fide_tier > PlayerTitle.WOMAN_GRANDMASTER.fide_tier
        )
        assert (
            PlayerTitle.INTERNATIONAL_MASTER.fide_tier
            > PlayerTitle.WOMAN_INTERNATIONAL_MASTER.fide_tier
        )

    def test_fm_and_wim_are_equal_tier(self):
        assert (
            PlayerTitle.FIDE_MASTER.fide_tier
            == PlayerTitle.WOMAN_INTERNATIONAL_MASTER.fide_tier
        )
