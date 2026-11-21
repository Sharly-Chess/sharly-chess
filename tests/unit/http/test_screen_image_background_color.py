"""The background colour an image screen takes from its image.

An image laid on a flat colour — a poster with a coloured border, a logo on
a white card — shows a band of the event's colour around it unless the
screen is given the same colour. The form of the screen offers to read that
colour from the image and fill the colour field with it, so that the arbiter
has nothing to match by hand; the field stays theirs, to change or to leave
on the colour of the event.

The image always answers with a colour: the colour of its border when it has
a flat one, the colour that covers most of its border when it has several,
and what its border averages out to when it bleeds to its edges. An image
left transparent all around itself, a logo, is read over its whole surface
instead.
"""

import base64
from collections.abc import Iterator
from io import BytesIO
from random import Random

import pytest
from PIL import Image, ImageDraw

from common import hexa_to_rgb
from common.background import image_background_color, inline_image_data
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.event.event_store import StoredScreen
from tests.test_config import ScreenType, TestUtils
from tests.unit.http.client import ApiClient
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-screen-image-color-http'
EVENT = EventUnderTest(EVENT_ID)
BORDER = (31, 61, 122)
BORDER_HEXA = '#1F3D7A'
OTHER_BORDER = (255, 255, 255)
# The colour a photograph of its own averages out to, its pixels being drawn
# at random over the whole range of each channel.
MID_GREY = (128, 128, 128)


def _bordered(color: tuple[int, int, int] = BORDER, format_: str = 'PNG') -> bytes:
    """A poster: a white sheet laid on a flat *color*, as every image
    screen the colour is read from."""
    image = Image.new('RGB', (400, 300), color)
    ImageDraw.Draw(image).rectangle((60, 40, 340, 260), fill=(255, 255, 255))
    return _data(image, format_)


def _photograph(size: tuple[int, int] = (200, 200)) -> bytes:
    """A photograph bleeding to its edges, which is laid on no colour."""
    return _data(_photograph_image(size))


def _photograph_image(size: tuple[int, int] = (200, 200)) -> Image.Image:
    random = Random(0)
    image = Image.new('RGB', size)
    image.putdata(
        [
            (random.randrange(256), random.randrange(256), random.randrange(256))
            for _ in range(size[0] * size[1])
        ]
    )
    return image


def _on_two_colors() -> bytes:
    """A photograph laid on two colours: half of its border is the first one,
    under a third of it the second one, and the rest the photograph itself."""
    image = _photograph_image((400, 400))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 399, 199), fill=BORDER)
    draw.rectangle((0, 360, 399, 399), fill=OTHER_BORDER)
    return _data(image)


def _data(image: Image.Image, format_: str = 'PNG') -> bytes:
    buffer = BytesIO()
    image.save(buffer, format_)
    return buffer.getvalue()


def _uploaded(image_data: bytes, media_type: str = 'image/png') -> str:
    """The image as the browser hands it to the form."""
    return f'data:{media_type};base64,{base64.b64encode(image_data).decode()}'


def _distance(hexa: str | None, color: tuple[int, int, int]) -> int:
    """How far a read colour is from the one the image was drawn with."""
    assert hexa is not None
    rgb = hexa_to_rgb(hexa)
    assert rgb is not None
    return max(abs(read - drawn) for read, drawn in zip(rgb, color, strict=True))


@pytest.mark.unit
class TestImageBackgroundColor:
    def test_a_flat_border_gives_its_colour(self):
        assert image_background_color(_bordered()) == BORDER_HEXA

    def test_the_artefacts_of_a_jpeg_border_are_averaged_out(self):
        """A JPEG leaves every pixel of a flat border a shade off, which
        reading the pixels around the border's median as one colour sees
        through."""
        assert _distance(image_background_color(_bordered(format_='JPEG')), BORDER) <= 4

    def test_an_image_laid_on_a_colour_on_two_sides_gives_that_colour(self):
        """A landscape photograph on a portrait screen is laid on the colour
        along its top and bottom only."""
        image = Image.new('RGB', (400, 600), BORDER)
        photograph = Image.open(BytesIO(_photograph()))
        image.paste(photograph.resize((400, 300)), (0, 150))
        assert image_background_color(_data(image)) == BORDER_HEXA

    def test_a_border_of_several_colours_gives_the_one_covering_most_of_it(self):
        """No colour is flat enough to be the one the image is laid on, so
        the shade that covers most of the border wins: the other colour and
        the photograph itself are each on less of it."""
        assert _distance(image_background_color(_on_two_colors()), BORDER) <= 8

    def test_a_photograph_gives_what_its_border_averages_out_to(self):
        """A photograph bleeding to its edges is laid on no colour of its
        own, and a colour is wanted all the same: its border averages out to
        the colour that shows the least around it."""
        assert _distance(image_background_color(_photograph()), MID_GREY) <= 30

    def test_an_image_transparent_around_itself_is_read_over_its_surface(self):
        """A logo on no background of its own says nothing along its border:
        the colour is read from the image itself."""
        image = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((50, 50, 150, 150), fill=(255, 0, 0, 255))
        assert image_background_color(_data(image)) == '#FF0000'

    def test_an_image_left_transparent_gives_no_colour(self):
        image = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
        assert image_background_color(_data(image)) is None

    def test_an_image_that_cannot_be_read_gives_no_colour(self):
        assert image_background_color(b'not an image') is None
        assert (
            image_background_color(b'<svg xmlns="http://www.w3.org/2000/svg"/>') is None
        )

    def test_an_uploaded_image_is_decoded(self):
        image_data = _bordered()
        assert inline_image_data(_uploaded(image_data)) == image_data

    def test_an_upload_that_is_not_base64_is_not_decoded(self):
        assert inline_image_data('data:image/png;base64,not base64 at all') is None


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create()
    yield EVENT_ID
    EVENT.delete()


