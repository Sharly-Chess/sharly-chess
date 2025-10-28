from abc import ABC
from functools import cached_property
from types import UnionType
from typing import TYPE_CHECKING, Optional, override, Any

from common.exception import OptionError
from common.i18n import _
from data.event import SharlyChessConfig
from data.print_documents.pairing_styles import BoardsPairingStyle, PairingStyle
from data.print_documents.place_card_types import PlayerCardType, PlaceCardType
from data.print_documents.player_sorters import (
    PlayerSorter,
    NamePlayerSorter,
)
from data.print_documents.player_splitters import PlayerSplitter, NoSplitPlayerSplitter
from data.print_documents.qrcode_types import NetworkQRCodeType, QRCodeType
from utils.option import Option

if TYPE_CHECKING:
    from data.event import Event


class PrintOption(Option, ABC):
    """Parent class of all the options of print documents."""

    def __init__(self, event: Optional['Event'], value: Any | None = None):
        super().__init__(value)
        self.event = event

    @property
    def template_name(self) -> str:
        return f'/admin/event/print_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        """Name of the file of the template representing the option."""
        return self.id.replace('-', '_')


class TournamentPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'tournament'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        # This is managed by the print controller
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/tournament.html'

    @override
    def validate(self):
        super().validate()
        if self.value is None:
            raise OptionError(_('Please choose the tournament.'), self)


class TournamentsPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'tournaments'

    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        # This is managed by the print controller
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/tournaments.html'


class PlayerPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'player'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/player.html'

    @override
    def validate(self):
        super().validate()
        if self.value is None:
            raise OptionError(_('Please choose a player.'), self)

    @property
    def players_per_tournament(self) -> dict[int, list[dict[str, Any]]]:
        if self.event is None:
            return {}

        tournaments = [tournament for tournament in self.event.tournaments]
        return {
            tournament.id: [
                {'id': player.id, 'full_name': player.full_name}
                for player in tournament.players_by_name_with_unpaired
            ]
            for tournament in tournaments
        }


class RoundPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'round'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/round.html'

    @override
    def validate(self):
        super().validate()
        if self.value is not None and self.value < 1:
            raise OptionError(_('A positive integer is expected.'), self)


class PlayerSplitPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'player-split'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return NoSplitPlayerSplitter.static_id()

    @property
    def player_splitter_options(self) -> dict[str, str]:
        from data.print_documents import PrintPlayerSplitterManager

        return PrintPlayerSplitterManager(self.event).options()

    @cached_property
    def player_splitter(self) -> PlayerSplitter:
        from data.print_documents import PrintPlayerSplitterManager

        return PrintPlayerSplitterManager(self.event).get_object(self.value)

    @override
    def validate(self):
        try:
            _splitter = self.player_splitter
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown player splitter: {self.value}', self)


class PlayerSortPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'player-sort'

    @property
    def type(self) -> type | UnionType:
        return str

    @property
    def default_value(self) -> Any:
        return NamePlayerSorter.static_id()

    @property
    def player_sorter_options(self) -> dict[str, str]:
        from data.print_documents import PrintPlayerSorterManager

        return PrintPlayerSorterManager(self.event).options()

    @cached_property
    def player_sorter(self) -> PlayerSorter:
        from data.print_documents import PrintPlayerSorterManager

        return PrintPlayerSorterManager(self.event).get_object(self.value)

    @override
    def validate(self):
        try:
            _sorter = self.player_sorter
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown player sorter: {self.value}', self)


class PairingStylePrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'pairing-style'

    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        return BoardsPairingStyle.static_id()

    @property
    def pairing_style_options(self) -> dict[str, str]:
        from data.print_documents import PrintPairingStyleManager

        return PrintPairingStyleManager(self.event).options()

    @cached_property
    def pairing_style(self) -> PairingStyle:
        from data.print_documents import PrintPairingStyleManager

        return PrintPairingStyleManager(self.event).get_object(self.value)

    @override
    def validate(self):
        try:
            _style = self.pairing_style
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown pairing style: {self.value}', self)


class ShowWarningsPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'show-warnings'

    @property
    def type(self) -> type | UnionType:
        return bool

    @property
    def default_value(self) -> Any:
        return True


class ClubThresholdPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'club-threshold'

    @property
    def type(self) -> type | UnionType:
        return int | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/club_threshold.html'

    @override
    def validate(self):
        super().validate()
        if self.value is not None and self.value < 0:
            raise OptionError(_('A positive value is expected.'), self)


class QRCodePrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'qrcode-type'

    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        return NetworkQRCodeType.static_id()

    @property
    def qrcode_print_document_id(self) -> str:
        from data.print_documents.documents import QRCodePrintDocument

        return QRCodePrintDocument.static_id()

    @property
    def qrcode_type_options(self) -> dict[str, str]:
        from data.print_documents import PrintQRCodeTypeManager

        return PrintQRCodeTypeManager(self.event).options()

    @cached_property
    def qrcode_type(self) -> QRCodeType:
        from data.print_documents import PrintQRCodeTypeManager

        return PrintQRCodeTypeManager(self.event).get_object(self.value)

    @property
    def valid_options_per_type(self) -> dict[str, list[str]]:
        from data.print_documents import PrintQRCodeTypeManager

        type_options = PrintQRCodeTypeManager(self.event).type_by_id()
        return {
            type_id: type_options[type_id].get_valid_options()
            for type_id in type_options
        }

    @override
    def validate(self):
        try:
            _style = self.qrcode_type
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown QR Code type: {self.value}', self)


class QRCodeNetworkPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'qrcode-network'

    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        return None

    @property
    def network_options(self) -> dict[str, str]:
        config = SharlyChessConfig()
        return {
            str(iface['ip']): f'{iface["label"]} ({iface["type"]})'
            if 'type' in iface and iface['type'] and iface['type'] != iface['label']
            else f'{iface["label"]}'
            for iface in config.lan_ifaces
        }

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/qrcode_network.html'


class PlaceCardPrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'place-card-type'

    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        return PlayerCardType.static_id()

    @property
    def place_card_print_document_id(self) -> str:
        from data.print_documents.documents import PlaceCardPrintDocument

        return PlaceCardPrintDocument.static_id()

    @property
    def place_card_type_options(self) -> dict[str, str]:
        from data.print_documents import PrintPlaceCardTypeManager

        return PrintPlaceCardTypeManager(self.event).options()

    @cached_property
    def place_card_type(self) -> PlaceCardType:
        from data.print_documents import PrintPlaceCardTypeManager

        return PrintPlaceCardTypeManager(self.event).get_object(self.value)

    @property
    def valid_options_per_type(self) -> dict[str, list[str]]:
        from data.print_documents import PrintPlaceCardTypeManager

        type_options = PrintPlaceCardTypeManager(self.event).type_by_id()
        return {
            type_id: type_options[type_id].get_valid_options()
            for type_id in type_options
        }

    @override
    def validate(self):
        try:
            _style = self.place_card_type
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown Place Card type: {self.value}', self)


class PlaceCardTemplatePrintOption(PrintOption):
    @staticmethod
    def static_id() -> str:
        return 'place-card-template'

    @property
    def type(self) -> type | UnionType:
        return str | None

    @property
    def default_value(self) -> Any:
        # This is managed by the print controller
        return None

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/place_card_template.html'

    @override
    def validate(self):
        super().validate()
        if self.value is None:
            raise OptionError(_('Please choose the template.'), self)
