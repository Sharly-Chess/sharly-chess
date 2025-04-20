import logging
from logging import Logger, getLogger
from logging.config import dictConfig

from colorama import Fore, Style

from common import APP_NAME, LOG_FILE


LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'colored': {
            '()': 'colorlog.ColoredFormatter',
            'fmt': '%(log_color)s%(asctime)s %(levelname)-10s%(message)s%(reset)s',
            'datefmt': '%y-%m-%d %H:%M:%S',
            'reset': True,
            'log_colors': {
                'DEBUG': 'white',
                'INFO': 'light_white',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_light_white',
            },
            'secondary_log_colors': {},
            'style': '%',
        },
        'standard': {
            'format': '%(asctime)s %(levelname)-10s%(message)s',
            'datefmt': '%y-%m-%d %H:%M:%S',
            'style': '%',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': logging.INFO,
            'formatter': 'colored',
            'stream': 'ext://sys.stdout',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': logging.DEBUG,
            'formatter': 'standard',
            'filename': str(LOG_FILE),
            'maxBytes': 500 * 1024,
            'backupCount': 5,
            'encoding': 'UTF-8',
        },
    },
    'loggers': {
        APP_NAME: {
            'handlers': ['console', 'file'],
            'level': logging.DEBUG,
            'propagate': False,
        },
        'litestar': {
            'handlers': ['console', 'file'],
            'level': logging.INFO,
        },
        'uvicorn': {
            'handlers': ['console', 'file'],
            'level': logging.INFO,
            'propagate': False,
        },
        'uvicorn.error': {
            'handlers': ['console', 'file'],
            'level': logging.INFO,
            'propagate': False,
        },
        'uvicorn.access': {
            'handlers': ['console', 'file'],
            'level': logging.INFO,
            'propagate': False,
        },
    },
}

dictConfig(LOGGING_CONFIG)
logger: Logger = getLogger(APP_NAME)


def get_logger() -> Logger:
    """Returns the global logger."""
    return logger


def set_console_log_level(level: int):
    LOGGING_CONFIG['handlers']['console']['level'] = level  # type: ignore
    dictConfig(LOGGING_CONFIG)
    global logger
    logger = getLogger(APP_NAME)


def __flush_logger():
    for handler in logger.handlers:
        handler.flush()


def print_interactive_info(string: str, end='\n'):
    """Prints the message to stdout with color."""
    __flush_logger()
    print(Fore.LIGHTWHITE_EX + Style.BRIGHT + string + Style.RESET_ALL, end=end)


def print_interactive_success(string: str, end='\n'):
    """Prints the message to stdout with color."""
    __flush_logger()
    print(Fore.GREEN + Style.BRIGHT + string + Style.RESET_ALL, end=end)


def print_interactive_warning(string: str, end='\n'):
    """Prints the message to stdout with color."""
    __flush_logger()
    print(Fore.YELLOW + Style.BRIGHT + string + Style.RESET_ALL, end=end)


def print_interactive_error(string: str, end='\n'):
    """Prints the message to stdout with color."""
    __flush_logger()
    print(Fore.RED + Style.BRIGHT + string + Style.RESET_ALL, end=end)


def print_interactive_input(string: str, end='\n'):
    """Prints the message to stdout with color."""
    __flush_logger()
    print(Fore.CYAN + Style.BRIGHT + string + Style.RESET_ALL, end=end)


def input_interactive(string: str) -> str:
    """Prints the message to stdout with color, and returns the user input.
    If the message could not be Unicode decoded, raises KeyboardInterrupt."""
    __flush_logger()
    print(Fore.CYAN + Style.BRIGHT + string + Style.RESET_ALL, end='')
    try:
        result = input().strip().upper()
    except UnicodeDecodeError as exc:
        raise KeyboardInterrupt() from exc
    return result
