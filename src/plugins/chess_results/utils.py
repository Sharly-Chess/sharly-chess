import base64
import json
from dataclasses import dataclass
from datetime import datetime
from functools import partial
import os
from io import StringIO
from logging import Logger
from pathlib import Path
from typing import Any, Self, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from dotenv import load_dotenv

from common import DEVEL_ENV, SharlyChessException
from common.logger import get_logger
from data.event import Event
from data.tournament import Tournament
from plugins.chess_results import PLUGIN_NAME, PLUGIN_DIR
from plugins.utils import PluginData, PluginUtils
from web.controllers.base_controller import WebContext


logger: Logger = get_logger()

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

CHESS_RESULTS_MIN_UPLOAD_DELAY = 3
CHESS_RESULTS_DEFAULT_UPLOAD_DELAY = 3
CHESS_RESULTS_EPOCH = datetime(2000, 1, 1)


class ChessResultsCredentials:
    def __init__(
        self,
        key: str,
        iv: str,
    ):
        """Reads credentials from the given file, raises SharlyChessException on error."""
        self.key: str = key
        self.iv: str = iv

    @classmethod
    def load_credentials(
        cls,
        file: Path,
    ) -> Optional[Self]:
        """Reads credentials from the given file, raises SharlyChessException on error."""
        try:
            with open(file, 'r') as f:
                (key, iv) = json.loads(
                    base64.b64decode(f.read().encode('ascii')).decode('ascii')
                )
            return cls(key, iv)
        except FileNotFoundError as e:
            if DEVEL_ENV:
                logger.warning(
                    f'Could not read Chess-Results credentials ({e}), '
                    'please run generate_chess_results_credentials.py.'
                )
                return None
            else:
                raise SharlyChessException(
                    'Could not read Chess-Results credentials.'
                ) from None

    @staticmethod
    def dump(
        credentials_file: Path,
        key: str,
        iv: str,
    ):
        """Dumps credentials to the given file.
        The credentials can be read by `creds = ChessResultsCredentials(file)`."""
        credentials_file.parent.mkdir(exist_ok=True, parents=True)
        with open(credentials_file, 'w') as f:
            f.write(
                base64.b64encode(
                    json.dumps(
                        (
                            key,
                            iv,
                        )
                    ).encode('ascii')
                ).decode('ascii')
            )


class ChessResultsUtils:
    @classmethod
    def resolve_auto_upload(cls, tournament: Tournament) -> bool:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        if tournament_plugin_data.auto_upload is not None:
            return tournament_plugin_data.auto_upload
        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        return event_plugin_data.auto_upload

    @classmethod
    def resolve_auto_upload_delay(cls, event: Event) -> int:
        plugin_data = cls.get_event_plugin_data(event)
        if plugin_data.auto_upload_delay is not None:
            return plugin_data.auto_upload_delay
        return CHESS_RESULTS_DEFAULT_UPLOAD_DELAY

    @classmethod
    def resolve_remark(cls, tournament: Tournament) -> str | None:
        tournament_plugin_data = cls.get_tournament_plugin_data(tournament)
        if not tournament_plugin_data.remark_default:
            return tournament_plugin_data.remark or ''
        event_plugin_data = cls.get_event_plugin_data(tournament.event)
        return event_plugin_data.remark or ''

    @staticmethod
    def get_event_plugin_data(event: Event) -> 'ChessResultsEventPluginData':
        plugin_data = event.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, ChessResultsEventPluginData)
        return plugin_data

    @staticmethod
    def get_tournament_plugin_data(
        tournament: Tournament,
    ) -> 'ChessResultsTournamentPluginData':
        plugin_data = tournament.plugin_data[PLUGIN_NAME]
        assert isinstance(plugin_data, ChessResultsTournamentPluginData)
        return plugin_data

    @staticmethod
    def get_bytes_from_env(var_name: str) -> bytes:
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f'Missing environment variable: {var_name}')
        return bytes.fromhex(value)

    @classmethod
    def encrypt(cls, decrypted_string: str) -> str:
        """
        Returns a HEX-encoded encrypted string (uppercase).
        """
        key = cls.get_bytes_from_env('CHESS_RESULTS_AES_KEY')
        iv = cls.get_bytes_from_env('CHESS_RESULTS_AES_IV')

        data = decrypted_string.encode('utf-8')

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
        return encrypted_bytes.hex().upper()

    @classmethod
    def get_connection_parameters(cls, tournament: Tournament) -> dict[str, str]:
        """Gets the parameters needed to manage a tournament on Chess-Results.com."""

        plugin_data = cls.get_tournament_plugin_data(tournament)
        tnr = plugin_data.tnr
        creator_id = plugin_data.creator_id or ''
        return {
            'tnr_sec': cls.encrypt(str(tnr)),
            'creator_id_sec': cls.encrypt(creator_id),
        }

    CREDENTIALS_FILE: Path = PLUGIN_DIR / '.credentials'

    @classmethod
    def dump_credentials(
        cls,
        key: str,
        iv: str,
    ):
        ChessResultsCredentials.dump(cls.CREDENTIALS_FILE, key, iv)

    @classmethod
    def load_credentials(
        cls,
    ):
        if credentials := ChessResultsCredentials.load_credentials(
            cls.CREDENTIALS_FILE
        ):
            load_dotenv(
                stream=StringIO(
                    f'CHESS_RESULTS_AES_KEY={credentials.key}\nCHESS_RESULTS_AES_IV={credentials.iv}'
                )
            )


