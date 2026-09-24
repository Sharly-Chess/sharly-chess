import pytest

from plugins.ffe.utils import FfePlayerPluginData, PlayerFFELicence


@pytest.mark.parametrize(
    'ffe_licence_number, expected_licence',
    [
        (None, PlayerFFELicence.NONE),
        ('', PlayerFFELicence.NONE),
        ('V68338', PlayerFFELicence.N),
    ],
)
def test_licence_requires_a_licence_number(
    ffe_licence_number: str | None, expected_licence: PlayerFFELicence
) -> None:
    plugin_data = FfePlayerPluginData.from_stored_value(
        {'ffe_licence': 'N', 'ffe_licence_number': ffe_licence_number}
    )
    assert plugin_data.ffe_licence == expected_licence

    plugin_data = FfePlayerPluginData(
        ffe_id=None,
        ffe_licence=PlayerFFELicence.N,
        ffe_licence_number=ffe_licence_number,
        league=None,
    )
    assert plugin_data.to_stored_value()['ffe_licence'] == expected_licence.value
