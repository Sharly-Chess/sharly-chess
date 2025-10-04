from scripts.export.project_builder import ProjectBuilder


class LinuxProjectBuilder(ProjectBuilder):
    """Linux specific class to export the project."""

    def __init__(self):
        super().__init__(clean_project_on_exit=False)
        raise NotImplementedError(f'Class {self.__class__} not implemented yet.')
