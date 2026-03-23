from plugins.sce.sce_event_status import (
    SCEEventStatus,
    PublishedSCEEventStatus,
    DraftSCEEventStatus,
    ArchivedSCEEventStatus,
    NoInternetSCEEventStatus,
    InvalidRefreshTokenSCEEventStatus,
    NotFoundSCEEventStatus,
    UnexpectedHttpSCEEventStatus,
    NotConnectedSCEEventStatus,
    NotReachableSCEEventStatus,
)
from plugins.sce.sce_sync_status import (
    SCESyncStatus,
    NeverSyncedSCESyncStatus,
    SuccessSCESyncStatus,
    TournamentConflictsSCESyncStatus,
    PlayerConflictsSCESyncStatus,
    NetworkFailureSCESyncStatus,
    UnexpectedFailureSCETournamentStatus,
    PlayerDuplicatesSCESyncStatus,
    PlayerDuplicatesAndConflictsSCESyncStatus,
)
from plugins.sce.sce_tournament_status import (
    SCETournamentStatus,
    NeverUploadedSCETournamentStatus,
    NotStartedSCETournamentStatus,
    SuccessSCETournamentStatus,
    ModifiedSCETournamentStatus,
    PendingSCETournamentStatus,
    OngoingSCETournamentStatus,
    NetworkFailureSCETournamentStatus,
    NotFoundFailureSCETournamentStatus,
    UnexpectedHTTPFailureSCETournamentStatus,
    AuthFailureSCETournamentStatus,
)
from utils.entity import EntityManager


class SCEEventStatusManager(EntityManager[SCEEventStatus]):
    def entity_types(self) -> list[type[SCEEventStatus]]:
        return [
            PublishedSCEEventStatus,
            DraftSCEEventStatus,
            ArchivedSCEEventStatus,
            NoInternetSCEEventStatus,
            InvalidRefreshTokenSCEEventStatus,
            NotFoundSCEEventStatus,
            UnexpectedHttpSCEEventStatus,
            NotConnectedSCEEventStatus,
            NotReachableSCEEventStatus,
        ]


class SCETournamentStatusManager(EntityManager[SCETournamentStatus]):
    def entity_types(self) -> list[type[SCETournamentStatus]]:
        return [
            NeverUploadedSCETournamentStatus,
            NotStartedSCETournamentStatus,
            SuccessSCETournamentStatus,
            ModifiedSCETournamentStatus,
            PendingSCETournamentStatus,
            OngoingSCETournamentStatus,
            NetworkFailureSCETournamentStatus,
            NotFoundFailureSCETournamentStatus,
            UnexpectedHTTPFailureSCETournamentStatus,
            AuthFailureSCETournamentStatus,
        ]


class SCESyncStatusManager(EntityManager[SCESyncStatus]):
    def entity_types(self) -> list[type[SCESyncStatus]]:
        return [
            NeverSyncedSCESyncStatus,
            SuccessSCESyncStatus,
            TournamentConflictsSCESyncStatus,
            PlayerConflictsSCESyncStatus,
            PlayerDuplicatesSCESyncStatus,
            PlayerDuplicatesAndConflictsSCESyncStatus,
            NetworkFailureSCESyncStatus,
            UnexpectedFailureSCETournamentStatus,
        ]
