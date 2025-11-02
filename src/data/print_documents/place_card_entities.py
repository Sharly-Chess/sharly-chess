import logging
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import toml
from toml import TomlDecodeError

from common.i18n import _
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig
from data.board import Board
from data.event import Event
from data.player import Player
from data.tournament import Tournament

logger: logging.Logger = get_logger()


class PlaceCardPlayer:
    """A utility class to pass unmodifiable players' data to print documents."""

    def __init__(
        self,
        player: Player | None,
    ):
        self.rating: str = ''
        self.rating_type: str = ''
        self.full_name: str = ''
        self.first_name: str = ''
        self.last_name: str = ''
        self.year_of_birth: str = ''
        self.gender: str = ''
        self.title: str = ''
        self.federation: str = ''
        self.club: str = ''
        self.category: str = ''
        if player:
            if player.rating:
                self.rating = str(player.rating)
            self.rating_type = player.rating_type.short_name
            self.full_name = player.full_name
            self.first_name = player.first_name
            self.last_name = player.last_name
            if player.year_of_birth:
                self.year_of_birth = str(player.year_of_birth)
            self.gender = player.gender.short_name
            self.title = player.title.short_name
            self.federation = player.federation.name
            self.club = player.club.name
            self.category = player.category.short_name


class PlaceCardBoard:
    """A utility class to pass unmodifiable boards' data to print documents."""

    def __init__(
        self,
        board: Board,
    ):
        self.id: int = board.id
        self.number: int = board.number
        self.white_player: PlaceCardPlayer = PlaceCardPlayer(board.white_player)
        self.black_player: PlaceCardPlayer = PlaceCardPlayer(board.black_player)


class PrintCardDate:
    """A utility class to pass unmodifiable dates to print documents."""

    def __init__(
        self,
        timestamp: float,
    ):
        dt: datetime = datetime.fromtimestamp(timestamp)
        self.year: int = dt.year
        self.month: int = dt.month
        self.day: int = dt.day


class PlaceCardTournament:
    """A utility class to pass unmodifiable tournaments' data to print documents."""

    def __init__(
        self,
        tournament: Tournament,
    ):
        self.name: str = tournament.name
        self.start: PrintCardDate = PrintCardDate(tournament.start_timestamp)
        self.stop: PrintCardDate = PrintCardDate(tournament.stop_timestamp)


class PlaceCardEvent:
    """A utility class to pass unmodifiable tournaments' data to print documents."""

    def __init__(
        self,
        event: Event,
    ):
        self.name: str = event.name
        self.start: PrintCardDate = PrintCardDate(event.start)
        self.stop: PrintCardDate = PrintCardDate(event.stop)


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

    def get_str(
        self,
        property: str,
        section: str = '',
        default: str = '',
        values: list[str] | None = None,
    ) -> str:
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
                section_data: str | int | float | dict[str, Any] = self.data[section]
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
        if value:
            if values:
                if value in values:
                    return value
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
        else:
            logger.debug(
                '[%s]: custom property [%s] not set, defaults to [%s].',
                self.toml_file.name,
                property,
                default,
            )
            return default

    def get_int(
        self,
        property: str,
        section: str = '',
        default: int | None = None,
    ) -> int | None:
        if value := self.get_str(
            section=section, property=property, default=str(default) if default else ''
        ):
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
        else:
            return default

    def get_float(
        self,
        property: str,
        section: str = '',
        default: float | None = None,
    ) -> float | None:
        if value := self.get_str(
            section=section, property=property, default=str(default) if default else ''
        ):
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
        else:
            return default

    def get_font_size(
        self,
        section: str = '',
        default: float | None = None,
    ) -> float | None:
        return self.get_float(section=section, property='font_size', default=default)

    def get_font_weight(
        self,
        section: str = '',
        default: str = 'normal',
    ) -> str:
        return self.get_str(
            section=section,
            property='font_weight',
            default=default,
            values=[
                'normal',
                'bold',
            ],
        )

    def get_font_style(
        self,
        section: str = '',
        default: str = 'normal',
    ) -> str:
        return self.get_str(
            section=section,
            property='font_style',
            default=default,
            values=[
                'normal',
                'italic',
            ],
        )

    def get_hor_align(
        self,
        section: str = '',
        default: str = 'left',
    ) -> str:
        return self.get_str(
            section=section,
            property='hor_align',
            default=default,
            values=[
                'left',
                'center',
                'right',
            ],
        )

    def get_ver_align(
        self,
        section: str = '',
        default: str = 'top',
    ) -> str:
        return self.get_str(
            section=section,
            property='ver_align',
            default=default,
            values=[
                'top',
                'middle',
                'bottom',
            ],
        )

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


