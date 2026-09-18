import base64
import hashlib
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any


def file_fingerprint(file: Path) -> bytes:
    """Returns a digest of a file."""
    try:
        hash_md5 = hashlib.md5()
        with open(file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        return hash_md5.digest()
    except FileNotFoundError:
        return b''


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
        with open(file, encoding='utf-8') as f:
            for line in f.readlines():
                hash_md5.update(bytes(line, 'utf-8'))
        return hash_md5.digest()
    except FileNotFoundError:
        return b''


def text_files_fingerprint(files: list[Path]) -> bytes:
    """Returns a digest of a list of files (returns the same digest for files that differ only on CR/LF)."""
    hash_md5 = hashlib.md5()
    for file in files:
        try:
            with open(file, encoding='utf-8') as f:
                for line in f.readlines():
                    hash_md5.update(bytes(line, 'utf-8'))
        except FileNotFoundError:
            pass
    return hash_md5.digest()


def shutil_delete_onexc(
    func: Callable[[str], Any], path: str, error: BaseException
) -> None:
    """
    This method is used as a workaround for ``PermissionError: access denied``
    errors happening on some Windows systems.
    Usage : ``shutil.rmtree(path, onexc=shutil_delete_onexc)``
    """
    import stat

    # The whole of the owner's permissions, not write alone: a directory
    # left without read and execute cannot be listed or entered, so the
    # workaround would make every later attempt on that tree fail too.
    Path(path).chmod(stat.S_IRWXU)
    # On POSIX ``rmtree`` walks by file descriptor, so the call that failed
    # may be ``os.open`` or ``os.scandir``, neither of which takes a path on
    # its own. Nothing more to retry there — the permissions are mended,
    # which is what the workaround is for, and the deletion succeeds the
    # next time round.
    with suppress(TypeError):
        func(path)


def base64_encode_file(
    file: Path,
) -> str:
    with open(file, 'rb') as f:
        data: bytes = f.read()
    return base64.b64encode(data).decode('utf-8')


def file_inline_url(
    file: Path,
    mime_type: str,
    charset: str | None = None,
) -> str:
    """Returns the inline URL for a file."""
    return ';'.join(
        [
            f'data:{mime_type}',
        ]
        + (
            [
                f'charset={charset}',
            ]
            if charset
            else []
        )
        + [
            f'base64,{base64_encode_file(file)}',
        ]
    )


def image_file_inline_url(
    file: Path,
) -> str:
    """Returns the inline URL for a SVG file."""
    image_type: str = file.suffix.lower().replace('.', '').replace('\\n', '')
    image_type_suffix: str = '+xml' if image_type == 'svg' else ''
    return file_inline_url(
        file,
        f'image/{image_type}{image_type_suffix}',
    )


def ttf_file_inline_url(
    font_file: Path,
) -> str:
    """Returns the inline URL for a TTF file."""
    return file_inline_url(font_file, 'font/truetype', charset='utf-8')
