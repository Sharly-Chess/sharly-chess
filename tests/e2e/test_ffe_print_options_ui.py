import pytest
from playwright.sync_api import Page, expect, APIRequestContext
from tests.test_config import TestUtils


EVENT_ID = 'test-ffe-print-options-e2e'


@pytest.fixture(scope='module', autouse=True)
def setup(api_request_context: APIRequestContext):
    TestUtils.create_event(EVENT_ID, via_api_request_context=api_request_context)
    TestUtils.create_tournament(
        EVENT_ID, 'Open A', via_api_request_context=api_request_context
    )
    TestUtils.create_tournament(
        EVENT_ID, 'Open B', via_api_request_context=api_request_context
    )

    yield

    TestUtils.delete_event(EVENT_ID, via_api_request_context=api_request_context)


@pytest.mark.e2e
class TestFFEPrintOptions:
    @pytest.mark.parametrize(
        'ffe_document_type',
        [
            'ffe-training-certificate-afm',
            'ffe-training-certificate-afc',
            'ffe-training-certificate-afo',
        ],
    )
    def test_training_certificates_choose_the_tournaments(
        self, page: Page, ffe_document_type: str
    ):
        page.goto(f'/event/{EVENT_ID}')
        TestUtils.wait_for_htmx_bound(page, '#print-button button')
        page.locator('#print-button button').click()
        expect(page.locator('.print-modal #document')).to_be_attached()
        TestUtils.wait_for_htmx_idle(page)

        TestUtils.select_and_confirm(page.locator('#document'), 'ffe-document')
        TestUtils.select_and_confirm(
            page.locator('#ffe-document-type'), ffe_document_type
        )
        expect(page.locator('#tournaments_container')).to_be_visible()
        expect(page.locator('#tournament_container')).to_be_hidden()

    def test_training_certificate_is_for_the_chosen_tournaments(self, page: Page):
        page.goto(f'/event/{EVENT_ID}')
        TestUtils.wait_for_htmx_bound(page, '#print-button button')
        page.locator('#print-button button').click()
        expect(page.locator('.print-modal #document')).to_be_attached()
        TestUtils.wait_for_htmx_idle(page)
        tournament_ids = {
            option['text']: option['value']
            for option in page.locator('#tournament option').evaluate_all(
                'options => options.map(o => ({text: o.text, value: o.value}))'
            )
            if option['value']
        }

        page.goto(
            f'/document-view/{EVENT_ID}/ffe-document'
            '?options=ffe-document-type=ffe-training-certificate-afm'
            f'|tournaments={tournament_ids["Open B"]}'
        )
        expect(page.locator('#event-name')).to_have_value(f'{EVENT_ID} (Open B)')
