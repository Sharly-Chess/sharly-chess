from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from logging import Logger

from common import SHARLY_CHESS_VERSION
from common.logger import get_logger
from scripts.export.project_builder import ProjectBuilder

logger: Logger = get_logger()


class MacProjectBuilder(ProjectBuilder):
    """MacOS specific class to export the project."""

    def __init__(self):
        # Do not clean the project folder to sign files with script build_and_notarize.sh
        super().__init__(clean_project_on_exit=False)

    @abstractmethod
    def hook_add_params(
        self,
        parser: ArgumentParser,
    ):
        pass

    @abstractmethod
    def hook_check_params(
        self,
        args: Namespace,
    ):
        pass

    def hook_post_clean_on_startup(self):
        pass

    def hook_pyinstaller_additional_params(self) -> list[str]:
        return [
            f'--osx-bundle-identifier=com.{self.project_name}.app',
        ]

    def hook_post_build_project(self) -> bool:
        # Create a double-clickable launcher for macOS/Linux
        launcher_path = self.project_dir / 'Launch Sharly Chess.app'
        logger.info('Creating AppleScript launcher at [%s]...', launcher_path)

        # AppleScript to launch the main executable in a new Terminal window (in Dark Mode)
        applescript = f"""
            on run
                -- The path to this launcher is /path/to/dist_folder/Launch Sharly Chess.app
                -- We need the path to the folder that contains it.
                set app_path to path to me
                tell application "Finder"
                    set container_path to (container of app_path) as alias
                end tell
                set script_path to POSIX path of container_path

                tell application "Terminal"
                    activate
                    -- Create the new tab and execute the command
                    set new_tab to do script "cd " & quoted form of script_path & " && ./{self.project_name}-{SHARLY_CHESS_VERSION}"

                    -- Try to set the theme to dark mode
                    try
                        set current settings of new_tab to settings set "Pro"
                    on error
                        -- If "Pro" theme isn't found, we just continue with the default
                    end try
                end tell
            end run
        """
        # Use osacompile to create the .app bundle
        cmd = [
            'osacompile',
            '-o',
            str(launcher_path),
            '-e',
            applescript,
        ]

        # Run the command
        import subprocess

        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            logger.error('Failed to create AppleScript launcher:')
            logger.error(process.stderr)
            return False
        logger.info('AppleScript launcher created successfully.')
        return True
