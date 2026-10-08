"""`SCEPlayerSyncData.changed_sce_data`: the fields an update sends.

Sharly-Chess.com keeps every field an update leaves out, so a computer sends
only what it changed and cannot overwrite what another one changed meanwhile.
"""

import dataclasses
from typing import Any

import pytest

from plugins.ffe.utils import PlayerFFELicence
from plugins.sce.sce_data import SCEFraSchoolSyncData, SCEPlayerSyncData
from utils.enum import PlayerGender, PlayerRatingType, PlayerTitle


def sync_data(**changes: Any) -> SCEPlayerSyncData:
    base = SCEPlayerSyncData(
        tournament_id='T1',
        last_name='DOE',
        first_name='John',
        federation='FRA',
        year_of_birth=1990,
        fide_id=123456,
        title=PlayerTitle.NONE,
        club='Club A',
        rating=1800,
        rating_type=PlayerRatingType.FIDE,
        phone='0600000000',
        gender=PlayerGender.MAN,
        comment='Comment',
        check_in=False,
        national_id='A12345',
        ffe_licence=PlayerFFELicence.A,
        ffe_league='IDF',
        fra_school=SCEFraSchoolSyncData(code='0750001A', label='School A'),
    )
    return dataclasses.replace(base, **changes)


@pytest.mark.unit
class TestChangedSCEData:
    def test_identical_data_sends_nothing(self) -> None:
        assert sync_data().changed_sce_data(sync_data()) == {}

    @pytest.mark.parametrize(
        ('changes', 'expected'),
        [
            ({'last_name': 'SMITH'}, {'last_name': 'SMITH'}),
            ({'first_name': 'Jane'}, {'first_name': 'Jane'}),
            ({'first_name': None}, {'first_name': None}),
            ({'club': 'Club B'}, {'club': 'Club B'}),
            ({'club': ''}, {'club': ''}),
            ({'fide_id': None}, {'fide_id': None}),
            ({'national_id': 'B999'}, {'national_id': 'B999'}),
            ({'federation': 'GER'}, {'federation': 'GER'}),
            ({'comment': None}, {'comment': None}),
            ({'check_in': True}, {'checked_in': True}),
            ({'ffe_league': 'BRE'}, {'ffe_league': 'BRE'}),
            ({'title': PlayerTitle.CANDIDATE_MASTER}, {'title': 'CM'}),
            ({'gender': PlayerGender.WOMAN}, {'gender': 'W'}),
            ({'ffe_licence': PlayerFFELicence.B}, {'ffe_licence_type': 'B'}),
            ({'ffe_licence': PlayerFFELicence.NONE}, {'ffe_licence_type': None}),
        ],
    )
    def test_single_changed_field_is_sent_alone(
        self, changes: dict, expected: dict
    ) -> None:
        assert sync_data(**changes).changed_sce_data(sync_data()) == expected

    def test_year_of_birth_change_is_sent(self) -> None:
        changed = sync_data(year_of_birth=1985).changed_sce_data(sync_data())

        assert changed == {'year_of_birth': 1985}

    def test_tournament_change_is_reported(self) -> None:
        changed = sync_data(tournament_id='T2').changed_sce_data(sync_data())

        assert changed == {'tournament_id': 'T2'}

    def test_check_in_alone_leaves_every_other_field_out(self) -> None:
        changed = sync_data(check_in=True).changed_sce_data(sync_data())

        assert set(changed) == {'checked_in'}

    def test_several_changed_fields_are_sent_together(self) -> None:
        changed = sync_data(
            club='Club B', check_in=True, comment=None
        ).changed_sce_data(sync_data())

        assert changed == {'club': 'Club B', 'checked_in': True, 'comment': None}

    def test_rating_travels_with_its_type(self) -> None:
        changed = sync_data(rating=1850).changed_sce_data(sync_data())

        assert changed == {'rating': 1850, 'rating_type': 'F'}

    def test_rating_type_travels_with_its_rating(self) -> None:
        changed = sync_data(rating_type=PlayerRatingType.NATIONAL).changed_sce_data(
            sync_data()
        )

        assert changed == {'rating': 1800, 'rating_type': 'N'}

    def test_cleared_rating_clears_its_type(self) -> None:
        changed = sync_data(rating=None, rating_type=None).changed_sce_data(sync_data())

        assert changed == {'rating': None, 'rating_type': None}

    def test_phone_is_sent_under_both_names(self) -> None:
        changed = sync_data(phone='0611111111').changed_sce_data(sync_data())

        assert changed == {'phone': '0611111111', 'phone_number': '0611111111'}

    def test_school_code_travels_with_its_label(self) -> None:
        changed = sync_data(
            fra_school=SCEFraSchoolSyncData(code='0750002B', label='School A')
        ).changed_sce_data(sync_data())

        assert changed == {
            'fra_school_code': '0750002B',
            'fra_school_label': 'School A',
        }

    def test_cleared_school_clears_code_and_label(self) -> None:
        changed = sync_data(fra_school=None).changed_sce_data(sync_data())

        assert changed == {'fra_school_code': None, 'fra_school_label': None}

    def test_values_are_those_of_the_changed_side(self) -> None:
        local = sync_data(club='Local club')
        remote = sync_data(club='Remote club')

        assert local.changed_sce_data(remote) == {'club': 'Local club'}
        assert remote.changed_sce_data(local) == {'club': 'Remote club'}
