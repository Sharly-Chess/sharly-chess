from pathlib import Path

from common.data_recovery import DataRecovery


def _create_data_dir(directory: Path) -> Path:
    (directory / 'events').mkdir(parents=True)
    return directory


def test_stored_dir_holds_the_data(tmp_path: Path):
    stored_dir = _create_data_dir(tmp_path / 'sharly-chess')
    assert DataRecovery._find_legacy_data_dir(stored_dir) == stored_dir


def test_data_one_level_above_the_stored_dir(tmp_path: Path):
    install_dir = _create_data_dir(tmp_path / 'sharly-chess')
    stored_dir = install_dir / '_internal'
    stored_dir.mkdir()
    assert DataRecovery._find_legacy_data_dir(stored_dir) == install_dir


def test_data_beside_the_application_bundle(tmp_path: Path):
    install_dir = _create_data_dir(tmp_path / 'sharly-chess')
    stored_dir = install_dir / 'SharlyChess.app' / 'Contents' / 'Frameworks'
    stored_dir.mkdir(parents=True)
    assert DataRecovery._find_legacy_data_dir(stored_dir) == install_dir


def test_bundle_content_takes_precedence_over_the_bundle_parent(tmp_path: Path):
    install_dir = _create_data_dir(tmp_path / 'sharly-chess')
    stored_dir = _create_data_dir(
        install_dir / 'SharlyChess.app' / 'Contents' / 'Frameworks'
    )
    assert DataRecovery._find_legacy_data_dir(stored_dir) == stored_dir


def test_no_data_found(tmp_path: Path):
    stored_dir = tmp_path / 'sharly-chess' / '_internal'
    stored_dir.mkdir(parents=True)
    assert DataRecovery._find_legacy_data_dir(stored_dir) is None
