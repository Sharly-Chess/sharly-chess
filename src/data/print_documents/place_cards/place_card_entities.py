import logging
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path
from typing import Any, Optional

import toml
from toml import TomlDecodeError

from common import BASE_DIR
from common.i18n import _
from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.print_documents.place_cards.place_card_data import (
    PlaceCardEvent,
    PlaceCardTournament,
    PlaceCardPlayer,
    PlaceCardBoard,
)
from utils.file import image_file_inline_url, ttf_file_inline_url

logger: logging.Logger = get_logger()


class PlaceCardCustomDataContainer:
    """A class used to pass data to Jinja templates with methods to simply retrieve the data."""

    def __init__(
        self,
        toml_file: Path,
    ):
        self.toml_file = toml_file
        self.data: dict[str, str | int | float | dict[str, Any]] = {}
        self.error: str = ''
        try:
            self.data = toml.load(toml_file)
        except TomlDecodeError as tde:
            self.error = f'[{self.toml_file.name}]: {tde}'

    def get_field(
        self,
        property: str,
        section: str = '',
        default: Any | None = None,
        values: list[Any] | None = None,
    ) -> Any | None:
        if not property:
            logger.warning(
                '[%s]: no custom section or property provided, defaults to [%s].',
                self.toml_file.name,
                default,
            )
            return default
        value: str
        if section:
            try:
                section_data: str | int | float | bool | dict[str, Any] = self.data[
                    section
                ]
                if not isinstance(section_data, dict):
                    logger.debug(
                        '[%s]: [%s] is not a section, property [%s] defaults to [%s].',
                        self.toml_file.name,
                        section,
                        property,
                        default,
                    )
                    return default
                try:
                    value = section_data[property]
                except KeyError:
                    logger.debug(
                        '[%s]: custom property [%s] of section [%s] not found, defaults to [%s].',
                        self.toml_file.name,
                        property,
                        section,
                        default,
                    )
                    return default
            except KeyError:
                logger.debug(
                    '[%s]: custom section [%s] not found, property [%s] defaults to [%s].',
                    self.toml_file.name,
                    section,
                    property,
                    default,
                )
                return default
        else:
            try:
                value = str(self.data[property])
            except KeyError:
                logger.debug(
                    '[%s]: custom property [%s] not found, defaults to [%s].',
                    self.toml_file.name,
                    property,
                    default,
                )
                return default
        if value is None:
            logger.debug(
                '[%s]: section=%s, custom property [%s] not set, defaults to [%s].',
                self.toml_file.name,
                section,
                property,
                default,
            )
            return default
        if values and value not in values:
            if section:
                logger.warning(
                    '[%s]: value [%s] not accepted for custom property [%s] of section [%s] (accepted values: [%s]), defaults to  [%s].',
                    self.toml_file.name,
                    self.data[property],
                    property,
                    section,
                    ', '.join(values),
                    default,
                )
            else:
                logger.warning(
                    '[%s]: value [%s] not accepted for custom property [%s] (accepted values: [%s]), defaults to  [%s].',
                    self.toml_file.name,
                    self.data[property],
                    property,
                    ', '.join(values),
                    default,
                )
            return default
        else:
            return value

    def get_opt_str(
        self,
        property: str,
        section: str = '',
        default: str | None = None,
        values: list[str] | None = None,
    ) -> str | None:
        value = self.get_field(
            property=property, section=section, default=default, values=values
        )
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    def get_str(
        self,
        property: str,
        section: str = '',
        default: str | None = None,
        values: list[str] | None = None,
    ) -> str:
        value = self.get_field(
            property=property, section=section, default=default, values=values
        )
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        return str(value)

    def get_opt_bool(
        self,
        property: str,
        section: str = '',
        default: bool | None = None,
    ) -> bool | None:
        value = self.get_field(property=property, section=section, default=default)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        match value.lower():
            case 'true' | 'on':
                return True
            case 'false' | 'off':
                return False
            case _:
                logger.warning(
                    '[%s]: value [%s] not accepted for custom property [%s] (bool expected), defaults to [%s].',
                    self.toml_file.name,
                    value,
                    property,
                    default,
                )
                return default

    def get_bool(
        self,
        property: str,
        section: str = '',
        default: bool | None = None,
    ) -> bool:
        return (
            self.get_opt_bool(property=property, section=section, default=default)
            or False
        )

    def get_opt_int(
        self,
        property: str,
        section: str = '',
        default: int | None = None,
    ) -> int | None:
        value = self.get_field(property=property, section=section, default=default)
        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except ValueError:
            assert property is not None
            logger.warning(
                '[%s]: value [%s] not accepted for custom property [%s] (integer expected), defaults to [%s].',
                self.toml_file.name,
                value,
                property,
                default,
            )
            return default

    def get_int(
        self,
        property: str,
        section: str = '',
        default: int | None = None,
    ) -> int:
        return (
            self.get_opt_int(property=property, section=section, default=default) or 0
        )

    def get_opt_float(
        self,
        property: str,
        section: str = '',
        default: float | None = None,
    ) -> float | None:
        value = self.get_field(property=property, section=section, default=default)
        if value is None:
            return None
        if isinstance(value, float):
            return value
        try:
            return float(value)
        except ValueError:
            assert property is not None
            logger.warning(
                'Value [%s] not accepted for custom property [%s] (float expected), defaults to [%s].',
                self.toml_file.name,
                self.data[property],
                property,
                default,
            )
            return default

    def get_float(
        self,
        property: str,
        section: str = '',
        default: float | None = None,
    ) -> float:
        return (
            self.get_opt_float(property=property, section=section, default=default)
            or 0.0
        )

    def get_section_properties(
        self,
        section: str = '',
    ) -> list[str]:
        if section:
            if section not in self.data:
                return []
            if not isinstance(self.data[section], dict):
                return []
            return [
                key
                for key in self.data[section].keys()  # type: ignore
            ]
        else:
            return [
                key for key in self.data.keys() if not isinstance(self.data[key], dict)
            ]

    def get_sections(
        self,
    ) -> list[str]:
        return [key for key in self.data.keys() if isinstance(self.data[key], dict)]

    def delete_entries(
        self,
        entries: list[str],
        section: str = '',
    ):
        for property in entries:
            with suppress(KeyError):
                if (
                    section
                    and section in self.data
                    and isinstance(self.data[section], dict)
                ):
                    del self.data[section][property]  # type: ignore
                else:
                    del self.data[property]


