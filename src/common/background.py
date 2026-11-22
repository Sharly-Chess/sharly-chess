import base64
import binascii
from collections import Counter
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
# The side of the grid the whole image is read on, when its border says
# nothing of the background: a 64 x 64 sample describes the colours of an
# image well enough and costs nothing to walk through.
IMAGE_SAMPLES_PER_SIDE = 64
# Pixels this close to the border's median colour, on every channel, count as
# that colour: a JPEG leaves the pixels of a flat border a shade apart.
SAME_SHADE_DISTANCE = 16
# That colour has to cover at least this share of the pixels to be taken as
# the one they are made of.
MIN_FLAT_SHARE = 0.6
# The number of shades the pixels are sorted into to find the dominant one of
# an image that is laid on no flat colour.
QUANTIZED_SHADES = 16
# A shade has to cover at least this share of the pixels to pass as their
# dominant colour; under that, they are averaged out instead.
MIN_DOMINANT_SHADE_SHARE = 0.35
# A pixel more transparent than this is not read as a colour.
MIN_OPAQUE_ALPHA = 128
# The media types of the images the browser draws but the imaging library does
# not open: a drawing, which is text rather than pixels.
VECTOR_MEDIA_TYPES = ('image/svg+xml',)
# A border has to be opaque over at least this share of itself to say what the
# image is laid on: what shows through a transparent border is the background.
MIN_OPAQUE_BORDER_SHARE = 0.6
# An image, on the other hand, is read wherever it holds ink, a logo being
# transparent all around itself; under this share it is read as transparent.
MIN_OPAQUE_IMAGE_SHARE = 0.05


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


def uploaded_image_is_an_image(image: str) -> bool:
    """Whether the data: URI *image* holds an image at all: a file given the
    extension of an image is handed over as one by the browser, and a
    database renamed poster.jpg is no image.

    A drawing is taken on its media type, the imaging library not opening
    one; anything else has to be opened to pass.
    """
    media_type = image.removeprefix('data:').partition(';')[0]
    if not media_type.startswith('image/'):
        return False
    if media_type in VECTOR_MEDIA_TYPES:
        return True
    data = inline_image_data(image)
    if not data:
        return False
    try:
        # The header alone tells an image from a file that is none, and the
        # pixels are left unread: an image missing its last bytes is still an
        # image, and the browser draws what it holds.
        with Image.open(BytesIO(data)):
            pass
    except Exception as e:
        logger.debug('Uploaded image is no image: %s', e)
        return False
    return True


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


def _image_pixels(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """The RGBA pixels of *image* read on a small grid: the whole of its
    surface rather than its sides."""
    width, height = image.size
    grid = image.resize(
        (min(width, IMAGE_SAMPLES_PER_SIDE), min(height, IMAGE_SAMPLES_PER_SIDE)),
        # Nearest neighbour keeps the colours of the image as they are:
        # another filter blends them, transparent pixels included, and makes
        # up colours the image does not hold.
        Image.Resampling.NEAREST,
    )
    data = grid.tobytes()
    return [
        (data[index], data[index + 1], data[index + 2], data[index + 3])
        for index in range(0, len(data), 4)
    ]


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


def _flat_color(pixels: Sequence[tuple[int, int, int]]) -> RGB | None:
    """The one colour the given pixels are made of, when most of them are a
    shade of it, as a JPEG leaves a flat border. ``None`` when they hold more
    than one colour.

    Pixels made of one colour have that colour on either side of their
    median, whichever side the rest of them falls on; those a shade away from
    the median are then that colour, and they are only read as flat when they
    make up most of the pixels.
    """
    median = RGB(*(median_low(channel) for channel in zip(*pixels, strict=True)))
    flat = [
        pixel
        for pixel in pixels
        if _shade_distance(pixel, median) <= SAME_SHADE_DISTANCE
    ]
    if len(flat) < MIN_FLAT_SHARE * len(pixels):
        return None
    return _average_color(flat)


def _dominant_color(pixels: Sequence[tuple[int, int, int]]) -> RGB | None:
    """The colour the given pixels mostly fall on, their shades sorted into a
    small palette: the blue of a sky, the green of a lawn. ``None`` when no
    shade stands out among the others.
    """
    strip = Image.new('RGB', (len(pixels), 1))
    strip.putdata(pixels)
    shades = list(strip.quantize(colors=QUANTIZED_SHADES).getdata())
    shade, count = Counter(shades).most_common(1)[0]
    if count < MIN_DOMINANT_SHADE_SHARE * len(pixels):
        return None
    # A shade of the palette stands for a range of colours: the pixels it
    # holds are averaged out rather than read off the palette itself.
    return _average_color(
        [
            pixel
            for pixel, pixel_shade in zip(pixels, shades, strict=True)
            if pixel_shade == shade
        ]
    )


def _laid_on_color(
    pixels: Sequence[tuple[int, int, int, int]], min_opaque_share: float
) -> RGB | None:
    """The colour the given pixels read as: the flat colour they are made of,
    or the dominant shade of a sky or a lawn, or what they all average out to.

    Returns ``None`` only when fewer than *min_opaque_share* of them are
    opaque: what shows through a transparent image is the background itself.
    """
    opaque = [pixel[:3] for pixel in pixels if pixel[3] >= MIN_OPAQUE_ALPHA]
    if not opaque or len(opaque) < min_opaque_share * len(pixels):
        return None
    return _flat_color(opaque) or _dominant_color(opaque) or _average_color(opaque)


def image_background_color(image_data: bytes) -> str | None:
    """The colour the image held in *image_data* is laid on, in #rrggbb
    format: the colour of its border, or, when its border says nothing of the
    background, the colour of the image itself.

    Returns ``None`` only when the image holds no colour to read: one the
    imaging library does not open (an SVG, for one) or one left transparent.
    The colour configured for the event is then the better background.
    """
    try:
        with Image.open(BytesIO(image_data)) as image:
            rgba = image.convert('RGBA')
            # The border is where the image meets the background, so that no
            # band of another colour shows around it. A border left
            # transparent says nothing of the background, and the image is
            # then read over its whole surface instead.
            color = _laid_on_color(
                _border_pixels(rgba), MIN_OPAQUE_BORDER_SHARE
            ) or _laid_on_color(_image_pixels(rgba), MIN_OPAQUE_IMAGE_SHARE)
    except Exception as e:
        # Whatever the imaging library makes of the bytes it is handed, an
        # image it cannot read simply has no colour to read: saving the
        # screen must not fail over it.
        logger.debug('No background colour read from the image: %s', e)
        return None
    return rgb_to_hexa(color) if color else None
