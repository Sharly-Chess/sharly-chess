from plugins.chessevent.engine.event_selector import EventSelector
from common.engine import Engine


class ChessEventEngine(Engine):
    """The ChessEvent Engine."""

    def __init__(self):
        try:
            super().__init__()
            if self.updated:
                return
            while EventSelector().run():
                pass
        except KeyboardInterrupt:
            pass
