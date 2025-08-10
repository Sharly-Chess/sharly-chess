import hashlib
from pathlib import Path


def file_fingerprint(file: Path) -> bytes:
    """Returns a digest of a file."""
    hash_md5 = hashlib.md5()
    with open(file, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.digest()


def shutil_delete_onerror(func, path, exc_info):
    """
    This method is used as a workaround for ``PermissionError: access denied``
    errors happening on some Windows systems.
    Usage : ``shutil.rmtree(path, onerror=shutil_delete_onerror)``
    """
    import stat
    import os

    os.chmod(path, stat.S_IWUSR)
    func(path)
