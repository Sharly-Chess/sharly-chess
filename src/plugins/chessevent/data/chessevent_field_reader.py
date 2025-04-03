from typing import Type, Optional, cast
from enum import IntEnum

class ChessEventFieldReader:
    def __init__(self, data: dict[str, bool | str | int | float | dict[int, float] | None]):
        self._data = data
        self.last_key: Optional[str] = None

    def get[T](self, key: str, expected_type: Type[T] | tuple[Type, ...], default: Optional[T] = None) -> T:
        self.last_key = key
        value = self._data.get(key, default)

        if value is None:
            if default is not None:
                return default
            raise KeyError(f"Missing required key: {key}")

        if not isinstance(value, expected_type):
            raise TypeError(f"Expected {expected_type} for key '{key}', got {value.__class__.__name__}")

        return cast(T, value)

    def get_enum[T](self, key: str, enum_cls: Type[IntEnum], default: Optional[T] = None) -> T:
        try:
            val = self.get(key, int, None)
            if val is None:
                if default is not None:
                    return default
                raise ValueError(f"No default value provided for key: {key}")
            return cast(T, enum_cls(val))
        except (ValueError, TypeError):
            if default is not None:
                return default
            raise
