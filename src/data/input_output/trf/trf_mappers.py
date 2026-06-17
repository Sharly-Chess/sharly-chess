from data.pairings import PairingVariation
from data.pairings.variations import (
    BergerRoundRobinVariation,
    BergerTeamRoundRobinVariation,
    DoubleBergerRoundRobinVariation,
    DoubleBergerTeamRoundRobinVariation,
    StandardSwissVariation,
    StandardTeamSwissVariation,
)
from plugins.pairing_acceleration.pairing_variations import BakuSwissVariation
from utils import CoreMapper
from utils.enum import (
    BoardColor,
    PlayerGender,
    PlayerTitle,
    Result,
    ScoreType,
    TeamColourType,
)


class TrfPlayerGender(CoreMapper[str, PlayerGender]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, PlayerGender]:
        return {
            '': PlayerGender.NONE,
            ' ': PlayerGender.NONE,
            'm': PlayerGender.MAN,
            'w': PlayerGender.WOMAN,
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


class TrfPointSystemResult(CoreMapper[str, Result]):
    @staticmethod
    def _core_object_by_outer_value() -> dict[str, Result]:
        return {
            'W': Result.WIN,
            'D': Result.DRAW,
            'L': Result.LOSS,
            'A': Result.ZERO_POINT_BYE,
            'P': Result.PAIRING_ALLOCATED_BYE,
        }


class TrfEncodedType:
    @classmethod
    def get_pairing_variation(cls, encoded_type: str) -> PairingVariation:
        variation = cls.get_supported_pairing_variation(encoded_type)
        if variation:
            return variation
        variation = cls.get_supported_pairing_variation(
            cls.get_not_supported_default_type(encoded_type)
        )
        assert variation is not None
        return variation

    @staticmethod
    def get_supported_pairing_variation(encoded_type: str) -> PairingVariation | None:
        match encoded_type:
            case 'FIDE_DUTCH_2026' | 'FIDE_DUTCH':
                return StandardSwissVariation()
            case 'FIDE_DUTCH_2026_BAKU' | 'FIDE_DUTCH_BAKU':
                return BakuSwissVariation()
            case 'FIDE_ROUNDROBIN' | 'BERGER_ROUNDROBIN' | 'BERGER_ROUNDROBIN_G1':
                return BergerRoundRobinVariation()
            case 'FIDE_DOUBLEROUNDROBIN':
                return DoubleBergerRoundRobinVariation()
            case 'OTHER_TEAM_ROUNDROBIN':
                return BergerTeamRoundRobinVariation()
            case 'OTHER_TEAM_DOUBLEROUNDROBIN':
                return DoubleBergerTeamRoundRobinVariation()
            case _ if encoded_type.startswith(
                ('FIDE_TEAM_TYPEA_', 'FIDE_TEAM_TYPEB_', 'FIDE_TEAM_')
            ):
                # FIDE_TEAM_[TYPE<A|B>_]<primary>[_<secondary>] team-Swiss
                # code. Score config + colour-preference rule are
                # recovered separately via ``get_team_score_config`` and
                # ``get_team_colour_type``; the variation itself is the
                # same Standard Team Swiss in every case (the bare
                # ``FIDE_TEAM_…`` prefix is the no-preference variant).
                return StandardTeamSwissVariation()
            case _:
                return None

    @staticmethod
    def get_team_score_config(
        encoded_type: str,
    ) -> tuple[ScoreType, ScoreType] | None:
        """Decode a ``FIDE_TEAM_TYPE<A|B>_<primary>[_<secondary>]``
        team-Swiss code into ``(primary_score, secondary_score)``.
        Returns ``None`` for codes that don't carry score config
        (non-team or unparseable). MP-only / GP-only codes echo the
        primary as the secondary."""
        suffix = TrfEncodedType._team_code_suffix(encoded_type)
        if suffix is None:
            return None
        parts = suffix.split('_')
        score_by_code = {'MP': ScoreType.MATCH_POINTS, 'GP': ScoreType.GAME_POINTS}
        if not parts or parts[0] not in score_by_code:
            return None
        primary = score_by_code[parts[0]]
        if len(parts) == 1:
            return primary, primary
        if parts[1] not in score_by_code:
            return None
        return primary, score_by_code[parts[1]]

    @staticmethod
    def get_team_colour_type(encoded_type: str) -> TeamColourType | None:
        """Decode the colour-preference rule (A / B / NONE) embedded in a
        team-Swiss encoded type. Returns ``None`` if the code isn't a
        team-Swiss code at all. The bare ``FIDE_TEAM_<P>[_<S>]`` prefix
        (no ``TYPE<A|B>_`` infix) corresponds to ``TeamColourType.NONE``
        — the FIDE convention for events that opt out of colour
        preferences."""
        if encoded_type.startswith('FIDE_TEAM_TYPEA_'):
            return TeamColourType.A
        if encoded_type.startswith('FIDE_TEAM_TYPEB_'):
            return TeamColourType.B
        if encoded_type.startswith('FIDE_TEAM_'):
            return TeamColourType.NONE
        return None

    @staticmethod
    def _team_code_suffix(encoded_type: str) -> str | None:
        for prefix in ('FIDE_TEAM_TYPEA_', 'FIDE_TEAM_TYPEB_', 'FIDE_TEAM_'):
            if encoded_type.startswith(prefix):
                return encoded_type[len(prefix) :]
        return None

    @classmethod
    def get_not_supported_default_type(cls, encoded_type: str) -> str:
        match encoded_type:
            case (
                'BERGER_ROUNDROBIN_G2'
                | 'BERGER_DOUBLEROUNDROBIN'
                | 'FIDE_SCHEVENINGEN_G2'
                | 'FIDE_DOUBLESCHEVENINGEN'
            ):
                return 'FIDE_DOUBLEROUNDROBIN'
            case (
                'CUSTOM_ROUNDROBIN'
                | 'FIDE_SCHILLER'
                | 'CUSTOM_SCHILLER'
                | 'CUSTOM_SCHEVENINGEN'
                | 'FIDE_SCHEVENINGEN_G1'
                | 'CUSTOM_KNOCKOUT'
            ):
                return 'FIDE_ROUNDROBIN'
            case _:
                if 'ROUNDROBIN' in encoded_type or 'SCHEVENINGEN' in encoded_type:
                    return 'FIDE_ROUNDROBIN'
                return 'FIDE_DUTCH_2026'


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
    ) -> str:
        if is_bye:
            return '-'
        return super().get_outer_value(core_object) or ' '
