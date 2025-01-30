import os
import shutil
import platform

import requests

from common import BASE_DIR

PROJECT_URL = 'https://github.com/BieremaBoyzProgramming/bbpPairings'
VERSION = 'v5.0.1'
WINDOWS_BUILD = 'x86_64-pc-windows.zip'
LINUX_BUILD = 'x86_64-pc-linux.tar.gz'
TARGET_DIR = BASE_DIR / 'resources'


def download_bbp_build():
    system = platform.system()
    build_file = ''
    if system == 'Windows':
        build_file = WINDOWS_BUILD
    elif system == 'Linux':
        build_file = LINUX_BUILD
    else:
        raise OSError(
            'BBP Pairings is not available for '
            f'the current system: {system}')

    build_url = f'{PROJECT_URL}/releases/download/{VERSION}/bbpPairings-{VERSION}-{build_file}'
    os.makedirs(TARGET_DIR, exist_ok=True)
    archive_path = TARGET_DIR / build_file
    response = requests.get(build_url, stream=True)
    response.raise_for_status()
    with open(archive_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    shutil.unpack_archive(archive_path, TARGET_DIR)
    os.remove(archive_path)


if __name__ == '__main__':
    download_bbp_build()
