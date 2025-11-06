import copy
import logging
from pathlib import Path
from typing import Any

from common import BASE_DIR
from common.i18n import _
from common.i18n.utils import parse_jinja_string
from common.logger import get_logger
from data.board import Board
from data.player import Player
from data.print_documents.place_cards.crop_marks import PlaceCardCropMarks
from data.print_documents.place_cards.data import PlaceCardBoard, PlaceCardPlayer
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
        self.image_path: Path
        self.font_path: Path
        self.id: str
        if self.embedded:
            self.id = toml_file.stem
            self.font_path = BASE_DIR / 'src/web/static/fonts'
            self.image_path = BASE_DIR / 'src/web/static/images'
        else:
            self.id = f'{toml_file.parent}/{toml_file.stem}'
            self.font_path = toml_file.parent / 'fonts'
            self.image_path = toml_file.parent / 'images'
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
                        image_path=self.image_path,
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
    def template_name(self) -> str:
        return '/admin/print/place_cards/template.html'

    @property
    def font_file(self) -> Path:
        default_file: Path = self.font_path / 'AtkinsonHyperlegibleNextVF-Variable.ttf'
        if not self.font:
            return default_file
        file: Path = self.font_path / self.font
        if not file.parent.samefile(self.font_path):
            logger.warning('Invalid font filename [%s].', self.font)
            return default_file
        if not file.is_file():
            logger.warning('Font file [%s] not found.', file)
            return default_file
        return file

    def template_context(
        self,
        tournament: Tournament,
        round_: int,
        place_card_type: PlaceCardType,
        mirror: bool,
        place_card_crop_marks: PlaceCardCropMarks,
        board_numbers: set[int],
    ) -> dict[str, Any]:
        file: Path = self.font_file
        items: list[PlaceCardItem] = self.items
        if mirror:
            # duplicate all the items
            back_items: list[PlaceCardItem] = copy.deepcopy(items)
            for item in back_items:
                item.back = not item.back
            items += back_items
        back_side: bool = any(item.back for item in items)
        css: dict[str, dict[str, str]] = {
            '@font-face': {
                'font-family': f'"{file.stem}"',
                'src': f'url("{ttf_file_inline_url(file)}") format("truetype")',
            },
            '*': {
                'font-family': f'{file.stem}, sans-serif',
            },
            '.card-wrapper': {
                'float': 'left',
                'display': 'flex',
                'flex-direction': 'column',
                'width': f'{self.width}{self.unit}',
                'height': f'{(2 if back_side else 1) * self.height}{self.unit}',
                'page-break-inside': 'avoid',
                'position': 'relative',
            },
            '.card': {
                'display': 'grid',
                'width': f'{self.width}{self.unit}',
                'height': f'{self.height}{self.unit}',
                'grid-template-columns': f'{self.padding}{self.unit} auto {self.padding}{self.unit}',
                'grid-auto-flow': 'row',
            },
            '.card.side-back .card-content': {
                'transform': 'rotate(180deg)',
                'transform-origin': 'center center',
            },
            '.card-cell.top, .card-cell.bottom': {
                'height': f'{self.padding}{self.unit}',
            },
            '.card-cell.middle, .card-content': {
                'height': f'{self.height - 2 * self.padding}{self.unit}',
            },
            '.card-cell.left, .card-cell.right': {
                'width': f'{self.padding}{self.unit}',
            },
            '.card-cell.center, .card-content': {
                'width': f'{self.width - 2 * self.padding}{self.unit}',
            },
        }
        css |= place_card_crop_marks.css
        css |= {
            '.card-content': {
                'position': 'relative',
                'background-color': 'rgba(255, 255, 255, 0.6)',
            },
            '.card-item-wrapper': {
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
            '.card-item': {
                'overflow': 'hidden',
                'white-space': 'nowrap',
                'text-overflow': 'ellipsis',
                'background-color': 'transparent',
                'max-width': f'{self.width - 2 * self.padding}{self.unit}',
            },
            '.federation-flag': {
                'height': '0.75em',
            },
            '.card-item.error': {
                'color': 'rgb(255, 0, 0)',
                'background-color': 'rgb(255, 220, 220)',
                'opacity': '1.0',
            },
        }
        players: list[Player] = place_card_type.players(tournament)
        boards: list[Board]
        if board_numbers:
            boards = [
                board
                for board in place_card_type.boards(tournament, round_)
                if board.number in board_numbers
            ]
        else:
            boards = place_card_type.boards(tournament, round_)
        federation_names = (
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
        federation_flag_urls: dict[str, str] = {
            name: image_file_inline_url(
                BASE_DIR / f'src/web/static/images/federations/{name}.svg'
            )
            for name in federation_names
        }
        js = f"""
    $(document).ready(function() {{
        {'\n'.join(f'$(".federation-flag.{name}").attr("src", "{url}");\n' for name, url in federation_flag_urls.items())}
    }});
"""
        return {
            'error': self.error,
            'back_side': back_side,
            'unit': self.unit,
            'template_css': '\n'.join(
                f'{target} {{\n{"\n".join(f"\t{key}: {value};" for key, value in entries.items())}\n}}'
                for target, entries in css.items()
            )
            + self.css,
            'template_js': js,
            'players': (PlaceCardPlayer(player) for player in players),
            'boards': (PlaceCardBoard(board) for board in boards),
            'items': self.items,
        }

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.id=}, {self.embedded=}, {self.template_name=}, {self.creator=})'
