import logging


def build_gui_handler():
    if GUILogHandler.instance is None:
        # Fallback to a plain stream handler so dictConfig doesn't break
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(message)s'))
        return h

    return GUILogHandler.instance


class GUILogHandler(logging.Handler):
    """Custom logging handler that forwards to GUI."""

    instance: 'GUILogHandler | None' = None

    def __init__(self, gui_instance):
        super().__init__()
        self.gui = gui_instance

        GUILogHandler.instance = self

    def emit(self, record):
        try:
            msg = self.format(record)
            self.gui.add_log_message(msg)
        except Exception:
            self.handleError(record)
