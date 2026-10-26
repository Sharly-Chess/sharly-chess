from functools import cache

from markupsafe import Markup

from common import BASE_DIR
from utils.file import ttf_file_inline_url

PRINT_FONT_FAMILY = 'AtkinsonHyperlegibleNext'

_PRINT_FONTS_DIR = BASE_DIR / 'src/web/static/fonts/print'


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
            f'    src: url("{ttf_file_inline_url(_PRINT_FONTS_DIR / f"{PRINT_FONT_FAMILY}-{face}.ttf")}") format("truetype");\n'
            f'    font-weight: {weight};\n'
            f'    font-style: {style};\n'
            f'}}'
            for face, weight, style in (
                ('Regular', 'normal', 'normal'),
                ('Bold', 'bold', 'normal'),
                ('Italic', 'normal', 'italic'),
                ('BoldItalic', 'bold', 'italic'),
            )
        )
    )
