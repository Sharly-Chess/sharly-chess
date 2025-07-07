from data.auth.roles import (
    Role,
    SpectatorRole,
    ResultOfficerRole,
    AdministratorRole,
    OrganizerRole,
    DisplayManagerRole,
    ChiefArbiterRole,
    DeputyChiefArbiterRole,
    SectorArbiterRole,
    PairingsOfficerRole,
    CheckInOfficerRole,
)
from utils.entity import EntityManager


class RoleManager(EntityManager[Role]):
    @staticmethod
    def entity_types() -> list[type[Role]]:
        return [
            AdministratorRole,
            OrganizerRole,
            DisplayManagerRole,
            ChiefArbiterRole,
            DeputyChiefArbiterRole,
            SectorArbiterRole,
            PairingsOfficerRole,
            CheckInOfficerRole,
            ResultOfficerRole,
            SpectatorRole,
        ]
