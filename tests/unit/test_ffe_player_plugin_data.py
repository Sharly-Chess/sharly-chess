import pytest

from data.event import Event
from database.sqlite.event.event_store import StoredEvent, StoredPlayer
from plugins.ffe import NATIONAL_SOURCE_ID
from plugins.ffe.utils import FFEUtils, FfePlayerPluginData, PlayerFFELicence
from utils.enum import PlayerRatingType


def _player(national_id: str | None, national_source: str | None) -> StoredPlayer:
    return StoredPlayer(
        id=1,
        last_name='DOE',
        national_id=national_id,
        national_source=national_source,
        plugin_data={
            'ffe': FfePlayerPluginData(
                ffe_licence=PlayerFFELicence.N, league=None
            ).to_stored_value()
        },
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    'national_id, national_source, expected_licence',
    [
        ('V68338', NATIONAL_SOURCE_ID, PlayerFFELicence.N),
        # An identifier typed in a French event is an FFE licence number.
        ('V68338', None, PlayerFFELicence.N),
        (None, None, PlayerFFELicence.NONE),
        ('', NATIONAL_SOURCE_ID, PlayerFFELicence.NONE),
        ('12345', 'knsb', PlayerFFELicence.NONE),
    ],
)
def test_licence_requires_a_licence_number(
    national_id: str | None,
    national_source: str | None,
    expected_licence: PlayerFFELicence,
) -> None:
    """The licence number of a player is their national id: a licence type
    without one means no licence."""
    event = Event(
        StoredEvent(
            uniq_id='ffe-licence-test',
            name='FFE licence test',
            federation='FRA',
            player_rating_type=PlayerRatingType.FIDE.value,
            enabled_plugins=['ffe'],
            stored_players=[_player(national_id, national_source)],
        )
    )
    player = event.players_by_id[1]
    assert FFEUtils.licence(player) == expected_licence
