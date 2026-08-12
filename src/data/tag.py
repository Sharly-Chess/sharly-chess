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
from common.i18n import _

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


@dataclass(frozen=True)
class TagSet:
    """A ready-made group of tags, offered while the registry is still empty
    so that an installation can be labelled without inventing everything.
    Its tags carry no id: they are proposals until the user takes them."""

    id: str
    name: str
    tags: list[Tag]


def default_tag_sets() -> list[TagSet]:
    """The sets proposed on an empty registry.

    Built on each call rather than held as a constant, so that the names
    follow the locale in use."""
    return [
        TagSet(
            id='time_control',
            name=_('Time control'),
            tags=[
                Tag(id=0, name=_('Standard'), color='#E100FF'),
                Tag(id=0, name=_('Rapid'), color='#EF75FF'),
                Tag(id=0, name=_('Blitz'), color='#FEB3FF'),
            ],
        ),
        TagSet(
            id='participants',
            name=_('Participants'),
            tags=[
                Tag(id=0, name=_('Open *** EVENT TAG NAME'), color='#008000'),
                Tag(id=0, name=_('Women *** EVENT TAG NAME'), color='#3E7F3E'),
                Tag(id=0, name=_('Youth *** EVENT TAG NAME'), color='#558255'),
            ],
        ),
        TagSet(
            id='organiser',
            name=_('Organiser'),
            tags=[
                Tag(id=0, name=_('Federation'), color='#0000FF'),
                Tag(id=0, name=_('League *** EVENT TAG NAME'), color='#4545FF'),
                Tag(id=0, name=_('Department *** EVENT TAG NAME'), color='#7D7DFF'),
                Tag(id=0, name=_('Club'), color='#B8B8FF'),
            ],
        ),
    ]
