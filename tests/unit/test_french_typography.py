"""The French translations keep their punctuation with the word before it:
the space before a colon, a semicolon, a question or exclamation mark, and
inside guillemets, is a no-break space, so that the punctuation never wraps
onto a line of its own."""

import re
from pathlib import Path

import pytest

from common import BASE_DIR

_CATALOGUES = sorted(
    [
        *(BASE_DIR / 'locale' / 'fr' / 'LC_MESSAGES').glob('*.po'),
        *(BASE_DIR / 'src' / 'plugins').glob('*/locale/fr/LC_MESSAGES/*.po'),
    ]
)

# A breaking space before the punctuation, or after an opening guillemet.
_BREAKING_SPACE = re.compile(r' (?=[:;?!»])|(?<=«) ')
# Punctuation glued to the word before it (HTML entities, which end in a
# semicolon, are left out).
_GLUED = re.compile(r'(?<=[A-Za-zÀ-ÿ\)\]·])[:;?!](?=[\s"]|\\n|$)')


def _translation_lines(path: Path) -> list[tuple[int, str]]:
    """The lines of the translations of *path*, with their numbers."""
    lines: list[tuple[int, str]] = []
    in_msgstr = False
    for number, line in enumerate(path.read_text(encoding='utf-8').split('\n'), 1):
        if line.startswith('msgstr'):
            in_msgstr = True
        elif line.startswith(('msgid', '#')) or not line.strip():
            in_msgstr = False
        if in_msgstr:
            lines.append((number, line))
    return lines


@pytest.mark.unit
@pytest.mark.parametrize('path', _CATALOGUES, ids=lambda path: path.name)
def test_french_punctuation_does_not_wrap(path: Path):
    faults = [
        f'{path.name}:{number}: {line}'
        for number, line in _translation_lines(path)
        if _BREAKING_SPACE.search(line) or _GLUED.search(re.sub(r'&[a-z]+;', '', line))
    ]
    assert not faults, '\n'.join(faults)
