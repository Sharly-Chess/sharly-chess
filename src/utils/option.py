from abc import ABC, abstractmethod
from types import UnionType
from typing import Any

from utils.entity import IdentifiableEntity


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


class OptionHandler[T: Option](IdentifiableEntity, ABC):
    """Abstract class handling options."""

    def __init__(self, options: list[T] | None = None):
        self.options: list[T] = options or self.default_options()

    @staticmethod
    def available_options() -> list[type[T]]:
        """Types of options the handler can be initialized with."""
        return []

    @classmethod
    def default_options(cls) -> list[T]:
        """List of all available options with default values."""
        return [option_type() for option_type in cls.available_options()]

    def validate_options(self):
        """Checks the validity of options, Raises a ValueError if invalid."""
        used_option_types: list[type[T]] = []
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

    def _get_option[V: Option](
        self, option_type: type[V]
    ) -> V:
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
