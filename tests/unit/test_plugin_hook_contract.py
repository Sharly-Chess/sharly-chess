"""What a plugin implements is what the application declares.

pluggy checks, when a plugin is registered, that an implementation names
a declared hook and takes no parameter the declaration lacks. It reads no
annotations, so a plugin can promise less than the application sends or
return what no caller expects. And the application names hooks by string
at its call sites, which nothing checks at all until the line runs.
"""

import ast
import inspect
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from common import APP_NAME, BASE_DIR
from plugins.hookspec import AppHookSpecs
from plugins.manager import plugin_manager
from plugins.utils import Plugin

SPEC_MARK = f'{APP_NAME}_spec'
IMPL_MARK = f'{APP_NAME}_impl'
SRC_DIR = BASE_DIR / 'src'


def _marked(cls: type, mark: str) -> Iterator[tuple[str, Callable[..., Any]]]:
    for name, function in inspect.getmembers(cls, inspect.isfunction):
        if hasattr(function, mark):
            yield name, function


def _specs() -> dict[str, inspect.Signature]:
    """Every declared hook, the application's and the plugins' own."""
    holders: list[type] = [AppHookSpecs]
    holders.extend(
        plugin.hookspecs for plugin in plugin_manager.all_plugins if plugin.hookspecs
    )
    return {
        name: inspect.signature(function)
        for holder in holders
        for name, function in _marked(holder, SPEC_MARK)
    }


def _implementations() -> Iterator[tuple[Plugin, str, inspect.Signature]]:
    for plugin in plugin_manager.all_plugins:
        for name, function in _marked(type(plugin), IMPL_MARK):
            yield plugin, name, inspect.signature(function)


def _members(annotation: Any) -> set[str]:
    """The top-level members of an annotation's union, spelled the same
    whether they came as a string, a class or a typing construct."""
    if annotation is inspect.Parameter.empty:
        return set()
    text = annotation if isinstance(annotation, str) else repr(annotation)
    text = re.sub(r'ForwardRef\(([^)]*)\)', r'\1', text)
    text = re.sub(r'<\w+ ([^>]*)>', r'\1', text)
    text = text.replace("'", '').replace('"', '').replace(' ', '')
    # A module path in front of a name says where the class lives, not
    # what it is: `data.player.Player` and `'Player'` name the same thing.
    text = re.sub(r'\b(?:[a-z_][a-z0-9_]*\.)+(?=[A-Za-z_])', '', text)
    while match := re.search(r'Optional\[((?:[^\[\]]|\[[^\[\]]*\])*)\]', text):
        text = text[: match.start()] + f'{match.group(1)}|None' + text[match.end() :]
    while match := re.search(r'Union\[((?:[^\[\]]|\[[^\[\]]*\])*)\]', text):
        text = (
            text[: match.start()]
            + match.group(1).replace(',', '|')
            + text[match.end() :]
        )
    members: set[str] = set()
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character == '[':
            depth += 1
        elif character == ']':
            depth -= 1
        elif character == '|' and depth == 0:
            members.add(text[start:index])
            start = index + 1
    members.add(text[start:])
    return members


def _impl_ids() -> list[str]:
    return [f'{plugin.id}.{name}' for plugin, name, _ in _implementations()]


@pytest.mark.unit
@pytest.mark.parametrize(
    ('plugin', 'name', 'implementation'), list(_implementations()), ids=_impl_ids()
)
def test_implementation_keeps_the_contract_of_its_spec(
    plugin: Plugin, name: str, implementation: inspect.Signature
) -> None:
    specs = _specs()
    assert name in specs, f'{plugin.id} implements {name}, which no spec declares'
    spec = specs[name]
    for parameter in implementation.parameters.values():
        if parameter.name == 'self':
            continue
        assert parameter.name in spec.parameters, (
            f'{plugin.id}.{name} takes {parameter.name}, which the spec never sends'
        )
        sent = _members(spec.parameters[parameter.name].annotation)
        accepted = _members(parameter.annotation)
        # The spec sends what it declares; the implementation has to accept
        # all of it, and may accept more.
        assert sent <= accepted, (
            f'{plugin.id}.{name} takes {parameter.name}: {parameter.annotation!r}, '
            f'the spec sends {spec.parameters[parameter.name].annotation!r}'
        )
    # An implementation may answer with part of what the spec declares, or
    # with None, which pluggy leaves out of the results.
    expected = _members(spec.return_annotation) | {'None'}
    returned = _members(implementation.return_annotation)
    assert returned <= expected, (
        f'{plugin.id}.{name} returns {implementation.return_annotation!r}, '
        f'the spec declares {spec.return_annotation!r}'
    )


def _named_hooks() -> Iterator[tuple[Path, int, str]]:
    """Each hook the source names, by string or as an attribute of a
    manager's ``hook`` relay, with where it does so."""
    for path in sorted(SRC_DIR.rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and _is_hook_relay(node.value):
                yield path, node.lineno, node.attr
            elif isinstance(node, ast.Call) and (name := _hook_name_argument(node)):
                yield path, node.lineno, name


def _is_hook_relay(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == 'hook'


def _hook_name_argument(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    position = {'hook_for_event': 1, 'hook_for_plugins': 0}.get(call.func.attr)
    if position is None:
        return None
    for keyword in call.keywords:
        if keyword.arg == 'hook_name':
            return _string(keyword.value)
    if len(call.args) > position:
        return _string(call.args[position])
    return None


def _string(node: ast.expr) -> str | None:
    return (
        node.value
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        else None
    )


@pytest.mark.unit
def test_every_hook_the_source_names_is_declared() -> None:
    specs = _specs()
    unknown = [
        f'{path.relative_to(BASE_DIR)}:{line}: {name}'
        for path, line, name in _named_hooks()
        if name not in specs
    ]
    assert not unknown, 'hooks named that no spec declares:\n' + '\n'.join(unknown)
