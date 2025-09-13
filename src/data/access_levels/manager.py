from data.access_levels.access_levels import (
    AccessLevel,
    SpectatorAccessLevel,
    ResultsEntryAccessLevel,
    AdministrationAccessLevel,
    OrganizationAccessLevel,
    ScreenManagementAccessLevel,
    ChiefArbitrationAccessLevel,
    DeputyChiefArbitrationAccessLevel,
    SectorArbitrationAccessLevel,
    PairingAccessLevel,
    CheckInAccessLevel,
)
from utils.entity import EntityManager


class AccessLevelManager(EntityManager[AccessLevel]):
    @staticmethod
    def entity_types() -> list[type[AccessLevel]]:
        return [
            AdministrationAccessLevel,
            OrganizationAccessLevel,
            ScreenManagementAccessLevel,
            ChiefArbitrationAccessLevel,
            DeputyChiefArbitrationAccessLevel,
            PairingAccessLevel,
            SectorArbitrationAccessLevel,
            CheckInAccessLevel,
            ResultsEntryAccessLevel,
            SpectatorAccessLevel,
        ]
