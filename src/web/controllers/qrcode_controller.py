from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import qrcode
import PIL.Image
from litestar import get
from litestar.plugins.htmx import HTMXRequest
from litestar.response import File

from common import BASE_DIR
from common.sharly_chess_config import SharlyChessConfig
from web.controllers.base_controller import BaseController


class QRCodeController(BaseController):
    @staticmethod
    def qrcode_response(
        url: str | None = None,
        filename_suffix: str | None = None,
        logo: bool = False,
    ) -> File:
        qr = qrcode.QRCode(
            box_size=40 if logo else 10,
            border=2 if logo else 0,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
        )
        # fallback to the website if no URL provided
        qr.add_data(url or SharlyChessConfig().url)
        qr.make()
        img = qr.make_image(fill_color='black', back_color='white')
        if logo:
            logo_file: Path = (
                BASE_DIR
                / 'src'
                / 'web'
                / 'static'
                / 'images'
                / 'sharly-chess-qr-logo.jpg'
            )
            logo_img = PIL.Image.open(logo_file)
            base_width: int = 360
            width_percent: float = base_width / float(logo_img.size[0])
            height_size = int((float(logo_img.size[1]) * float(width_percent)))
            resized_logo = logo_img.resize(
                (base_width, height_size), PIL.Image.Resampling.LANCZOS
            )
            pos = (
                (img.size[0] - resized_logo.size[0]) // 2,
                (img.size[1] - resized_logo.size[1]) // 2,
            )
            img.paste(resized_logo, pos)
        temp_file = NamedTemporaryFile(delete=False, mode='wb', suffix='.jpg')
        img.save(temp_file, format='jpeg')
        return File(
            path=temp_file.name,
            filename=f'sharly_chess_qr{"_logo" if logo else ""}_{filename_suffix or "website"}.jpg',
            content_disposition_type='inline',
        )

    @get(
        path='/qrcode/lan_url',
        name='qrcode-lan-url',
    )
    async def qrcode(
        self,
        request: HTMXRequest,
        logo: Any = None,
    ) -> File:
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        suffix: str | None = None
        if sharly_chess_config.lan_ip:
            suffix = f'lan_url_{sharly_chess_config.lan_ip.replace(".", "_")}'
        return self.qrcode_response(
            url=sharly_chess_config.lan_url,
            filename_suffix=suffix,
            logo=logo is not None,
        )
