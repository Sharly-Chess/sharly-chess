import logging
from typing import Optional, TYPE_CHECKING

from common.logger import get_logger
from data.print_documents.place_cards.toml_container import TOMLContainer

if TYPE_CHECKING:
    from data.print_documents.place_cards.template import PlaceCardTemplate


logger: logging.Logger = get_logger()


class PlaceCardItemStyle:
    """A class to store the styles to apply to a place card item."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str = '',
        template: Optional['PlaceCardTemplate'] = None,
    ):
        for prop in data.get_section_properties(section):
            if prop not in self.allowed_properties():
                logger.warning('Unknown property [%s], ignored.', prop)
        self._font_size: float = data.get_float(
            section=section,
            property='font_size',
            default=template.font_size if template else 14.0,
        )
        self._bold: bool = data.get_bool(
            section=section,
            property='bold',
            default=template.bold if template else False,
        )
        self._italic: bool = data.get_bool(
            section=section,
            property='italic',
            default=template.italic if template else False,
        )
        self._h_align: str = data.get_str(
            section=section,
            property='h_align',
            default=template.h_align if template else 'left',
            values=['left', 'center', 'right'],
        )
        self._v_align: str = data.get_str(
            section=section,
            property='v_align',
            default=template.v_align if template else 'top',
            values=['top', 'middle', 'bottom'],
        )
        self._h_pos: float = data.get_float(
            section=section,
            property='h_pos',
            default=template.h_pos if template else 0.0,
        )
        self._v_pos: float = data.get_float(
            section=section,
            property='v_pos',
            default=template.v_pos if template else 0.0,
        )
        self._opacity: float = data.get_float(
            section=section,
            property='opacity',
            default=template.opacity if template else 1.0,
        )
        self._color: str = data.get_str(
            section=section,
            property='color',
            default=template.color if template else '',
        )
        self._background_color: str = data.get_str(
            section=section,
            property='background_color',
            default=template.background_color if template else '',
        )
        self._text_align: str = data.get_str(
            section=section,
            property='text_align',
            default=template.text_align if template else 'left',
            values=['left', 'center', 'right'],
        )

    @property
    def font_size(self) -> float:
        return self._font_size

    @property
    def bold(self) -> bool:
        return self._bold

    @property
    def italic(self) -> bool:
        return self._italic

    @property
    def h_align(self) -> str:
        return self._h_align

    @property
    def v_align(self) -> str:
        return self._v_align

    @property
    def h_pos(self) -> float:
        return self._h_pos

    @property
    def v_pos(self) -> float:
        return self._v_pos

    @property
    def opacity(self) -> float:
        return self._opacity

    @property
    def text_align(self) -> str:
        return self._text_align

    @property
    def color(self) -> str:
        return self._color

    @property
    def background_color(self) -> str:
        return self._background_color

    def allowed_properties(
        self,
    ) -> set[str]:
        return {
            'font_size',
            'bold',
            'italic',
            'h_align',
            'v_align',
            'h_pos',
            'v_pos',
            'opacity',
            'color',
            'background_color',
            'text_align',
        }

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.font_size=}, {self.bold=}, {self.italic=}, {self.h_align=}, {self.h_pos=}, {self.v_align=}, {self.v_pos=}, {self.opacity=})'
