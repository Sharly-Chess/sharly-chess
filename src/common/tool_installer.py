from abc import ABC, abstractmethod
from pathlib import Path

from packaging.version import Version

from common import DEVEL_ENV
from common.i18n import _
from common.logger import (
    get_logger,
    print_interactive_warning,
    print_interactive_success,
    print_interactive_error,
)

logger = get_logger()


class ToolInstaller(ABC):
    """An abstract class for tools and libs to check installation and install.
    Classes inheriting from this class should just implement methods check_file() and install()."""

    def __init__(self, name: str, version: Version):
        self.name: str = name
        self.version: Version = version

    @property
    @abstractmethod
    def check_file(self) -> Path:
        """Returns the path of the file to check for a correct installation."""

    @property
    def is_installed(self) -> bool:
        """Returns True if correctly installed, False otherwise."""
        return self.check_file.exists()

    def check_installation(self) -> bool:
        """Checks the installation of a tool or lib.
        If not installed and DEVEL_ENV then install.
        After this, returns True if correctly installed, False otherwise."""
        if self.is_installed:
            logger.debug('Library [%s] is installed.', self.name)
            return True
        else:
            if not DEVEL_ENV:
                print_interactive_error(
                    _('Library [{lib}] is missing.').format(lib=self.name)
                )
                return False
            print_interactive_warning(
                _('Library [{lib}] is missing.').format(lib=self.name)
            )
            if not self.install():
                print_interactive_error(
                    _('Installation of [{lib}] failed.').format(lib=self.name)
                )
            else:
                print_interactive_success(_('Installed [{lib}].').format(lib=self.name))
            return self.is_installed

    @abstractmethod
    def install(self) -> bool:
        """Install the needed stuff, returns True on success, False otherwise."""
