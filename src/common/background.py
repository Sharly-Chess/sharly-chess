import base64
from logging import Logger
from pathlib import Path

import validators

from common import CUSTOM_DIR
from common.logger import get_logger
from common.sharly_chess_config import SharlyChessConfig

logger: Logger = get_logger()


def inline_image_url(image: str | None) -> str:
    """
    :param image: an already true-URL (absolute or relative starting by '/')
    or the path of a custom file (a path relative to /custom is expected)
    :return: a true URL (data-inline if a file path is provided).
    If no file could be found, returns the error image.
    """
    if not image:
        return ''
    if image.startswith('/') or validators.url(image):
        return image
    file: Path = CUSTOM_DIR / image
    if not file.exists():
        logger.warning('Image [%s] not found.', file)
        return SharlyChessConfig.error_background_image
    with open(file, 'rb') as f:
        data: bytes = f.read()
    encoded_data = base64.b64encode(data).decode('utf-8')
    image_type = file.suffix.lower().replace('.', '').replace('\\n', '')
    if image_type == 'svg':
        return f'data:image/{image_type}+xml;base64,{encoded_data}'
    else:
        return f'data:image/{image_type};base64,{encoded_data}'
