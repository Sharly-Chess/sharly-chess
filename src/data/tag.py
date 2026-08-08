"""Event tags.

A *tag* is a free label — "regional", "youth", "rapid"... — that events can
be given to organise and filter the event lists. Tags are global to the
installation (they live in the config database) and events reference them by
id, so renaming an event never loses its tags.

Ids only mean something within an installation: they are stripped when an
event is exported to, or imported from, a ``.sce`` file. An id that no longer
resolves (a tag deleted while events still referenced it) is simply ignored.
"""

from dataclasses import dataclass
from functools import cached_property

from common import hexa_to_rgb

DEFAULT_TAG_COLOR: str = '#6C757D'


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    color: str = DEFAULT_TAG_COLOR

    @cached_property
    def text_color(self) -> str:
        """Black or white, whichever reads better on ``color``. Tag colours
        are picked freely by the user, so the badge label has to adapt."""
        rgb = hexa_to_rgb(self.color)
        if rgb is None:
            return '#FFFFFF'
        red, green, blue = rgb
        # Perceived brightness (ITU-R BT.601 luma), 0-255.
        luma = 0.299 * red + 0.587 * green + 0.114 * blue
        return '#000000' if luma > 150 else '#FFFFFF'

    @property
    def form_key(self) -> str:
        return str(self.id)
