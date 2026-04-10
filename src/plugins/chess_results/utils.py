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
from database.sqlite.event.event_database import EventDatabase
from database.sqlite.sqlite_database import SQLiteDatabase
from plugins.chess_results import PLUGIN_NAME, PLUGIN_DIR
from plugins.chess_results.chess_results_upload_status import (
    CRUploadStatus,
    FailureCRUploadStatus,
    NetworkFailureCRUploadStatus,
    UnexpectedFailureCRUploadStatus,
    NeverUploadedCRUploadStatus,
    ModifiedCRUploadStatus,
    UpToDateCRUploadStatus,
    OngoingCRUploadStatus,
    PendingCRUploadStatus,
    FinishedFailureCRUploadStatus,
)
from plugins.utils import PluginData, PluginUtils
from utils.date_time import format_datetime
from utils.entity import EntityManager
from web.controllers.base_controller import WebContext


logger: Logger = get_logger()

get_data = partial(PluginUtils.get_plugin_data, PLUGIN_NAME)

CHESS_RESULTS_UPLOAD_DELAY = 3
CHESS_RESULTS_EPOCH = datetime(2000, 1, 1)


class ChessResultsCredentials:
    def __init__(
        self,
        key: str,
        iv: str,
    ):
        self.key: str = key
        self.iv: str = iv

    @classmethod
    def load(
        cls,
        file: Path,
    ) -> Optional[Self]:
        """Reads credentials from the given file, raises SharlyChessException
        on error (logs a warning and returns None on DEVEL_ENV)."""
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
        """Dumps credentials to the given file."""
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


class CRUtils:
    @classmethod
    def resolve_auto_upload(cls, tournament: Tournament) -> bool:
        if not cls.get_event_plugin_data(tournament.event).auto_upload:
            return False
        return cls.get_tournament_plugin_data(tournament).auto_upload

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

    CREDENTIALS_FILE: Path = PLUGIN_DIR / '.credentials'

    @classmethod
    def dump_credentials(
        cls,
        key: str,
        iv: str,
    ):
        """Dumps the credentials to the module base64-encoded file."""
        ChessResultsCredentials.dump(cls.CREDENTIALS_FILE, key, iv)

    @classmethod
    def load_credentials(
        cls,
    ):
        """Dumps the credentials from the module base64-encoded file."""
        if credentials := ChessResultsCredentials.load(cls.CREDENTIALS_FILE):
            load_dotenv(
                stream=StringIO(
                    f'CHESS_RESULTS_AES_KEY={credentials.key}\nCHESS_RESULTS_AES_IV={credentials.iv}'
                )
            )

    @classmethod
    def tournament_public_url(cls, tournament: Tournament) -> str:
        tnr = cls.get_tournament_plugin_data(tournament).tnr
        return f'https://chess-results.com/tnr{tnr}.aspx'

    @classmethod
    def tournament_private_url(cls, tournament: Tournament) -> str:
        plugin_data = cls.get_tournament_plugin_data(tournament)
        tnr = plugin_data.tnr
        tnr_sec = cls.encrypt(str(tnr))
        creator_id_sec = cls.encrypt(plugin_data.creator_id or '')
        return (
            f'https://chess-results.com/Stammdaten.aspx?&art=1&lan=1&tabkey=26&'
            f'key1={tnr}&luser_sec={creator_id_sec}&tnr_sec={tnr_sec}'
        )

    @staticmethod
    def update_tournament_plugin_data(
        tournament: Tournament,
        plugin_data: 'ChessResultsTournamentPluginData',
    ):
        tournament.stored_tournament.plugin_data[PLUGIN_NAME] = (
            plugin_data.to_stored_value()
        )
        tournament.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(tournament.event.uniq_id, write=True) as database:
            database.execute(
                'UPDATE tournament SET plugin_data = '
                f"json_set(plugin_data,'$.{PLUGIN_NAME}', json(?)) WHERE id = ?",
                (json.dumps(plugin_data.to_stored_value()), tournament.id),
            )

    @staticmethod
    def update_event_plugin_data(
        event: Event,
        plugin_data: 'ChessResultsEventPluginData',
    ):
        event.stored_event.plugin_data[PLUGIN_NAME] = plugin_data.to_stored_value()
        event.plugin_data[PLUGIN_NAME] = plugin_data
        with EventDatabase(event.uniq_id, True) as database:
            database.execute(
                'UPDATE info SET plugin_data = '
                f"json_set(plugin_data,'$.{PLUGIN_NAME}', json(?))",
                (json.dumps(plugin_data.to_stored_value()),),
            )

    @classmethod
    def resolve_tournament_upload_statuses(
        cls, tournament: Tournament
    ) -> list[CRUploadStatus]:
        from plugins.chess_results.chess_results_background_uploader import (
            CRBackgroundUploader,
        )

        plugin_data = cls.get_tournament_plugin_data(tournament)
        statuses: list[CRUploadStatus] = []

        # Last upload failure
        if plugin_data.upload_failure_id:
            status = CRUploadFailureStatusManager().get_object(
                plugin_data.upload_failure_id
            )
            statuses.append(status)

        is_modified = CRBackgroundUploader.chess_results_upload_needed(tournament)
        # Current data status
        if not plugin_data.last_upload_at:
            statuses.append(NeverUploadedCRUploadStatus())
        elif is_modified:
            statuses.append(ModifiedCRUploadStatus())
        else:
            statuses.append(UpToDateCRUploadStatus())

        # Next upload status
        if CRBackgroundUploader.is_upload_ongoing(tournament):
            statuses.append(OngoingCRUploadStatus())
        elif CRBackgroundUploader.is_upload_queued(tournament) or (
            CRBackgroundUploader.is_upload_scheduled(tournament) and is_modified
        ):
            statuses.append(PendingCRUploadStatus())
        return statuses


