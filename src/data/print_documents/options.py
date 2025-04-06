from abc import ABC
from functools import cached_property
from types import UnionType
from typing import override, Any

from common.i18n import _
from data.print_documents.player_splitters import PlayerSplitter
from utils.option import Option, OptionError


class PrintOption(Option, ABC):
    """Parent class of all the options of print documents."""


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
        return 'no-split'

    @property
    def template_name(self) -> str:
        return '/admin/event/print_options/player_split.html'

    @property
    def player_splitter_options(self) -> dict[str, str]:
        from data.print_documents import PrintPlayerSplitterManager

        return PrintPlayerSplitterManager.options()

    @cached_property
    def player_splitter(self) -> PlayerSplitter | None:
        from data.print_documents import PrintPlayerSplitterManager

        return PrintPlayerSplitterManager.get_object(self.value)

    @override
    def validate(self):
        try:
            _splitter = self.player_splitter
        except KeyError:
            # Untranslated, should not happen
            raise OptionError(f'Unknown player splitter: {self.value}', self)