ChessResultsUtils.load_credentials()


@dataclass
class ChessResultsConfigPluginData(PluginData):
    creator_id: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            creator_id=stored_value.get('creator_id'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'creator_id': self.creator_id,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            creator_id=WebContext.form_data_to_str(data, 'creator_id'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'creator_id': self.creator_id,
            }
        )


@dataclass
class ChessResultsEventPluginData(PluginData):
    auto_upload: bool
    auto_upload_delay: int
    remark: str | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            auto_upload=stored_value.get('auto_upload') or False,
            auto_upload_delay=stored_value.get(
                'auto_upload_delay', CHESS_RESULTS_DEFAULT_UPLOAD_DELAY
            ),
            remark=stored_value.get('remark'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'auto_upload': self.auto_upload,
            'auto_upload_delay': self.auto_upload_delay,
            'remark': self.remark,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        return cls(
            auto_upload=WebContext.form_data_to_bool(data, 'auto_upload'),
            auto_upload_delay=WebContext.form_data_to_int(data, 'auto_upload_delay')
            or CHESS_RESULTS_DEFAULT_UPLOAD_DELAY,
            remark=WebContext.form_data_to_str(data, 'remark'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'auto_upload': self.auto_upload,
                'auto_upload_delay': self.auto_upload_delay,
                'remark': self.remark,
            }
        )


@dataclass
class ChessResultsTournamentPluginData(PluginData):
    auto_upload: bool | None = None
    tnr: str | None = None
    creator_id: str | None = None
    last_upload: float | None = None
    remark: str | None = None
    remark_default: bool = True

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            tnr=stored_value.get('tnr', None),
            creator_id=stored_value.get('creator_id', None),
            auto_upload=stored_value.get('auto_upload', None),
            remark=stored_value.get('remark'),
            remark_default=stored_value.get('remark_default', True),
            last_upload=stored_value.get('last_upload', 0.0),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'tnr': self.tnr,
            'creator_id': self.creator_id,
            'auto_upload': self.auto_upload,
            'remark': self.remark,
            'remark_default': self.remark_default,
            'last_upload': self.last_upload,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        tnr: str | None = None
        creator_id: str | None = None
        last_upload: float | None = None
        if previous_object and action != 'clone':
            tnr = previous_object.tnr
            creator_id = previous_object.creator_id
            last_upload = previous_object.last_upload

        return cls(
            tnr=tnr,
            creator_id=creator_id,
            last_upload=last_upload,
            remark=WebContext.form_data_to_str(data, 'remark'),
            remark_default=WebContext.form_data_to_bool(data, 'remark_checkbox'),
            auto_upload=WebContext.form_data_to_bool_or_none(data, 'auto_upload'),
        )

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'auto_upload': self.auto_upload,
                'remark': self.remark,
                'remark_checkbox': self.remark_default,
            }
        )
