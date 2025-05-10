from pathlib import Path

from common import LOG_DIR, APP_NAME
from common.engine import Engine
from plugins.ffe import PLUGIN_NAME
from plugins.ffe.engine.event_selector import EventSelector


class FFEEngine(Engine):
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
        return LOG_DIR / PLUGIN_NAME / f'{APP_NAME}-{PLUGIN_NAME}.log'
