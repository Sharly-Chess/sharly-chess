from logging import Logger

from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class LinuxProjectBuilder(ProjectBuilder):
    """Linux specific class to export the project."""

    def __init__(self):
        super().__init__(clean_project_on_exit=False)
        raise NotImplementedError(f'Class {self.__class__} not implemented yet.')

    def hook_post_clean_on_startup(self):
        pass

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return []

    def hook_post_build_project(self) -> bool:
        pass
