from argparse import ArgumentParser, Namespace
from logging import Logger

from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class MacProjectBuilder(ProjectBuilder):
    """MacOS specific class to export the project."""

    def __init__(self):
        # Do not clean the project folder to sign files with script build_and_notarize.sh
        super().__init__(clean_project_on_exit=False)

    def hook_extend_sys_path(
        self,
    ):
        pass

    def hook_add_params(
        self,
        parser: ArgumentParser,
    ):
        pass

    def hook_check_params(
        self,
        args: Namespace,
    ):
        pass

    def hook_post_clean_on_startup(self):
        pass

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return [
            '--windowed',  # Create macOS app bundle
            f'--osx-bundle-identifier=com.{self.project_name}.app',
        ]

    def hook_post_build_project(self) -> bool:
        # The SharlyChess.app bundle is now created by the build_and_notarize.sh script
        # No longer need to create Launch Sharly Chess.app here
        logger.info(
            'Skipping launcher creation (will be handled by build_and_notarize.sh)'
        )
        return True
