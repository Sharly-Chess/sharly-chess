"""Keeps hand-written copies of the administration's components from growing.

The admin templates are moving onto the components of
``src/web/templates/admin/components``. This check counts, per template, the
markup those components replace (buttons, modal frames, notes, badges...),
and compares the counts with a baseline: a count going up, or a template
that is not in the baseline, fails. A count going down asks for the baseline
to be lowered in the same change, with ``--update-baseline``.

Usage:
    python scripts/lint/template_components.py               check
    python scripts/lint/template_components.py --update-baseline
    python scripts/lint/template_components.py --report      counts per rule
"""

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name('template_components_baseline.json')

ADMIN_TEMPLATES = ROOT / 'src/web/templates/admin'
EXCLUDED_DIRECTORIES = (ADMIN_TEMPLATES / 'components', ADMIN_TEMPLATES / 'print')
PLUGIN_TEMPLATES_GLOB = 'src/plugins/*/templates'
TEMPLATE_SUFFIXES = ('.html', '.j2')

_CLASS_ATTRIBUTE = re.compile(r'\bclass="([^"]*)"')
_CLASS_TOKEN = re.compile(r'[\w-]+')

_FIXED_COLOURS = {
    'text-dark',
    'text-white',
    'text-light',
    'bg-primary',
    'bg-secondary',
    'bg-success',
    'bg-danger',
    'bg-warning',
    'bg-info',
    'bg-light',
    'bg-dark',
    'bg-white',
}

# The rules on the classes of one element, each giving how many times the
# element breaks it, with the component that replaces the markup.
CLASS_RULES: dict[str, tuple[Callable[[set[str]], int], str]] = {
    'button': (
        lambda tokens: int('btn' in tokens),
        'components.button, modal_button, cancel_button or menu_button',
    ),
    'modal-dialog': (
        lambda tokens: int('modal-dialog' in tokens),
        "{% extends '/admin/components/modal.html' %}",
    ),
    'modal-header': (
        lambda tokens: int('modal-header' in tokens),
        "{% extends '/admin/components/modal.html' %}",
    ),
    'note': (
        lambda tokens: int('alert' in tokens),
        'components.note or components.banner',
    ),
    'badge': (
        lambda tokens: int('badge' in tokens),
        'components.badge or components.delta_badge',
    ),
    'menu-item': (
        lambda tokens: int('dropdown-item' in tokens),
        'components.menu_item',
    ),
    'empty-state': (
        lambda tokens: int('admin-empty-state' in tokens),
        'components.empty_state',
    ),
    'icon-spacing': (
        lambda tokens: int(
            'pe-1' in tokens and any(token.startswith('bi-') for token in tokens)
        ),
        'the icon argument of the components, which space the icon themselves',
    ),
    'dead-white-class': (
        lambda tokens: int(
            'white' in tokens
            and 'btn' in tokens
            and not tokens & {'result-button', 'admin-result-button'}
        ),
        'nothing: the class has no effect on buttons',
    ),
    'fixed-colour': (
        lambda tokens: len(tokens & _FIXED_COLOURS),
        'theme tokens (--pw-*, --bs-*) or a component',
    ),
}

# The rules on the raw text of a template.
TEXT_RULES: dict[str, tuple[re.Pattern[str], str]] = {
    'modal-trigger': (
        re.compile(r'data-bs-target="#modal-wrapper"'),
        'components.modal_button or components.modal_trigger_attrs',
    ),
    'warning-heading': (
        re.compile(r'<h[3-6]\b[^>]*\btext-(?:danger|warning)\b'),
        'components.note',
    ),
}

RULES: dict[str, str] = {
    name: replacement for name, (_, replacement) in CLASS_RULES.items()
} | {name: replacement for name, (_, replacement) in TEXT_RULES.items()}

_INLINE_STYLE = re.compile(r'\bstyle="')

Counts = dict[str, dict[str, int]]


def template_paths() -> Iterator[Path]:
    """The templates the check covers, in a stable order."""
    roots = [ADMIN_TEMPLATES, *sorted(ROOT.glob(PLUGIN_TEMPLATES_GLOB))]
    for root in roots:
        for path in sorted(root.rglob('*')):
            if (
                path.is_file()
                and path.suffix in TEMPLATE_SUFFIXES
                and not any(path.is_relative_to(d) for d in EXCLUDED_DIRECTORIES)
            ):
                yield path


def count_text(text: str) -> Counter[str]:
    """How many times the markup of ``text`` breaks each rule."""
    counts: Counter[str] = Counter()
    for match in _CLASS_ATTRIBUTE.finditer(text):
        tokens = set(_CLASS_TOKEN.findall(match.group(1)))
        for name, (rule, _) in CLASS_RULES.items():
            counts[name] += rule(tokens)
    for name, (pattern, _) in TEXT_RULES.items():
        counts[name] += len(pattern.findall(text))
    return +counts


def current_counts() -> Counts:
    counts: Counts = {}
    for path in template_paths():
        file_counts = count_text(path.read_text(encoding='utf-8'))
        if file_counts:
            counts[path.relative_to(ROOT).as_posix()] = dict(
                sorted(file_counts.items())
            )
    return counts


def load_baseline() -> Counts:
    if not BASELINE_PATH.exists():
        return {}
    baseline: Counts = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
    return baseline


def write_baseline(counts: Counts) -> None:
    BASELINE_PATH.write_text(
        json.dumps(counts, indent=2, sort_keys=True, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )


def compare(current: Counts, baseline: Counts) -> tuple[list[str], list[str]]:
    """The increases over the baseline, and the decreases under it."""
    increases: list[str] = []
    decreases: list[str] = []
    for file in sorted(current.keys() | baseline.keys()):
        now = current.get(file, {})
        before = baseline.get(file, {})
        for rule in sorted(now.keys() | before.keys()):
            count, allowed = now.get(rule, 0), before.get(rule, 0)
            if count > allowed:
                increases.append(
                    f'{file}: {count} {rule} (baseline {allowed}); use {RULES[rule]}'
                )
            elif count < allowed:
                decreases.append(f'{file}: {count} {rule} (baseline {allowed})')
    return increases, decreases


def report(current: Counts) -> None:
    totals: Counter[str] = Counter()
    for file_counts in current.values():
        totals.update(file_counts)
    for rule, total in totals.most_common():
        print(f'{total:6} {rule}')
    styles = sum(
        len(_INLINE_STYLE.findall(path.read_text(encoding='utf-8')))
        for path in template_paths()
    )
    print(f'{styles:6} inline styles (not enforced)')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--update-baseline', action='store_true')
    group.add_argument('--report', action='store_true')
    arguments = parser.parse_args(argv)

    current = current_counts()
    if arguments.update_baseline:
        write_baseline(current)
        print(f'Wrote {BASELINE_PATH.relative_to(ROOT)}.')
        return 0
    if arguments.report:
        report(current)
        return 0

    increases, decreases = compare(current, load_baseline())
    if increases:
        print('Hand-written component markup has grown:')
        print('\n'.join(f'  {line}' for line in increases))
    if decreases:
        print('Hand-written component markup has shrunk; lower the baseline')
        print('with `python scripts/lint/template_components.py --update-baseline`:')
        print('\n'.join(f'  {line}' for line in decreases))
    return 1 if increases or decreases else 0


if __name__ == '__main__':
    sys.exit(main())
