from abc import ABC

from common.i18n import _
from utils.entity import IdentifiableEntity


class PlaceCardCutting(IdentifiableEntity, ABC):
    solid_style: str = '1px solid black'
    dashed_style: str = '1px dashed black'

    @property
    def style(self) -> str:
        return ''

    @property
    def css(self) -> dict[str, dict[str, str]]:
        return {}


class NonePlaceCardCutting(PlaceCardCutting):
    @staticmethod
    def static_id() -> str:
        return 'none'

    @staticmethod
    def static_name() -> str:
        return _('No marks')


class BorderPlaceCardCutting(PlaceCardCutting):
    @staticmethod
    def static_id() -> str:
        return 'border'

    @staticmethod
    def static_name() -> str:
        return _('Border')

    @property
    def css(self) -> dict[str, dict[str, str]]:
        return {
            ', '.join(
                [
                    '.side-back .card-cell.top',
                    '.side-single .card-cell.top',
                ]
            ): {
                'border-top': self.style,
            },
            ', '.join(
                [
                    '.card-cell.right',
                ]
            ): {
                'border-right': self.style,
            },
            ', '.join(
                [
                    '.side-front .card-cell.bottom',
                    '.side-single .card-cell.bottom',
                ]
            ): {
                'border-bottom': self.style,
            },
            ', '.join(
                [
                    '.card-cell.left',
                ]
            ): {
                'border-left': self.style,
            },
        }


class SolidBorderPlaceCardCutting(BorderPlaceCardCutting):
    @staticmethod
    def static_id() -> str:
        return 'border'

    @staticmethod
    def static_name() -> str:
        return _('Border')

    @property
    def style(self) -> str:
        return self.solid_style


class DashedBorderPlaceCardCutting(BorderPlaceCardCutting):
    @staticmethod
    def static_id() -> str:
        return 'dashed-border'

    @staticmethod
    def static_name() -> str:
        return _('Dashed border')

    @property
    def style(self) -> str:
        return self.dashed_style


class CornersPlaceCardCutting(PlaceCardCutting):
    @staticmethod
    def static_id() -> str:
        return 'corners'

    @staticmethod
    def static_name() -> str:
        return _('Corners')

    @property
    def style(self) -> str:
        return self.solid_style

    @property
    def css(self) -> dict[str, dict[str, str]]:
        return {
            ', '.join(
                [
                    '.side-back .card-cell.top.left',
                    '.side-back .card-cell.top.right',
                    '.side-single .card-cell.top.left',
                    '.side-single .card-cell.top.right',
                ]
            ): {
                'border-top': self.style,
            },
            ', '.join(
                [
                    '.side-back .card-cell.top.right',
                    '.side-front .card-cell.bottom.right',
                    '.side-single .card-cell.top.right',
                    '.side-single .card-cell.bottom.right',
                ]
            ): {
                'border-right': self.style,
            },
            ', '.join(
                [
                    '.side-front .card-cell.bottom.left',
                    '.side-front .card-cell.bottom.right',
                    '.side-single .card-cell.bottom.left',
                    '.side-single .card-cell.bottom.right',
                ]
            ): {
                'border-bottom': self.style,
            },
            ', '.join(
                [
                    '.side-back .card-cell.top.left',
                    '.side-single .card-cell.top.left',
                    '.side-front .card-cell.bottom.left',
                    '.side-single .card-cell.bottom.left',
                ]
            ): {
                'border-left': self.style,
            },
        }
