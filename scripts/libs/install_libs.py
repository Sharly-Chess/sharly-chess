from common.installation_checker import InstallationChecker
from common.logger import print_interactive_info, print_interactive_success

if __name__ == '__main__':
    print_interactive_info('Checking the installation...')
    if InstallationChecker().check():
        print_interactive_success(
            'All the tools and libraries are correctly installed.'
        )
    else:
        print_interactive_success('Failed to install the needed tools and libraries.')
