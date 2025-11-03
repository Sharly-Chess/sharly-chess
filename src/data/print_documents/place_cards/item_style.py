import logging

from common.logger import get_logger
from data.print_documents.place_cards.toml_container import TOMLContainer

logger: logging.Logger = get_logger()


class PlaceCardItemStyle:
    """A class to store the styles to apply to a place card item."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str,
        default_font_size: float | None = None,
        default_bold: bool | None = None,
        default_italic: bool | None = None,
        default_h_align: str | None = None,
        default_v_align: str | None = None,
        default_h_pos: float | None = None,
        default_v_pos: float | None = None,
        default_opacity: float | None = None,
    ):
        for property in data.get_section_properties(section):
            if property not in self.allowed_properties:
                logger.warning('Unknown property [%s], ignored.', property)
        self.font_size: float = data.get_float(
            section=section,
            property='font_size',
            default=default_font_size or 14.0,
        )
        self.bold: bool = data.get_bool(
            section=section,
            property='bold',
            default=default_bold or False,
        )
        self.italic: bool = data.get_bool(
            section=section,
            property='italic',
            default=default_italic or False,
        )
        self.h_align: str = data.get_str(
            section=section,
            property='h_align',
            default=default_h_align or 'left',
            values=['left', 'center', 'right'],
        )
        self.v_align: str = data.get_str(
            section=section,
            property='v_align',
            default=default_v_align or 'top',
            values=['top', 'middle', 'bottom'],
        )
        self.h_pos: float = data.get_float(
            section=section,
            property='h_pos',
            default=default_h_pos or 0.0,
        )
        self.v_pos: float = data.get_float(
            section=section,
            property='v_pos',
            default=default_v_pos or 0.0,
        )
        self.opacity: float = data.get_float(
            section=section,
            property='opacity',
            default=default_opacity or 1.0,
        )

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
        ]

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.font_size=}, {self.bold=}, {self.italic=}, {self.h_align=}, {self.h_pos=}, {self.v_align=}, {self.v_pos=}, {self.opacity=})'
