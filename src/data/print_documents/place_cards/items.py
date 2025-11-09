import copy
import logging
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from typing import Self
from PIL import Image

from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.print_documents.place_cards.data import (
    PlaceCardEvent,
    PlaceCardTournament,
    PlaceCardPlayer,
    PlaceCardBoard,
)
from data.print_documents.place_cards.item_style import PlaceCardItemStyle
from data.print_documents.place_cards.toml_container import TOMLContainer
from utils.file import image_file_inline_url

logger: logging.Logger = get_logger()


class PlaceCardItem(PlaceCardItemStyle, ABC):
    """A class to store an item of a place card (style and content)."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str,
        default_style: PlaceCardItemStyle,
    ):
        self.id: str = section
        super().__init__(
            data,
            section,
            default_style,
        )
        self.css_class: str = f'item-{self.id.replace("_", "-")}'
        self.display: bool = data.get_bool(
            section=section, property='display', default=True
        )
        self.width: float | None = data.get_float(
            section=section,
            property='width',
            default=None,
        )
        self.height: float | None = data.get_float(
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
        self.rotate: float | None = data.get_float(
            section=section,
            property='rotate',
            default=None,
        )
        self.back: bool = (
            data.get_str(
                section=section,
                property='side',
                default='front',
                values=[
                    'front',
                    'back',
                ],
            )
            == 'back'
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
            'rotate',
            'side',
            'css',
        ]

    def render_error(
        self,
        message: str,
    ) -> str:
        return f'<i class="bi bi-bug-fill"></i> {self.id}: {message}'

    def render_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        """Returns the HTML to output for the item."""
        return f'<div class="card-item-wrapper {self.css_class}">{self._inner_html(event, tournament, board, player)}</div>'

    @abstractmethod
    def _inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        """Returns the inner HTML of the item."""
        pass

    def _wrapper_css_properties(
        self,
    ) -> dict[str, str]:
        """Returns the CSS for the wrapper of the item."""
        wrapper_css: dict[str, str] = {
            'display': 'flex',
        }
        match self.h_align:
            case 'center':
                wrapper_css['justify-content'] = 'center'
        match self.v_align:
            case 'middle':
                wrapper_css['align-items'] = 'center'
        return wrapper_css

    def _item_css_properties(
        self,
        unit: str,
    ) -> dict[str, str]:
        """Returns the CSS for the item."""
        item_css: dict[str, str] = {
            'opacity': f'{self.opacity}',
        }
        # font-size must apply to subitems (for federation flags)
        if self.width:
            item_css['width'] = f'{self.width}{unit}'
        if self.height:
            item_css['height'] = f'{self.height}{unit}'
        match self.h_align:
            case 'left':
                item_css['left'] = f'{self.h_pos}{unit}'
                item_css['margin-right'] = 'auto'
            case 'center':
                item_css['margin-left'] = 'auto'
                item_css['margin-right'] = 'auto'
            case 'right':
                item_css['right'] = f'{self.h_pos}{unit}'
                item_css['margin-left'] = 'auto'
        match self.v_align:
            case 'top' | 'bottom':
                item_css['position'] = 'absolute'
                item_css[self.v_align] = f'{self.v_pos}{unit}'
        if self.max_width is not None:
            item_css['max-width'] = f'{self.max_width}{unit}'
        if self.rotate:
            item_css['transform'] = f'rotate({self.rotate}deg)'
        if self.background_color:
            item_css['background-color'] = self.background_color
        if self.color:
            item_css['color'] = self.color
        return item_css

    def _inner_css_properties(
        self,
        unit: str,
    ) -> dict[str, str]:
        """Returns the CSS for the children of the item."""
        inner_css: dict[str, str] = {}
        return inner_css

    def render_css(
        self,
        template_css_class: str,
        unit: str,
    ) -> str:
        """Returns the CSS to print for the item."""
        return (
            f'.{template_css_class} .card-item-wrapper.{self.css_class} {{\n{";\n".join(f"{key}: {value};" for key, value in self._wrapper_css_properties().items())}\n}}\n'
            + f'.{template_css_class} .{self.css_class} .card-item {{\n{";\n".join(f"{key}: {value};" for key, value in self._item_css_properties(unit).items())}\n}}\n'
            + f'.{template_css_class} .{self.css_class} .card-item * {{\n{";\n".join(f"{key}: {value};" for key, value in self._inner_css_properties(unit).items())}\n}}\n'
            + f'.{template_css_class} .{self.css_class} .card-item {{\n{self.css}\n}}\n'
        )

    def mirror(
        self,
        mirror_rotate: bool,
    ) -> Self:
        mirror_item: Self = copy.deepcopy(self)
        mirror_item.back = not self.back
        mirror_item.id = f'{self.id}_mirror'
        mirror_item.css_class = f'{self.css_class}-mirror'
        if not mirror_rotate:
            # real mirror mode (otherwise only rotate)
            match self.h_align:
                case 'left':
                    mirror_item._h_align = 'right'
                case 'right':
                    mirror_item._h_align = 'left'
            match self.text_align:
                case 'left':
                    mirror_item._text_align = 'right'
                case 'right':
                    mirror_item._text_align = 'left'
        return mirror_item


class PlaceCardText(PlaceCardItem):
    """A class to store a text item of a place card."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str,
        default_style: PlaceCardItemStyle,
    ):
        super().__init__(data, section, default_style)
        self.raw_text: str = data.get_str(
            section=section,
            property='text',
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

    def _inner_html(
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

    def _item_css_properties(
        self,
        unit: str,
    ) -> dict[str, str]:
        item_css: dict[str, str] = {
            'font-size': f'{self.font_size}pt',
            'font-weight': 'bold' if self.bold else 'normal',
            'font-style': 'italic' if self.italic else 'normal',
        }
        match self.text_align:
            case 'left' | 'center' | 'right' | 'auto':
                item_css['text-align'] = self.text_align
        return super()._item_css_properties(unit) | item_css

    def _inner_css_properties(
        self,
        unit: str,
    ) -> dict[str, str]:
        inner_css: dict[str, str] = {
            # the font style must be set to inner elements to apply to the federation flags.
            'font-size': f'{self.font_size}pt',
        }
        return super()._inner_css_properties(unit) | inner_css

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.raw_text=}, {self.back=})'


