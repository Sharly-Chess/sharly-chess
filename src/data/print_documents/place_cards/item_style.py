import logging
from typing import Optional

from common.logger import get_logger
from data.print_documents.place_cards.toml_container import TOMLContainer

logger: logging.Logger = get_logger()


class PlaceCardItemStyle:
    """A class to store the styles to apply to a place card item."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str,
        default_style: Optional['PlaceCardItemStyle'] = None,
    ):
        for property in data.get_section_properties(section):
            if property not in self.allowed_properties:
                logger.warning('Unknown property [%s], ignored.', property)
        self._font_size: float = data.get_float(
            section=section,
            property='font_size',
            default=default_style.font_size if default_style else 14.0,
        )
        self._bold: bool = data.get_bool(
            section=section,
            property='bold',
            default=default_style.bold if default_style else False,
        )
        self._italic: bool = data.get_bool(
            section=section,
            property='italic',
            default=default_style.italic if default_style else False,
        )
        self._h_align: str = data.get_str(
            section=section,
            property='h_align',
            default=default_style.h_align if default_style else 'left',
            values=['left', 'center', 'right'],
        )
        self._v_align: str = data.get_str(
            section=section,
            property='v_align',
            default=default_style.v_align if default_style else 'top',
            values=['top', 'middle', 'bottom'],
        )
        self._h_pos: float = data.get_float(
            section=section,
            property='h_pos',
            default=default_style.h_pos if default_style else 0.0,
        )
        self._v_pos: float = data.get_float(
            section=section,
            property='v_pos',
            default=default_style.v_pos if default_style else 0.0,
        )
        self._opacity: float = data.get_float(
            section=section,
            property='opacity',
            default=default_style.opacity if default_style else 1.0,
        )
        self._text_align: str = data.get_str(
            section=section,
            property='text_align',
            default=default_style.text_align if default_style else 'left',
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
    def allowed_properties(
        self,
    ) -> list[str]:
        return [
            'font_size',
            'bold',
            'italic',
            'h_align',
            'v_align',
            'h_pos',
            'v_pos',
            'opacity',
            'text_align',
        ]

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.font_size=}, {self.bold=}, {self.italic=}, {self.h_align=}, {self.h_pos=}, {self.v_align=}, {self.v_pos=}, {self.opacity=})'
