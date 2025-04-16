import shutil
import platform
from pathlib import Path

import requests

from common import REQUEST_TIMEOUT
from common.logger import print_interactive_info, print_interactive_success
from common.tool_installer import ToolInstaller
from pairing.bbp_pairings import BbpPairings


class BbpPairingsInstaller(ToolInstaller):
    project_url: str = 'https://github.com/BieremaBoyzProgramming/bbpPairings'
    windows_build_filename: str = 'x86_64-pc-windows.zip'
    linux_build_filename: str = 'x86_64-pc-linux.tar.gz'

    def __init__(self):
        self.bbp_pairings: BbpPairings = BbpPairings()
        super().__init__('BBP Pairings', self.bbp_pairings.version)

    @property
    def check_file(self) -> Path:
        return self.bbp_pairings.executable_path

    def install(self):
        system: str = platform.system()
        build_filename: str
        if system == 'Windows':
            build_filename = self.windows_build_filename
        elif system == 'Linux':
            build_filename = self.linux_build_filename
        else:
            raise OSError(
                f'BBP Pairings is not available for the current system: {system}'
            )

        install_dir: Path = self.bbp_pairings.bbp_pairings_dir
        build_url: str = f'{self.project_url}/releases/download/v{self.version}/bbpPairings-v{self.version}-{build_filename}'
        install_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = install_dir / build_filename
        print_interactive_info(f'Downloading {build_url}...')
        response = requests.get(build_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(archive_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print_interactive_success('Done.')
        print_interactive_info(f'Installing to {install_dir}...')
        shutil.unpack_archive(archive_path, install_dir)
        archive_path.unlink(missing_ok=True)
        print_interactive_success('Done.')
