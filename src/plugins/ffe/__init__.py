from pathlib import Path

import common
from plugins import PLUGINS_DIR

PLUGIN_NAME: str = 'ffe'
PLUGIN_DIR: Path = PLUGINS_DIR / PLUGIN_NAME
TMP_DIR: Path = common.TMP_DIR / PLUGIN_NAME
