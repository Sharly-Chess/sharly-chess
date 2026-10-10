import json
import sys
from pathlib import Path

import pytest

from utils import program_variables
from utils.program_variables import ProgramVar


@pytest.fixture
def linux_data_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_file = tmp_path / 'config' / 'sharly-chess' / 'program_vars.json'
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(program_variables, 'LINUX_DATA_FILE', data_file)
    return data_file


def test_linux_values_are_stored_in_the_data_file(linux_data_file: Path):
    ProgramVar.VERSION.write_value('5.1.5')
    ProgramVar.LOCALE.write_value('fr')
    assert ProgramVar.VERSION.read_value() == '5.1.5'
    assert ProgramVar.LOCALE.read_value() == 'fr'
    assert json.loads(linux_data_file.read_text()) == {
        ProgramVar.VERSION.stored_name: '5.1.5',
        ProgramVar.LOCALE.stored_name: 'fr',
    }


def test_linux_value_is_overwritten(linux_data_file: Path):
    ProgramVar.VERSION.write_value('5.1.4')
    ProgramVar.VERSION.write_value('5.1.5')
    assert ProgramVar.VERSION.read_value() == '5.1.5'
    assert len(json.loads(linux_data_file.read_text())) == 1


def test_linux_value_missing_from_the_data_file_is_read_from_the_environment(
    linux_data_file: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(ProgramVar.VERSION.stored_name, '5.1.4')
    assert ProgramVar.VERSION.read_value() == '5.1.4'


def test_linux_cleared_value_hides_the_environment(
    linux_data_file: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(ProgramVar.LEGACY_VERSION.stored_name, '4.2.8')
    ProgramVar.LEGACY_VERSION.clear_value()
    assert ProgramVar.LEGACY_VERSION.read_value() is None


def test_linux_unreadable_data_file_holds_no_value(linux_data_file: Path):
    linux_data_file.parent.mkdir(parents=True)
    linux_data_file.write_text('not json')
    assert ProgramVar.VERSION.read_value() is None
