from abc import ABC, abstractmethod
import base64
from io import BytesIO
from typing import TYPE_CHECKING

import PIL
import qrcode

from common import BASE_DIR, Path
from common.i18n import _
from data.event import SharlyChessConfig
from utils.entity import IdentifiableEntity

if TYPE_CHECKING:
    from data.print_documents.documents import QRCodePrintDocument


class QRCodeType(IdentifiableEntity, ABC):
    @staticmethod
    @abstractmethod
    def get_valid_options() -> list[str]:
        """Returns a dict of valid options for the QR code type."""

    @staticmethod
    def generate_qr_code(
        url: str,
        logo: Path | None = None,
    ) -> str:
        qr = qrcode.QRCode(
            box_size=40 if logo else 10,
            border=2 if logo else 0,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
        )
        qr.add_data(url)
        qr.make()
        img = qr.make_image(
            # use tuples instead of 'black'/'white' to allow colored logos
            fill_color=(0, 0, 0),
            back_color=(255, 255, 255),
        )
        if logo:
            logo_img = PIL.Image.open(logo)
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

        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f'data:image/png;base64,{img_str}'

    @staticmethod
    @abstractmethod
    def url(doc: 'QRCodePrintDocument') -> tuple[bool, str]:
        """Returns the URL of the QR code, or an error message."""

    @staticmethod
    @abstractmethod
    def get_qr_code(url: str) -> str:
        """Returns the QR code as a base64 encoded string."""

    @staticmethod
    @abstractmethod
    def title(doc: 'QRCodePrintDocument') -> str:
        """Returns the page title."""

    @staticmethod
    def subtitle(doc: 'QRCodePrintDocument') -> str | None:
        """Returns the page subtitle."""
        return None

    @staticmethod
    @abstractmethod
    def info(doc: 'QRCodePrintDocument') -> str:
        """Returns info to display under the QR code."""


class NetworkQRCodeType(QRCodeType):
    @staticmethod
    def static_id() -> str:
        return 'network'

    @staticmethod
    def static_name() -> str:
        return _('Network')

    @staticmethod
    def get_valid_options() -> list[str]:
        from data.print_documents.options import QRCodeNetworkPrintOption

        return [QRCodeNetworkPrintOption.static_id()]

    @staticmethod
    def title(doc: 'QRCodePrintDocument') -> str:
        return 'Sharly Chess'

    @staticmethod
    def info(doc: 'QRCodePrintDocument') -> str:
        from data.print_documents.options import QRCodeNetworkPrintOption

        ip = doc._get_option(QRCodeNetworkPrintOption).value
        details = next(
            (iface for iface in SharlyChessConfig().lan_ifaces if iface['ip'] == ip),
            None,
        )
        if not details or 'type' not in details:
            return _(
                'Connect to the Sharly Chess network, then scan to access the Sharly Chess server.'
            )

        return _(
            'Connect to the Sharly Chess network via {type},<br />then scan to access the Sharly Chess server.'
        ).format(type=details['type'])

    @staticmethod
    def url(doc: 'QRCodePrintDocument') -> tuple[bool, str]:
        from data.print_documents.options import QRCodeNetworkPrintOption

        ip = doc._get_option(QRCodeNetworkPrintOption).value
        return True, SharlyChessConfig().app_url(ip)

    @staticmethod
    def get_qr_code(url: str) -> str:
        return QRCodeType.generate_qr_code(
            url=url,
            logo=BASE_DIR
            / 'src'
            / 'web'
            / 'static'
            / 'images'
            / 'sharly-chess-qr-logo.jpg',
        )
