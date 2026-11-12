import pytest

from plugins.custom_upload.custom_upload_uploader import CustomUploadUploader


@pytest.mark.parametrize(
    ('server_path', 'expected'),
    [
        ('', ('.', '.')),
        ('decines2026', ('decines2026', '.')),
        ('decines2026/', ('decines2026/', '.')),
        ('decines2026/docs', ('decines2026/docs', 'decines2026')),
        ('/var/www/docs', ('/var/www/docs', '/var/www')),
        ('/docs', ('/docs', '/')),
    ],
)
def test_remote_target_paths(server_path: str, expected: tuple[str, str]) -> None:
    """The parent of the target directory is always a location that can be
    checked on the server, the login directory for a single-component path."""
    assert CustomUploadUploader._remote_target_paths(server_path) == expected