class PlaceCardImage(PlaceCardItem):
    """A class to store an image item of a place card."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str,
        default_style: PlaceCardItemStyle,
        images_path: list[Path],
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
        self.image_paths: list[Path] = images_path

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

    def _inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        return f'<img class="card-item image {self.css_class}" />'

    @cached_property
    def image_file(
        self,
    ) -> Path | None:
        if not (Path() / self.image).parent.samefile(Path()):
            logger.warning('Invalid image filename [%s].', self.image)
            return None
        for image_path in self.image_paths:
            file: Path = image_path / self.image
            if not file.is_file():
                logger.debug('Image file [%s] not found.', file)
                continue
            return file
        logger.warning('Image file [%s] not found.', self.image)
        return None

    def _item_css_properties(
        self,
        unit: str,
    ) -> dict[str, str]:
        image_file: Path = (
            self.image_file
            if self.image_file
            else SharlyChessConfig.embedded_place_cards_path
            / 'images/sharly-chess-logo.svg'
        )
        item_css: dict[str, str] = {
            'background-image': f'url("{image_file_inline_url(image_file)}")',
            'background-size': 'contain',
        }
        if not self.image_file:
            item_css['background-color'] = 'red'
        if self.width and self.height:
            width = self.width
            height = self.height
        else:
            image = Image.open(image_file)
            ratio: float = image.size[0] / image.size[1]
            if self.width:
                width = self.width
                height = self.width / ratio
            else:
                assert self.height
                width = self.height * ratio
                height = self.height
        item_css['width'] = f'{width}{unit}'
        item_css['height'] = f'{height}{unit}'

        return super()._item_css_properties(unit) | item_css

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.image=}, {self.back=})'
