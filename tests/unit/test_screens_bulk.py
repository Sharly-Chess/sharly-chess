import pytest

from web.admin.screens.bulk import merged_form_data, parse_item_ids, shared_form_data


class TestParseItemIds:
    def test_screens_and_paged_screens_are_told_apart(self):
        assert parse_item_ids(['3', 'family-5', '7', '3']) == ([3, 7], [5])

    def test_an_unknown_id_is_refused(self):
        with pytest.raises(ValueError):
            parse_item_ids(['screen-3'])


class TestSharedFormData:
    def test_values_held_alike_are_shared_and_others_mixed(self):
        shared, mixed = shared_form_data(
            [
                {'font_size': '120', 'columns': '2', 'name': 'A'},
                {'font_size': '120', 'columns': '3', 'name': 'B'},
            ]
        )
        assert shared == {'font_size': '120'}
        assert mixed == {'columns'}

    def test_an_unticked_switch_reads_the_same_whatever_its_source(self):
        shared, mixed = shared_form_data(
            [{'input_exit_button': 'off'}, {'input_exit_button': ''}, {}]
        )
        assert shared == {'input_exit_button': ''}
        assert mixed == set()

    def test_a_field_only_some_items_have_is_mixed(self):
        _, mixed = shared_form_data([{'parts': '3'}, {}])
        assert mixed == {'parts'}


class TestMergedFormData:
    def test_only_the_changed_fields_are_taken_from_the_form(self):
        merged = merged_form_data(
            {'font_size': '100', 'columns': '2', 'accepts_input': 'on'},
            {'font_size': '130', 'columns': '4'},
            ['font_size', 'accepts_input'],
        )
        assert merged == {'font_size': '130', 'columns': '2'}

    def test_the_fields_of_each_screen_are_never_overwritten(self):
        merged = merged_form_data(
            {'name': 'Hall', 'first': '1'},
            {'name': 'Other', 'first': '9'},
            ['name', 'first'],
        )
        assert merged == {'name': 'Hall', 'first': '1'}
