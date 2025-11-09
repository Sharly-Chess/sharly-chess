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
        template_css_class: str,
    ) -> str:
        return '\n'.join(
            f'{locator} {{\n{"\n".join(f"\t{key}: {value};" for key, value in properties.items())}\n}}'
            for locator, properties in self._css_properties(template_css_class).items()
        )

    def _css_properties(
        self,
        template_css_class: str,
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

    def _css_properties(
        self,
        template_css_class: str,
    ) -> dict[str, dict[str, str]]:
        return {
            ', '.join(
                [
                    f'.{template_css_class} .side-back .card-cell.top',
                    f'.{template_css_class} .side-single .card-cell.top',
                ]
            ): {
                'border-top': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .card-cell.right',
                ]
            ): {
                'border-right': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .side-front .card-cell.bottom',
                    f'.{template_css_class} .side-single .card-cell.bottom',
                ]
            ): {
                'border-bottom': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .card-cell.left',
                ]
            ): {
                'border-left': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .side-front',
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

    def _css_properties(
        self,
        template_css_class: str,
    ) -> dict[str, dict[str, str]]:
        return {
            ', '.join(
                [
                    f'.{template_css_class} .side-back .card-cell.top.left',
                    f'.{template_css_class} .side-back .card-cell.top.right',
                    f'.{template_css_class} .side-single .card-cell.top.left',
                    f'.{template_css_class} .side-single .card-cell.top.right',
                ]
            ): {
                'border-top': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .card-cell.top.right',
                    f'.{template_css_class} .card-cell.bottom.right',
                ]
            ): {
                'border-right': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .side-front .card-cell.bottom.left',
                    f'.{template_css_class} .side-front .card-cell.bottom.right',
                    f'.{template_css_class} .side-single .card-cell.bottom.left',
                    f'.{template_css_class} .side-single .card-cell.bottom.right',
                ]
            ): {
                'border-bottom': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .card-cell.top.left',
                    f'.{template_css_class} .card-cell.bottom.left',
                ]
            ): {
                'border-left': self.border_style,
            },
            ', '.join(
                [
                    f'.{template_css_class} .side-front',
                ]
            ): {
                'border-top': self.dotted_style,
            },
        }
