"""File containing the base classes of the entity architecture.
For a feature to implement the architecture:
- create classes implementing *IdentifiableEntity*
- add a class implementing *EntityManager* listing all the classes
    (location: /src/data/entity_managers.py)"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from data.event import Event


class IdentifiableEntity(ABC):
    """Abstract class representing an entity which needs to be
    identified internally and represented in the UI"""

    @staticmethod
    @abstractmethod
    def static_id() -> str:
        """Represents the entity in forms, databases and query params.
        Should be unique amongst entities from the same parent class."""
        pass

    @staticmethod
    @abstractmethod
    def static_name() -> str:
        """Represents the entity in the UI."""
        pass

    @property
    def id(self) -> str:
        return self.static_id()

    @property
    def name(self) -> str:
        return self.static_name()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IdentifiableEntity):
            return NotImplemented
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


class EntityManager[T: IdentifiableEntity](ABC):
    @abstractmethod
    def entity_types(self) -> list[type[T]]:
        """List of all the *IdentifiableEntity* classes to manage."""

    def options(self) -> dict[str, str]:
        return {
            entity_type.static_id(): entity_type.static_name()
            for entity_type in self.entity_types()
        }

    def type_by_id(self) -> dict[str, type[T]]:
        return {
            entity_type.static_id(): entity_type for entity_type in self.entity_types()
        }

    def get_type(self, id_: str) -> type[T]:
        """Get a type by its ID.
        Raises a KeyError if the ID is unknown."""
        return self.type_by_id()[id_]

    def get_object(self, id_: str) -> T:
        """Get an object by its ID.
        Raises a KeyError if the ID is unknown."""
        return self.type_by_id()[id_]()

    def objects(self) -> list[T]:
        """Get one object per type initialized with the default constructor."""
        return [type_() for type_ in self.entity_types()]

    def ids(self) -> list[str]:
        """Get a list of all the entity IDs."""
        return [type_.static_id() for type_ in self.entity_types()]


class EventBoundEntityManager[T: IdentifiableEntity](EntityManager[T], ABC):
    def __init__(self, event: Optional['Event']):
        self.event = event
