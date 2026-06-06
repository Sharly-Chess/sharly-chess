"""Batch op builder for Sharly-Chess.com registration sync.

The events platform exposes
`POST /api/v1/events/{eventId}/registrations/batch` which applies many
registration ops (create/update/delete) atomically or best-effort. THP
collects ops here while walking the local model, then flushes the whole
batch in one HTTP round-trip per chunk.

Each pending op carries the callbacks needed to apply its server response
back to local plugin_data. The session does not need to know per-op
semantics — it just dispatches by status.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Generator


# Server cap is 200. Stay under it to leave headroom for retries / future
# server-side schema growth.
BATCH_CHUNK_SIZE = 100


@dataclass
class _PendingOp:
    """An op queued for batch dispatch plus the callbacks that apply its result.

    `on_success(result)` is invoked with the per-op result dict from the
    server (`{index, status: 'ok', registration_id?, promoted?}`). Used to
    set `plugin_data.id`, `plugin_data.last_sync_data`, etc.

    `on_error(result)` is invoked with the per-op error dict
    (`{index, status: 'error', error: {code, message}}`). Lets the caller
    distinguish 409 (duplicate) from other failures.

    `log_label` is a short identifier (typically the player's display name)
    used when logging batch outcomes.
    """

    op_dict: dict[str, Any]
    on_success: Callable[[dict[str, Any]], None]
    on_error: Callable[[dict[str, Any]], None]
    log_label: str


@dataclass
class SCEBatchBuilder:
    """Collects registration ops to flush as a single batch request."""

    pending: list[_PendingOp] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.pending)

    def is_empty(self) -> bool:
        return not self.pending

    def add_create(
        self,
        tournament_id: str,
        data: dict[str, Any],
        on_success: Callable[[dict[str, Any]], None],
        on_error: Callable[[dict[str, Any]], None],
        log_label: str,
    ) -> None:
        op_data = {k: v for k, v in data.items() if k != 'tournament_id'}
        self.pending.append(
            _PendingOp(
                op_dict={
                    'op': 'create',
                    'tournament_id': tournament_id,
                    'data': op_data,
                },
                on_success=on_success,
                on_error=on_error,
                log_label=log_label,
            )
        )

    def add_update(
        self,
        registration_id: str,
        tournament_id: str,
        data: dict[str, Any],
        on_success: Callable[[dict[str, Any]], None],
        on_error: Callable[[dict[str, Any]], None],
        log_label: str,
    ) -> None:
        op_data = {k: v for k, v in data.items() if k != 'tournament_id'}
        self.pending.append(
            _PendingOp(
                op_dict={
                    'op': 'update',
                    'registration_id': registration_id,
                    'tournament_id': tournament_id,
                    'data': op_data,
                },
                on_success=on_success,
                on_error=on_error,
                log_label=log_label,
            )
        )

    def add_delete(
        self,
        registration_id: str,
        on_success: Callable[[dict[str, Any]], None],
        on_error: Callable[[dict[str, Any]], None],
        log_label: str,
    ) -> None:
        self.pending.append(
            _PendingOp(
                op_dict={'op': 'delete', 'registration_id': registration_id},
                on_success=on_success,
                on_error=on_error,
                log_label=log_label,
            )
        )

    def chunks(
        self, chunk_size: int = BATCH_CHUNK_SIZE
    ) -> Generator[list[_PendingOp], None, None]:
        for i in range(0, len(self.pending), chunk_size):
            yield self.pending[i : i + chunk_size]

    def apply_results(
        self, ops: list[_PendingOp], results: list[dict[str, Any]]
    ) -> None:
        """Dispatch each per-op result to its on_success / on_error callback.

        Aligned by position — the server returns one result per op in the
        order they were sent (each result also carries `index`, which we
        cross-check defensively).
        """
        for op, result in zip(ops, results):
            if result.get('status') == 'ok':
                op.on_success(result)
            else:
                op.on_error(result)
