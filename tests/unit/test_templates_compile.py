"""Every template compiles, and every template it names exists.

Jinja parses a template on first use, so a stray tag or a renamed partial
only surfaces when a request reaches the page that carries it. Loading
each one through the application's own environment finds both up front.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from jinja2 import TemplateSyntaxError, meta

from common import BASE_DIR
from web.settings import template_dirs, template_engine

STATIC_DIR = BASE_DIR / 'src/web/static'


def _templates() -> Iterator[tuple[Path, str]]:
    """Each template as ``(search path, name)``, the name being what a
    controller or an ``include`` would ask for. Stylesheets and scripts
    under a template directory are templates too."""
    for directory in template_dirs:
        if directory == STATIC_DIR:
            continue
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                yield directory, path.relative_to(directory).as_posix()


def _template_ids() -> list[str]:
    return [name for _, name in _templates()]


@pytest.mark.unit
@pytest.mark.parametrize(('directory', 'name'), list(_templates()), ids=_template_ids())
def test_template_compiles_and_its_references_resolve(
    directory: Path, name: str
) -> None:
    environment = template_engine.engine
    source = (directory / name).read_text(encoding='utf-8')
    try:
        ast = environment.parse(source, name=name, filename=str(directory / name))
    except TemplateSyntaxError as error:
        pytest.fail(f'{name}:{error.lineno}: {error.message}')
    missing = sorted(
        {
            referenced
            for referenced in meta.find_referenced_templates(ast)
            if referenced is not None
            and not _resolves(environment.join_path(referenced, name))
        }
    )
    assert not missing, f'{name} refers to templates that do not exist: {missing}'


def _resolves(name: str) -> bool:
    """Whether the loader would find ``name``: it joins each segment onto
    the search path, so a leading slash roots the name at the search path
    rather than at the file system. The static directory counts, as print
    views pull the library files in to build self-contained documents."""
    relative = name.lstrip('/')
    return any((directory / relative).is_file() for directory in template_dirs)
