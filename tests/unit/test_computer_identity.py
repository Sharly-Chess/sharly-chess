"""The key pair the computer is recognised by.

It belongs to the computer rather than to any event, so it is generated once
and kept for good.
"""

import hashlib
import re
import time
from threading import Thread
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from common import computer_identity as module
from common.computer_identity import ComputerIdentity, computer_identity


class FakeConfigDatabase:
    """A config database holding no key yet, slow to write one."""

    private_key: str | None = None
    public_key: str | None = None
    writes = 0

    def __init__(self, write: bool = False) -> None:
        pass

    def __enter__(self) -> 'FakeConfigDatabase':
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def load_stored_config(self) -> SimpleNamespace:
        return SimpleNamespace(
            computer_private_key=FakeConfigDatabase.private_key,
            computer_public_key=FakeConfigDatabase.public_key,
        )

    def update_computer_keys(self, private_key: str, public_key: str) -> None:
        time.sleep(0.01)
        FakeConfigDatabase.private_key = private_key
        FakeConfigDatabase.public_key = public_key
        FakeConfigDatabase.writes += 1


@pytest.fixture
def empty_config(monkeypatch: pytest.MonkeyPatch) -> type[FakeConfigDatabase]:
    FakeConfigDatabase.private_key = None
    FakeConfigDatabase.public_key = None
    FakeConfigDatabase.writes = 0
    monkeypatch.setattr(module, 'ConfigDatabase', FakeConfigDatabase)
    return FakeConfigDatabase


@pytest.mark.unit
class TestComputerIdentity:
    def test_the_identity_is_kept(self) -> None:
        assert computer_identity() == computer_identity()

    def test_the_identity_is_stored_in_the_config(self) -> None:
        from database.sqlite.config.config_database import ConfigDatabase

        identity = computer_identity()

        with ConfigDatabase() as database:
            stored_config = database.load_stored_config()
        assert stored_config.computer_public_key == identity.public_key
        assert stored_config.computer_private_key == identity.private_key

    def test_the_keys_are_an_ed25519_pair(self) -> None:
        identity = computer_identity()

        private_key = serialization.load_ssh_private_key(
            identity.private_key.encode(), password=None
        )

        assert isinstance(private_key, Ed25519PrivateKey)
        public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        assert public.decode() == identity.public_key
        assert identity.public_key.startswith('ssh-ed25519 ')

    def test_the_device_id_is_derived_from_the_public_key(self) -> None:
        identity = ComputerIdentity(private_key='private', public_key='public')

        assert identity.device_id == hashlib.sha256(b'public').hexdigest()[:32]

    def test_the_device_id_is_short_hexadecimal(self) -> None:
        assert re.fullmatch(r'[0-9a-f]{32}', computer_identity().device_id)

    def test_a_key_is_generated_the_first_time(
        self, empty_config: type[FakeConfigDatabase]
    ) -> None:
        identity = computer_identity()

        assert empty_config.writes == 1
        assert empty_config.public_key == identity.public_key
        assert computer_identity() == identity
        assert empty_config.writes == 1

    def test_every_generated_key_is_new(self) -> None:
        assert module._generate_key_pair() != module._generate_key_pair()

    def test_simultaneous_first_requests_share_one_identity(
        self, empty_config: type[FakeConfigDatabase]
    ) -> None:
        identities: list[ComputerIdentity] = []
        threads = [
            Thread(target=lambda: identities.append(computer_identity()))
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(identities) == 8
        assert len(set(identities)) == 1
        assert empty_config.writes == 1
