from typing import Any

from common.i18n import _
from common.sharly_chess_config import SharlyChessConfig
from data.print_documents.documents import (
    PrintDocument,
)
from data.print_documents.fonts import PRINT_FONT_FAMILY, print_font_faces
from plugins.chess960.utils import board_svg


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
        return {
            'sharly_chess_config': SharlyChessConfig(),
            'font_family': PRINT_FONT_FAMILY,
            'font_faces': print_font_faces(),
            'positions': {number: board_svg(number) for number in range(1, 961)},
            'event': self.event,
        }
