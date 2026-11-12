import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from common.exception import PairingEngineTimeout
from data.pairings import engines
from utils import Utils


@pytest.fixture
def kept_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / 'kept'
    monkeypatch.setattr(engines, 'BBP_FILES_DIR', directory)
    return directory


def _tournament() -> Any:
    return SimpleNamespace(sanitized_name='cup', log_prefix='[cup] ')


def test_run_bbp_keeps_the_input_before_running(
    tmp_path: Path, kept_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_file = tmp_path / 'team-pairings-input.trfx'
    input_file.write_text('012 Cup\n', encoding='utf-8')
    seen: list[bool] = []

    def run_process(cmd: list, **kwargs: Any) -> subprocess.CompletedProcess:
        seen.append((kept_dir / 'cup-team-pairings-input.trfx').exists())
        assert kwargs['timeout'] == engines.BBP_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(cmd, 0, '', '')

    monkeypatch.setattr(Utils, 'run_process', run_process)
    engines.run_bbp(_tournament(), '--team', input_file, '-p', tmp_path / 'out')
    assert seen == [True]


def test_run_bbp_reports_an_engine_that_does_not_answer(
    tmp_path: Path, kept_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_file = tmp_path / 'pairings-input.trfx'
    input_file.write_text('012 Open\n', encoding='utf-8')

    def run_process(cmd: list, **kwargs: Any) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(cmd, kwargs['timeout'])

    monkeypatch.setattr(Utils, 'run_process', run_process)
    with pytest.raises(PairingEngineTimeout) as raised:
        engines.run_bbp(_tournament(), '--dutch', input_file, '-p', tmp_path / 'out')
    kept_file = kept_dir / 'cup-pairings-input.trfx'
    assert kept_file.read_text(encoding='utf-8') == '012 Open\n'
    assert str(engines.BBP_TIMEOUT_SECONDS) in raised.value.detail
    assert str(kept_file) in raised.value.detail
