from common.engine import Engine
from plugins.ffe.engine.event_selector import EventSelector


class FFEEngine(Engine):
    def __init__(self):
        try:
            super().__init__()
            if self.updated:
                return
            while EventSelector().run():
                pass
        except KeyboardInterrupt:
            pass
