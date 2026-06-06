"""Unit tests for `plugins.sce.sce_batch.SCEBatchBuilder`.

Focused on the builder's pure behaviour — op construction, chunking, and
callback dispatch. Higher-level coverage (HTTP wiring, plugin_data
mutations) lives in integration tests against a running events platform.
"""

import pytest

from plugins.sce.sce_batch import SCEBatchBuilder


@pytest.mark.unit
class TestSCEBatchBuilder:
    def test_empty_builder(self):
        b = SCEBatchBuilder()
        assert b.is_empty()
        assert len(b) == 0
        assert list(b.chunks()) == []

    def test_add_create_strips_tournament_id_from_data(self):
        b = SCEBatchBuilder()
        called = {}

        def on_success(r):
            called['success'] = r

        def on_error(r):
            called['error'] = r

        b.add_create(
            tournament_id='T1',
            data={'tournament_id': 'T1', 'last_name': 'Carlsen', 'year_of_birth': 1990},
            on_success=on_success,
            on_error=on_error,
            log_label='Carlsen',
        )

        assert len(b) == 1
        op = b.pending[0]
        assert op.op_dict['op'] == 'create'
        assert op.op_dict['tournament_id'] == 'T1'
        assert 'tournament_id' not in op.op_dict['data']
        assert op.op_dict['data']['last_name'] == 'Carlsen'
        assert op.log_label == 'Carlsen'

    def test_add_update_strips_tournament_id_from_data(self):
        b = SCEBatchBuilder()
        b.add_update(
            registration_id='R1',
            tournament_id='T2',
            data={'tournament_id': 'T2', 'last_name': 'Smith', 'year_of_birth': 1985},
            on_success=lambda r: None,
            on_error=lambda r: None,
            log_label='Smith',
        )
        op = b.pending[0]
        assert op.op_dict == {
            'op': 'update',
            'registration_id': 'R1',
            'tournament_id': 'T2',
            'data': {'last_name': 'Smith', 'year_of_birth': 1985},
        }

    def test_add_delete(self):
        b = SCEBatchBuilder()
        b.add_delete(
            registration_id='R7',
            on_success=lambda r: None,
            on_error=lambda r: None,
            log_label='Doe',
        )
        op = b.pending[0]
        assert op.op_dict == {'op': 'delete', 'registration_id': 'R7'}

    def test_chunks_splits_at_chunk_size(self):
        b = SCEBatchBuilder()
        for i in range(25):
            b.add_delete(
                registration_id=f'R{i}',
                on_success=lambda r: None,
                on_error=lambda r: None,
                log_label=f'P{i}',
            )
        chunks = list(b.chunks(chunk_size=10))
        assert len(chunks) == 3
        assert len(chunks[0]) == 10
        assert len(chunks[1]) == 10
        assert len(chunks[2]) == 5

    def test_apply_results_dispatches_per_op(self):
        b = SCEBatchBuilder()
        outcomes: list[tuple[str, dict]] = []

        for i in range(3):
            b.add_create(
                tournament_id='T1',
                data={'last_name': f'L{i}', 'year_of_birth': 1990},
                on_success=lambda r, idx=i: outcomes.append((f'ok-{idx}', r)),
                on_error=lambda r, idx=i: outcomes.append((f'err-{idx}', r)),
                log_label=f'P{i}',
            )

        chunk = b.pending
        results = [
            {'index': 0, 'status': 'ok', 'registration_id': 'X0'},
            {
                'index': 1,
                'status': 'error',
                'error': {'code': 'conflict', 'message': 'dup'},
            },
            {'index': 2, 'status': 'ok', 'registration_id': 'X2', 'promoted': True},
        ]
        b.apply_results(chunk, results)

        assert outcomes == [
            ('ok-0', results[0]),
            ('err-1', results[1]),
            ('ok-2', results[2]),
        ]
