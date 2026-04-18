from typing import Any

from data.criteria.tournament_criteria import (
    TournamentCriterion,
    RatingTournamentCriterion,
    AgeCategoryTournamentCriterion,
    GenderTournamentCriterion,
    ClubTournamentCriterion,
    FederationTournamentCriterion,
)
from data.pairings.systems import SwissPairingSystem, RoundRobinPairingSystem
from data.pairings import PairingSystem
from plugins.ffe.ffe_entity import (
    FfeLicenceTournamentCriterion,
    FfeLeagueTournamentCriterion,
)
from utils import CoreMapper
from utils.enum import PlayerGender, PlayerRatingType


class SCEPlayerGender(CoreMapper[str, PlayerGender]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PlayerGender]:
        return {
            'M': PlayerGender.MAN,
            'W': PlayerGender.WOMAN,
        }


class SCEPlayerRatingType(CoreMapper[str, PlayerRatingType]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PlayerRatingType]:
        return {
            'F': PlayerRatingType.FIDE,
            'N': PlayerRatingType.NATIONAL,
            'E': PlayerRatingType.ESTIMATED,
        }


class SCEPairingSystem(CoreMapper[str, PairingSystem]):
    @classmethod
    def _core_object_by_outer_value(cls) -> dict[str, PairingSystem]:
        return {
            'swiss': SwissPairingSystem(),
            'roundrobin': RoundRobinPairingSystem(),
        }


class SCEAgeCategory:
    @staticmethod
    def core_id_from_sce_id(sce_id: str) -> str:
        if sce_id.endswith('+'):
            return f'O{sce_id[:-1]}'
        return sce_id

    @staticmethod
    def sce_id_from_core_id(core_id: str) -> str:
        if core_id.startswith('O'):
            return f'{core_id[1:]}+'
        return core_id


class SCETournamentCriteria:
    @classmethod
    def sce_data_to_core_value(
        cls, sce_data: dict[str, Any]
    ) -> list[TournamentCriterion]:
        criteria: list[TournamentCriterion] = []

        rating_min = sce_data.get('ratingMin')
        rating_max = sce_data.get('ratingMax')
        if rating_min or rating_max:
            criteria.append(
                RatingTournamentCriterion({'min': rating_min, 'max': rating_max})
            )
        category_min = sce_data.get('ageCategoryMin')
        category_max = sce_data.get('ageCategoryMax')
        if category_min or category_max:
            min_category_id = (
                SCEAgeCategory.core_id_from_sce_id(category_min)
                if category_min
                else None
            )
            max_category_id = (
                SCEAgeCategory.core_id_from_sce_id(category_max)
                if category_max
                else None
            )
            criteria.append(
                AgeCategoryTournamentCriterion(
                    {'min': min_category_id, 'max': max_category_id}
                )
            )
        if gender := sce_data.get('gender'):
            criteria.append(
                GenderTournamentCriterion(SCEPlayerGender.get_core_object(gender).value)
            )
        if ffe_licence := sce_data.get('ffeLicenceMin'):
            criteria.append(FfeLicenceTournamentCriterion(ffe_licence))
        if ffe_league := sce_data.get('ffeLeague'):
            criteria.append(FfeLeagueTournamentCriterion(ffe_league))
        if club := sce_data.get('club'):
            criteria.append(ClubTournamentCriterion(club))
        if federation := sce_data.get('federation'):
            criteria.append(FederationTournamentCriterion(federation))

        return criteria

    @classmethod
    def core_value_to_sce_data(
        cls, criteria: list[TournamentCriterion]
    ) -> dict[str, Any]:
        sce_data: dict[str, Any] = {}
        for criterion in criteria:
            value = criterion.value
            if isinstance(criterion, RatingTournamentCriterion):
                sce_data['ratingMin'] = value.get('min')
                sce_data['ratingMax'] = value.get('max')
            elif isinstance(criterion, AgeCategoryTournamentCriterion):
                if min_category := value.get('min'):
                    sce_data['ageCategoryMin'] = SCEAgeCategory.sce_id_from_core_id(
                        min_category
                    )
                if max_category := value.get('max'):
                    sce_data['ageCategoryMax'] = SCEAgeCategory.sce_id_from_core_id(
                        max_category
                    )
            elif isinstance(criterion, GenderTournamentCriterion):
                sce_data['gender'] = SCEPlayerGender.get_outer_value(
                    PlayerGender(value)
                )
            elif isinstance(criterion, FfeLicenceTournamentCriterion):
                sce_data['ffeLicenceMin'] = value
            elif isinstance(criterion, FfeLeagueTournamentCriterion):
                sce_data['ffeLeague'] = value
            elif isinstance(criterion, ClubTournamentCriterion):
                sce_data['club'] = value
            elif isinstance(criterion, FederationTournamentCriterion):
                sce_data['federation'] = value

        return sce_data
