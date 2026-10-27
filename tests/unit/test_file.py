from pathlib import Path

from utils.file import is_within, overlap


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
