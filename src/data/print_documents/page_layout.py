import re

from markupsafe import Markup

from common.i18n import _

_PLACEHOLDER = re.compile(r'\{(page|pages)\}')


def css_string(value: str) -> str:
    """``value`` as a double-quoted CSS string."""
    escaped = ''.join(
        f'\\{ord(char):06x}' if char in '"\\' or ord(char) < 0x20 else char
        for char in value
    )
    return f'"{escaped}"'


def page_number_content() -> str:
    """The CSS ``content`` value numbering the pages, from the translated
    ``Page {page} of {pages}``."""
    parts: list[str] = []
    position = 0
    template = _('Page {page} of {pages}')
    for match in _PLACEHOLDER.finditer(template):
        if match.start() > position:
            parts.append(css_string(template[position : match.start()]))
        parts.append(f'counter({match.group(1)})')
        position = match.end()
    if position < len(template):
        parts.append(css_string(template[position:]))
    return ' '.join(parts)


def page_footer_rule(left: str, center: str) -> Markup:
    """The ``@page`` rule printing ``left`` and ``center`` at the bottom of
    every page, and the page number on the right."""
    box = 'font-family: "AtkinsonHyperlegibleNext", Arial, sans-serif; font-size: 7.5pt; color: #000000;'
    return Markup(
        '@page {\n'
        '    margin: 12mm 10mm 14mm;\n'
        f'    @bottom-left {{ content: {css_string(left)}; {box} vertical-align: top; padding-top: 4mm; }}\n'
        f'    @bottom-center {{ content: {css_string(center)}; {box} vertical-align: top; padding-top: 4mm; }}\n'
        f'    @bottom-right {{ content: {page_number_content()}; {box} vertical-align: top; padding-top: 4mm; }}\n'
        '}'
    )
