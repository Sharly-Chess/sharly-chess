"""What a translation may take from its source string, and what it names
on its own.

A language does not always count what English counts — a knock-out round of
16 players is ``8es de finale`` in French — so a string can pass more values
than its own wording uses and say so in an ``i18n:`` comment. The letters an
ordinal raises are the language's own.
"""

from unittest.mock import patch

import pytest
from babel.messages.catalog import Message

from common.i18n.locale_info import DomainLocaleInfo
from web.settings import _ordinal_suffix_pattern, raise_ordinal_suffix_svg


def _raise_svg(value: str, suffixes: tuple[str, ...]) -> str:
    with patch('web.settings.ordinal_suffixes', return_value=suffixes):
        return str(raise_ordinal_suffix_svg(value))


def _tokens_match(msgid: str, msgstr: str, *comments: str) -> bool:
    message = Message(msgid, msgstr, auto_comments=list(comments))
    return DomainLocaleInfo.message_tokens_match(
        msgid, msgstr, DomainLocaleInfo.offered_tokens(message)
    )


@pytest.mark.unit
class TestMessageTokens:
    def test_without_an_offer_the_tokens_must_match(self):
        assert _tokens_match('Round of {count}', 'Tour à {count}')
        assert not _tokens_match('Round of {count}', '{matches}es de finale')

    def test_an_offered_token_may_replace_the_source_one(self):
        assert _tokens_match(
            'Round of {count}',
            '{matches}es de finale',
            'i18n: {matches} is the games the round plays.',
        )

    def test_a_token_nobody_offers_is_still_refused(self):
        assert not _tokens_match(
            'Round of {count}',
            '{rounds}es de finale',
            'i18n: {matches} is the games the round plays.',
        )


@pytest.mark.unit
class TestOrdinalSuffixPattern:
    """The letters raised over a number are the language's own — '8es de
    finale' in French, '1st' in English."""

    def test_the_longest_suffix_wins(self):
        pattern = _ordinal_suffix_pattern(('e', 'es', 'er'))
        assert pattern is not None
        assert pattern.sub(r'[\1]', '8es de finale') == '8[es] de finale'
        assert pattern.sub(r'[\1]', '1er tour') == '1[er] tour'

    def test_english_suffixes(self):
        pattern = _ordinal_suffix_pattern(('st', 'nd', 'rd', 'th'))
        assert pattern is not None
        assert (
            pattern.sub(r'[\1]', '1st, 2nd, 3rd, 4th') == '1[st], 2[nd], 3[rd], 4[th]'
        )

    def test_letters_of_their_own_are_left_alone(self):
        pattern = _ordinal_suffix_pattern(('st', 'nd', 'rd', 'th'))
        assert pattern is not None
        assert pattern.sub(r'[\1]', 'Round of 16') == 'Round of 16'

    def test_a_language_that_raises_none(self):
        assert _ordinal_suffix_pattern(()) is None


@pytest.mark.unit
class TestSvgOrdinalSuffix:
    """SVG text has no <sup>, so the suffix is lifted with a shifted tspan
    and the rest of the line brought back down to the baseline."""

    def test_the_line_returns_to_the_baseline(self):
        assert _raise_svg('8es de finale', ('es', 'e')) == (
            '8<tspan class="ordinal-sup" dy="-0.5em">es</tspan>'
            '<tspan dy="0.33em"> de finale</tspan>'
        )

    def test_a_label_without_an_ordinal_is_left_alone(self):
        assert _raise_svg('Quarterfinals', ('st', 'nd', 'rd', 'th')) == 'Quarterfinals'
