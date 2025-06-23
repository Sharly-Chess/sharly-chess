from pathlib import Path
from tempfile import NamedTemporaryFile

import qrcode
import PIL.Image
from litestar import get
from litestar.plugins.htmx import HTMXRequest
from litestar.response import File

from common import BASE_DIR
from common.sharly_chess_config import SharlyChessConfig
from web.controllers.base_controller import BaseController


class QRCodeController(BaseController):
    def qrcode_response(
        self,
        url: str | None,
        filename_suffix: str,
    ) -> File:
        temp_file = NamedTemporaryFile(delete=False, mode='wb', suffix='.jpg')
        logo_file: Path = (
            BASE_DIR / 'src' / 'web' / 'static' / 'images' / 'sharly-chess-qr-logo.jpg'
        )
        logo = PIL.Image.open(logo_file)
        base_width: int = 225
        width_percent = base_width / float(logo.size[0])
        height_size = int((float(logo.size[1]) * float(width_percent)))
        resized_logo = logo.resize(
            (base_width, height_size), PIL.Image.Resampling.LANCZOS
        )
        qr = qrcode.QRCode(
            box_size=24,
            border=2,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
        )
        # fallback to the website if no URL provided
        qr.add_data(url or SharlyChessConfig().url)
        qr.make()
        img = qr.make_image(fill_color=(34, 37, 41), back_color=(223, 226, 230))
        pos = (
            (img.size[0] - resized_logo.size[0]) // 2,
            (img.size[1] - resized_logo.size[1]) // 2,
        )
        img.paste(resized_logo, pos)
        img.save(temp_file, format='jpeg')
        return File(
            path=temp_file.name, filename=f'sharly_chess_qr_{filename_suffix}.jpg'
        )

    @get(
        path='/qrcode/lan_url',
        name='qrcode-lan-url',
        cache=1,
    )
    async def qrcode(
        self,
        request: HTMXRequest,
    ) -> File:
        return self.qrcode_response(
            url=SharlyChessConfig().lan_url,
            filename_suffix='lan_url',
        )