class PlaceCardTemplate:
    """A class representing the place cards templates."""

    def __init__(
        self,
        toml_file: Path,
    ):
        from data.print_documents import PrintPlaceCardTypeManager
        from data.print_documents.place_card_types import PlaceCardType

        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        self.embedded: bool = (
            toml_file.parent == SharlyChessConfig.embedded_place_cards_path
        )
        self.id: str = toml_file.stem
        self.custom_data = PlaceCardCustomDataContainer(toml_file)
        # -------------------- type
        self.type: PlaceCardType = PrintPlaceCardTypeManager().get_object(
            self.custom_data.get_str(
                'type', default='player', values=PrintPlaceCardTypeManager().ids()
            )
        )
        # -------------------- file
        property: str = 'file'
        file_str: str = self.custom_data.get_str(
            property, default=f'{toml_file.stem}.html'
        )
        default_file_str: str = f'{toml_file.stem}.html'
        if file_str.find('/') != -1:
            logger.warning(
                '[%s]: invalid value [%s] for property [%s] (path not allowed), defaults to [%s].',
                toml_file.name,
                file_str,
                property,
                default_file_str,
            )
            file_str = default_file_str
        if not sharly_chess_config.uniq_id_regex.match(Path(file_str).stem):
            logger.warning(
                '[%s]: invalid value [%s] for property [%s] (invalid characters found), defaults to [%s].',
                toml_file.name,
                file_str,
                property,
                default_file_str,
            )
            file_str = default_file_str
        # The path of the HTML template file
        self.template_file: Path = toml_file.parent / file_str
        if not self.template_file.is_file():
            if self.embedded:
                # Custom TOML file, try to find the template file in the custom path
                logger.debug(
                    '[%s]: file [%s] not found in folder [%s], looking in folder [%s].',
                    toml_file.name,
                    file_str,
                    sharly_chess_config.custom_place_cards_path,
                    sharly_chess_config.embedded_place_cards_path,
                )
                self.template_file = (
                    SharlyChessConfig.embedded_place_cards_path / file_str
                )
            if not self.template_file.is_file():
                self.template_file: Path = (
                    SharlyChessConfig.embedded_place_cards_path
                    / f'_{self.type.static_id()}.html'
                )
                logger.debug(
                    '[%s]: file [%s] not found in folder [%s], defaults to [%s].',
                    toml_file.name,
                    file_str,
                    sharly_chess_config.custom_place_cards_path,
                    self.template_file.name,
                )
                # We do not test here, assuming that the embedded default template file exists for all the place cards types
        # The template name passed to Jinja (e.g. '/admin/print/place_cards/test.html')
        self.template_name: str = f'{"/admin/print/place_cards/" if self.template_file.parent == sharly_chess_config.embedded_place_cards_path else "/place_cards_templates/"}{self.template_file.name}'
        self.name: str = self.custom_data.get_str('name', default=toml_file.stem)
        self.creator: str = self.custom_data.get_str('creator', default=_('Unknown'))
        self.custom_data.delete_entries(
            [
                'type',
                'file',
                'name',
                'creator',
            ]
        )

    @property
    def template_context(self) -> dict[str, Any]:
        return {
            'custom': self.custom_data,
        }

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self.id=}, {self.embedded=}, {self.template_name=}, {self.creator=})'
