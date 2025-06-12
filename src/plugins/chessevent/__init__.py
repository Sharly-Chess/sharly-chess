import sys
from pathlib import Path

import common
from plugins import PLUGINS_DIR

PLUGIN_NAME: str = 'chessevent'
PLUGIN_DIR: Path = PLUGINS_DIR / PLUGIN_NAME
TMP_DIR: Path = common.TMP_DIR / PLUGIN_NAME

try:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError as error:
    from common.logger import get_logger

    logger = get_logger()
    logger.critical(
        'Could not create directory [%s]: %s',
        TMP_DIR.absolute(),
        error,
    )
    input()
    sys.exit(1)
