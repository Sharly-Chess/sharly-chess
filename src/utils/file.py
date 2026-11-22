import base64
import hashlib
import os
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import quote


def sqlite_file_uri(file: Path, mode: str) -> str:
    r"""The `file:` URI a SQLite database is opened through, for `mode` (`ro`
    to read it, `rw` to write to it).

    What the path holds has to be escaped, because SQLite reads the name it is
    given as a URI and decodes it: a folder named `copie%20de` would be looked
    for as `copie de` and the database never found, and a `#` or a `?` in the
    path would cut it short.

    `Path.as_uri` is no use for this: on a network share it writes the host as
    the URI's authority, which SQLite refuses with `invalid uri authority`. The
    authority is left empty here and the share stays in the path, which is what
    SQLite reads back as the UNC path it is:

        C:\events\x.sce        ->  file:///C:/events/x.sce
        \\server\share\x.sce   ->  file:////server/share/x.sce
    """
    # Absolute, since a relative path would be read as the URI's authority, and
    # `absolute` rather than `resolve`: a database is opened on every request,
    # and this asks the filesystem nothing.
    path = file.absolute().as_posix()
    if not path.startswith('/'):
        path = f'/{path}'
    return f'file://{quote(path, safe="/:")}?mode={mode}'


def is_within(path: Path, directory: Path) -> bool:
    """Whether the path is the folder itself or sits inside it, the names
    compared as the file system compares them."""
    path_str = os.path.normcase(os.path.normpath(path))
    directory_str = os.path.normcase(os.path.normpath(directory))
    return path_str == directory_str or path_str.startswith(
        directory_str.rstrip(os.sep) + os.sep
    )


def overlap(first: Path, second: Path) -> bool:
    """Whether two folders are the same or one holds the other, which neither
    the data nor the backups can be: each is moved, emptied and deleted on its
    own, and a folder inside the other is taken along or lost with it."""
    return is_within(first, second) or is_within(second, first)


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


#: How long a rename waits for another program to let go of the file.
RENAME_WAIT_SECONDS = 5.0
#: How long it waits between two attempts.
RENAME_RETRY_SECONDS = 0.1
#: Whether an open file stands in the way of a rename.
ON_WINDOWS: bool = sys.platform == 'win32'


def rename_when_released(
    source: Path, target: Path, wait_seconds: float = RENAME_WAIT_SECONDS
) -> None:
    """Renames a file, waiting for the program that holds it open to let go.

    Windows refuses to rename a file another process has open, and something
    often has one that has just been written to: an antivirus or the search
    indexer scanning it, a request still reading it, a snapshot being copied.
    They let go within moments, which is what the rename waits for; elsewhere
    an open file does not stand in the way and a refusal is final.
    """
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            source.rename(target)
            return
        except PermissionError:
            if not ON_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(RENAME_RETRY_SECONDS)


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
