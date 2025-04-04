"""File containing the base classes of the entity architecture.
For a feature to implement the architecture:
- create classes implementing *IdentifiableEntity*
- add a class implementing *EntityManager* listing all the classes
    (location: /src/data/entity_managers.py)"""
from abc import ABC, abstractmethod
from types import UnionType
from typing import Any


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


class EntityManager[IdentifiableEntity](ABC):
    @staticmethod
    @abstractmethod
    def entity_types() -> list[type[IdentifiableEntity]]:
        """List of all the *IdentifiableEntity* classes to manage."""

    @classmethod
    def options(cls) -> dict[str, str]:
        return {
            entity_type.static_id(): entity_type.static_name()
            for entity_type in cls.entity_types()
        }

    @classmethod
    def type_by_id(cls) -> dict[str, type[IdentifiableEntity]]:
        return {
            entity_type.static_id(): entity_type for entity_type in cls.entity_types()
        }

    @classmethod
    def get_type(cls, id_: str) -> type[IdentifiableEntity]:
        """Get a type by its ID.
        Raises a KeyError if the ID is unknown."""
        return cls.type_by_id()[id_]

    @classmethod
    def get_object(cls, id_: str) -> IdentifiableEntity:
        """Get an object by its ID.
        Raises a KeyError if the ID is unknown."""
        return cls.type_by_id()[id_]()

    @classmethod
    def objects(cls) -> list[IdentifiableEntity]:
        """Get one object per type initialized with the default constructor."""
        return [type_() for type_ in cls.entity_types()]


class OptionError(ValueError):
    def __init__(self, message: str, option: 'Option'):
        super().__init__(message)
        self.option = option


class Option(IdentifiableEntity, ABC):
    """Abstract class representing an option.
    Options can either be represented in the DB or in a form."""

    def __init__(self, value: Any | None = None):
        self.value = value if value is not None else self.default_value

    @staticmethod
    def static_name() -> str:
        """UI representation is handled by the template."""
        return ''

    @property
    @abstractmethod
    def type(self) -> type | UnionType:
        """Expected type for the value of the option"""
        pass

    @property
    @abstractmethod
    def default_value(self) -> Any:
        """Value used as default for the option.
        Should be of type {self.type}"""
        pass

    @property
    @abstractmethod
    def template_name(self) -> str:
        """Name of the template representing the option in a form.
        Template is intended to be used with a context where
        "option" refers to the Option object
        """
        pass

    @property
    def container_id(self) -> str:
        """ID of the HTML element containing the template."""
        return f'{self.id}_container'

    def validate(self):
        """Checks if the value is correctly implemented.
        Raises an OptionError if not."""
        if not isinstance(self.value, self.type):
            raise OptionError(f'{self.value=} (expected type: {self.type})', self)


class OptionHandler(IdentifiableEntity, ABC):
    """Abstract class handling options."""

    def __init__(self, options: list[Option] | None = None):
        self.options: list[Option] = options or self.default_options()

    @staticmethod
    def available_options() -> list[type[Option]]:
        """Types of options the handler can be initialized with."""
        return []

    @classmethod
    def default_options(cls) -> list[Option]:
        """List of all available options with default values."""
        return [option_type() for option_type in cls.available_options()]

    def validate_options(self):
        """Checks the validity of options, Raises a ValueError if invalid."""
        used_option_types: list[type[Option]] = []
        for option in self.options:
            option.validate()
            option_type = type(option)
            if option_type in used_option_types:
                raise OptionError(f'Option [{option.id}] already used', option)
            if option_type not in self.available_options():
                raise OptionError(
                    f'Option [{option.id}] not available [{self.name}]', option
                )
            used_option_types.append(option_type)

    def _get_option[Option](
        self, option_type: type[Option]
    ) -> Option:
        """Retrieve an option from its type. If no option with this type
        exists in the options, returns on with the default value"""
        return next(
            (option for option in self.options if isinstance(option, option_type)),
            option_type(),
        )

    def get_option_values(self) -> list:
        """Retrieves for each of the available options
        the corresponding value in an ordered list.
        Intended usage: option1, option2 = self.get_option_values()"""
        return [
            self._get_option(option_type).value
            for option_type in self.available_options()
        ]

