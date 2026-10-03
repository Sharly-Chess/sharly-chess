"""The national identifier shown in the player form belongs to the data
source the player comes from, which is not always the FFE one."""

import pytest

from plugins.ffe import NATIONAL_SOURCE_ID
from plugins.ffe.ffe import FfePlugin


def _validate(national_id: str, national_source: str) -> dict[str, str]:
    data = {'national_id': national_id, 'national_source': national_source}
    errors: dict[str, str] = {}
    FfePlugin().validate_player_form_fields(data=data, errors=errors)
    return errors


@pytest.mark.unit
def test_a_licence_number_of_the_federation_is_checked() -> None:
    assert 'national_id' in _validate('363359H', NATIONAL_SOURCE_ID)
    assert 'national_id' not in _validate('X81840', NATIONAL_SOURCE_ID)


@pytest.mark.unit
def test_a_player_without_a_source_is_checked_as_well() -> None:
    """An empty source means the field holds the identifier of the event
    federation's list, which is this one wherever the plugin is active."""
    assert 'national_id' in _validate('363359H', '')


@pytest.mark.unit
def test_an_identifier_of_another_federation_is_left_alone() -> None:
    assert _validate('363359H', 'ecf') == {}
