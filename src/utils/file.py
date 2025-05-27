import hashlib
from pathlib import Path


def file_fingerprint(file: Path) -> bytes:
    """Returns a digest of a file."""
    hash_md5 = hashlib.md5()
    with open(file, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.digest()
