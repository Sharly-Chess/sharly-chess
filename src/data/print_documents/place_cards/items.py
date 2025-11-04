import logging
from abc import ABC, abstractmethod
from pathlib import Path

from common.i18n import _
from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
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
        return f'<div class="card-item-wrapper {self.css_class}">{self.inner_html(event, tournament, board, player)}</div>'

    @abstractmethod
    def inner_html(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        board: PlaceCardBoard | None = None,
        player: PlaceCardPlayer | None = None,
    ) -> str:
        """Returns the inner HTML of the item."""
        pass

    def wrapper_css(
        self,
        unit: str,
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

    def item_css(
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
        return item_css

    def inner_css(
        self,
        unit: str,
    ) -> dict[str, str]:
        """Returns the CSS for the children of the item."""
        inner_css: dict[str, str] = {}
        return inner_css

    def render_css(
        self,
        unit: str,
    ) -> str:
        """Returns the CSS to print for the item."""
        return (
            f'.card-item-wrapper.{self.css_class} {{\n{";\n".join(f"{key}: {value};" for key, value in self.wrapper_css(unit).items())}\n}}\n'
            + f'.card-item.{self.css_class} {{\n{";\n".join(f"{key}: {value};" for key, value in self.item_css(unit).items())}\n}}\n'
            + f'.card-item.{self.css_class} * {{\n{";\n".join(f"{key}: {value};" for key, value in self.inner_css(unit).items())}\n}}\n'
            + f'.card-item.{self.css_class} {{\n{self.css}\n}}\n'
        )

    def render_js(
        self,
    ) -> str:
        return ''


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

    def inner_html(
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

    def item_css(
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
        return super().item_css(unit) | item_css

    def inner_css(
        self,
        unit: str,
    ) -> dict[str, str]:
        inner_css: dict[str, str] = {
            # the font style must be set to inner elements to apply to the federation flags.
            'font-size': f'{self.font_size}pt',
        }
        return super().inner_css(unit) | inner_css


class PlaceCardImage(PlaceCardItem):
    """A class to store an image item of a place card."""

    def __init__(
        self,
        data: TOMLContainer,
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

    def inner_html(
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
