"""The background fields of the form of an image screen.

The background of an image screen is what its image is laid on: a colour,
or a blurred copy of the image itself. Neither can be chosen before an
image is given, and the colour is of no use under a blur, so the form turns
off the fields that have nothing to describe yet.
"""

import base64

import pytest
from playwright.sync_api import APIRequestContext, Page, expect

from tests.test_config import TestUtils

EVENT_ID = 'event-test-image-screen-form'
IMAGE_URL = 'https://my.club.us/poster.jpg'
ONE_PIXEL_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4'
    'nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=='
)


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    yield
    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


# A file given the extension of an image and holding something else: the
# header of a database, as a file renamed poster.jpg would hand over.
NOT_AN_IMAGE = b'\x00\x01\x00\x00Standard Jet DB\x00'


@pytest.mark.e2e
class TestImageScreenFormBackground:
    @staticmethod
    def _open_creation_form(page: Page):
        page.goto(f'/event/{EVENT_ID}/screens')
        page.get_by_text('Create a screen').first.click()
        page.locator('[data-testid="create-screen-type-image"]').click()
        modal = page.locator('.modal-dialog')
        expect(modal).to_be_visible()
        # The form arrives with the swap the click started.
        TestUtils.wait_for_htmx_idle(page)
        return modal

    def test_the_background_fields_wait_for_an_image(self, page: Page):
        """With no image given, there is nothing to blur and nothing to lay
        the image on: the blur box, the colour and the colour read from the
        image are all turned off until an image is given, and again once it
        is taken away."""
        modal = self._open_creation_form(page)
        url = modal.locator('[name="background_image"]')
        blurred = modal.locator('[name="background_blurred"]')
        use_default = modal.locator('[name="background_color_checkbox"]')
        color = modal.locator('[name="background_color"]')
        from_image = modal.locator('#background-color-from-image')
        expect(blurred).to_be_disabled()
        expect(use_default).to_be_disabled()
        expect(color).to_be_disabled()
        expect(from_image).to_be_disabled()
        url.fill(IMAGE_URL)
        expect(blurred).to_be_enabled()
        expect(use_default).to_be_enabled()
        expect(from_image).to_be_enabled()
        # The colour of the event is used until the box is unchecked.
        expect(color).to_be_disabled()
        use_default.uncheck()
        expect(color).to_be_enabled()
        url.fill('')
        expect(blurred).to_be_disabled()
        expect(use_default).to_be_disabled()
        expect(color).to_be_disabled()
        expect(from_image).to_be_disabled()

    def test_a_blurred_background_makes_no_use_of_a_colour(self, page: Page):
        """A blur carries the image itself, so no colour is chosen and none
        is read from the image."""
        modal = self._open_creation_form(page)
        modal.locator('[name="background_image"]').fill(IMAGE_URL)
        use_default = modal.locator('[name="background_color_checkbox"]')
        color = modal.locator('[name="background_color"]')
        from_image = modal.locator('#background-color-from-image')
        use_default.uncheck()
        expect(color).to_be_enabled()
        blurred = modal.locator('[name="background_blurred"]')
        blurred.check()
        expect(use_default).to_be_disabled()
        expect(color).to_be_disabled()
        expect(from_image).to_be_disabled()
        blurred.uncheck()
        expect(use_default).to_be_enabled()
        expect(color).to_be_enabled()
        expect(from_image).to_be_enabled()

    def test_an_uploaded_image_turns_the_background_fields_on(self, page: Page):
        """An upload is written into a hidden field, which fires nothing of
        its own: the fields are told about it all the same."""
        modal = self._open_creation_form(page)
        modal.locator('#background-image-file').set_input_files(
            files=[
                {
                    'name': 'poster.png',
                    'mimeType': 'image/png',
                    'buffer': ONE_PIXEL_PNG,
                }
            ]
        )
        expect(modal.locator('[name="background_blurred"]')).to_be_enabled()
        expect(modal.locator('[name="background_color_checkbox"]')).to_be_enabled()
        expect(modal.locator('#background-color-from-image')).to_be_enabled()

    def test_a_file_that_is_no_image_is_refused(self, page: Page):
        """A file renamed with the extension of an image is handed over as an
        image by the browser: the form says so on the modal and keeps the
        background fields off, there being no image to describe."""
        modal = self._open_creation_form(page)
        modal.locator('#background-image-file').set_input_files(
            files=[
                {
                    'name': 'challenger.jpg',
                    'mimeType': 'image/jpeg',
                    'buffer': NOT_AN_IMAGE,
                }
            ]
        )
        alert = modal.locator('#background-image-alert')
        expect(alert).to_be_visible()
        expect(alert).to_contain_text('not an image')
        expect(modal.locator('[name="background_blurred"]')).to_be_disabled()
        expect(modal.locator('[name="background_color_checkbox"]')).to_be_disabled()
        expect(modal.locator('[name="background_color"]')).to_be_disabled()
        expect(modal.locator('#background-color-from-image')).to_be_disabled()
        expect(modal.locator('#background-image-preview')).to_be_hidden()
        # An image chosen afterwards leaves nothing of the error.
        modal.locator('#background-image-file').set_input_files(
            files=[
                {
                    'name': 'poster.png',
                    'mimeType': 'image/png',
                    'buffer': ONE_PIXEL_PNG,
                }
            ]
        )
        expect(alert).to_be_hidden()
        expect(modal.locator('[name="background_blurred"]')).to_be_enabled()

    def test_the_error_is_closed_by_its_cross_and_shown_again(self, page: Page):
        """The cross of the banner hides it; the next file that is no image
        shows it again, which taking it out of the form would not."""
        modal = self._open_creation_form(page)
        alert = modal.locator('#background-image-alert')
        for _closed in range(2):
            modal.locator('#background-image-file').set_input_files(
                files=[
                    {
                        'name': 'challenger.jpg',
                        'mimeType': 'image/jpeg',
                        'buffer': NOT_AN_IMAGE,
                    }
                ]
            )
            expect(alert).to_be_visible()
            alert.locator('.btn-close').click()
            expect(alert).to_be_hidden()
