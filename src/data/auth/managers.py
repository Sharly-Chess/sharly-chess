from data.auth.roles import (
    Role,
    SpectatorRole,
    ResultsEntryRole,
    AdministrationRole,
    OrganizationRole,
    ScreenManagementRole,
    ChiefArbitrationRole,
    DeputyChiefArbitrationRole,
    SectorArbitrationRole,
    PairingRole,
    CheckInRole,
)
from utils.entity import EntityManager


class RoleManager(EntityManager[Role]):
    @staticmethod
    def entity_types() -> list[type[Role]]:
        return [
            AdministrationRole,
            OrganizationRole,
            ScreenManagementRole,
            ChiefArbitrationRole,
            DeputyChiefArbitrationRole,
            SectorArbitrationRole,
            PairingRole,
            CheckInRole,
            ResultsEntryRole,
            SpectatorRole,
        ]
