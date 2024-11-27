import base64
from logging import Logger
from pathlib import Path

import validators

from common import get_logger
from common.papi_web_config import PapiWebConfig

logger: Logger = get_logger()


def inline_image_url(image: str | None) -> str:
    """
    Return a true URL or
    :param image: an already true-URL (absolute or relative starting by '/')
    or the path of a custom file (a path relative to /custom is expected)
    :return: a true URL (data-inline if a file path is provided).
    If no file could be found, returns the error image.
    """
    if not image:
        return ''
    if image.startswith('/') or validators.url(image):
        return image
    file: Path = PapiWebConfig.custom_path / image
    if not file.exists():
        file: Path = PapiWebConfig.embedded_custom_path / image
        if not file.exists():
            logger.warning(f'L\'image [{file}] n\'existe pas.')
            return PapiWebConfig.error_background_image
    with open(file, 'rb') as f:
        data: bytes = f.read()
    encoded_data: str = base64.b64encode(data).decode('utf-8')
    return f'data:image/{file.suffix};base64,{encoded_data}'
