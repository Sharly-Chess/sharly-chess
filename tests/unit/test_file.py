from pathlib import Path

import pytest

from utils.file import is_within, overlap, rename_when_released


def test_a_folder_is_within_itself_and_its_parents():
    assert is_within(Path('/data/Sharly Chess'), Path('/data/Sharly Chess'))
    assert is_within(Path('/data/Sharly Chess/events'), Path('/data'))
    assert not is_within(Path('/data/Sharly Chess'), Path('/data/Sharly'))
    assert not is_within(Path('/data'), Path('/data/Sharly Chess'))


def test_folders_overlap_whichever_holds_the_other():
    """The data and the backups are each moved, emptied and deleted on their
    own, so neither can hold the other."""
    data_dir = Path('/data/Sharly Chess/data')

    assert overlap(data_dir, data_dir)
    assert overlap(data_dir / 'snapshots', data_dir)
    assert overlap(data_dir, data_dir / 'snapshots')
    assert not overlap(data_dir, data_dir.with_name('snapshots'))


def _held_for(monkeypatch, refusals: int, on_windows: bool) -> list[Path]:
    """Makes the renames refused as Windows refuses a file another process
    holds open, the given number of times."""
    import utils.file

    monkeypatch.setattr(utils.file, 'ON_WINDOWS', on_windows)
    monkeypatch.setattr(utils.file, 'RENAME_RETRY_SECONDS', 0)
    real_rename = Path.rename
    attempts: list[Path] = []

    def rename(self: Path, target: Path) -> Path:
        attempts.append(self)
        if len(attempts) <= refusals:
            raise PermissionError(32, 'The file is being used by another process')
        return real_rename(self, target)

    monkeypatch.setattr(Path, 'rename', rename)
    return attempts


def test_a_rename_waits_for_the_file_to_be_let_go_on_windows(tmp_path, monkeypatch):
    source = tmp_path / 'event.sce'
    source.write_text('data')
    attempts = _held_for(monkeypatch, refusals=3, on_windows=True)

    rename_when_released(source, tmp_path / 'event.sca')

    assert len(attempts) == 4
    assert (tmp_path / 'event.sca').read_text() == 'data'
    assert not source.exists()


def test_a_rename_held_for_too_long_is_refused(tmp_path, monkeypatch):
    source = tmp_path / 'event.sce'
    source.write_text('data')
    _held_for(monkeypatch, refusals=1_000_000, on_windows=True)

    with pytest.raises(PermissionError):
        rename_when_released(source, tmp_path / 'event.sca', wait_seconds=0.05)
    assert source.exists()


def test_a_refused_rename_is_final_outside_windows(tmp_path, monkeypatch):
    source = tmp_path / 'event.sce'
    source.write_text('data')
    attempts = _held_for(monkeypatch, refusals=1, on_windows=False)

    with pytest.raises(PermissionError):
        rename_when_released(source, tmp_path / 'event.sca')
    assert len(attempts) == 1
