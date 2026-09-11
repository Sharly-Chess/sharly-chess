"""Which screens leave the venue.

`public` says who may look; this says from where. The two are wanted apart: a
public input screen belongs on the venue's own network, where being in the room
is what stands between a player and somebody else's result, while a pairing
display beside it is worth showing to anyone following the tournament.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from litestar.exceptions import NotFoundException, PermissionDeniedException

from litestar.plugins.htmx import HTMXRequest

from data.access_levels.actions import AuthAction
from data.access_levels.client import Client
from data.screens.screen import Screen
from web.guards import ViewScreenEntityGuard


def entity(uniq_id: str, public: bool, remote: bool):
    return SimpleNamespace(uniq_id=uniq_id, public=public, remote=remote)


def client(remote: bool, allowed: set[AuthAction] | None = None):
    """A caller, named by where it came from and what it may do."""
    return SimpleNamespace(
        remote=remote,
        allowed_actions=allowed
        if allowed is not None
        else {AuthAction.VIEW_PUBLIC_SCREENS},
        account=SimpleNamespace(full_name='Someone'),
    )


def authorize(subject, caller) -> None:
    """Run the real guard against a given entity and caller."""

    class Guard(ViewScreenEntityGuard):
        @staticmethod
        def get_entity(request):
            return subject

    Guard().authorize_client(cast(Client, caller), cast(HTMXRequest, None))


def test_a_screen_kept_off_the_internet_is_not_served_to_a_remote_viewer():
    with pytest.raises(NotFoundException):
        authorize(entity('input', public=True, remote=False), client(remote=True))


def test_the_same_screen_is_served_on_the_venue_network():
    authorize(entity('input', public=True, remote=False), client(remote=False))


def test_a_screen_put_on_the_internet_is_served_to_a_remote_viewer():
    authorize(entity('pairings', public=True, remote=True), client(remote=True))


def test_being_on_the_internet_does_not_make_a_private_screen_public():
    """The two questions stay apart: this one still asks who is looking."""
    with pytest.raises(PermissionDeniedException):
        authorize(entity('results', public=False, remote=True), client(remote=True))


def test_a_private_screen_on_the_internet_opens_to_someone_allowed():
    authorize(
        entity('results', public=False, remote=True),
        client(remote=True, allowed={AuthAction.VIEW_PRIVATE_SCREENS}),
    )


def test_a_refusal_from_the_internet_says_not_found_rather_than_forbidden():
    """No account changes the answer, so a refusal that named the screen would
    only tell whoever is probing the hostname that it is there."""
    with pytest.raises(NotFoundException):
        authorize(
            entity('input', public=True, remote=False),
            client(remote=True, allowed={AuthAction.VIEW_PRIVATE_SCREENS}),
        )


class FakeStoredScreen:
    def __init__(self, remote: bool) -> None:
        self.remote = remote
        self.public = True
        self.uniq_id = 'a-screen'


def test_a_screen_from_a_family_takes_the_family_s_answer(monkeypatch):
    """A family generates its screens, so what it says goes for all of them."""
    family = SimpleNamespace(remote=True, public=True)
    screen = Screen.__new__(Screen)
    screen.stored_screen = None
    screen._family_ref = cast(Any, lambda: family)

    assert screen.remote is True

    family.remote = False
    assert screen.remote is False


def reachable(caller, entities):
    return Client.reachable(cast(Client, caller), entities)


def test_a_listing_shown_on_the_venue_network_holds_everything():
    entities = [entity('input', True, False), entity('pairings', True, True)]

    assert reachable(client(remote=False), entities) == entities


def test_a_listing_shown_over_the_internet_holds_only_what_is_served_there():
    """Listing a screen that answers nothing reads as a broken tournament
    rather than as one kept on the venue's own network on purpose."""
    served = entity('pairings', True, True)
    entities = [entity('input', True, False), served]

    assert reachable(client(remote=True), entities) == [served]
