from typing import Any, cast

from litestar import Request, Response
from litestar.plugins.htmx import HTMXRequest

from data.journal import (
    Actor,
    Author,
    AuthorKind,
    Source,
    SourceKind,
    check_journal_scope,
    current_journal_scope,
    end_journal_scope,
    set_actor_provider,
    start_journal_scope,
)
from web.utils import RequestUtils


def request_actor(request: HTMXRequest) -> Actor:
    """Who acts through *request*, if anybody, the account it is signed in
    with telling; and where from: the computer running the application, a
    screen, or another device of the network."""
    client = RequestUtils.get_client(request)
    account = client.account
    host = client.host or None
    author: Author | None = None
    if account.administrator:
        author = Author(AuthorKind.ADMINISTRATOR, account.id)
    elif account.user_account:
        author = Author(AuthorKind.ACCOUNT, account.id)
    if RequestUtils.REQUEST_SCREEN_ATTR in request.state:
        screen = RequestUtils.get_screen(request)
        source = Source(SourceKind.SCREEN, screen.name, host)
    elif client.is_local:
        source = Source(SourceKind.COMPUTER, host=host)
    else:
        source = Source(SourceKind.NETWORK, host=host)
    return Actor(author, source)


async def open_journal_scope(request: Request[Any, Any, Any]) -> None:
    """Hands the journal the author of what the request does, and follows what
    it writes."""
    set_actor_provider(lambda: request_actor(cast(HTMXRequest, request)))
    start_journal_scope(f'{request.method} {request.url.path}')


async def close_journal_scope(response: Response[Any]) -> Response[Any]:
    """Checks that what the request wrote is journaled, or said not to be."""
    if (scope := current_journal_scope()) is not None:
        end_journal_scope()
        check_journal_scope(scope)
    return response
