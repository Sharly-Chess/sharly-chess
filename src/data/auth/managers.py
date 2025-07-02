from data.auth.roles import Role, SpectatorRole, ResultOfficerRole
from utils.entity import EntityManager


class RoleManager(EntityManager[Role]):
    @staticmethod
    def entity_types() -> list[type[Role]]:
        return [
            SpectatorRole,
            ResultOfficerRole,
        ]