def _create(api: ApiClient, name: str, **overrides: str) -> StoredScreen:
    return TestUtils.create_screen(api, EVENT_ID, name, ScreenType.IMAGE, overrides)


def _update(api: ApiClient, screen: StoredScreen, **overrides: str) -> StoredScreen:
    """The screen's form, submitted again with *overrides*."""
    assert screen.id is not None
    data: dict[str, object] = {'name': screen.name, 'public': True}
    data |= overrides
    response = api.patch(
        f'/screen-update/{EVENT_ID}/{screen.id}',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data=TestUtils.prepare_form_data(data),
    )
    TestUtils.check_api_response(response)
    with EventDatabase(EVENT_ID) as database:
        stored_screen = database.get_stored_screen(screen.id)
    assert stored_screen is not None
    return stored_screen


def _read_color(api: ApiClient, **image: str) -> str:
    """What the button of the form reads from the image it is given."""
    response = api.post(
        f'/screen-image-color/{EVENT_ID}',
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data=TestUtils.prepare_form_data(dict(image)),
    )
    TestUtils.check_api_response(response)
    return response.text()


@pytest.mark.unit
class TestImageScreenBackgroundColor:
    def test_the_colour_of_an_uploaded_image_is_read(self, api: ApiClient, event: str):
        assert _read_color(api, background_image_upload=_uploaded(_bordered())) == (
            BORDER_HEXA
        )

    def test_a_photograph_reads_as_a_colour_of_its_own(
        self, api: ApiClient, event: str
    ):
        """A photograph bleeding to its edges is laid on no colour, and the
        form is answered with a colour all the same."""
        read = _read_color(api, background_image_upload=_uploaded(_photograph()))
        assert _distance(read, MID_GREY) <= 30

    def test_an_image_that_cannot_be_read_reads_as_nothing(
        self, api: ApiClient, event: str
    ):
        """Nothing is answered only when there is no image to read."""
        assert (
            _read_color(api, background_image_upload='data:image/png;base64,??') == ''
        )
        assert _read_color(api, background_image='not a URL') == ''
        assert _read_color(api) == ''

    def test_a_colour_chosen_by_hand_is_kept(self, api: ApiClient, event: str):
        """The colour read from an image is set in the form, and saved as any
        other colour the arbiter chooses."""
        stored_screen = _create(
            api,
            'Poster',
            background_image_upload=_uploaded(_bordered()),
            background_color=BORDER_HEXA,
        )
        assert stored_screen.background_color == BORDER_HEXA
        stored_screen = _update(
            api,
            stored_screen,
            background_image_upload=_uploaded(_bordered()),
            background_color='#ABCDEF',
        )
        assert stored_screen.background_color == '#ABCDEF'

    def test_a_screen_saved_without_a_colour_keeps_the_event_colour(
        self, api: ApiClient, event: str
    ):
        stored_screen = _create(
            api,
            'Poster',
            background_image_upload=_uploaded(_bordered()),
            background_color_checkbox='on',
        )
        assert stored_screen.background_color is None


@pytest.mark.unit
class TestImageScreenBlurredBackground:
    """An image laid blurred behind itself fills the screen, which then makes
    no use of a background colour. Unlike the box that reads the colour, this
    one is a setting of the screen and is kept with it."""

    def test_the_background_is_not_blurred_by_default(self, api: ApiClient, event: str):
        stored_screen = _create(
            api, 'Poster', background_image_upload=_uploaded(_bordered())
        )
        assert stored_screen.background_blurred is False

    def test_the_box_blurs_the_background_and_is_kept(self, api: ApiClient, event: str):
        image = _uploaded(_bordered())
        stored_screen = _create(
            api, 'Poster', background_image_upload=image, background_blurred='on'
        )
        assert stored_screen.background_blurred is True
        stored_screen = _update(api, stored_screen, background_image_upload=image)
        assert stored_screen.background_blurred is False

    def test_the_colour_waits_under_the_blur(self, api: ApiClient, event: str):
        """The form disables the fields of the colour while the blur hides it,
        so they are not submitted; the colour is kept all the same, and the
        screen shows it again once the blur is unticked."""
        image = _uploaded(_bordered())
        stored_screen = _create(
            api, 'Poster', background_image_upload=image, background_color='#ABCDEF'
        )
        stored_screen = _update(
            api, stored_screen, background_image_upload=image, background_blurred='on'
        )
        assert stored_screen.background_blurred is True
        assert stored_screen.background_color == '#ABCDEF'
        stored_screen = _update(
            api,
            stored_screen,
            background_image_upload=image,
            background_color='#ABCDEF',
        )
        assert stored_screen.background_blurred is False
        assert stored_screen.background_color == '#ABCDEF'
