import hashlib
from pathlib import Path


def file_fingerprint(file: Path) -> bytes:
    """Returns a digest of a file."""
    try:
        hash_md5 = hashlib.md5()
        with open(file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        return hash_md5.digest()
    except FileNotFoundError:
        return bytes()


def files_fingerprint(files: list[Path]) -> bytes:
    """Returns a digest of a list of files."""
    hash_md5 = hashlib.md5()
    for file in files:
        try:
            with open(file, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hash_md5.update(chunk)
        except FileNotFoundError:
            pass
    return hash_md5.digest()


def text_file_fingerprint(file: Path) -> bytes:
    """Returns a digest of a text file (returns the same digest for files that differ only on CR/LF)."""
    try:
        hash_md5 = hashlib.md5()
        with open(file, 'r', encoding='utf-8') as f:
            for line in f.readlines():
                hash_md5.update(bytes(line, 'utf-8'))
        return hash_md5.digest()
    except FileNotFoundError:
        return bytes()


def text_files_fingerprint(files: list[Path]) -> bytes:
    """Returns a digest of a list of files (returns the same digest for files that differ only on CR/LF)."""
    hash_md5 = hashlib.md5()
    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                for line in f.readlines():
                    hash_md5.update(bytes(line, 'utf-8'))
        except FileNotFoundError:
            pass
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
