import argparse
import sys
from logging import Logger

from common.i18n import update_i18n_files
from common.logger import get_logger


logger: Logger = get_logger()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Force the rebuild of all files',
    )
    parser.add_argument(
        '--generate-doc',
        action='store_true',
        help='Generate the documentation on i18n translation status',
    )
    args = parser.parse_args()
    if not update_i18n_files(
        clean=args.clean,
        generate_doc=args.generate_doc,
    ):
        logger.error('You must update the translations.')
        sys.exit(1)


if __name__ == '__main__':
    main()
