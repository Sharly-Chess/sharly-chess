"""The component gallery shows every admin component, and their text reads
against its background in both themes."""

import pytest
from playwright.sync_api import Page, expect

# For each visible element holding text of its own, outside disabled controls
# (which WCAG leaves out), the contrast ratio of its colour over the
# backgrounds behind it, semi-transparent ones composited on the first opaque
# one below them.
_LOW_CONTRAST_SCRIPT = """
() => {
    const parse = (value) => {
        const match = value.match(/rgba?\\(([^)]+)\\)/);
        if (!match) return [0, 0, 0, 0];
        const parts = match[1].split(/[\\s,/]+/).filter(Boolean).map(Number);
        return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
    };
    const over = (top, bottom) => {
        const alpha = top[3] + bottom[3] * (1 - top[3]);
        if (alpha === 0) return [0, 0, 0, 0];
        const mix = (i) =>
            (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / alpha;
        return [mix(0), mix(1), mix(2), alpha];
    };
    const background = (element) => {
        const layers = [];
        for (let node = element; node; node = node.parentElement) {
            const colour = parse(getComputedStyle(node).backgroundColor);
            if (colour[3] > 0) layers.push(colour);
            if (colour[3] >= 1) break;
        }
        let result = parse(getComputedStyle(document.body).backgroundColor);
        if (result[3] < 1) result = [255, 255, 255, 1];
        for (const layer of layers.reverse()) result = over(layer, result);
        return result;
    };
    const luminance = ([r, g, b]) => {
        const channel = (value) => {
            const c = value / 255;
            return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        };
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };
    const failures = [];
    for (const element of document.querySelectorAll('#component-gallery *')) {
        const ownText = [...element.childNodes]
            .filter((node) => node.nodeType === Node.TEXT_NODE)
            .map((node) => node.textContent.trim())
            .join('');
        if (!ownText) continue;
        if (element.closest(':disabled, [disabled], .disabled')) continue;
        const style = getComputedStyle(element);
        const box = element.getBoundingClientRect();
        if (style.visibility === 'hidden' || box.width === 0 || box.height === 0) {
            continue;
        }
        const back = background(element);
        const fore = over(parse(style.color), back);
        const [light, dark] = [luminance(fore), luminance(back)].sort((a, b) => b - a);
        const ratio = (light + 0.05) / (dark + 0.05);
        const size = parseFloat(style.fontSize);
        const large = size >= 24 || (size >= 18.66 && Number(style.fontWeight) >= 700);
        const minimum = large ? 3 : 4.5;
        if (ratio < minimum) {
            const where = element.closest('[data-gallery-sample], section');
            failures.push(
                `${(where && (where.dataset.gallerySample || where.id)) || '?'}: `
                + `"${ownText.slice(0, 40)}" ${ratio.toFixed(2)} < ${minimum}`
            );
        }
    }
    return failures;
}
"""


@pytest.mark.e2e
class TestComponentGallery:
    @pytest.mark.parametrize('theme', ['light', 'dark'])
    def test_text_contrast(self, page: Page, theme: str) -> None:
        page.goto('/dev/components')
        expect(page.locator('#component-gallery')).to_be_visible()
        # Colours ease from one theme to the other; read them once settled.
        page.add_style_tag(content='* { transition: none !important; }')
        page.evaluate(
            'theme => { window.scRequestedTheme = theme; window.scApplyTheme(); }',
            theme,
        )
        expect(page.locator('body')).to_have_attribute('data-bs-theme', theme)
        assert page.evaluate(_LOW_CONTRAST_SCRIPT) == []

    def test_every_section_is_shown(self, page: Page) -> None:
        page.goto('/dev/components')
        for section in [
            'buttons',
            'menus',
            'notes',
            'badges',
            'banners',
            'empty-states',
            'modals',
        ]:
            expect(page.locator(f'#gallery-{section}')).to_be_visible()
        expect(page.locator('#gallery-modals .modal-dialog')).to_have_count(3)
