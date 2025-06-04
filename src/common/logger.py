import logging
from logging import Logger, getLogger
from logging.config import dictConfig
from pathlib import Path
from typing import Any

from colorama import Fore, Style

from common import APP_NAME


class LoggingConfigValues:
    """This class is used to store the parameters used to build the logging config."""

    console_log_level: int = logging.INFO
    console_color: bool = True
    console_show_date: bool = False
    console_show_level: bool = False
    file_path: Path | None = None


def default_logging_config_values() -> LoggingConfigValues:
    """The default values of the logging config, used in forms."""
    return LoggingConfigValues()


# The module logging parameters, used to build the logging config.
_LOGGING_CONFIG_VALUES: LoggingConfigValues = default_logging_config_values()
_LOGGER: Logger


def logging_config_values() -> LoggingConfigValues:
    """The default values of the logging config, used in forms."""
    global _LOGGING_CONFIG_VALUES
    return _LOGGING_CONFIG_VALUES


def set_logging_config(
    console_log_level: int | None = None,
    console_color: bool | None = None,
    console_show_date: bool | None = None,
    console_show_level: bool | None = None,
    file_path: Path | None = None,
) -> dict[str, Any]:
    """Set logging parameters, returns the logging config as a dict that can be used by logging libraries."""
    global _LOGGING_CONFIG_VALUES, _LOGGER
    if console_log_level is not None:
        _LOGGING_CONFIG_VALUES.console_log_level = console_log_level
    if console_color is not None:
        _LOGGING_CONFIG_VALUES.console_color = console_color
    if console_show_date is not None:
        _LOGGING_CONFIG_VALUES.console_show_date = console_show_date
    if console_show_level is not None:
        _LOGGING_CONFIG_VALUES.console_show_level = console_show_level
    if file_path is not None:
        _LOGGING_CONFIG_VALUES.file_path = file_path
    if _LOGGING_CONFIG_VALUES.file_path is not None:
        _LOGGING_CONFIG_VALUES.file_path.parent.mkdir(parents=True, exist_ok=True)
    dictConfig(logging_config := get_logging_config())
    _LOGGER = getLogger(APP_NAME)
    return logging_config


def get_logging_config() -> dict[str, Any]:
    """Returns the logging config as a dict that can be used by logging libraries."""
    global _LOGGING_CONFIG_VALUES
    console_format: str = f'{
        "%(log_color)s" if _LOGGING_CONFIG_VALUES.console_color else ""
    }{"%(asctime)s " if _LOGGING_CONFIG_VALUES.console_show_date else ""}{
        "%(levelname)-10s" if _LOGGING_CONFIG_VALUES.console_show_level else ""
    }%(message)s{"%(reset)s" if _LOGGING_CONFIG_VALUES.console_color else ""}'
    logging_config: dict[str, Any] = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'console_formatter': {
                '()': 'colorlog.ColoredFormatter',
                'fmt': console_format,
                'datefmt': '%Y-%m-%d %H:%M:%S',
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
            'file_formatter': {
                'format': '%(asctime)s %(levelname)-10s%(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S',
                'style': '%',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': _LOGGING_CONFIG_VALUES.console_log_level,
                'formatter': 'console_formatter',
                'stream': 'ext://sys.stdout',
            },
        },
        'loggers': {
            APP_NAME: {
                'handlers': ['console'],
                'level': logging.DEBUG,
                'propagate': False,
            },
            'litestar': {
                'handlers': ['console'],
                'level': logging.INFO,
            },
            'uvicorn': {
                'handlers': ['console'],
                'level': logging.INFO,
                'propagate': False,
            },
            'uvicorn.error': {
                'handlers': ['console'],
                'level': logging.INFO,
                'propagate': False,
            },
            'uvicorn.access': {
                'handlers': ['console'],
                'level': logging.INFO,
                'propagate': False,
            },
        },
    }
    if _LOGGING_CONFIG_VALUES.file_path:
        logging_config['handlers']['file'] = {  # type: ignore
            'class': 'logging.handlers.RotatingFileHandler',
            'level': logging.DEBUG,
            'formatter': 'file_formatter',
            'filename': str(_LOGGING_CONFIG_VALUES.file_path),
            'maxBytes': 500 * 1024,
            'backupCount': 5,
            'encoding': 'UTF-8',
        }
        for logger_name in logging_config['loggers']:
            logging_config['loggers'][logger_name]['handlers'].append('file')  # type: ignore
    return logging_config


set_logging_config()


def get_logger() -> Logger:
    """Returns the global logger."""
    global _LOGGER
    return _LOGGER


def __flush_logger():
    for handler in _LOGGER.handlers:
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
