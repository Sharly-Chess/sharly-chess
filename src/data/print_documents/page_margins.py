from typing import Annotated

import msgspec

Margin = Annotated[float, msgspec.Meta(ge=0, le=100)]

DEFAULT_MARGIN = 72 * 10 / 25.4
"""The margin of the pages of a document that gives none: 10 mm, in points."""


class PageMargins(msgspec.Struct):
    """The margins of the pages a document prints on, in points."""

    top: Margin = DEFAULT_MARGIN
    right: Margin = DEFAULT_MARGIN
    bottom: Margin = DEFAULT_MARGIN
    left: Margin = DEFAULT_MARGIN
