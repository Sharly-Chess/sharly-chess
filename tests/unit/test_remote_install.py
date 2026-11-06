"""The computer's identity for remote access.

The relay recognises a laptop by the key pair the computer already holds, so
nothing here generates one of its own: what remote access adds is the
identifier the control plane calls that computer by, which has to outlive the
events served under it.
"""

import pytest

from common.computer_identity import computer_identity
from web.remote_install import forget_remote_install, remote_install, set_install_id


@pytest.fixture(autouse=True)
def unregistered():
    forget_remote_install()
    yield
    forget_remote_install()


def test_the_computer_is_known_by_the_key_it_is_known_by_elsewhere():
    install = remote_install()

    assert install.public_key == computer_identity().public_key
    assert install.public_key.startswith('ssh-ed25519 ')
    assert not install.is_registered


def test_the_key_is_one_an_ssh_client_can_present():
    install = remote_install()

    key = install.signing_key()

    assert f'{key.get_name()} {key.get_base64()}' == install.public_key


def test_the_identifier_is_kept_without_disturbing_the_key():
    install = remote_install()

    registered = set_install_id('install_abc')

    assert registered.install_id == 'install_abc'
    assert registered.public_key == install.public_key
    assert remote_install().install_id == 'install_abc'
    assert remote_install().is_registered


def test_forgetting_the_identifier_leaves_the_computer_itself_alone():
    """A disowned computer registers again rather than becoming another one."""
    set_install_id('install_abc')
    key = remote_install().public_key

    forget_remote_install()

    assert not remote_install().is_registered
    assert remote_install().public_key == key
