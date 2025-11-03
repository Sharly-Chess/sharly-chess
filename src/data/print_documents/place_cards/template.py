import logging
from pathlib import Path
from typing import Any

from common import BASE_DIR
from common.i18n import _
from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.print_documents.place_cards.item_style import PlaceCardItemStyle
from data.print_documents.place_cards.items import (
    PlaceCardItem,
    PlaceCardImage,
    PlaceCardText,
)
from data.print_documents.place_cards.toml_container import TOMLContainer
from utils.file import ttf_file_inline_url

logger: logging.Logger = get_logger()


class PlaceCardTemplate:
    """A class representing the place cards templates."""

    def __init__(
        self,
        toml_file: Path,
    ):
        from data.print_documents import PrintPlaceCardTypeManager
        from data.print_documents.place_cards.types import (
            PlaceCardType,
            PlayerCardType,
        )

        self.embedded: bool = (
            toml_file.parent == SharlyChessConfig.embedded_place_cards_path
        )
        self.id: str = toml_file.stem
        custom_data = TOMLContainer(toml_file)
        for property in custom_data.get_section_properties(''):
            match property:
                case (
                    'type'
                    | 'name'
                    | 'creator'
                    | 'unit'
                    | 'width'
                    | 'height'
                    | 'padding'
                    | 'cutting_marks'
                    | 'css'
                    | 'js'
                    | 'font'
                ):
                    pass
                case _:
                    logger.warning('Unknown property [%s], ignored.', property)
        self.type: PlaceCardType = PrintPlaceCardTypeManager().get_object(
            custom_data.get_str(
                'type',
                default=PlayerCardType.static_id(),
                values=PrintPlaceCardTypeManager().ids(),
            )
        )
        self.template_name: str = (
            f'/admin/print/place_cards/{self.type.static_id()}.html'
        )
        self.name: str = (
            parse_jinja_string(template_string=custom_data.get_str('name', default=''))
            or toml_file.stem
        )
        self.creator: str = custom_data.get_str('creator', default=_('Unknown'))
        self.unit: str = custom_data.get_str(
            'unit',
            default='mm',
            values=[
                'mm',
                'in',
            ],
        )
        self.width: float = custom_data.get_float('width', default=116.0)
        self.height: float = custom_data.get_float('height', default=36.0)
        self.padding: float = custom_data.get_float('padding', default=2.0)
        self.cutting_marks: str = custom_data.get_str(
            'cutting_marks', default='corners', values=['border', 'corners', 'none']
        )
        self.css: str = custom_data.get_str('css', default='')
        self.js: str = custom_data.get_str('js', default='')
        self.font: str = custom_data.get_str('font', default='')
        default_item_style: PlaceCardItemStyle = PlaceCardItemStyle(
            custom_data, section='default'
        )
        items: list[PlaceCardItem] = []
        for section in custom_data.get_sections():
            if section == 'default':
                pass
            elif 'image' in custom_data.get_section_properties(section):
                items.append(
                    PlaceCardImage(
                        custom_data,
                        section=section,
                        default_style=default_item_style,
                        image_path=BASE_DIR / 'src/web/static/images'
                        if self.embedded
                        else SharlyChessConfig.custom_place_cards_path / 'images',
                        unit=self.unit,
                    )
                )
            else:
                items.append(
                    PlaceCardText(
                        custom_data, section=section, default_style=default_item_style
                    )
                )
        self.items = [item for item in items if item.type == 'image'] + [
            item for item in items if item.type != 'image'
        ]
        self.error = custom_data.error

    @property
    def font_file(self) -> Path:
        default_file: Path = (
            BASE_DIR / 'src/web/static/fonts/AtkinsonHyperlegibleNextVF-Variable.ttf'
        )
        if not self.font:
            return default_file
        font_path: Path = SharlyChessConfig.custom_place_cards_path / 'fonts'
        file: Path = font_path / self.font
        if not file.parent.samefile(font_path):
            logger.warning('Invalid font filename [%s].', self.font)
            return default_file
        if not file.is_file():
            logger.warning('Font file [%s] not found.', file)
            return default_file
        return file

    @property
    def template_context(self) -> dict[str, Any]:
        file: Path = self.font_file
        font_css: str = f"""
@font-face {{
    font-family: "{file.stem}";
    src: url("{ttf_file_inline_url(file)}") format("truetype");
    /* font-weight: 400 900; */
}}
* {{
    font-family: {file.stem}, sans-serif;
}}
"""
        return {
            'error': self.error,
            'unit': self.unit,
            'creator': self.creator,
            'width': self.width,
            'height': self.height,
            'padding': self.padding,
            'cutting_marks': self.cutting_marks,
            'template_css': font_css + self.css,
            'template_js': self.js,
            'items': self.items,
        }

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.id=}, {self.embedded=}, {self.template_name=}, {self.creator=})'
