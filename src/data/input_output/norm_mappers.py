from utils import CoreMapper
from utils.enum import Result, BoardColor


class NormResult(CoreMapper[str, Result]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, Result]:
        return {
            '0': Result.LOSS,
            '0.5': Result.DRAW,
            '1': Result.WIN,
        }

    @classmethod
    def get_outer_value(cls, core_object: Result) -> str:
        if norm_result := super().get_outer_value(core_object):
            return norm_result
        norm_result_by_result = {
            Result.UNRATED_LOSS: '-',
            Result.UNRATED_DRAW: '=',
            Result.UNRATED_WIN: '+',
            Result.FORFEIT_LOSS: '-',
            Result.FORFEIT_WIN: '+',
            Result.HALF_POINT_BYE: '',
            Result.FULL_POINT_BYE: '',
            Result.PAIRING_ALLOCATED_BYE: '+',
            Result.ZERO_POINT_BYE: '',
            Result.DOUBLE_FORFEIT: '-',
            Result.PENALTY_LL: '-',
            Result.PENALTY_LD: '-',
            Result.PENALTY_DL: '=',
            Result.UNRATED_PENALTY_LL: '-',
            Result.UNRATED_PENALTY_LD: '-',
            Result.UNRATED_PENALTY_DL: '=',
            Result.REST_GAME: '',
            Result.NO_RESULT: '',
        }
        if core_object in norm_result_by_result:
            return norm_result_by_result[core_object]
        raise ValueError(f'Unhandled result ({core_object.value})')


class TrfSeedColor(CoreMapper[str, BoardColor]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, BoardColor]:
        return {
            'white1': BoardColor.WHITE,
            'black1': BoardColor.BLACK,
        }


class TrfColor(CoreMapper[str, BoardColor | None]):  # type: ignore
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, BoardColor | None]:
        return {
            'w': BoardColor.WHITE,
            'b': BoardColor.BLACK,
            ' ': None,
            '-': None,
        }

    @classmethod
    def get_outer_value(
        cls,
        core_object: BoardColor | None,
        is_bye: bool = False,
    ) -> str | None:
        if is_bye:
            return '-'
        return super().get_outer_value(core_object)
