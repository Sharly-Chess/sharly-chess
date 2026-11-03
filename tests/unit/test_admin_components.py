"""The administration's template components render the markup they promise."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Any

import pytest

from web.settings import template_engine

_VOID_ELEMENTS = {'area', 'br', 'col', 'hr', 'img', 'input', 'link', 'meta', 'source'}


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list['Node | str'] = field(default_factory=list)

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get('class') or '').split()

    def has(self, name: str) -> bool:
        return name in self.attrs

    def __getitem__(self, name: str) -> str:
        value = self.attrs[name]
        assert value is not None, f'{name} is a bare attribute'
        return value

    def text(self) -> str:
        return ' '.join(
            ''.join(
                child if isinstance(child, str) else child.text()
                for child in self.children
            ).split()
        )

    def find_all(self, tag: str | None = None, cls: str | None = None) -> list['Node']:
        """The descendants with this tag and class, in document order."""
        found: list[Node] = []
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (
                    cls is None or cls in child.classes
                ):
                    found.append(child)
                found.extend(child.find_all(tag, cls))
        return found

    def only(self, tag: str | None = None, cls: str | None = None) -> 'Node':
        found = self.find_all(tag, cls)
        assert len(found) == 1, f'{len(found)} elements match {tag}.{cls}'
        return found[0]


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node('#root')
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in _VOID_ELEMENTS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        while len(self.stack) > 1:
            if self.stack.pop().tag == tag:
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _parse(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _url_for(name: str, **params: Any) -> str:
    return '/' + '/'.join([name, *(str(value) for value in params.values())])


def _render(source: str, **context: Any) -> Node:
    template = template_engine.engine.from_string(
        "{% import '/admin/components/macros.j2' as components with context %}" + source
    )
    return _parse(template.render(locale='en', url_for=_url_for, **context))


@pytest.mark.unit
class TestButton:
    def test_kind_size_icon_and_label(self) -> None:
        root = _render(
            "{{ components.button('Save', kind='primary', icon='save', size='sm',"
            " type='submit', attrs={'form': 'modal-form'}) }}"
        )
        button = root.only('button')
        assert button.classes == ['btn', 'btn-primary', 'sc-btn', 'btn-sm']
        assert button['type'] == 'submit'
        assert button['form'] == 'modal-form'
        assert button.only('i').classes == ['bi-floppy-fill']
        assert button.text() == 'Save'

    def test_unknown_icon_name_is_used_as_a_class(self) -> None:
        root = _render("{{ components.button('Shuffle', icon='bi-shuffle') }}")
        assert root.only('i').classes == ['bi-shuffle']

    def test_bare_and_omitted_attributes(self) -> None:
        root = _render(
            "{{ components.button('A', attrs={'autofocus': true, 'hidden': false,"
            " 'data-x': none}) }}"
        )
        button = root.only('button')
        assert button.has('autofocus')
        assert not button.has('hidden')
        assert not button.has('data-x')

    def test_attribute_values_and_labels_are_escaped(self) -> None:
        root = _render(
            "{{ components.button(value, attrs={'data-x': value}) }}",
            value='"><script>',
        )
        assert not root.find_all('script')
        button = root.only('button')
        assert button['data-x'] == '"><script>'
        assert button.text() == '"><script>'

    def test_icon_only_button_names_itself_and_shows_its_label_as_tooltip(
        self,
    ) -> None:
        root = _render(
            "{{ components.button('Settings', icon='settings', icon_only=true) }}"
        )
        button = root.only('button')
        assert button['aria-label'] == 'Settings'
        assert 'sc-btn-icon-only' in button.classes
        assert button.text() == ''
        assert 'Settings' in root.only('span', 'sc-tooltip-wrapper')['data-bs-title']

    def test_enabled_button_tooltip(self) -> None:
        root = _render("{{ components.button('Add', tooltip='Adds one.') }}")
        wrapper = root.only('span', 'sc-tooltip-wrapper')
        assert 'sharly-chess-tooltip-info' in wrapper['data-bs-custom-class']
        assert 'Adds one.' in wrapper['data-bs-title']

    def test_not_allowed_button_is_disabled_inert_and_explains_why(self) -> None:
        root = _render(
            "{{ components.button('Delete', allowed=false, reason='Not yours.',"
            " tooltip='Deletes.',"
            " attrs={'hx-delete': '/x', 'data-bs-toggle': 'modal', 'id': 'b'}) }}"
        )
        button = root.only('button')
        assert button.has('disabled')
        assert not button.has('hx-delete')
        assert not button.has('data-bs-toggle')
        assert button['id'] == 'b'
        wrapper = root.only('span', 'sc-tooltip-wrapper')
        assert 'sharly-chess-tooltip-warning' in wrapper['data-bs-custom-class']
        assert 'Not yours.' in wrapper['data-bs-title']
        assert 'Deletes.' not in wrapper['data-bs-title']

    def test_call_replaces_the_label(self) -> None:
        root = _render(
            "{% call components.button('Rich') %}<b>Rich</b> text{% endcall %}"
        )
        assert root.only('button').only('b').text() == 'Rich'
        assert root.only('button').text() == 'Rich text'

    def test_cancel_button_closes_the_modal(self) -> None:
        root = _render('{{ components.cancel_button() }}')
        button = root.only('button')
        assert button['data-bs-dismiss'] == 'modal'
        assert 'btn-secondary' in button.classes
        assert button.only('i').classes == ['bi-x-circle-fill']
        assert button.text() == 'Cancel'


@pytest.mark.unit
class TestModalTriggers:
    def test_modal_button(self) -> None:
        root = _render(
            "{{ components.modal_button('/modal', 'Create', kind='primary',"
            " icon='add', attrs={'hx-trigger': 'click, SC_Plus from:body'}) }}"
        )
        button = root.only('button')
        assert button['hx-get'] == '/modal'
        assert button['hx-target'] == 'body'
        assert button['hx-indicator'] == '#please-wait'
        assert button['data-bs-toggle'] == 'modal'
        assert button['data-bs-target'] == '#modal-wrapper'
        assert button['hx-trigger'] == 'click, SC_Plus from:body'

    def test_modal_trigger_attrs(self) -> None:
        root = _render("<div {{ components.modal_trigger_attrs('/modal') }}>Card</div>")
        div = root.only('div')
        assert div['hx-get'] == '/modal'
        assert div['data-bs-target'] == '#modal-wrapper'


@pytest.mark.unit
class TestMenu:
    def test_menu_with_items(self) -> None:
        root = _render(
            "{% call components.menu_button('Actions', align='end') %}"
            "{{ components.menu_header('Group') }}"
            "{{ components.menu_item('Open', icon='edit', url='/m', modal=true) }}"
            '{{ components.menu_divider() }}'
            "{{ components.menu_item('Load', url='/l', active=true) }}"
            "{{ components.menu_item('No', allowed=false, reason='Why.',"
            " url='/n') }}"
            '{% endcall %}'
        )
        menu_root = root.only('div', 'sc-menu')
        toggle = menu_root.find_all('button')[0]
        assert 'dropdown-toggle' in toggle.classes
        assert toggle['data-bs-toggle'] == 'dropdown'
        menu = menu_root.only('ul', 'dropdown-menu')
        assert 'dropdown-menu-end' in menu.classes
        items = menu.find_all('button', 'dropdown-item')
        assert [item.text() for item in items] == ['Open', 'Load', 'No']
        assert items[0]['data-bs-target'] == '#modal-wrapper'
        assert items[0]['hx-get'] == '/m'
        assert not items[1].has('data-bs-target')
        assert items[1]['hx-get'] == '/l'
        assert 'active' in items[1].classes
        assert items[2].has('disabled')
        assert not items[2].has('hx-get')
        assert menu.only(cls='dropdown-header').text() == 'Group'
        assert menu.find_all('hr', 'dropdown-divider')

    def test_not_allowed_menu_has_no_items(self) -> None:
        root = _render(
            "{% call components.menu_button('Actions', allowed=false,"
            " reason='Why.') %}{{ components.menu_item('Open') }}{% endcall %}"
        )
        assert not root.find_all('ul')
        assert root.only('button').has('disabled')
        assert 'Why.' in root.only('span', 'sc-tooltip-wrapper')['data-bs-title']


@pytest.mark.unit
class TestNote:
    @pytest.mark.parametrize(
        ('level', 'icon'),
        [
            ('info', 'bi-info-circle-fill'),
            ('warning', 'bi-exclamation-triangle-fill'),
            ('danger', 'bi-exclamation-octagon-fill'),
            ('secondary', 'bi-info-circle'),
        ],
    )
    def test_level_gives_the_icon(self, level: str, icon: str) -> None:
        root = _render('{{ components.note(level, "Text") }}', level=level)
        note = root.only('div', 'alert')
        assert note.classes == ['alert', f'alert-{level}', 'sc-note']
        assert note.only('i').classes == [icon]
        assert note.only(cls='sc-note-body').text() == 'Text'

    def test_compact_rich_note_with_its_own_icon(self) -> None:
        root = _render(
            "{% call components.note('warning', icon='bi-flag', compact=true) %}"
            '<a href="#">Link</a>{% endcall %}'
        )
        note = root.only('div', 'alert')
        assert 'sc-note-compact' in note.classes
        assert note.only('i').classes == ['bi-flag']
        assert note.only(cls='sc-note-body').only('a').text() == 'Link'

    def test_note_actions_and_attributes(self) -> None:
        root = _render(
            "{{ components.note('danger', 'Text', actions=components.button('Go'),"
            " attrs={'id': 'n', 'style': 'display:none'}) }}"
        )
        note = root.only('div', 'alert')
        assert note['id'] == 'n'
        assert note['style'] == 'display:none'
        assert note.only(cls='sc-note-actions').only('button').text() == 'Go'
        assert not root.only(cls='sc-note-body').find_all('button')


@pytest.mark.unit
class TestBadges:
    def test_badge(self) -> None:
        root = _render(
            "{{ components.badge('primary', 'FIDE', icon='bi-star-fill', pill=true) }}"
        )
        badge = root.only('span', 'badge')
        assert badge.classes == [
            'badge',
            'sc-badge',
            'sc-badge-primary',
            'rounded-pill',
        ]
        assert badge.only('i').classes == ['bi-star-fill']
        assert badge.text() == 'FIDE'

    @pytest.mark.parametrize(
        ('value', 'kind', 'text'),
        [(2, 'success', '+2'), (-1.5, 'danger', '−1.5'), (0, 'neutral', '0')],
    )
    def test_delta_badge(self, value: float, kind: str, text: str) -> None:
        root = _render('{{ components.delta_badge(value) }}', value=value)
        badge = root.only('span', 'badge')
        assert f'sc-badge-{kind}' in badge.classes
        assert 'rounded-pill' in badge.classes
        assert badge.text() == text


@pytest.mark.unit
class TestBadgeVariants:
    def test_badge_opening_a_modal(self) -> None:
        root = _render(
            "{{ components.badge('success', '+1', modal_url='/m',"
            " attrs={'onclick': 'event.stopPropagation()'}) }}"
        )
        link = root.only('a', 'badge')
        assert 'sc-badge-action' in link.classes
        assert link['role'] == 'button'
        assert link['hx-get'] == '/m'
        assert link['data-bs-target'] == '#modal-wrapper'
        assert link['onclick'] == 'event.stopPropagation()'

    def test_rich_badge(self) -> None:
        root = _render(
            "{% call components.badge('warning', 'TB') %}TB"
            "{{ components.icon('warning') }}{% endcall %}"
        )
        badge = root.only('span', 'badge')
        assert badge.text() == 'TB'
        assert badge.only('i').classes == ['bi-exclamation-triangle-fill']

    def test_tag_badges(self) -> None:
        tag = SimpleNamespace(name='Youth', color='#ff0000', text_color='#ffffff')
        root = _render(
            '{{ components.tag_badge(tag, count=3, tinted=true, dimmed=true) }}'
            '{{ components.tag_badges([tag, tag]) }}',
            tag=tag,
        )
        tinted = root.find_all('span', 'tag-badge')[0]
        assert {'sc-tag-badge-tinted', 'opacity-50'} <= set(tinted.classes)
        assert '--sc-tag-color: #ff0000' in tinted['style']
        assert tinted.text() == 'Youth(3)'
        group = root.only('span', 'sc-badge-group')
        assert len(group.find_all('span', 'tag-badge')) == 2


def _render_pairing_components(source: str, **context: Any) -> Node:
    template = template_engine.engine.from_string(
        "{% import '/admin/components/pairings.j2' as pairing_components"
        ' with context %}' + source
    )
    return _parse(
        template.render(
            locale='en',
            url_for=_url_for,
            admin_event=SimpleNamespace(uniq_id='event'),
            **context,
        )
    )


class _PointAdjustments:
    def __init__(self, mp: float, gp: float, explanation: str = '') -> None:
        self.mp, self.gp, self.explanation = mp, gp, explanation

    def effective(self, team_id: int, round_: int) -> tuple[float, float]:
        return self.mp, self.gp

    def from_rule_set(self, team_id: int, round_: int) -> SimpleNamespace | None:
        return (
            SimpleNamespace(explanation=self.explanation) if self.explanation else None
        )

    def stored(self, team_id: int, round_: int) -> None:
        return None


@pytest.mark.unit
class TestPairingComponents:
    @pytest.mark.parametrize(
        ('mp', 'gp', 'explanation', 'kind', 'text'),
        [
            (-1, 0, '', 'danger', '-1 MP'),
            (0, 2, '', 'success', '+2 GP'),
            (1, -0.5, '', 'danger', '+1 MP -0.5 GP'),
            (0, 0, 'Forfeit rule', 'neutral', '0 GP'),
        ],
    )
    def test_team_points_badge(
        self, mp: float, gp: float, explanation: str, kind: str, text: str
    ) -> None:
        tournament = SimpleNamespace(
            id=1, point_adjustments=_PointAdjustments(mp, gp, explanation)
        )
        root = _render_pairing_components(
            '{{ pairing_components.team_points_badge(tournament, 7, 2, editable=true) }}',
            tournament=tournament,
        )
        badge = root.only('a', 'badge')
        assert f'sc-badge-{kind}' in badge.classes
        raw_text = ''.join(child for child in badge.children if isinstance(child, str))
        assert raw_text.strip() == text
        assert badge['hx-get'] == '/admin-team-point-adjustment-modal/event/1/2/7'

    def test_no_team_points_badge_without_adjustment(self) -> None:
        tournament = SimpleNamespace(id=1, point_adjustments=_PointAdjustments(0, 0))
        root = _render_pairing_components(
            '{{ pairing_components.team_points_badge(tournament, 7, 2) }}',
            tournament=tournament,
        )
        assert not root.find_all(cls='badge')

    def test_advance_mark(self) -> None:
        root = _render_pairing_components(
            "{{ pairing_components.advance_mark('Armageddon', side='end') }}"
        )
        mark = root.only('span', 'badge')
        assert {'sc-badge-primary', 'sc-advance-mark', 'sc-advance-mark-end'} <= set(
            mark.classes
        )
        assert mark.text() == '1'
        assert 'Armageddon' in mark['data-bs-title']


@pytest.mark.unit
class TestOtherComponents:
    def test_banner(self) -> None:
        root = _render(
            "{{ components.banner('warning', 'Careful', icon='warning',"
            ' dismissible=false) }}'
        )
        banner = root.only('div', 'alert')
        assert 'message-warning' in banner.classes
        assert banner.only('i').classes[0] == 'bi-exclamation-triangle-fill'
        assert not banner.find_all(cls='btn-close')
        assert 'Careful' in banner.text()

    def test_empty_state(self) -> None:
        root = _render(
            "{% call components.empty_state('Nothing') %}<p>Explain.</p>{% endcall %}"
        )
        state = root.only('div', 'admin-empty-state')
        assert state.only('h5').text() == 'Nothing'
        assert state.only('p').text() == 'Explain.'

    def test_section_heading(self) -> None:
        root = _render("{{ components.section_heading('Part') }}")
        assert root.only('h3', 'sc-section-heading').text() == 'Part'


def _render_template(name: str, **context: Any) -> Node:
    html = template_engine.engine.get_template(name).render(
        locale='en',
        url_for=_url_for,
        admin_event=SimpleNamespace(uniq_id='event'),
        **context,
    )
    return _parse(html)


@pytest.mark.unit
class TestDeleteModal:
    def test_delete_modal_on_the_modal_shell(self) -> None:
        root = _render_template(
            'admin/teams/team_delete_modal.html',
            admin_team=SimpleNamespace(id=3, name='Rooks'),
        )
        dialog = root.only('div', 'modal-dialog')
        assert dialog['id'] == 'delete-modal'
        assert 'sc-modal-fit' in dialog.classes
        assert 'modal-dialog-scrollable' in dialog.classes
        assert dialog.only(cls='modal-title').text() == 'Delete team'
        assert not dialog.only(cls='modal-header').find_all(cls='btn-close')
        body = dialog.only(cls='modal-body')
        assert 'Rooks' in body.only('h4').text()
        warning = body.only('div', 'alert-danger')
        assert 'permanent' in warning.text()
        assert warning.only('i').classes == ['bi-exclamation-triangle-fill']
        assert body.only('form')['hx-delete'].strip() == '/admin-team-delete/event/3'
        footer_buttons = dialog.only(cls='modal-footer').find_all('button')
        assert [button.text() for button in footer_buttons] == ['Cancel', 'Delete']
        delete_button = footer_buttons[1]
        assert delete_button['id'] == 'delete-button'
        assert delete_button['form'] == 'modal-form'
        assert delete_button['type'] == 'submit'
        assert 'btn-danger' in delete_button.classes
        assert delete_button.only('i').classes == ['bi-trash']

    def test_delete_modal_label_and_warning(self) -> None:
        root = _render_template(
            'admin/championship/source_delete_modal.html',
            championship=SimpleNamespace(uniq_id='c'),
            source=SimpleNamespace(id=1, tournament_name='Open A'),
        )
        delete_button = root.only('button', 'btn-danger')
        assert delete_button.text() == 'Remove'
        assert delete_button.only('i').classes == ['bi-trash']
        assert 'Remove this tournament' in root.only('div', 'alert-danger').text()

    def test_delete_modal_url(self) -> None:
        root = _render_template(
            'admin/timers/timer_hours_clear_modal.html',
            admin_timer=SimpleNamespace(id=2, name='Main'),
        )
        assert root.only('form')['hx-delete'].strip() == (
            '/admin-timer-hours-clear/event/2'
        )
        assert root.only('button', 'btn-danger').text() == 'Clear all'
