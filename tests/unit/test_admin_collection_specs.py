from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import DictLoader, Environment

from web.admin.collection import (
    _SPEC_MODULES,
    AdminCollectionSpec,
    AdminCollectionViewMode,
    ComponentPlacement,
    ListColumn,
    get_admin_collection_spec,
)
from web.controllers.admin.base_admin_controller import AdminWebContext
from web.session import SessionAdminCollectionViewMode


TEMPLATES_ROOT = Path(__file__).parents[2] / 'src' / 'web' / 'templates'


def test_collection_specs_are_owned_by_feature_modules() -> None:
    for key, module_name in _SPEC_MODULES.items():
        assert module_name.startswith('web.admin.')
        assert module_name.endswith('.collection')
        spec = get_admin_collection_spec(key)
        assert isinstance(spec, AdminCollectionSpec)
        assert spec.key == key


@pytest.mark.parametrize('key', _SPEC_MODULES)
def test_collection_spec_components_exist_in_feature_template(key: str) -> None:
    spec = get_admin_collection_spec(key)
    source = (TEMPLATES_ROOT / spec.components_template.removeprefix('/')).read_text()
    components = {
        placement.component_id
        for placement in (
            *spec.card.header,
            *spec.card.summary,
            *spec.card.body,
            *spec.card.details,
            *spec.card.footer,
            *spec.list.columns,
            *spec.list.details,
        )
    }
    for component in components:
        assert f'macro {component}(' in source
    for href_component in (
        spec.card_href_component,
        spec.row_href_component,
    ):
        if href_component:
            assert f'macro {href_component}(' in source


def test_collection_specs_remain_easy_to_extend() -> None:
    spec = get_admin_collection_spec('tournaments')
    assert not spec.__dataclass_params__.frozen


def test_collection_specs_are_isolated_between_requests() -> None:
    first_spec = get_admin_collection_spec('screens')
    first_spec.add_list_column(
        ListColumn(
            'plugin-status',
            template='/plugin/status.j2',
            label='Plugin status',
        ),
        before='actions',
    )

    second_spec = get_admin_collection_spec('screens')
    assert 'plugin-status' not in {
        column.component_id for column in second_spec.list.columns
    }


def test_plugin_components_can_be_ordered_in_each_view() -> None:
    spec = get_admin_collection_spec('screens')
    spec.add_list_column(
        ListColumn(
            'plugin-status',
            template='/plugin/status.j2',
            label='Plugin status',
            width='9rem',
        ),
        before='actions',
    )
    spec.add_list_detail(
        ComponentPlacement(
            'plugin-list-details',
            template='/plugin/list_details.j2',
        )
    )
    spec.add_card_detail(
        ComponentPlacement(
            'plugin-card-details',
            template='/plugin/card_details.j2',
        )
    )

    assert [column.component_id for column in spec.list.columns][-2:] == [
        'plugin-status',
        'actions',
    ]
    assert spec.list.details[-1].component_id == 'plugin-list-details'
    assert spec.card.details[-1].component_id == 'plugin-card-details'


def test_plugin_component_order_rejects_invalid_positions() -> None:
    spec = get_admin_collection_spec('screens')

    with pytest.raises(ValueError, match='either before or after'):
        spec.add_list_column(
            ListColumn('plugin-status', template='/plugin/status.j2'),
            before='identity',
            after='actions',
        )
    with pytest.raises(ValueError, match='Unknown collection component'):
        spec.add_list_detail(
            ComponentPlacement('plugin-details', template='/plugin/details.j2'),
            before='missing',
        )
    with pytest.raises(ValueError, match='Duplicate collection component'):
        spec.add_list_column(ListColumn('actions', template='/plugin/actions.j2'))


def test_plugin_component_template_renders_with_collection_context() -> None:
    macro_source = (TEMPLATES_ROOT / 'admin/common/collection_macros.j2').read_text()
    environment = Environment(
        loader=DictLoader(
            {
                'collection_macros.j2': macro_source,
                'plugin/status.j2': (
                    '{{ item.name }}-{{ view }}-{{ placement.component_id }}'
                ),
            }
        ),
        autoescape=True,
    )
    template = environment.from_string(
        "{% import 'collection_macros.j2' as collection_macros %}"
        "{{ collection_macros.component(components, placement, item, 'list') }}"
    )

    rendered = template.render(
        components={},
        placement=ListColumn(
            'plugin-status',
            template='plugin/status.j2',
        ),
        item=SimpleNamespace(name='Ready'),
    )

    assert 'collection-component-plugin-status' in rendered
    assert 'Ready-list-plugin-status' in rendered


def test_admin_context_applies_collection_plugins_to_a_fresh_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = object()

    class PluginManager:
        def hook_for_event(self, hook_event, hook_name):
            assert hook_event is event
            assert hook_name == 'extend_admin_collection'

            def extend_collection(**kwargs) -> None:
                assert kwargs['collection_key'] == 'screens'
                assert kwargs['event'] is event
                kwargs['collection_spec'].add_list_column(
                    ListColumn(
                        'plugin-status',
                        template='/plugin/status.j2',
                    ),
                    before='actions',
                )

            return extend_collection

    monkeypatch.setattr(
        'web.controllers.admin.base_admin_controller.plugin_manager',
        PluginManager(),
    )
    context = object.__new__(AdminWebContext)
    context.admin_event = event

    first_spec = context.get_admin_collection_spec('screens')
    second_spec = context.get_admin_collection_spec('screens')

    assert [column.component_id for column in first_spec.list.columns].count(
        'plugin-status'
    ) == 1
    assert [column.component_id for column in second_spec.list.columns].count(
        'plugin-status'
    ) == 1


@pytest.mark.parametrize('key', _SPEC_MODULES)
def test_collection_detail_placements_are_additive(key: str) -> None:
    spec = get_admin_collection_spec(key)
    card_core_components = {
        placement.component_id
        for placement in (
            *spec.card.header,
            *spec.card.summary,
            *spec.card.body,
            *spec.card.footer,
        )
    }
    card_detail_components = {placement.component_id for placement in spec.card.details}
    list_core_components = {placement.component_id for placement in spec.list.columns}
    list_detail_components = {placement.component_id for placement in spec.list.details}

    assert card_core_components.isdisjoint(card_detail_components)
    assert list_core_components.isdisjoint(list_detail_components)


def test_collection_view_defaults_to_list() -> None:
    request = SimpleNamespace(session={})
    assert (
        SessionAdminCollectionViewMode(request, 'new-collection').get()
        == AdminCollectionViewMode.LIST
    )
