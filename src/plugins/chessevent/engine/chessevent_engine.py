from pathlib import Path

from common import LOG_DIR, APP_NAME
from plugins.chessevent import PLUGIN_NAME
from plugins.chessevent.engine.event_selector import EventSelector
from common.engine import Engine


class ChessEventEngine(Engine):
    """The ChessEvent Engine."""

    def __init__(self):
        try:
            super().__init__()
            if self.error:
                return
            while EventSelector().run():
                pass
        except KeyboardInterrupt:
            pass

    @property
    def log_file_path(self) -> Path:
        return LOG_DIR / PLUGIN_NAME / f'{APP_NAME}.log'