class PlaceCardItemStyle:
    """A class to store the styles to apply to a place card item."""

    def __init__(
        self,
        data: PlaceCardCustomDataContainer,
        section: str,
        default_style: Optional['PlaceCardItemStyle'] = None,
    ):
        for property in data.get_section_properties(section):
            if property not in self.allowed_properties:
                logger.warning('Unknown property [%s], ignored.', property)
        self.font_size: float = data.get_float(
            section=section,
            property='font_size',
            default=default_style.font_size if default_style else 14.0,
        )
        self.bold: bool = data.get_bool(
            section=section,
            property='bold',
            default=default_style.bold if default_style else False,
        )
        self.italic: bool = data.get_bool(
            section=section,
            property='italic',
            default=default_style.italic if default_style else False,
        )
        self.h_align: str = data.get_str(
            section=section,
            property='h_align',
            default=default_style.h_align if default_style else 'left',
            values=['left', 'center', 'right'],
        )
        self.v_align: str = data.get_str(
            section=section,
            property='v_align',
            default=default_style.v_align if default_style else 'top',
            values=['top', 'middle', 'bottom'],
        )
        self.h_pos: float = data.get_float(
            section=section,
            property='h_pos',
            default=default_style.h_pos if default_style else 0.0,
        )
        self.v_pos: float = data.get_float(
            section=section,
            property='v_pos',
            default=default_style.v_pos if default_style else 0.0,
        )
        self.opacity: float = data.get_float(
            section=section,
            property='opacity',
            default=1.0,
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


class PlaceCardItem(PlaceCardItemStyle, ABC):
    """A class to store an item of a place card (style and content)."""

    def __init__(
        self,
        data: PlaceCardCustomDataContainer,
        section: str,
        default_style: PlaceCardItemStyle,
    ):
        self.id: str = section
        super().__init__(data, section, default_style)
        self.css_class: str = self.id.replace('_', '-')
        self.display: bool = data.get_bool(
            section=section, property='display', default=True
        )
        self.width: float = data.get_float(
            section=section,
            property='width',
            default=None,
        )
        self.height: float = data.get_float(
            section=section,
            property='height',
            default=None,
        )
        self.max_width: float | None = data.get_opt_float(
            section=section,
            property='max_width',
            default=None,
        )
        self.css: str = data.get_str(
            section=section,
            property='css',
            default='',
        )

    @property
    @abstractmethod
    def type(self) -> str:
        """Returns a string corresponding to the type of the item."""
        pass

    @property
    def allowed_properties(
        self,
    ) -> list[str]:
        return super().allowed_properties + [
            'display',
            'width',
            'height',
            'max_width',
            'css',
        ]

    def render_error(
        self,
        message: str,
    ) -> str:
        return f'<i class="bi bi-bug-fill"></i> {self.id}: {message}'

    @abstractmethod
    def render_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        """Returns the HTML to output for the item."""
        pass

    def render_css(
        self,
        unit: str,
    ) -> str:
        """Returns the CSS for the item."""
        div_css: list[str] = [
            f'font-size: {self.font_size}pt',
            f'font-weight: {"bold" if self.bold else "normal"}',
            f'font-style: {"italic" if self.italic else "normal"}',
            f'opacity: {self.opacity}',
        ]
        inner_css: list[str] = [
            # the font style must be set to inner elements to apply to the federation flags.
            f'font-size: {self.font_size}pt',
            f'font-weight: {"bold" if self.bold else "normal"}',
            f'font-style: {"italic" if self.italic else "normal"}',
        ]
        if self.width:
            div_css += [f'width: {self.width}{unit}']
        if self.height:
            div_css += [f'height: {self.height}{unit}']
        match self.h_align:
            case 'left':
                div_css += [
                    f'left: {self.h_pos}{unit}',
                    'text-align: left',
                ]
            case 'center':
                div_css += [
                    'width: 100%',
                    'text-align: center',
                ]
            case 'right':
                div_css += [
                    f'right: {self.h_pos}{unit}',
                    'text-align: right',
                ]
        match self.v_align:
            case 'top':
                div_css += [
                    f'top: {self.v_pos}{unit}',
                ]
            case 'middle':
                div_css += [
                    'width: 100%',
                    'text-align: center',
                ]
            case 'bottom':
                div_css += [
                    f'bottom: {self.v_pos}{unit}',
                ]
        if self.max_width is not None:
            div_css += [f'max-width: {self.max_width}{unit}']
        return (
            f'.{self.css_class} {{\n{"\n".join(f"{css_entry};" for css_entry in div_css)}\n}}\n'
            + f'.{self.css_class} * {{\n{"\n".join(f"{css_entry};" for css_entry in inner_css)}\n}}\n'
            + f'.{self.css_class} {{\n{self.css}\n}}\n'
        )

    def render_js(
        self,
    ) -> str:
        return ''


class PlaceCardText(PlaceCardItem):
    """A class to store a text item of a place card."""

    def __init__(
        self,
        data: PlaceCardCustomDataContainer,
        section: str,
        default_style: PlaceCardItemStyle,
    ):
        super().__init__(data, section, default_style)
        self.raw_text: str = data.get_str(
            section=section, property='text', default=_(f'[{self.id}]: No text.')
        )

    @property
    def type(self) -> str:
        return 'text'

    @property
    def allowed_properties(
        self,
    ) -> list[str]:
        return super().allowed_properties + [
            'text',
        ]

    def render_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        if not self.display:
            return ''
        content: str = parse_jinja_string(
            template_string=self.raw_text,
            context={
                'event': event,
                'tournament': tournament,
                'board': board,
                'player': player,
            },
            on_error=self.render_error('Jinja error'),
        )
        return (
            f'<div class="card-item {self.css_class}">{content}</div>'
            if self.display
            else ''
        )


class PlaceCardImage(PlaceCardItem):
    """A class to store an image item of a place card."""

    def __init__(
        self,
        data: PlaceCardCustomDataContainer,
        section: str,
        default_style: PlaceCardItemStyle,
        image_path: Path,
        unit: str,
    ):
        super().__init__(data, section, default_style)
        self.image: str = data.get_str(section=section, property='image')
        if not self.width and not self.height:
            self.width = self.height = 30.0 if unit == 'mm' else 1.0
            logger.warning(
                'Use [width] or [height] in section [%s] to size the image (defaults to %sx%s).',
                section,
                self.width,
                self.height,
            )
        self.image_path: Path = image_path

    @property
    def type(self) -> str:
        return 'image'

    @property
    def allowed_properties(
        self,
    ) -> list[str]:
        return super().allowed_properties + [
            'image',
        ]

    def render_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        return f'<img class="card-item image {self.css_class}" />'

    def render_js(
        self,
    ) -> str:
        file: Path = self.image_path / self.image
        error: bool = False
        if not file.parent.samefile(self.image_path):
            logger.warning('Invalid image filename [%s].', self.image)
            error = True
        elif not file.is_file():
            logger.warning('Image file [%s] not found.', file)
            error = True
        if error:
            return f"""
            $(document).ready(function() {{
                $(".card-item.{self.css_class}").addClass("error");
            }});
            """
        else:
            return f"""
            $(document).ready(function() {{
                $(".card-item.{self.css_class}").attr("src", "{image_file_inline_url(file)}");
            }});
            """


class PlaceCardTrueTypeFont(PlaceCardItem):
    """A class to store a font item of a place card."""

    def __init__(
        self,
        data: PlaceCardCustomDataContainer,
        section: str,
        default_style: PlaceCardItemStyle,
        font_path: Path,
    ):
        super().__init__(data, section, default_style)
        self.font: str = data.get_str(section=section, property='font')
        self.font_path: Path = font_path

    @property
    def type(self) -> str:
        return 'font'

    @property
    def allowed_properties(
        self,
    ) -> list[str]:
        return [
            'font',
        ]

    def render_inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        return ''

    def render_inner_css(
        self,
        unit: str,
    ) -> str:
        file: Path = self.font_path / self.font
        if not file.parent.samefile(self.font_path):
            logger.warning('Invalid font filename [%s].', self.font)
        elif not file.is_file():
            logger.warning('Font file [%s] not found.', file)
        return f"""
@font-face {{
    font-family: "{self.id}";
    src: url("{ttf_file_inline_url(file)}") format("truetype");
    /* font-weight: 400 900; */
}}
* {{
    font-family: {self.id}, sans-serif;
}}
"""


class PlaceCardTemplate:
    """A class representing the place cards templates."""

    def __init__(
        self,
        toml_file: Path,
    ):
        from data.print_documents import PrintPlaceCardTypeManager
        from data.print_documents.place_cards.place_card_types import (
            PlaceCardType,
            PlayerCardType,
        )

        self.embedded: bool = (
            toml_file.parent == SharlyChessConfig.embedded_place_cards_path
        )
        self.id: str = toml_file.stem
        custom_data = PlaceCardCustomDataContainer(toml_file)
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
