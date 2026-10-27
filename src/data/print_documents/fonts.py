from functools import cache
from pathlib import Path

from markupsafe import Markup

from common import BASE_DIR
from utils.file import ttf_file_inline_url

PRINT_FONT_FAMILY = 'AtkinsonHyperlegibleNext'

_PRINT_FONTS_DIR = BASE_DIR / 'src/web/static/fonts/print'

PRINT_FONT_FILES: dict[tuple[bool, bool], Path] = {
    (bold, italic): _PRINT_FONTS_DIR / f'{PRINT_FONT_FAMILY}-{face}.ttf'
    for bold, italic, face in (
        (False, False, 'Regular'),
        (True, False, 'Bold'),
        (False, True, 'Italic'),
        (True, True, 'BoldItalic'),
    )
}
"""The files of the print font, by whether they are bold and italic."""


@cache
def print_font_faces() -> Markup:
    """The @font-face rules embedding the print font in a document.

    Each weight and style is a static font: Chrome writes variable fonts into
    PDFs as Type 3 fonts, whose text most PDF viewers cannot select or copy.
    """
    return Markup(
        '\n'.join(
            f'@font-face {{\n'
            f'    font-family: "{PRINT_FONT_FAMILY}";\n'
            f'    src: url("{ttf_file_inline_url(file)}") format("truetype");\n'
            f'    font-weight: {"bold" if bold else "normal"};\n'
            f'    font-style: {"italic" if italic else "normal"};\n'
            f'}}'
            for (bold, italic), file in PRINT_FONT_FILES.items()
        )
    )
