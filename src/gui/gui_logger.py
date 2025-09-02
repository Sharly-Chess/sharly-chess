import logging
import colorlog


def build_gui_handler():
    if GUILogHandler.instance is None:
        # Fallback to a plain stream handler so dictConfig doesn't break
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(message)s'))
        return h

    fmt = (
        '%(log_color)s%(levelname)-8s%(reset)s '  # colored level
        '%(message_log_color)s%(message)s%(reset)s'  # colored message
    )
    GUILogHandler.instance.setFormatter(
        colorlog.ColoredFormatter(
            fmt=fmt,
            datefmt='%Y-%m-%d %H:%M:%S',
            reset=True,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'white',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
            secondary_log_colors={
                'message': {
                    'DEBUG': 'cyan',
                    'INFO': 'white',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'bold_red',
                }
            },
            style='%',
        )
    )
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
            tag = (
                'error'
                if record.levelno >= logging.ERROR
                else 'warning'
                if record.levelno >= logging.WARNING
                else 'info'
                if record.levelno >= logging.INFO
                else 'debug'
            )
            # (optional) strip double resets at the end
            # msg = re.sub(r'(?:\x1b\[[0-9;]*m)+$', '\x1b[0m', msg)
            self.gui.add_log_message(msg, tag)
        except Exception:
            self.handleError(record)
