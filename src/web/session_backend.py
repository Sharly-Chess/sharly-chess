"""Custom server-side session backend that skips redundant DB writes.

Litestar's default ServerSideSessionBackend writes session data to the store
on **every** HTTP response, even when the session dict was never modified.
With many concurrent clients polling via HTMX, this creates massive write
contention on the SQLite session database and leads to "database is locked"
errors.

This backend records a hash of the session data when it is loaded and
compares it before writing.  If the data hasn't changed, the write is
skipped entirely, eliminating the vast majority of session-DB writes for
read-only requests (screen polling, 304 responses, etc.).
"""

from hashlib import sha256
from typing import Any

from litestar.connection import ASGIConnection
from litestar.datastructures import MutableScopeHeaders, Cookie
from litestar.middleware.session.server_side import ServerSideSessionBackend
from litestar.types import Message, ScopeSession
from litestar.utils.dataclass import extract_dataclass_items
from litestar.utils.empty import Empty

_SESSION_HASH_KEY = '_sharly_session_hash'


class SkipUnchangedSessionBackend(ServerSideSessionBackend):
    """A session backend that avoids writing to the store when the session
    data did not change during the request lifecycle."""

    async def load_from_connection(self, connection: ASGIConnection) -> dict[str, Any]:
        """Load session data and store a hash of the original state in the connection scope."""
        data = await super().load_from_connection(connection)
        # Store a fingerprint of the loaded data so we can detect changes later.
        connection.scope[_SESSION_HASH_KEY] = _hash_session(data)
        return data

    async def store_in_message(
        self,
        scope_session: ScopeSession,
        message: Message,
        connection: ASGIConnection,
    ) -> None:
        """Only persist to the store when session data actually changed."""
        if message['type'] != 'http.response.start':
            # Not the right ASGI message; nothing to do.
            return

        scope = connection.scope
        store = self.config.get_store_from_app(scope['app'])
        headers = MutableScopeHeaders.from_message(message)
        session_id = self.get_session_id(connection)

        cookie_params = dict(
            extract_dataclass_items(
                self.config, exclude_none=True, include=Cookie.__dict__.keys()
            )
        )

        if scope_session is Empty:
            # Session was explicitly cleared — delete from store.
            await self.delete(session_id, store=store)
            headers.add(
                'Set-Cookie',
                Cookie(
                    value='null', key=self.config.key, expires=0, **cookie_params
                ).to_header(header=''),
            )
        else:
            # Check whether the session actually changed.
            original_hash = scope.get(_SESSION_HASH_KEY)
            current_hash = _hash_session(scope_session)

            if original_hash != current_hash:
                # Session was modified — persist to the store.
                serialised_data = self.serialize_data(scope_session, scope)
                await self.set(session_id=session_id, data=serialised_data, store=store)

            # Always refresh the cookie (keeps expiry date updated).
            headers.add(
                'Set-Cookie',
                Cookie(
                    value=session_id, key=self.config.key, **cookie_params
                ).to_header(header=''),
            )


def _hash_session(data: ScopeSession) -> str:
    """Compute a deterministic hash of session data for change detection."""
    if data is Empty or data is None:
        return ''
    # Use repr for a quick deterministic serialisation of a dict.
    # Sorting keys ensures deterministic ordering.
    return sha256(repr(sorted(data.items())).encode()).hexdigest()
