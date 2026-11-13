import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from common.data_recovery import DataRecovery


@pytest.mark.unit
class TestRecoverFile:
    def test_a_readable_file_is_copied(self, tmp_path: Path):
        source = tmp_path / 'event.sce'
        source.write_bytes(b'event')
        target_dir = tmp_path / 'events'
        target_dir.mkdir()

        assert DataRecovery._recover_file(source, target_dir)
        assert (target_dir / 'event.sce').read_bytes() == b'event'

    def test_a_refused_file_is_left_behind_without_raising(self, tmp_path: Path):
        source = tmp_path / 'event.sce'
        source.write_bytes(b'event')
        target_dir = tmp_path / 'events'
        target_dir.mkdir()

        with patch.object(shutil, 'copy', side_effect=PermissionError(13, 'refused')):
            assert not DataRecovery._recover_file(source, target_dir)
        assert source.is_file()
        assert not (target_dir / 'event.sce').exists()
