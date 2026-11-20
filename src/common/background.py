import base64
import binascii
from collections.abc import Sequence
from io import BytesIO
from logging import Logger
from pathlib import Path
from statistics import median_low

import validators
from PIL import Image

from common import CUSTOM_DIR, RGB, rgb_to_hexa
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig

logger: Logger = get_logger()

# At most this many pixels are read along each side of the image: enough to
# tell a bordered image from a photograph, cheap even on a full-size image.
BORDER_SAMPLES_PER_SIDE = 100
# Pixels this close to the border's median colour, on every channel, count as
# that colour: a JPEG leaves the pixels of a flat border a shade apart.
SAME_SHADE_DISTANCE = 16
# That colour has to cover at least this share of the border to be taken as
# the one the image is laid on.
MIN_DOMINANT_BORDER_SHARE = 0.6
# A border pixel more transparent than this is not read as a colour.
MIN_OPAQUE_ALPHA = 128


def inline_image_url(image: str | None) -> str:
    """
    :param image: an already true-URL (absolute or relative starting by '/')
    or the path of a custom file (a path relative to /custom is expected)
    :return: a true URL (data-inline if a file path is provided).
    If no file could be found, returns the error image.
    """
    if not image:
        return ''
    # A data: URI (an uploaded image stored inline) or a true URL is used as-is.
    if image.startswith(('/', 'data:')) or validators.url(image):
        return image
    file: Path = CUSTOM_DIR / image
    if not file.exists():
        logger.warning('Image [%s] not found.', file)
        return SharlyChessConfig.error_background_image
    with open(file, 'rb') as f:
        data: bytes = f.read()
    encoded_data = base64.b64encode(data).decode('utf-8')
    image_type = file.suffix.lower().replace('.', '').replace('\\n', '')
    if image_type == 'svg':
        return f'data:image/{image_type}+xml;base64,{encoded_data}'
    return f'data:image/{image_type};base64,{encoded_data}'


def inline_image_data(image: str) -> bytes | None:
    """The bytes an uploaded image's data: URI holds, or ``None`` when it
    holds nothing readable."""
    _, _, encoded = image.partition('base64,')
    try:
        return base64.b64decode(encoded, validate=True)
    except binascii.Error as e:
        logger.warning('Uploaded image not decoded: %s', e)
        return None


def _border_pixels(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """The RGBA pixels along the four sides of *image*, sampled evenly."""
    width, height = image.size
    edges = (
        image.crop((0, 0, width, 1)),
        image.crop((0, height - 1, width, height)),
        image.crop((0, 0, 1, height)),
        image.crop((width - 1, 0, width, height)),
    )
    pixels: list[tuple[int, int, int, int]] = []
    for edge in edges:
        # A one-pixel-wide strip, read as the RGBA bytes of its pixels.
        data = edge.tobytes()
        count = edge.width * edge.height
        for index in range(0, count, max(1, count // BORDER_SAMPLES_PER_SIDE)):
            red, green, blue, alpha = data[index * 4 : index * 4 + 4]
            pixels.append((red, green, blue, alpha))
    return pixels


def _shade_distance(pixel: tuple[int, int, int], color: tuple[int, int, int]) -> int:
    """How far *pixel* is from *color*, as its largest gap on a channel."""
    return max(
        abs(channel - reference)
        for channel, reference in zip(pixel, color, strict=True)
    )


def _average_color(pixels: Sequence[tuple[int, int, int]]) -> RGB:
    """The colour the given pixels average out to."""
    return RGB(
        *(round(sum(channel) / len(pixels)) for channel in zip(*pixels, strict=True))
    )


def border_color(image_data: bytes) -> str | None:
    """The colour the image held in *image_data* is laid on, read from its
    border pixels and returned in #rrggbb format.

    Returns ``None`` when no colour can be read: an image the imaging library
    does not open (an SVG, for one), a border left transparent, or a border
    holding no dominant colour (a photograph bleeding to its edges). The
    colour configured for the event is then the better background.
    """
    try:
        with Image.open(BytesIO(image_data)) as image:
            pixels = _border_pixels(image.convert('RGBA'))
    except Exception as e:
        # Whatever the imaging library makes of the bytes it is handed, an
        # image it cannot read simply has no colour to read: saving the
        # screen must not fail over it.
        logger.debug('No border colour read from the image: %s', e)
        return None
    opaque = [pixel[:3] for pixel in pixels if pixel[3] >= MIN_OPAQUE_ALPHA]
    if not opaque or len(opaque) < MIN_DOMINANT_BORDER_SHARE * len(pixels):
        return None
    # A border made of one colour has that colour on either side of its
    # median, whichever side the rest of the border falls on; the pixels
    # a shade away from the median are then that colour, and the border is
    # only taken as flat when they make up most of it.
    median = RGB(*(median_low(channel) for channel in zip(*opaque, strict=True)))
    flat = [
        pixel
        for pixel in opaque
        if _shade_distance(pixel, median) <= SAME_SHADE_DISTANCE
    ]
    if len(flat) < MIN_DOMINANT_BORDER_SHARE * len(opaque):
        return None
    return rgb_to_hexa(_average_color(flat))
