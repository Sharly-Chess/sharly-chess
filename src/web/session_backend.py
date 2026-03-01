from hashlib import sha256
from typing import Any

from litestar.connection import ASGIConnection
from litestar.datastructures import MutableScopeHeaders, Cookie
from litestar.middleware.session.server_side import ServerSideSessionBackend
from litestar.types import Message, ScopeSession, Empty
from litestar.utils.dataclass import extract_dataclass_items

SESSION_HASH_KEY = 'sharly-session-hash'


def _hash_session(data: ScopeSession) -> str:
    if data is Empty or data is None:
        return ''

    # the repr and sorting are done to ensure a deterministic hash
    return sha256(repr(sorted(data.items())).encode()).hexdigest()


class SkipUnchangedSessionBackend(ServerSideSessionBackend):
    async def load_from_connection(self, connection: ASGIConnection) -> dict[str, Any]:
        data = await super().load_from_connection(connection)

        connection.scope[SESSION_HASH_KEY] = _hash_session(data)  # type: ignore[literal-required]
        return data

    async def store_in_message(
        self, scope_session: ScopeSession, message: Message, connection: ASGIConnection
    ) -> None:
        if message['type'] != 'http.response.start':
            await super().store_in_message(scope_session, message, connection)

        scope = connection.scope

        if scope_session is Empty:
            return await self.store_in_message(scope_session, message, connection)

        original_hash = scope.get(SESSION_HASH_KEY, '')
        current_hash = _hash_session(scope_session)

        if original_hash != current_hash:
            return await super().store_in_message(scope_session, message, connection)
        else:
            # Refresh the cookie, even if the session data did not change.
            # This is only done when we are sure that the session has not changed (assuming no SHA256 collision)
            headers = MutableScopeHeaders.from_message(message)
            session_id = self.get_session_id(connection)

            cookie_parms = dict(
                extract_dataclass_items(
                    self.config, exclude_none=True, include=Cookie.__dict__.keys()
                )
            )
            headers.add(
                'Set-Cookie',
                Cookie(value=session_id, key=self.config.key, **cookie_parms).to_header(
                    header=''
                ),
            )
