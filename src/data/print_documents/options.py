from abc import ABC
from functools import cached_property
from types import UnionType
from typing import override, Any

from common.i18n import _
from data.print_documents.pairing_styles import BoardsPairingStyle, PairingStyle
from data.print_documents.player_sorters import (
    PlayerSorter,
    NamePlayerSorter,
)
from data.print_documents.player_splitters import PlayerSplitter, NoSplitPlayerSplitter
from utils.option import Option, OptionError


class PrintOption(Option, ABC):
    """Parent class of all the options of print documents."""

    @property
    def template_name(self) -> str:
        return f'/admin/event/print_options/{self.template_file_name}.html'

    @property
    def template_file_name(self) -> str:
        """Name of the file of the template representing the option."""
        return self.id.replace('-', '_')


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

        return PrintPlayerSplitterManager.options()

    @cached_property
    def player_splitter(self) -> PlayerSplitter:
        from data.print_documents import PrintPlayerSplitterManager

        return PrintPlayerSplitterManager.get_object(self.value)

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

        return PrintPlayerSorterManager.options()

    @cached_property
    def player_sorter(self) -> PlayerSorter:
        from data.print_documents import PrintPlayerSorterManager

        return PrintPlayerSorterManager.get_object(self.value)

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

        return PrintPairingStyleManager.options()

    @cached_property
    def pairing_style(self) -> PairingStyle:
        from data.print_documents import PrintPairingStyleManager

        return PrintPairingStyleManager.get_object(self.value)

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
