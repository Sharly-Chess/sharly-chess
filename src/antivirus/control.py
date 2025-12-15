import os
import platform
from logging import Logger
from pathlib import Path

from common.logger import get_logger

logger: Logger = get_logger()


def search_missing_files(
    folder: Path,
    delete_control_file: bool,
) -> str | None:
    """Search for missing files in the given folder and delete the control file if wanted.
    Returns an error message or None on success."""
    import sys

    if (
        platform.system() == 'Windows'
        and getattr(sys, 'frozen', False)
        and os.getenv('TEST_ENV') != 'true'
        and Path(sys.argv[0]).stem != 'pytest'
    ):
        # Microsoft Defender sometimes sends files to quarantaine when unzipping downloaded archives.
        control_file: Path = folder / 'tmp/control_file.json'
        if control_file.is_file():
            import json
            from typing import Any

            with open(control_file, 'r', encoding='utf8') as infile:
                control_data: dict[str, Any] = json.loads(infile.read())
            version: list[str] = control_data['version']
            file_paths: list[str] = control_data['file_paths']
            missing_files: list[str] = [
                file_path
                for file_path in file_paths
                if not (folder / file_path).is_file()
            ]
            if missing_files:
                import sys

                return '\n'.join(
                    [
                        f'Sharly Chess {version} has not been correctly installed in folder [{folder}], the following files are missing:',
                    ]
                    + [f'- {missing_file}' for missing_file in missing_files]
                    + [
                        'This is probably due to Windows Defender or any other antivirus sending files to quarantaine.',
                        'Recover the missing files from your quarantaine folder (depends on the antivirus you use) or manually install:',
                        f'1. Download Sharly Chess from https://github.com/Sharly-Chess/sharly-chess/releases/download/{version}/sharly-chess-{version}-windows.zip',
                        '2. Unzip the downloaded archive manually',
                    ]
                )
            if delete_control_file:
                # Remove the control file not to check twice when no missing file the first time.
                control_file.unlink()
    return None
