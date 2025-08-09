from dataclasses import is_dataclass, fields
from enum import Enum
from types import UnionType, GenericAlias
from typing import Any, get_origin, get_args

from common.exception import SharlyChessException
from common.i18n import _


class DictReaderException(SharlyChessException):
    def __init__(self, path: list[str], message: str):
        log_prefix = '.'.join(path) + ' - ' if path else ''
        super().__init__(log_prefix + message)


def dict_to_dataclass[T](
    data_class: type[T], dict_obj: dict[str, Any], path: list[str] | None = None
) -> T:
    """Method converting a dictionary into a dataclass object.
    Can recursively convert the sub dictionaries into other dataclasses.

    Raises a DictReaderException if:.
        - A required (i.e. without default value) field is missing
        - An unknown field is encountered
        - a value is of incorrect type"""

    if not is_dataclass(data_class):
        raise ValueError(f'{data_class} is not a dataclass')
    if path is None:
        path = []

    field_types: dict[str, type] = {f.name: f.type for f in fields(data_class)}
    kwargs = {}

    for key, value in dict_obj.items():
        if key not in field_types:
            raise DictReaderException(
                path, _('Unknown field [{field}].').format(field=key)
            )
        field_type = field_types[key]
        kwargs[key] = _read_field_value(key, value, field_type, path)

    for field in fields(data_class):
        if field.name not in kwargs and field.default == field.default_factory:
            raise DictReaderException(
                path, _('Missing required field [{field}].').format(field=field.name)
            )
    return data_class(**kwargs)


def _read_field_value(
    field_name: str,
    field_value: Any,
    field_type: type | UnionType | GenericAlias,
    path: list[str],
) -> Any:
    """Read a value into the expected type.
    Raises a DictReaderException if the types do not match."""
    if isinstance(field_type, UnionType):
        for sub_type in get_args(field_type):
            try:
                return _read_field_value(field_name, field_value, sub_type, path)
            except DictReaderException:
                pass
        _check_type(field_name, field_value, field_type, path)
    elif isinstance(field_type, GenericAlias):
        base_type = get_origin(field_type)
        if base_type is dict:
            _check_type(field_name, field_value, dict, path)
            key_type, value_type = get_args(field_type)
            field_dict: dict = {}
            for key, value in field_value.items():
                if key_type is int and isinstance(key, str) and key.isdigit():
                    key = int(key)
                _check_type(field_name, key, key_type, path)
                field_dict[key] = _read_field_value(
                    str(key), value, value_type, path + [str(key)]
                )
            return field_dict
        elif base_type is list:
            _check_type(field_name, field_value, list, path)
            sub_type = get_args(field_type)[0]
            return [
                _read_field_value(field_name, sub_value, sub_type, path)
                for sub_value in field_value
            ]
        else:
            raise ValueError(f'Unhandled type [{field_type}]')
    elif isinstance(field_value, field_type):
        return field_value
    elif is_dataclass(field_type):
        _check_type(field_name, field_value, dict, path)
        return dict_to_dataclass(field_type, field_value, path + [field_name])
    elif issubclass(field_type, Enum):
        try:
            return field_type(field_value)
        except ValueError:
            raise DictReaderException(
                path,
                _(
                    'Invalid value [{value}] for field [{field}] '
                    '(expected one of [{expected_values}]).'
                ).format(
                    value=field_value,
                    field=field_name,
                    expected_values=', '.join(member.value for member in field_type),
                ),
            )
    _check_type(field_name, field_value, field_type, path)


def _check_type(
    field_name: str,
    field_value: Any,
    field_type: type | UnionType,
    path: list[str],
):
    if not isinstance(field_value, field_type):
        raise DictReaderException(
            path,
            _(
                'Invalid type [{type}] for field [{field}] (expected: {expected}).'
            ).format(
                type=type(field_value).__name__,
                field=field_name,
                expected=(
                    field_type.__name__ if isinstance(field_type, type) else field_type
                ),
            ),
        )
