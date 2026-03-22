import os
from pathlib import Path

from plugins import PLUGINS_DIR

PLUGIN_NAME: str = 'sce'
PLUGIN_DIR: Path = PLUGINS_DIR / PLUGIN_NAME

SCE_BASE_URL = os.getenv('SCE_BASE_URL') or 'http://localhost:3001'
SCE_SYNC_DELAY = 3
SCE_UPLOAD_DELAY = 3
SCE_CLIENT_ID = 'sharlychess'
