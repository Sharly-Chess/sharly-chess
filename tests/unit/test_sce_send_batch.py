"""Unit tests for `SCESession.send_batch`.

Covers HTTP-level wiring: URL, method, payload shape, chunking, and how
batch responses are dispatched back to per-op callbacks.
`_run_with_token_validation` is stubbed so the token-refresh dance is
out of scope here (tested separately if needed).
"""

from unittest.mock import MagicMock

import pytest
from litestar.status_codes import HTTP_200_OK

from common import SharlyChessException
from plugins.sce.sce_batch import SCEBatchBuilder
from plugins.sce.sce_session import SCESession


def make_session_for_batch(monkeypatch) -> SCESession:
    """Build an SCESession that returns a known batch URL without needing
    real event tokens/plugin_data."""
    session = SCESession.__new__(SCESession)
    session.event = MagicMock()
    session.event.uniq_id = 'test-event'
    session.new_check_ins_tournament_sce_ids = set()

    # Override the property that would otherwise read plugin_data.tokens.
    monkeypatch.setattr(
        SCESession,
        'registrations_batch_url',
        property(lambda self: 'https://test/api/v1/events/E1/registrations/batch'),
    )
    monkeypatch.setattr(
        SCESession,
        'api_headers',
        property(
            lambda self: {
                'Authorization': 'Bearer T',
                'Content-Type': 'application/json',
            }
        ),
    )
    return session


def _fake_response(status: int, body: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    return r


@pytest.mark.unit
class TestSendBatch:
    def test_empty_builder_is_a_noop(self, monkeypatch):
        session = make_session_for_batch(monkeypatch)
        called = {'count': 0}

        def fake_runner(fn, skip_validation=False):
            called['count'] += 1
            return _fake_response(200, {'results': []})

        monkeypatch.setattr(session, '_run_with_token_validation', fake_runner)

        session.send_batch(SCEBatchBuilder())
        assert called['count'] == 0

    def test_single_chunk_dispatches_results_to_callbacks(self, monkeypatch):
        session = make_session_for_batch(monkeypatch)
        builder = SCEBatchBuilder()
        outcomes: list[tuple[str, dict]] = []

        for i in range(3):
            builder.add_delete(
                registration_id=f'R{i}',
                on_success=lambda r, idx=i: outcomes.append((f'ok-{idx}', r)),
                on_error=lambda r, idx=i: outcomes.append((f'err-{idx}', r)),
                log_label=f'P{i}',
            )

        results = [
            {'index': 0, 'status': 'ok', 'registration_id': 'R0'},
            {
                'index': 1,
                'status': 'error',
                'error': {'code': 'not_found', 'message': '!'},
            },
            {'index': 2, 'status': 'ok', 'registration_id': 'R2'},
        ]
        monkeypatch.setattr(
            session,
            '_run_with_token_validation',
            lambda fn, skip_validation=False: _fake_response(207, {'results': results}),
        )

        session.send_batch(builder)

        assert outcomes == [
            ('ok-0', results[0]),
            ('err-1', results[1]),
            ('ok-2', results[2]),
        ]

    def test_chunks_send_separate_requests(self, monkeypatch):
        session = make_session_for_batch(monkeypatch)
        builder = SCEBatchBuilder()
        for i in range(7):
            builder.add_delete(
                registration_id=f'R{i}',
                on_success=lambda r: None,
                on_error=lambda r: None,
                log_label=f'P{i}',
            )

        request_count = {'n': 0}

        def fake_runner(fn, skip_validation=False):
            request_count['n'] += 1
            # Inspect what the closed-over partial would post by calling it.
            # The fn is partial(_send_batch_request, ops=...) — we ignore
            # actually sending and craft a matching results list.
            ops = fn.keywords['ops']
            return _fake_response(
                200,
                {
                    'results': [
                        {
                            'index': i,
                            'status': 'ok',
                            'registration_id': op['registration_id'],
                        }
                        for i, op in enumerate(ops)
                    ]
                },
            )

        monkeypatch.setattr(session, '_run_with_token_validation', fake_runner)

        # Force tiny chunks via internal chunks() arg by monkeypatching.
        original_chunks = SCEBatchBuilder.chunks
        monkeypatch.setattr(
            SCEBatchBuilder,
            'chunks',
            lambda self, chunk_size=2: original_chunks(self, chunk_size=2),
        )

        session.send_batch(builder)
        # 7 ops in chunks of 2 → 4 requests (2, 2, 2, 1).
        assert request_count['n'] == 4

    def test_http_failure_raises_sharly_chess_exception(self, monkeypatch):
        session = make_session_for_batch(monkeypatch)
        builder = SCEBatchBuilder()
        builder.add_delete(
            registration_id='R0',
            on_success=lambda r: pytest.fail('should not be called'),
            on_error=lambda r: pytest.fail('should not be called'),
            log_label='P0',
        )

        # 500 with a request attribute so validate_api_response can format.
        resp = _fake_response(500, {})
        resp.request.method = 'POST'
        resp.url = 'https://test/...'
        resp.raise_for_status.side_effect = __import__('requests').HTTPError('500')

        monkeypatch.setattr(
            session,
            '_run_with_token_validation',
            lambda fn, skip_validation=False: resp,
        )

        with pytest.raises(SharlyChessException):
            session.send_batch(builder)

    def test_payload_uses_best_effort_mode(self, monkeypatch):
        session = make_session_for_batch(monkeypatch)
        builder = SCEBatchBuilder()
        builder.add_delete(
            registration_id='R0',
            on_success=lambda r: None,
            on_error=lambda r: None,
            log_label='P0',
        )

        captured: dict = {}

        def fake_post(url, headers=None, json=None, **kw):
            captured['url'] = url
            captured['headers'] = headers
            captured['json'] = json
            return _fake_response(
                HTTP_200_OK, {'results': [{'index': 0, 'status': 'ok'}]}
            )

        # _run_with_token_validation runs fn() directly here.
        monkeypatch.setattr(
            session,
            '_run_with_token_validation',
            lambda fn, skip_validation=False: fn(),
        )
        monkeypatch.setattr('plugins.sce.sce_session.requests.post', fake_post)

        session.send_batch(builder)

        assert captured['url'] == 'https://test/api/v1/events/E1/registrations/batch'
        assert captured['headers']['Authorization'] == 'Bearer T'
        assert captured['json']['mode'] == 'best_effort'
        assert len(captured['json']['ops']) == 1
        assert captured['json']['ops'][0]['op'] == 'delete'
