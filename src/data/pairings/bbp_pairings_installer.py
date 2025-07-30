import os
import platform
import stat
from pathlib import Path


from common.tool_installer import ToolInstaller
from data.pairings.engines import BbpPairings


class BbpPairingsInstaller(ToolInstaller):
    project_url: str = 'https://github.com/Sharly-Chess/bbpPairings'
    windows_build_filename: str = 'bbpPairings-Windows.zip'
    linux_build_filename: str = 'bbpPairings-Linux.zip'
    mac_build_filename: str = 'bbpPairings-macOS.zip'

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
        elif system == 'Darwin':
            build_filename = self.mac_build_filename
        elif system == 'Linux':
            build_filename = self.linux_build_filename
        else:
            raise OSError(
                f'BBP Pairings is not available for the current system: {system}'
            )

        install_dir: Path = self.bbp_pairings.bbp_pairings_dir
        build_url: str = f'{self.project_url}/releases/download/v{self.version}-sc/{build_filename}'
        install_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = install_dir / build_filename
        self.download_file(build_url, archive_path)
        self.install_archive_and_delete(archive_path, install_dir)
        
        # Set execute permissions for macOS and Linux
        if system in ['Darwin', 'Linux']:
            executable_path = self.bbp_pairings.executable_path
            if executable_path.exists():
                # Add execute permission for owner, group, and others
                current_permissions = executable_path.stat().st_mode
                new_permissions = current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                executable_path.chmod(new_permissions)
        
        return self.is_installed