CRUtils.load_credentials()


class CRUploadFailureStatusManager(EntityManager[FailureCRUploadStatus]):
    def entity_types(self) -> list[type[FailureCRUploadStatus]]:
        return [
            NetworkFailureCRUploadStatus,
            UnexpectedFailureCRUploadStatus,
            FinishedFailureCRUploadStatus,
        ]


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
    auto_upload: bool = True
    remark: str | None = None
    state: int | None = None

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            auto_upload=stored_value.get('auto_upload', True),
            remark=stored_value.get('remark'),
            state=stored_value.get('state'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'auto_upload': self.auto_upload,
            'remark': self.remark,
            'state': self.state,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        plugin_data = cls(
            remark=WebContext.form_data_to_str(data, 'chess_results_remark'),
            state=WebContext.form_data_to_int(data, 'chess_results_state'),
        )
        if previous_object:
            plugin_data.auto_upload = previous_object.auto_upload
        return plugin_data

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'chess_results_remark': self.remark,
                'chess_results_state': self.state,
            }
        )


@dataclass
class ChessResultsTournamentPluginData(PluginData):
    auto_upload: bool = False
    tnr: str | None = None
    creator_id: str | None = None
    last_upload_at: datetime | None = None
    last_upload_attempt_at: datetime | None = None
    upload_failure_id: str | None = None
    remark: str | None = None
    remark_default: bool = True

    @property
    def last_upload_at_str(self) -> str:
        if not self.last_upload_at:
            return '-'
        return format_datetime(self.last_upload_at)

    @classmethod
    def from_stored_value(cls, stored_value: dict[str, Any]) -> Self:
        return cls(
            tnr=stored_value.get('tnr', None),
            creator_id=stored_value.get('creator_id', None),
            auto_upload=stored_value.get('auto_upload', False),
            remark=stored_value.get('remark'),
            remark_default=stored_value.get('remark_default', True),
            last_upload_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload')
            ),
            last_upload_attempt_at=SQLiteDatabase.load_optional_timestamp_from_database_field(
                stored_value.get('last_upload_attempt_at')
            ),
            upload_failure_id=stored_value.get('upload_failure_id'),
        )

    def to_stored_value(self) -> dict[str, Any]:
        return {
            'tnr': self.tnr,
            'creator_id': self.creator_id,
            'auto_upload': self.auto_upload,
            'remark': self.remark,
            'remark_default': self.remark_default,
            'last_upload': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_at
            ),
            'last_upload_attempt_at': SQLiteDatabase.dump_optional_datetime_to_timestamp_field(
                self.last_upload_attempt_at
            ),
            'upload_failure_id': self.upload_failure_id,
        }

    @classmethod
    def from_form_data(
        cls,
        data: dict[str, str],
        previous_object: Self | None = None,
        action: str | None = None,
    ) -> Self:
        plugin_data = cls(
            remark=WebContext.form_data_to_str(data, 'chess_results_remark'),
            remark_default=WebContext.form_data_to_bool(
                data, 'chess_results_remark_checkbox'
            ),
        )
        if previous_object:
            if action != 'clone':
                plugin_data.tnr = previous_object.tnr
                plugin_data.creator_id = previous_object.creator_id
                plugin_data.last_upload_at = previous_object.last_upload_at
                plugin_data.last_upload_attempt_at = (
                    previous_object.last_upload_attempt_at
                )
                plugin_data.upload_failure_id = previous_object.upload_failure_id
            plugin_data.auto_upload = plugin_data.auto_upload
        return plugin_data

    def to_form_data(self, action: str | None = None) -> dict[str, str]:
        return WebContext.values_dict_to_form_data(
            {
                'chess_results_remark': self.remark,
                'chess_results_remark_checkbox': self.remark_default,
            }
        )
