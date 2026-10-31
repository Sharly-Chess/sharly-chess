"""Every select of the admin view is drawn by select2.

A native select opens a list in the colours of the system, which on the
dark admin view leaves light text on a white list. The screens of the
players and spectators are light, and keep their native selects.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from common import BASE_DIR
from web.settings import template_dirs

STATIC_DIR = BASE_DIR / 'src/web/static'

SELECT2_CLASS = 'sharly-chess-select2'

_COMMENT = re.compile(r'\{#.*?#\}', re.DOTALL)
_SELECT_TAG = re.compile(r'<select\b[^>]*>', re.DOTALL)
_CLASS = re.compile(r'\bclass="([^"]*)"')


def _admin_templates() -> Iterator[tuple[Path, str]]:
    for directory in template_dirs:
        if directory == STATIC_DIR:
            continue
        for path in sorted(directory.rglob('*')):
            name = path.relative_to(directory).as_posix()
            if path.is_file() and not name.startswith('user/'):
                yield path, name


@pytest.mark.unit
def test_admin_selects_use_select2() -> None:
    native = []
    for path, name in _admin_templates():
        source = _COMMENT.sub(
            lambda comment: '\n' * comment.group().count('\n'),
            path.read_text(encoding='utf-8'),
        )
        for tag in _SELECT_TAG.finditer(source):
            classes = _CLASS.search(tag.group())
            if not classes or SELECT2_CLASS not in classes.group(1).split():
                line = source.count('\n', 0, tag.start()) + 1
                native.append(f'{name}:{line}')
    assert not native, (
        f'Selects without the {SELECT2_CLASS} class (add inline-select2 to '
        f'have it set up): {native}'
    )
