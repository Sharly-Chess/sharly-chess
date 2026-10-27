import os
import subprocess
import sys
from pathlib import Path

from utils.instance_lock import InstanceLock

_SRC_DIR = Path(__file__).resolve().parents[2] / 'src'

_HOLDER_SCRIPT = """
import sys
from pathlib import Path
from utils.instance_lock import InstanceLock

lock = InstanceLock(Path(sys.argv[1]))
print('acquired' if lock.acquire() else 'refused', flush=True)
sys.stdin.readline()
"""


def _start_holder(directory: Path) -> subprocess.Popen[str]:
    env = os.environ | {'PYTHONPATH': str(_SRC_DIR)}
    process = subprocess.Popen(
        [sys.executable, '-c', _HOLDER_SCRIPT, str(directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == 'acquired'
    return process


def test_a_second_lock_on_the_same_folder_is_refused(tmp_path: Path):
    first = InstanceLock(tmp_path)
    second = InstanceLock(tmp_path)

    assert first.acquire()
    assert not second.acquire()

    first.release()
    assert second.acquire()
    second.release()


def test_the_holder_information_is_readable_while_locked(tmp_path: Path):
    lock = InstanceLock(tmp_path)
    assert lock.acquire()
    lock.publish_url('http://127.0.0.1:81')

    info = InstanceLock(tmp_path).read_info()

    assert info['pid'] == os.getpid()
    assert info['url'] == 'http://127.0.0.1:81'
    lock.release()


def test_the_lock_of_another_process_is_detected(tmp_path: Path):
    holder = _start_holder(tmp_path)
    try:
        assert InstanceLock.is_held_by_another_process(tmp_path)
        assert not InstanceLock(tmp_path).acquire()
    finally:
        holder.kill()
        holder.wait()


def test_a_killed_process_leaves_no_lock_behind(tmp_path: Path):
    holder = _start_holder(tmp_path)
    holder.kill()
    holder.wait()

    lock = InstanceLock(tmp_path)
    assert lock.acquire()
    lock.release()


def test_the_lock_held_by_this_process_is_not_another_one(tmp_path: Path):
    lock = InstanceLock(tmp_path)
    assert lock.acquire()
    InstanceLock.held = lock
    try:
        assert not InstanceLock.is_held_by_another_process(tmp_path)
    finally:
        lock.release()
    assert InstanceLock.held is None


def test_a_missing_folder_is_not_locked(tmp_path: Path):
    missing = tmp_path / 'missing'

    assert not InstanceLock.is_held_by_another_process(missing)
    assert not missing.exists()
