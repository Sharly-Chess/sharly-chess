import copy
import html
import logging
import re
from pathlib import Path
from typing import Any

from common import BASE_DIR
from common.i18n import _
from common.i18n.utils import parse_jinja_string, parse_jinja_template
from common.logger import get_logger
from data.event import Event
from data.print_documents.place_cards.crop_marks import (
    PlaceCardCropMarks,
    CornersPlaceCardCropMarks,
)
from data.print_documents.place_cards.data import (
    PlaceCardBoard,
    PlaceCardPlayer,
    PlaceCardEvent,
    PlaceCardTournament,
    PlaceCardPairing,
)
from data.print_documents.place_cards.item_style import PlaceCardItemStyle
from data.print_documents.place_cards.items import (
    PlaceCardItem,
    PlaceCardImage,
    PlaceCardText,
)
from data.print_documents.place_cards.toml_container import TOMLContainer
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

        self.error = custom_data.error

    @property
    def tooltip(self) -> str:
        return f"""
        <div class="place-card-template-name"><b>{html.escape(self.name)}</b></div>
        <div class="place-card-template-creator">{_('Creator: {creator}').format(creator=html.escape(self.creator))}</div>
        <div class="place-card-template-preview">{self.preview(None)}</div>
        """

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

    @staticmethod
    def get_federations(
        players: list[PlaceCardPlayer],
        pairings: list[PlaceCardPairing],
    ) -> set[str]:
        """Return the federations of the players in the template data."""
        return (
            set(
                pairing.white_player.federation
                for pairing in pairings
                if pairing.black_player
            )
            .union(
                set(
                    pairing.black_player.federation
                    for pairing in pairings
                    if pairing.black_player
                )
            )
            .union(set(player.federation for player in players))
        )

    def _template_context(
        self,
        event: PlaceCardEvent,
        tournament: PlaceCardTournament,
        round_: int,
        mirror: bool,
        place_card_crop_marks: PlaceCardCropMarks,
        players: list[PlaceCardPlayer],
        boards: list[PlaceCardBoard],
        pairings: list[PlaceCardPairing],
    ) -> dict[str, Any]:
        items: list[PlaceCardItem] = copy.deepcopy(self.items)
        if mirror:
            # duplicate all the items on the back side
            back_items: list[PlaceCardItem] = [
                PlaceCardItem.mirror(item, self.type.mirror_rotate) for item in items
            ]
            items += back_items
        back_side: bool = any(item.back for item in items)
        federations: set[str] = self.get_federations(players, pairings)
        return {
            'event': event,
            'tournament': tournament,
            'round': round_,
            'error': self.error,
            'back_side': back_side,
            'unit': self.unit,
            'template_css_class': self.css_class,
            'template_css': self.render_css(
                place_card_crop_marks, back_side, federations
            ),
            'players': players,
            'boards': boards,
            'pairings': pairings,
            'items': items,
        }

    def template_context(
        self,
        event: Event,
        tournament: Tournament,
        round_: int,
        mirror: bool,
        place_card_crop_marks: PlaceCardCropMarks,
        board_numbers: set[int],
        player_ids: list[int],
    ) -> dict[str, Any]:
        return self._template_context(
            event=PlaceCardEvent(event),
            tournament=PlaceCardTournament(tournament),
            round_=round_,
            mirror=mirror,
            place_card_crop_marks=place_card_crop_marks,
            players=self.type.players(tournament, player_ids=player_ids),
            boards=self.type.boards(tournament, board_numbers=board_numbers),
            pairings=self.type.pairings(
                tournament, round_, board_numbers=board_numbers
            ),
        )

    def preview(
        self,
        tournament: Tournament | None,
    ) -> str:
        """Returns a string to preview the template with moc data."""
        return parse_jinja_template(
            '/admin/print/place_cards/preview.html',
            self._template_context(
                event=PlaceCardEvent(tournament.event if tournament else None),
                tournament=PlaceCardTournament(tournament),
                round_=1,
                mirror=False,
                place_card_crop_marks=CornersPlaceCardCropMarks(),
                players=self.type.preview_players(tournament),
                boards=self.type.preview_boards(tournament),
                pairings=self.type.preview_pairings(tournament),
            ),
        )

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.id=}, {self.embedded=}, {self.template_name=}, {self.creator=})'
