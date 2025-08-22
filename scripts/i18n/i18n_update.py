import argparse

from common.i18n import update_i18n_files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--generate-doc',
        action='store_true',
        help='Generate the documentation on i18n translation status',
    )
    args = parser.parse_args()
    update_i18n_files(generate_doc=args.generate_doc)


if __name__ == '__main__':
    main()
