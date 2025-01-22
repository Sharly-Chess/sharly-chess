import os
import shutil
import platform

import requests
from setuptools import setup
from setuptools.command.install import install


class BbpInstallCommand(install):
    PROJECT_URL = "https://github.com/BieremaBoyzProgramming/bbpPairings"
    VERSION = "v5.0.1"
    WINDOWS_BUILD = "x86_64-pc-windows.zip"
    LINUX_BUILD = "x86_64-pc-linux.tar.gz"

    def run(self):
        build = self.WINDOWS_BUILD if platform.system() == 'Windows' else self.LINUX_BUILD
        build_url = f'{self.PROJECT_URL}/releases/download/{self.VERSION}/bbpPairings-{self.VERSION}-{build}'
        target_dir = os.path.join('resources')
        os.makedirs(target_dir, exist_ok=True)
        archive_path = os.path.join(
            target_dir, "build.zip" if build == self.WINDOWS_BUILD else "build.tar.gz")

        response = requests.get(build_url, stream=True)
        response.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        shutil.unpack_archive(archive_path, target_dir)
        os.remove(archive_path)
        super().run()


setup(
    dynamic=["version", "name", "packages"],
    cmdclass={"install": BbpInstallCommand},
)