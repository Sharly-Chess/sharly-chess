"""Fonts embedded in a Word file (ECMA-376 Part 1, 17.8.1), so that the file
is laid out in the fonts of its document on a computer that lacks them."""

import uuid
from pathlib import Path

from docx.document import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.opc.part import Part
from docx.opc.oxml import serialize_part_xml
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn

_OBFUSCATED_FONT_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument.obfuscatedFont'
)
# The characters of a font key, braces and dashes included, whose hexadecimal
# digits give the bytes of the obfuscation key, in that order.
_KEY_POSITIONS = (35, 33, 31, 29, 27, 25, 22, 20, 17, 15, 12, 10, 7, 5, 3, 1)
_EMBED_TAGS = {
    (False, False): 'w:embedRegular',
    (True, False): 'w:embedBold',
    (False, True): 'w:embedItalic',
    (True, True): 'w:embedBoldItalic',
}
# The elements of the settings that come before embedTrueTypeFonts.
_SETTINGS_BEFORE_EMBEDDING = frozenset(
    qn(tag)
    for tag in (
        'w:writeProtection',
        'w:view',
        'w:zoom',
        'w:removePersonalInformation',
        'w:removeDateAndTime',
        'w:doNotDisplayPageBoundaries',
        'w:displayBackgroundShape',
        'w:printPostScriptOverText',
        'w:printFractionalCharacterWidth',
        'w:printFormsData',
    )
)


def obfuscated(font: bytes, key: str) -> bytes:
    """A font obfuscated with a key, as a Word file holds it: its first 32
    bytes are combined with those of the key. Obfuscating twice restores the
    font."""
    key_bytes = bytes(
        int(key[position : position + 2], 16) for position in _KEY_POSITIONS
    )
    head = bytes(byte ^ key_bytes[index % 16] for index, byte in enumerate(font[:32]))
    return head + font[32:]


def embed_font(
    document: Document, family: str, files: dict[tuple[bool, bool], Path]
) -> None:
    """Embed the files of a font family, by whether they are bold and italic."""
    package = document.part.package
    font_table = document.part.part_related_by(RELATIONSHIP_TYPE.FONT_TABLE)
    fonts = parse_xml(font_table.blob)
    font = next(
        (
            element
            for element in fonts.findall(qn('w:font'))
            if element.get(qn('w:name')) == family
        ),
        None,
    )
    if font is None:
        font = OxmlElement('w:font')
        font.set(qn('w:name'), family)
        fonts.append(font)
    for style, tag in _EMBED_TAGS.items():
        if style not in files:
            continue
        key = f'{{{str(uuid.uuid4()).upper()}}}'
        part = Part(
            package.next_partname('/word/fonts/font%d.odttf'),
            _OBFUSCATED_FONT_CONTENT_TYPE,
            obfuscated(files[style].read_bytes(), key),
            package,
        )
        embedded = OxmlElement(tag)
        font.append(embedded)
        embedded.set(qn('r:id'), font_table.relate_to(part, RELATIONSHIP_TYPE.FONT))
        embedded.set(qn('w:fontKey'), key)
    font_table._blob = serialize_part_xml(fonts)
    _enable_embedded_fonts(document)


def _enable_embedded_fonts(document: Document) -> None:
    settings = document.settings.element
    if settings.find(qn('w:embedTrueTypeFonts')) is not None:
        return
    element = OxmlElement('w:embedTrueTypeFonts')
    successor = next(
        (child for child in settings if child.tag not in _SETTINGS_BEFORE_EMBEDDING),
        None,
    )
    if successor is None:
        settings.append(element)
    else:
        successor.addprevious(element)
