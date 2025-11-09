from abc import ABC

from common.i18n import _
from utils.entity import IdentifiableEntity


class PlaceCardCropMarks(IdentifiableEntity, ABC):
    solid_style: str = '1px solid #000'
    dashed_style: str = '1px dashed #000'
    dotted_style: str = '1px dotted #aaa'

    @property
    def border_style(self) -> str:
        return ''

    def render_css(
        self,
    ) -> str:
        return '\n'.join(
            f'{locator} {{\n{"\n".join(f"\t{key}: {value};" for key, value in properties.items())}\n}}'
            for locator, properties in self._css_properties.items()
        )

    @property
    def _css_properties(
        self,
    ) -> dict[str, dict[str, str]]:
        return {}


class NonePlaceCardCropMarks(PlaceCardCropMarks):
    @staticmethod
    def static_id() -> str:
        return 'none'

    @staticmethod
    def static_name() -> str:
        return _('No marks')


class BorderPlaceCardCropMarks(PlaceCardCropMarks):
    @staticmethod
    def static_id() -> str:
        return 'border'

    @staticmethod
    def static_name() -> str:
        return _('Border')

    @property
    def top_border_style(self) -> str:
        return ''

    @property
    def _css_properties(self) -> dict[str, dict[str, str]]:
        return {
            ', '.join(
                [
                    '.side-back .card-cell.top',
                    '.side-single .card-cell.top',
                ]
            ): {
                'border-top': self.border_style,
            },
            ', '.join(
                [
                    '.card-cell.right',
                ]
            ): {
                'border-right': self.border_style,
            },
            ', '.join(
                [
                    '.side-front .card-cell.bottom',
                    '.side-single .card-cell.bottom',
                ]
            ): {
                'border-bottom': self.border_style,
            },
            ', '.join(
                [
                    '.card-cell.left',
                ]
            ): {
                'border-left': self.border_style,
            },
            ', '.join(
                [
                    '.side-front',
                ]
            ): {
                'border-top': self.dotted_style,
            },
        }


class SolidBorderPlaceCardCropMarks(BorderPlaceCardCropMarks):
    @staticmethod
    def static_id() -> str:
        return 'border'

    @staticmethod
    def static_name() -> str:
        return _('Border')

    @property
    def border_style(self) -> str:
        return self.solid_style


class DashedBorderPlaceCardCropMarks(BorderPlaceCardCropMarks):
    @staticmethod
    def static_id() -> str:
        return 'dashed-border'

    @staticmethod
    def static_name() -> str:
        return _('Dashed border')

    @property
    def border_style(self) -> str:
        return self.dashed_style


class CornersPlaceCardCropMarks(PlaceCardCropMarks):
    @staticmethod
    def static_id() -> str:
        return 'corners'

    @staticmethod
    def static_name() -> str:
        return _('Corners')

    @property
    def border_style(self) -> str:
        return self.solid_style

    @property
    def _css_properties(self) -> dict[str, dict[str, str]]:
        return {
            ', '.join(
                [
                    '.side-back .card-cell.top.left',
                    '.side-back .card-cell.top.right',
                    '.side-single .card-cell.top.left',
                    '.side-single .card-cell.top.right',
                ]
            ): {
                'border-top': self.border_style,
            },
            ', '.join(
                [
                    '.card-cell.top.right',
                    '.card-cell.bottom.right',
                ]
            ): {
                'border-right': self.border_style,
            },
            ', '.join(
                [
                    '.side-front .card-cell.bottom.left',
                    '.side-front .card-cell.bottom.right',
                    '.side-single .card-cell.bottom.left',
                    '.side-single .card-cell.bottom.right',
                ]
            ): {
                'border-bottom': self.border_style,
            },
            ', '.join(
                [
                    '.card-cell.top.left',
                    '.card-cell.bottom.left',
                ]
            ): {
                'border-left': self.border_style,
            },
            ', '.join(
                [
                    '.side-front',
                ]
            ): {
                'border-top': self.dotted_style,
            },
        }
