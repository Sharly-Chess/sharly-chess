from common import SharlyChessException
from plugins.chessevent.chessevent_status import ChessEventStatus


class ChessEventStatusError(SharlyChessException):
    def __init__(self, message: str, status: ChessEventStatus):
        super().__init__(message)
        self.status = status
