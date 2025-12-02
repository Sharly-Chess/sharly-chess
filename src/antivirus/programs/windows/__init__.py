import winreg
from logging import Logger
from typing import Literal, Any

from antivirus.programs.antivirus import Antivirus
from common.logger import get_logger

logger: Logger = get_logger()


class WindowsAntivirus(Antivirus):
    def __init__(
        self,
        name: str,
        signatures: list[str],
    ):
        super().__init__(name, signatures)


class WinregistryException(Exception):
    pass


class WinRegistry:
    @classmethod
    def _set_value(
        cls,
        key: winreg.HKEYType | int,
        sub_key: str,
        name: str,
        type_: Literal[4, 5] | int,
        value: Any,
    ):
        """Sets the value of an entry of the registry, raises an exception on error."""
        try:
            winreg.CreateKey(key, sub_key)
            registry_key = winreg.OpenKey(
                key,
                sub_key,
                0,
                winreg.KEY_WRITE,
            )
            winreg.SetValueEx(
                registry_key,
                name,
                0,
                type_,
                value,
            )
            winreg.CloseKey(registry_key)
        except WindowsError as we:
            raise WinregistryException(
                f'{cls.__name__}._set_value(key=[{key}], sub_key=[{sub_key}], name=[{name}], value=[{value}]) raised an error: {we}'
            )

    @classmethod
    def _set_hklm_value(
        cls,
        sub_key: str,
        name: str,
        type: Literal[4, 5] | int,
        value: Any,
    ):
        cls._set_value(winreg.HKEY_LOCAL_MACHINE, sub_key, name, type, value)

    @classmethod
    def set_hklm_dword(
        cls,
        sub_key: str,
        name: str,
        value: Any,
    ):
        cls._set_hklm_value(sub_key, name, winreg.REG_DWORD, value)

    @classmethod
    def set_hklm_sz(
        cls,
        sub_key: str,
        name: str,
        value: Any,
    ):
        cls._set_hklm_value(sub_key, name, winreg.REG_SZ, value)

    @classmethod
    def _get_value(
        cls,
        key: winreg.HKEYType | int,
        sub_key: str,
        name: str,
    ) -> Any:
        try:
            registry_key = winreg.OpenKey(
                key,
                sub_key,
                0,
                winreg.KEY_READ,
            )
            value, regtype = winreg.QueryValueEx(registry_key, name)
            winreg.CloseKey(registry_key)
            return value
        except WindowsError:
            return None

    @classmethod
    def get_hklm_value(
        cls,
        sub_key: str,
        name: str,
    ) -> Any:
        return cls._get_value(winreg.HKEY_LOCAL_MACHINE, sub_key, name)

    @classmethod
    def get_hkcu_value(
        cls,
        sub_key: str,
        name: str,
    ) -> Any:
        return cls._get_value(winreg.HKEY_CURRENT_USER, sub_key, name)

    @classmethod
    def _get_values(
        cls,
        key: winreg.HKEYType | int,
        sub_key: str,
    ) -> dict[str, Any]:
        key_dict = {}
        i = 0
        try:
            registry_key = winreg.OpenKey(key, sub_key, 0, winreg.KEY_READ)
            while True:
                try:
                    subvalue = winreg.EnumValue(registry_key, i)
                except WindowsError:
                    break
                key_dict[subvalue[0]] = subvalue[1:]
                i += 1
            return key_dict
        except WindowsError as we:
            raise WinregistryException(
                f'{cls.__name__}._get_values(key=[{key}], sub_key=[{sub_key}]) raised an error: {we}'
            )

    @classmethod
    def get_hklm_values(
        cls,
        sub_key: str,
    ) -> dict[str, Any]:
        return cls._get_values(winreg.HKEY_LOCAL_MACHINE, sub_key)

    @classmethod
    def get_hkcu_values(
        cls,
        sub_key: str,
    ) -> dict[str, Any]:
        return cls._get_values(winreg.HKEY_CURRENT_USER, sub_key)

    @classmethod
    def _delete_value(
        cls,
        key: winreg.HKEYType | int,
        sub_key: str,
        name: str,
    ):
        """Deletes a value of the registry, raises an exception on error."""
        try:
            open_key = winreg.OpenKey(key, sub_key, 0, winreg.KEY_ALL_ACCESS)
            winreg.DeleteValue(open_key, name)
            open_key.Close()
        except WindowsError as we:
            raise WinregistryException(
                f'{cls.__name__}._delete_value(key=[{key}], sub_key=[{sub_key}], name=[{name}]) raised an error: {we}'
            )

    @classmethod
    def delete_hklm_value(
        cls,
        sub_key: str,
        name: str,
    ):
        cls._delete_value(winreg.HKEY_LOCAL_MACHINE, sub_key, name)

    @classmethod
    def delete_hkcu_value(
        cls,
        sub_key: str,
        name: str,
    ):
        cls._delete_value(winreg.HKEY_CURRENT_USER, sub_key, name)

    @classmethod
    def _delete_sub_key(
        cls,
        key: winreg.HKEYType | int,
        sub_key: str,
        sub_sub_key: str = '',
    ):
        # https://stackoverflow.com/questions/38205784/python-how-to-delete-registry-key-and-subkeys-from-hklm-getting-error-5
        """Deletes an entry of the registry, raises an exception on error."""
        if sub_sub_key == '':
            current_key = sub_key
        else:
            current_key = sub_key + '\\' + sub_sub_key
        try:
            open_key = winreg.OpenKey(key, current_key, 0, winreg.KEY_ALL_ACCESS)
            info_key = winreg.QueryInfoKey(open_key)
            for x in range(0, info_key[0]):
                # NOTE:: This code is to delete the key and all subkeys.
                #  If you just want to walk through them, then
                #  you should pass x to EnumKey. subkey = _winreg.EnumKey(open_key, x)
                #  Deleting the subkey will change the SubKey count used by EnumKey.
                #  We must always pass 0 to EnumKey so we
                #  always get back the new first SubKey.
                local_sub_key = winreg.EnumKey(open_key, 0)
                try:
                    winreg.DeleteKey(open_key, local_sub_key)
                except Exception:
                    cls._delete_sub_key(key, current_key, local_sub_key)
                    # no extra delete here since each call
                    # to _delete_registry_sub_key will try to delete itself when its empty.
            winreg.DeleteKey(open_key, '')
            open_key.Close()
        except WindowsError as we:
            raise WinregistryException(
                f'{cls.__name__}._delete_sub_key(key=[{key}], sub_key=[{sub_key}], sub_sub_key=[{sub_sub_key}]) raised an error: {we}'
            )

    @classmethod
    def delete_hklm_key(
        cls,
        sub_key: str,
    ):
        cls._delete_sub_key(winreg.HKEY_LOCAL_MACHINE, sub_key)

    @classmethod
    def delete_hkcu_key(
        cls,
        sub_key: str,
    ):
        cls._delete_sub_key(winreg.HKEY_CURRENT_USER, sub_key)
