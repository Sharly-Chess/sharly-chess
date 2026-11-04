"""Functions called by the templates that a large page calls thousands of
times, written in Python rather than as macros."""

import re
import typing as t

from markupsafe import Markup, escape

from common.i18n import gettext

_TOOLTIP_KINDS = ('info', 'warning', 'error')


def tooltip_attributes(
    tooltip_type: str, tooltip_text: str, tooltip_placement: str | None = 'top'
) -> Markup:
    """The attributes of an element that shows a tooltip. The style, the icon
    and the markup of the tooltip are added by the browser (base.js) from the
    kind named in data-sc-tooltip; the placement is written only when it is
    not the default one, on top."""
    kind = tooltip_type if tooltip_type in _TOOLTIP_KINDS else ''
    attributes = (
        f'data-bs-toggle="tooltip" data-sc-tooltip="{kind}"'
        if kind
        else 'data-bs-toggle="tooltip" data-sc-tooltip'
    )
    if tooltip_placement and tooltip_placement != 'top':
        attributes += f' data-bs-placement="{escape(tooltip_placement)}"'
    return Markup(f'{attributes} data-bs-title="{escape(tooltip_text)}"')


_HTML_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)


def compact_html(html: str) -> Markup:
    """Markup with its comments dropped and its runs of spaces brought down to
    one, for the parts of a page repeated hundreds of times. Not for markup
    holding scripts, <pre> or <textarea>, where spacing counts."""
    return Markup(' '.join(_HTML_COMMENT.sub('', str(html)).split()))


class RecordMark(t.NamedTuple):
    """One square of a player's record: what it shows, its colours and its
    tooltip."""

    text: str
    css_class: str = ''
    tooltip: str | None = None


def player_record_marks(player: t.Any) -> list[RecordMark]:
    """The squares of a player's record, one per round."""
    marks: list[RecordMark] = []
    for pairing in player.single_tournament_player.pairings.values():
        box = 'player-record-white' if pairing.color == 'W' else 'player-record-black'
        if pairing.zero_point_bye:
            mark = RecordMark(
                Markup('<i class="bi bi-0-circle-fill"></i>'),
                'text-secondary',
                gettext('Zero-Point Bye'),
            )
        elif pairing.needs_pairing:
            mark = RecordMark('', 'text-secondary')
        elif pairing.paired_no_result:
            mark = RecordMark(Markup('&nbsp;'), box)
        elif pairing.exempt:
            mark = RecordMark('+', tooltip=gettext('Pairing Allocated Bye'))
        elif pairing.loss:
            mark = RecordMark(
                'L' if pairing.unrated_loss else '0',
                box,
                gettext('Unrated Loss') if pairing.unrated_loss else gettext('Loss'),
            )
        elif pairing.draw:
            mark = RecordMark(
                'D' if pairing.unrated_draw else '=',
                box,
                gettext('Unrated Draw') if pairing.unrated_draw else gettext('Draw'),
            )
        elif pairing.win:
            mark = RecordMark(
                'W' if pairing.unrated_gain else '1',
                box,
                gettext('Unrated Win') if pairing.unrated_gain else gettext('Win'),
            )
        elif pairing.half_point_bye:
            mark = RecordMark(
                Markup('<i class="bi bi-circle-half"></i>'),
                'text-secondary',
                gettext('Half-Point Bye'),
            )
        elif pairing.full_point_bye:
            mark = RecordMark(
                Markup('<i class="bi bi-1-circle-fill"></i>'),
                'text-secondary',
                gettext('Full-Point Bye'),
            )
        elif pairing.forfeit_loss or pairing.double_forfeit:
            mark = RecordMark('-', box, gettext('Forfeit Loss'))
        elif pairing.forfeit_gain:
            mark = RecordMark('+', box, gettext('Forfeit Win'))
        else:
            mark = RecordMark('?', 'player-record-unknown')
        marks.append(mark)
    return marks
