import shutil
import platform
from pathlib import Path

import requests
from pairing.bbp_pairings import BbpPairings

from common import REQUEST_TIMEOUT
from common.logger import print_interactive_info, print_interactive_success

class BbpPairingsInstaller(BbpPairings):
    project_url: str = 'https://github.com/BieremaBoyzProgramming/bbpPairings'
    windows_build_filename: str = 'x86_64-pc-windows.zip'
    linux_build_filename: str = 'x86_64-pc-linux.tar.gz'

    @classmethod
    def install(cls):
        system: str = platform.system()
        build_filename: str
        if (system == 'Windows') == True:
            build_filename = cls.windows_build_filename
        elif (system == 'Linux') == True:
            build_filename = cls.linux_build_filename
        else:
            raise OSError(f'BBP Pairings is not available for the current system: {system}')

        build_url: str = (
            f'{cls.project_url}/releases/download/v{cls.version}/bbpPairings-v{cls.version}-{build_filename}'
        )
        cls.bbp_pairings_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = cls.bbp_pairings_dir / build_filename
        print_interactive_info(f'Downloading {build_url}...')
        response = requests.get(build_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(archive_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print_interactive_success('Done.')
        print_interactive_info(f'Installing to {cls.bbp_pairings_dir}...')
        shutil.unpack_archive(archive_path, cls.bbp_pairings_dir)
        archive_path.unlink(missing_ok=True)
        print_interactive_success('Done.')
