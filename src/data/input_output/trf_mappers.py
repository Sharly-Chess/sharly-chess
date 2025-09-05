from utils import CoreMapper
from utils.enum import PlayerGender, PlayerTitle, Result, BoardColor


class TrfPlayerGender(CoreMapper[str, PlayerGender]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, PlayerGender]:
        return {
            '': PlayerGender.NONE,
            'm': PlayerGender.MALE,
            'w': PlayerGender.FEMALE,
        }


class TrfPlayerTitle(CoreMapper[str, PlayerTitle]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, PlayerTitle]:
        return {
            '': PlayerTitle.NONE,
            'cf': PlayerTitle.WOMAN_CANDIDATE_MASTER,
            'c': PlayerTitle.CANDIDATE_MASTER,
            'ff': PlayerTitle.WOMAN_FIDE_MASTER,
            'f': PlayerTitle.FIDE_MASTER,
            'mf': PlayerTitle.WOMAN_INTERNATIONAL_MASTER,
            'm': PlayerTitle.INTERNATIONAL_MASTER,
            'gf': PlayerTitle.WOMAN_GRANDMASTER,
            'g': PlayerTitle.GRANDMASTER,
        }


class TrfResult(CoreMapper[str, Result]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, Result]:
        return {
            '0': Result.LOSS,
            '=': Result.DRAW,
            '1': Result.WIN,
            'L': Result.UNRATED_LOSS,
            'D': Result.UNRATED_DRAW,
            'W': Result.UNRATED_WIN,
            '-': Result.FORFEIT_LOSS,
            '+': Result.FORFEIT_WIN,
            'H': Result.HALF_POINT_BYE,
            'F': Result.FULL_POINT_BYE,
            'U': Result.PAIRING_ALLOCATED_BYE,
            'Z': Result.ZERO_POINT_BYE,
        }

    @classmethod
    def get_outer_value(cls, core_object: Result) -> str:
        if trf_result := super().get_outer_value(core_object):
            return trf_result
        trf_result_by_result = {
            Result.DOUBLE_FORFEIT: '-',
            Result.PENALTY_LL: '0',
            Result.PENALTY_LD: '0',
            Result.PENALTY_DL: '=',
            Result.UNRATED_PENALTY_LL: 'L',
            Result.UNRATED_PENALTY_LD: 'L',
            Result.UNRATED_PENALTY_DL: 'D',
            Result.REST_GAME: ' ',
            Result.NO_RESULT: ' ',
        }
        if core_object in trf_result_by_result:
            return trf_result_by_result[core_object]
        raise ValueError(f'Unhandled result ({core_object.value})')

    @classmethod
    def get_core_object(
        cls,
        outer_value: str,
        has_opponent: bool = False,
        is_round_robin: bool = False,
    ) -> Result:
        if outer_value == ' ':
            if has_opponent:
                return Result.NO_RESULT
            if is_round_robin:
                return Result.REST_GAME
            return Result.ZERO_POINT_BYE
        return super().get_core_object(outer_value)


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
