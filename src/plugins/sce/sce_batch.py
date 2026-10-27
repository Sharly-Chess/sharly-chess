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
from typing import Any
from collections.abc import Callable, Generator


# Server cap is 200. Stay under it to leave headroom for retries / future
# server-side schema growth.
BATCH_CHUNK_SIZE = 100


def _with_precondition(
    op_dict: dict[str, Any], expected_updated_at: str | None
) -> dict[str, Any]:
    """Makes the op apply only if the registration still has the
    `updated_at` it was read with; otherwise the server refuses it with
    `precondition_failed`."""
    if expected_updated_at:
        op_dict['expected_updated_at'] = expected_updated_at
    return op_dict


@dataclass
class _PendingOp:
    """An op queued for batch dispatch plus the callbacks that apply its result.

    `on_success(result)` is invoked with the per-op result dict from the
    server (`{index, status: 'ok', registration_id?, promoted?}`). Used to
    set `plugin_data.id`, `plugin_data.last_sync_data`, etc.

    `on_error(result)` is invoked with the per-op error dict
    (`{index, status: 'error', error: {code, message}}`). Lets the caller
    distinguish 409 (duplicate) and 412 (changed since read, see
    `is_stale_result`) from other failures.

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
        expected_updated_at: str | None = None,
    ) -> None:
        op_data = {k: v for k, v in data.items() if k != 'tournament_id'}
        self.pending.append(
            _PendingOp(
                op_dict=_with_precondition(
                    {
                        'op': 'update',
                        'registration_id': registration_id,
                        'tournament_id': tournament_id,
                        'data': op_data,
                    },
                    expected_updated_at,
                ),
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
        expected_updated_at: str | None = None,
    ) -> None:
        self.pending.append(
            _PendingOp(
                op_dict=_with_precondition(
                    {'op': 'delete', 'registration_id': registration_id},
                    expected_updated_at,
                ),
                on_success=on_success,
                on_error=on_error,
                log_label=log_label,
            )
        )

    def chunks(self, chunk_size: int = BATCH_CHUNK_SIZE) -> Generator[list[_PendingOp]]:
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
        for op, result in zip(ops, results, strict=True):
            if result.get('status') == 'ok':
                op.on_success(result)
            else:
                op.on_error(result)


def is_stale_result(result: dict[str, Any]) -> bool:
    """True when an op was refused because the registration changed on
    Sharly-Chess.com since it was read: nothing failed, the next sync merges
    the newer data."""
    return (result.get('error') or {}).get('code') == 'precondition_failed'
