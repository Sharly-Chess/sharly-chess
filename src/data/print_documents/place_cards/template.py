import copy
import html
import logging
import re
from pathlib import Path
from typing import Any

from common import BASE_DIR
from common.i18n import _
from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
from data.board import Board
from data.event import Event
from data.player import Player
from data.print_documents.place_cards.crop_marks import PlaceCardCropMarks
from data.print_documents.place_cards.data import (
    PlaceCardBoard,
    PlaceCardPlayer,
    PlaceCardEvent,
    PlaceCardTournament,
)
from data.print_documents.place_cards.item_style import PlaceCardItemStyle
from data.print_documents.place_cards.items import (
    PlaceCardItem,
    PlaceCardImage,
    PlaceCardText,
)
from data.print_documents.place_cards.toml_container import TOMLContainer
from data.print_documents.place_cards.types import PlaceCardType
from data.tournament import Tournament
from utils.file import ttf_file_inline_url, image_file_inline_url

logger: logging.Logger = get_logger()


class PlaceCardTemplate:
    """A class representing the place cards templates."""

    def __init__(
        self,
        embedded: bool,
        toml_file: Path,
    ):
        from data.print_documents import PrintPlaceCardTypeManager
        from data.print_documents.place_cards.types import (
            PlaceCardType,
            PlayerCardType,
        )

        self.embedded: bool = embedded
        self.id: str
        self.default_font_file = (
            BASE_DIR / 'src/web/static/fonts/AtkinsonHyperlegibleNextVF-Variable.ttf'
        )
        self.default_image_file = (
            BASE_DIR / 'src/web/static/images/sharly-chess-logo.svg'
        )
        if self.embedded:
            self.id = toml_file.stem
        else:
            self.id = f'{toml_file.parent.name}/{toml_file.stem}'
        self.css_class: str = f'template-{re.sub(r"[^a-zA-Z0-9_\-]", "-", self.id)}'
        self.font_paths: list[Path] = [
            toml_file.parent / 'fonts',
            BASE_DIR / 'src/web/static/fonts',
        ]
        self.image_paths: list[Path] = [
            toml_file.parent / 'images',
            BASE_DIR / 'src/web/static/images',
        ]
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
                    | 'css'
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
        self.css: str = custom_data.get_str('css', default='')
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
                        images_path=self.image_paths,
                        unit=self.unit,
                    )
                )
            else:
                items.append(
                    PlaceCardText(
                        custom_data, section=section, default_style=default_item_style
                    )
                )
        self.items: list[PlaceCardItem] = [
            item for item in items if item.type == 'image'
        ] + [item for item in items if item.type != 'image']
        self.tooltip: str = f"""
<div><b>{_('Name: {name}').format(name=html.escape(self.name))}</b></div>
<div>{_('Creator: {creator}').format(creator=html.escape(self.creator))}</div>
<iframe
        src="/"
        style="width: {self.width}{self.unit}; height: {(2 if any(item.back for item in self.items) else 1) * self.height}{self.unit};"
        width="320" height="240"
>
</iframe>
"""

        self.error = custom_data.error

    @property
    def template_name(self) -> str:
        return '/admin/print/place_cards/template.html'

    @property
    def font_file(self) -> Path:
        if not self.font:
            return self.default_font_file
        if not (Path() / self.font).parent.samefile(Path()):
            logger.debug('Invalid font filename [%s].', self.font)
            return self.default_font_file
        for font_path in self.font_paths:
            file: Path = font_path / self.font
            if not file.is_file():
                logger.warning('Font file [%s] not found.', file)
                continue
            return file
        logger.warning('Font file [%s] not found.', self.font)
        return self.default_font_file

    def render_css(
        self,
        place_card_crop_marks: PlaceCardCropMarks,
        back_side: bool,
        federations: set[str],
    ) -> str:
        file: Path = self.font_file
        css_properties: dict[str, dict[str, str]] = {
            '@font-face': {
                'font-family': f'"{file.stem}"',
                'src': f'url("{ttf_file_inline_url(file)}") format("truetype")',
            },
            f'.{self.css_class} *': {
                'font-family': f'{file.stem}, sans-serif',
            },
            f'.card-wrapper.{self.css_class}': {
                'float': 'left',
                'display': 'flex',
                'flex-direction': 'column',
                'width': f'{self.width}{self.unit}',
                'height': f'{(2 if back_side else 1) * self.height}{self.unit}',
                'page-break-inside': 'avoid',
                'position': 'relative',
            },
            f'.{self.css_class} .card': {
                'display': 'grid',
                'width': f'{self.width}{self.unit}',
                'height': f'{self.height}{self.unit}',
                'grid-template-columns': f'{self.padding}{self.unit} auto {self.padding}{self.unit}',
                'grid-auto-flow': 'row',
            },
            f'.{self.css_class} .card.side-back .card-content': {
                'transform': 'rotate(180deg)',
                'transform-origin': 'center center',
            },
            f'.{self.css_class} .card-cell.top, .{self.css_class} .card-cell.bottom': {
                'height': f'{self.padding}{self.unit}',
            },
            f'.{self.css_class} .card-cell.middle, .{self.css_class} .card-content': {
                'height': f'{self.height - 2 * self.padding}{self.unit}',
            },
            f'.{self.css_class} .card-cell.left, .{self.css_class} .card-cell.right': {
                'width': f'{self.padding}{self.unit}',
            },
            f'.{self.css_class} .card-cell.center, .{self.css_class} .card-content': {
                'width': f'{self.width - 2 * self.padding}{self.unit}',
            },
            f'.{self.css_class} .card-content': {
                'position': 'relative',
                'background-color': 'rgba(255, 255, 255, 0.6)',
            },
            f'.{self.css_class} .card-item-wrapper': {
                'position': 'absolute',
                'top': '0.0',
                'left': '0.0',
                'overflow': 'hidden',
                'white-space': 'nowrap',
                'text-overflow': 'ellipsis',
                'background-color': 'transparent',
                'width': f'{self.width - 2 * self.padding}{self.unit}',
                'height': f'{self.height - 2 * self.padding}{self.unit}',
            },
            f'.{self.css_class} .card-item': {
                'overflow': 'hidden',
                'white-space': 'nowrap',
                'text-overflow': 'ellipsis',
                'background-color': 'transparent',
                'max-width': f'{self.width - 2 * self.padding}{self.unit}',
            },
            f'.{self.css_class} .federation-flag': {
                'height': '0.7em',
                'width': '0.93em',
            },
            f'.{self.css_class} .card-item.error': {
                'color': 'rgb(255, 0, 0)',
                'background-color': 'rgb(255, 220, 220)',
                'opacity': '1.0',
            },
        }
        css_properties |= {
            f'.federation-flag.{federation}': {
                'background-image': f'url("{image_file_inline_url(BASE_DIR / f"src/web/static/images/federations/{federation}.svg")}")'
            }
            for federation in federations
        }
        return (
            '\n'.join(
                f'{locator} {{\n{"\n".join(f"\t{key}: {value};" for key, value in properties.items())}\n}}'
                for locator, properties in css_properties.items()
            )
            + place_card_crop_marks.render_css()
            + self.css
        )

    def template_context(
        self,
        event: Event,
        tournament: Tournament,
        round_: int,
        place_card_type: PlaceCardType,
        mirror: bool,
        place_card_crop_marks: PlaceCardCropMarks,
        board_numbers: set[int],
        player_ids: list[int],
    ) -> dict[str, Any]:
        items: list[PlaceCardItem] = copy.deepcopy(self.items)
        if mirror:
            # duplicate all the items on the back side
            back_items: list[PlaceCardItem] = [
                PlaceCardItem.mirror(item, place_card_type.mirror_rotate)
                for item in items
            ]
            items += back_items
        back_side: bool = any(item.back for item in items)
        players: list[Player] = place_card_type.players(tournament)
        if player_ids:
            players = [player for player in players if player.id in player_ids]
        boards: list[Board] = place_card_type.boards(tournament, round_)
        if board_numbers:
            boards = [board for board in boards if board.number in board_numbers]
        federations = (
            set(
                board.white_player.federation.name
                for board in boards
                if board.black_player
            )
            .union(
                set(
                    board.black_player.federation.name
                    for board in boards
                    if board.black_player
                )
            )
            .union(set(player.federation.name for player in players))
        )
        return {
            'event': PlaceCardEvent(event),
            'tournament': PlaceCardTournament(tournament),
            'round': round_,
            'error': self.error,
            'back_side': back_side,
            'unit': self.unit,
            'template_css_class': self.css_class,
            'template_css': self.render_css(
                place_card_crop_marks, back_side, federations
            ),
            'players': (PlaceCardPlayer(player) for player in players),
            'boards': (PlaceCardBoard(board) for board in boards),
            'items': items,
        }

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.id=}, {self.embedded=}, {self.template_name=}, {self.creator=})'
