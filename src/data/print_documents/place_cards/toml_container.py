import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

import toml
from toml import TomlDecodeError

from common.logger import get_logger

logger: logging.Logger = get_logger()


class TOMLContainer:
    """A utility class to read TOML files."""

    def __init__(
        self,
        toml_file: Path,
    ):
        self.toml_file = toml_file
        self.data: dict[str, str | int | float | dict[str, Any]] = {}
        self.error: str = ''
        try:
            self.data = toml.load(toml_file)
        except TomlDecodeError as tde:
            self.error = f'[{self.toml_file.name}]: {tde}'

    def get_field(
        self,
        property: str,
        section: str = '',
        default: Any | None = None,
        values: list[Any] | None = None,
    ) -> Any | None:
        if not property:
            logger.warning(
                '[%s]: no custom section or property provided, defaults to [%s].',
                self.toml_file.name,
                default,
            )
            return default
        value: str
        if section:
            try:
                section_data: str | int | float | bool | dict[str, Any] = self.data[
                    section
                ]
                if not isinstance(section_data, dict):
                    logger.debug(
                        '[%s]: [%s] is not a section, property [%s] defaults to [%s].',
                        self.toml_file.name,
                        section,
                        property,
                        default,
                    )
                    return default
                try:
                    value = section_data[property]
                except KeyError:
                    logger.debug(
                        '[%s]: custom property [%s] of section [%s] not found, defaults to [%s].',
                        self.toml_file.name,
                        property,
                        section,
                        default,
                    )
                    return default
            except KeyError:
                logger.debug(
                    '[%s]: custom section [%s] not found, property [%s] defaults to [%s].',
                    self.toml_file.name,
                    section,
                    property,
                    default,
                )
                return default
        else:
            try:
                value = str(self.data[property])
            except KeyError:
                logger.debug(
                    '[%s]: custom property [%s] not found, defaults to [%s].',
                    self.toml_file.name,
                    property,
                    default,
                )
                return default
        if value is None:
            logger.debug(
                '[%s]: section=%s, custom property [%s] not set, defaults to [%s].',
                self.toml_file.name,
                section,
                property,
                default,
            )
            return default
        if values and value not in values:
            if section:
                logger.warning(
                    '[%s]: value [%s] not accepted for custom property [%s] of section [%s] (accepted values: [%s]), defaults to  [%s].',
                    self.toml_file.name,
                    value,
                    property,
                    section,
                    ', '.join(values),
                    default,
                )
            else:
                logger.warning(
                    '[%s]: value [%s] not accepted for custom property [%s] (accepted values: [%s]), defaults to  [%s].',
                    self.toml_file.name,
                    value,
                    property,
                    ', '.join(values),
                    default,
                )
            return default
        else:
            return value

    def get_opt_str(
        self,
        property: str,
        section: str = '',
        default: str | None = None,
        values: list[str] | None = None,
    ) -> str | None:
        value = self.get_field(
            property=property, section=section, default=default, values=values
        )
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    def get_str(
        self,
        property: str,
        section: str = '',
        default: str | None = None,
        values: list[str] | None = None,
    ) -> str:
        value = self.get_field(
            property=property, section=section, default=default, values=values
        )
        if value is None:
            return ''
        if isinstance(value, str):
            return value
        return str(value)

    def get_opt_bool(
        self,
        property: str,
        section: str = '',
        default: bool | None = None,
    ) -> bool | None:
        value = self.get_field(property=property, section=section, default=default)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        match value.lower():
            case 'true' | 'on':
                return True
            case 'false' | 'off':
                return False
            case _:
                logger.warning(
                    '[%s]: value [%s] not accepted for custom property [%s] (bool expected), defaults to [%s].',
                    self.toml_file.name,
                    value,
                    property,
                    default,
                )
                return default

    def get_bool(
        self,
        property: str,
        section: str = '',
        default: bool | None = None,
    ) -> bool:
        return (
            self.get_opt_bool(property=property, section=section, default=default)
            or False
        )

    def get_opt_int(
        self,
        property: str,
        section: str = '',
        default: int | None = None,
    ) -> int | None:
        value = self.get_field(property=property, section=section, default=default)
        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except ValueError:
            assert property is not None
            logger.warning(
                '[%s]: value [%s] not accepted for custom property [%s] (integer expected), defaults to [%s].',
                self.toml_file.name,
                value,
                property,
                default,
            )
            return default

    def get_int(
        self,
        property: str,
        section: str = '',
        default: int | None = None,
    ) -> int:
        return (
            self.get_opt_int(property=property, section=section, default=default) or 0
        )

    def get_opt_float(
        self,
        property: str,
        section: str = '',
        default: float | None = None,
    ) -> float | None:
        value = self.get_field(property=property, section=section, default=default)
        if value is None:
            return None
        if isinstance(value, float):
            return value
        try:
            return float(value)
        except ValueError:
            assert property is not None
            logger.warning(
                'Value [%s] not accepted for custom property [%s] (float expected), defaults to [%s].',
                self.toml_file.name,
                self.data[property],
                property,
                default,
            )
            return default

    def get_float(
        self,
        property: str,
        section: str = '',
        default: float | None = None,
    ) -> float:
        return (
            self.get_opt_float(property=property, section=section, default=default)
            or 0.0
        )

    def get_section_properties(
        self,
        section: str = '',
    ) -> list[str]:
        if section:
            if section not in self.data:
                return []
            if not isinstance(self.data[section], dict):
                return []
            return [
                key
                for key in self.data[section].keys()  # type: ignore
            ]
        else:
            return [
                key for key in self.data.keys() if not isinstance(self.data[key], dict)
            ]

    def get_sections(
        self,
    ) -> list[str]:
        return [key for key in self.data.keys() if isinstance(self.data[key], dict)]

    def delete_entries(
        self,
        entries: list[str],
        section: str = '',
    ):
        for property in entries:
            with suppress(KeyError):
                if (
                    section
                    and section in self.data
                    and isinstance(self.data[section], dict)
                ):
                    del self.data[section][property]  # type: ignore
                else:
                    del self.data[property]
