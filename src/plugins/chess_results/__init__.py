from pathlib import Path

import common
from plugins import PLUGINS_DIR

PLUGIN_NAME: str = 'chess_results'
PLUGIN_DIR: Path = PLUGINS_DIR / PLUGIN_NAME
TMP_DIR: Path = common.TMP_DIR / PLUGIN_NAME
TMP_DIR.mkdir(parents=True, exist_ok=True)
MAX_TIE_BREAKS: int = 6
