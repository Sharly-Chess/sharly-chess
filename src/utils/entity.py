"""File containing the base classes of the entity architecture.
For a feature to implement the architecture:
- create classes implementing *IdentifiableEntity*
- add a class implementing *EntityManager* listing all the classes
    (location: /src/data/entity_managers.py)"""
from abc import ABC, abstractmethod


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


class EntityManager[T: IdentifiableEntity](ABC):
    @staticmethod
    @abstractmethod
    def entity_types() -> list[type[T]]:
        """List of all the *IdentifiableEntity* classes to manage."""

    @classmethod
    def options(cls) -> dict[str, str]:
        return {
            entity_type.static_id(): entity_type.static_name()
            for entity_type in cls.entity_types()
        }

    @classmethod
    def type_by_id(cls) -> dict[str, type[T]]:
        return {
            entity_type.static_id(): entity_type for entity_type in cls.entity_types()
        }

    @classmethod
    def get_type(cls, id_: str) -> type[T]:
        """Get a type by its ID.
        Raises a KeyError if the ID is unknown."""
        return cls.type_by_id()[id_]

    @classmethod
    def get_object(cls, id_: str) -> T:
        """Get an object by its ID.
        Raises a KeyError if the ID is unknown."""
        return cls.type_by_id()[id_]()

    @classmethod
    def objects(cls) -> list[T]:
        """Get one object per type initialized with the default constructor."""
        return [type_() for type_ in cls.entity_types()]
