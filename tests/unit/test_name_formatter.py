import pytest

from utils.name_formatter import NameFormatterManager


@pytest.mark.unit
@pytest.mark.parametrize(
    ('formatter_id', 'capitalise_last_name', 'expected'),
    [
        ('LAST_FIRST', False, 'de la Tour Jean'),
        ('LAST_FIRST', True, 'DE LA TOUR Jean'),
        ('LAST_COMMA_FIRST', False, 'de la Tour, Jean'),
        ('LAST_COMMA_FIRST', True, 'DE LA TOUR, Jean'),
        ('FIRST_LAST', False, 'Jean de la Tour'),
        ('FIRST_LAST', True, 'Jean DE LA TOUR'),
        ('FIRST_COMMA_LAST', False, 'Jean, de la Tour'),
        ('FIRST_COMMA_LAST', True, 'Jean, DE LA TOUR'),
    ],
)
def test_a_full_name_is_displayed_in_the_format_chosen(
    formatter_id: str, capitalise_last_name: bool, expected: str
):
    formatter = NameFormatterManager().get_object(formatter_id)
    formatter.capitalise_last_name = capitalise_last_name
    assert formatter.format('Jean', 'de la Tour') == expected


@pytest.mark.unit
@pytest.mark.parametrize('formatter_id', NameFormatterManager().ids())
@pytest.mark.parametrize(
    ('capitalise_last_name', 'expected'), [(False, 'de la Tour'), (True, 'DE LA TOUR')]
)
def test_a_name_without_first_name_is_its_last_name(
    formatter_id: str, capitalise_last_name: bool, expected: str
):
    formatter = NameFormatterManager().get_object(formatter_id)
    formatter.capitalise_last_name = capitalise_last_name
    assert formatter.format(None, 'de la Tour') == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ('formatter_id', 'expected'),
    [
        ('LAST_FIRST', ('tour', 'jean')),
        ('LAST_COMMA_FIRST', ('tour', 'jean')),
        ('FIRST_LAST', ('jean', 'tour')),
        ('FIRST_COMMA_LAST', ('jean', 'tour')),
    ],
)
def test_names_are_sorted_by_the_name_displayed_first(
    formatter_id: str, expected: tuple[str, str]
):
    formatter = NameFormatterManager().get_object(formatter_id)
    assert formatter.sort_key('Jean', 'Tour') == expected
