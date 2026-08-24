from typing import Any

from common import BASE_DIR
from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.print_documents.documents import (
    PrintDocument,
)
from plugins.chess960.utils import board_svg
from utils.file import ttf_file_inline_url


class Chess960PrintDocument(PrintDocument):
    @staticmethod
    def static_id() -> str:
        return 'chess960-positions'

    @staticmethod
    def static_name() -> str:
        return _('Chess960 positions')

    @property
    def title(self) -> str:
        return _('All Chess960 positions')

    @property
    def template_name(self) -> str:
        return 'print_documents/chess960_positions.html'

    @property
    def template_context(self) -> dict[str, Any]:
        font_file = (
            BASE_DIR / 'src/web/static/fonts/AtkinsonHyperlegibleNextVF-Variable.ttf'
        )
        return {
            'sharly_chess_config': SharlyChessConfig(),
            'font_family': font_file.stem,
            'font_url': ttf_file_inline_url(font_file),
            'positions': {number: board_svg(number) for number in range(1, 961)},
            'event': self.event,
        }
