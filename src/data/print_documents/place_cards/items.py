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
            default_font_size=default_style.font_size,
            default_bold=default_style.bold,
            default_italic=default_style.italic,
            default_h_align=default_style.h_align,
            default_v_align=default_style.v_align,
            default_h_pos=default_style.h_pos,
            default_v_pos=default_style.v_pos,
            default_opacity=default_style.opacity,
        )
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
