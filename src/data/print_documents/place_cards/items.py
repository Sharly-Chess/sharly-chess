import copy
import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from typing import Self, TYPE_CHECKING
from xml.etree.ElementTree import ElementTree

from PIL import Image, UnidentifiedImageError

from common import BASE_DIR
from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
from data.print_documents.place_cards.data import (
    PlaceCardEvent,
    PlaceCardTournament,
    PlaceCardPlayer,
    PlaceCardBoard,
    PlaceCardPairing,
    PlaceCardTeam,
)
from data.print_documents.place_cards.item_style import PlaceCardItemStyle
from data.print_documents.place_cards.toml_container import TOMLContainer
from utils.file import image_file_inline_url

if TYPE_CHECKING:
    from data.print_documents.place_cards.template import PlaceCardTemplate


logger: logging.Logger = get_logger()


class PlaceCardItem(PlaceCardItemStyle, ABC):
    """A class to store an item of a place card (style and content)."""

    def __init__(
        self,
        data: TOMLContainer,
        section: str,
        template: 'PlaceCardTemplate',
    ):
        self.id: str = section
        super().__init__(
            data,
            section,
            template,
        )
        self.css_class: str = f'item-{self.id.replace("_", "-")}'
        self.display: bool = data.get_bool(
            section=section, prop='display', default=True
        )
        self.width: float | None = data.get_float(
            section=section,
            prop='width',
            default=None,
        )
        self.height: float | None = data.get_float(
            section=section,
            prop='height',
            default=None,
        )
        self.max_width: float | None = data.get_opt_float(
            section=section,
            prop='max_width',
            default=None,
        )
        self.css: str = data.get_str(
            section=section,
            prop='css',
            default='',
        )
        self.rotate: float | None = data.get_float(
            section=section,
            prop='rotate',
            default=None,
        )
        self.back: bool = (
            data.get_str(
                section=section,
                prop='side',
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

    def allowed_properties(
        self,
    ) -> set[str]:
        return (
            super()
            .allowed_properties()
            .union(
                {
                    'display',
                    'width',
                    'height',
                    'max_width',
                    'rotate',
                    'side',
                    'css',
                }
            )
        )

    def render_error(
        self,
        message: str,
    ) -> str:
        return f'<i class="bi bi-bug-fill"></i> {self.id}: {message}'

    def render_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        player: PlaceCardPlayer | None = None,
        board: PlaceCardBoard | None = None,
        pairing: PlaceCardPairing | None = None,
        team: PlaceCardTeam | None = None,
        preview: bool = False,
    ) -> str:
        """Returns the HTML to output for the item."""
        return f'<div class="card-item-wrapper {self.css_class}">{self._inner_html(event, tournament, player, board, pairing, team, preview)}</div>'

    @abstractmethod
    def _inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        player: PlaceCardPlayer | None = None,
        board: PlaceCardBoard | None = None,
        pairing: PlaceCardPairing | None = None,
        team: PlaceCardTeam | None = None,
        preview: bool = False,
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
        template: 'PlaceCardTemplate',
    ):
        super().__init__(data, section, template)
        self.raw_text: str = data.get_str(
            section=section,
            prop='text',
        )
        self.preview_text: str = data.get_str(
            section=section,
            prop='preview_text',
            default='',
        )

    @property
    def type(self) -> str:
        return 'text'

    def allowed_properties(
        self,
    ) -> set[str]:
        return (
            super()
            .allowed_properties()
            .union(
                {
                    'text',
                    'preview_text',
                }
            )
        )

    def _inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        player: PlaceCardPlayer | None = None,
        board: PlaceCardBoard | None = None,
        pairing: PlaceCardPairing | None = None,
        team: PlaceCardTeam | None = None,
        preview: bool = False,
    ) -> str:
        if not self.display:
            return ''
        content: str = parse_jinja_string(
            template_string=self.preview_text
            if preview and self.preview_text
            else self.raw_text,
            context={
                'event': event,
                'tournament': tournament,
                'player': player,
                'board': board,
                'pairing': pairing,
                'team': team,
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
        if self.italic:
            # Italic glyphs overhang their advance width; without a
            # little slack the item's overflow:hidden clips the last
            # letter's slant.
            item_css['padding-right'] = '0.15em'
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
        template: 'PlaceCardTemplate',
    ):
        super().__init__(data, section, template)
        self.image_paths: list[Path] = template.image_paths
        image_name: str = data.get_str(section=section, prop='image')
        image: Path | None = None
        if not (Path() / image_name).parent.samefile(Path()):
            logger.warning('Invalid image filename [%s].', image_name)
        else:
            for image_path in self.image_paths:
                file: Path = image_path / image_name
                if file.is_file():
                    image = file
                    break
                logger.debug('Image file [%s] not found.', file)
            if not image:
                logger.warning('Image file [%s] not found.', image_name)
        if not image:
            self._background_color = 'red'
        self.image = image or self.default_image
        if not self.width and not self.height:
            self.width = self.height = 30.0 / (1.0 if template.unit == 'mm' else 25.4)
            logger.warning(
                'Use [width] or [height] in section [%s] to size the image (defaults to %sx%s).',
                self.image.name,
                self.width,
                self.height,
            )
        elif not self.width or not self.height:
            ratio: float = self.get_image_ratio(self.image)
            if not ratio:
                self._background_color = 'red'
                logger.warning(
                    'Could not get ratio for image [%s], defaults to [%s].',
                    self.image.name,
                    self.default_image.name,
                )
                self.image = self.default_image
                ratio = self.get_image_ratio(self.image)
            if self.width:
                self.height = self.width / ratio
            else:
                assert self.height
                self.width = self.height * ratio
        self.url = image_file_inline_url(self.image)

    @property
    def default_image(self) -> Path:
        return BASE_DIR / 'src/web/static/images/sharly-chess-logo.svg'

    @staticmethod
    def get_image_ratio(image_file: Path) -> float:
        try:
            image = Image.open(image_file)
            return image.size[0] / image.size[1]
        except UnidentifiedImageError:
            # try to get the dimensions or view box of SVG files
            with open(image_file, 'rt') as f:
                svg_tree: ElementTree = ET.ElementTree(ET.fromstring(f.read()))
            if not svg_tree:
                return 0.0
            svg_root: ET.Element | None = svg_tree.getroot()
            if svg_root is None:
                return 0.0
            try:
                width = int(svg_root.attrib.get('width') or '0')
                height = int(svg_root.attrib.get('height') or '0')
                if width and height:
                    return width / height
            except ValueError:
                return 0.0
            view_box: str | None = svg_root.attrib.get('viewBox')
            if not view_box:
                return 0.0
            _, _, width_str, height_str = view_box.split()
            try:
                return int(width_str.strip() or '0') / int(height_str.strip() or '0')
            except ValueError:
                return 0.0

    @property
    def type(self) -> str:
        return 'image'

    def allowed_properties(
        self,
    ) -> set[str]:
        return (
            super()
            .allowed_properties()
            .union(
                {
                    'image',
                }
            )
        )

    def _inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        player: PlaceCardPlayer | None = None,
        board: PlaceCardBoard | None = None,
        pairing: PlaceCardPairing | None = None,
        team: PlaceCardTeam | None = None,
        preview: bool = False,
    ) -> str:
        return f'<div class="card-item image {self.css_class}"></div>'

    @cached_property
    def image_file(
        self,
    ) -> Path | None:
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
        return super()._item_css_properties(unit) | {
            'background-image': f'url("{self.url}")',
            'background-size': 'contain',
            'width': f'{self.width}{unit}',
            'height': f'{self.height}{unit}',
        }

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.image=}, {self.back=})'
