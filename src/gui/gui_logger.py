import logging
from typing import Any


def build_gui_handler() -> logging.Handler:
    if GUILogHandler.instance is None:
        return logging.NullHandler()

    return GUILogHandler.instance


class GUILogHandler(logging.Handler):
    """Custom logging handler that forwards to GUI."""

    instance: 'GUILogHandler | None' = None

    def __init__(self, gui_instance: Any) -> None:
        super().__init__()
        self.gui = gui_instance

        GUILogHandler.instance = self

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.gui.add_log_message(msg)
        except Exception:
            self.handleError(record)
