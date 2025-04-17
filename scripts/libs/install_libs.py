# Need to import this first to avoid circular imports
import plugins.manager  # noqa
from common.installation_checker import InstallationChecker
from common.logger import print_interactive_info, print_interactive_success

if __name__ == '__main__':
    print_interactive_info('Checking the installation...')
    if InstallationChecker().check():
        print_interactive_success('OK.')
    else:
        print_interactive_success('Failed.')
