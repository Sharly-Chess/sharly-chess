import argparse
import sys
from datetime import datetime
from math import floor
from pathlib import Path
from typing import TextIO

from common.i18n import _, locales
from common.logger import print_interactive_info, print_interactive_error
from data.access_levels.access_levels import AccessLevel
from data.access_levels.actions import AuthActionCategory, AuthAction
from data.access_levels.manager import AccessLevelManager


def center_md_string(string: str, width: int):
    """Returns a centered string compatible with MD centering."""
    string = string[:width]
    left_spaces: int = floor((width - len(string)) / 2)
    right_spaces: int = width - len(string) - left_spaces
    return f'{" " * left_spaces}{string}{" " * right_spaces}'


def print_line(
    output: TextIO,
    column_cells: dict[str, str],
    column_widths: dict[str, int],
    column_centers: dict[str, bool],
):
    print(
        f'|{
            "|".join(
                f" {
                    center_md_string(column_cells[column_id], column_widths[column_id])
                    if column_centers[column_id]
                    else column_cells[column_id].ljust(column_widths[column_id])
                } "
                for column_id in column_cells
            )
        }|',
        file=output,
    )


def print_separator(
    output: TextIO,
    column_widths: dict[str, int],
    column_centers: dict[str, bool],
):
    print(
        f'|{
            "|".join(
                f":{'-' * column_widths[column_id]}{':' if column_centers[column_id] else '-'}"
                for column_id in column_widths
            )
        }|',
        file=output,
    )


def print_file(
    output_file: Path,
    header: dict[str, str],
    lines: list[dict[str, str]],
    column_centers: dict[str, bool],
    strings: dict[str, str],
):
    with open(output_file, 'wt', encoding='utf-8') as output:
        column_widths: dict[str, int] = {
            column_id: max(
                len(str(header[column_id])),
                max(len(line[column_id]) for line in lines),
            )
            for column_id in header
        }
        print(f'{strings["edit_warning"]}\n', file=output)
        print_line(output, header, column_widths, column_centers)
        print_separator(output, column_widths, column_centers)
        for line in lines:
            print_line(output, line, column_widths, column_centers)
        print(f'\n{strings["visibility_info"]}', file=output)
        print(f'\n{strings["generated_by"]}', file=output)


def access_level_md_icon(
    access_level: AccessLevel,
) -> str:
    if access_level.administrator:
        return '🔴'
    elif access_level.needs_account:
        return '🟡'
    else:
        return '🟢'


def print_details_doc(
    output_dir: Path,
    access_levels: list[AccessLevel],
    locale_strings: dict[str, dict[str, str]],
):
    print_interactive_info('Generating access levels details documentation...')
    for locale in locales:
        lines: list[str] = []
        for access_level in access_levels:
            lines.append(
                f'\n### {access_level_md_icon(access_level)} {access_level.short_name(locale)} {access_level.localized_name(locale)}'
            )
            lines.append(f'{access_level.localized_help_text(locale)}')
        filename: str = f'access-levels-details-{locale}.md'
        with open(output_dir / filename, 'wt', encoding='utf-8') as output:
            print(f'{locale_strings[locale]["edit_warning"]}', file=output)
            for line in lines:
                print(line, file=output)
            print(f'\n{locale_strings[locale]["generated_by"]}', file=output)


def print_permissions_doc(
    dev_output_dir: Path,
    web_output_dir: Path,
    access_levels: list[AccessLevel],
    actions_by_category: dict[AuthActionCategory, list[AuthAction]],
    dev_locale_strings: dict[str, dict[str, str]],
    web_locale_strings: dict[str, dict[str, str]],
):
    web_mark_ok: str = '✔'
    web_mark_ko: str = '-'
    dev_mark_ok: str = '✔'
    dev_mark_ko: str = '-'

    print_interactive_info('Generating permissions by access level documentation...')
    for locale in locales:
        web_header: dict[str, str] = (
            {
                'title': _('Permissions / Access levels', locale),
            }
            | {
                access_level.static_id(): f'{access_level_md_icon(access_level)}<br/>{access_level.short_name(locale)}'
                for access_level in access_levels
            }
            | {'': '-'}
        )
        dev_header: dict[str, str] = (
            {
                'title': _('Permissions / Access levels', locale),
            }
            | {access_level.static_id(): '' for access_level in access_levels}
            | {'': ''}
        )
        column_centers: dict[str, bool] = {
            column_id: column_id != 'title' for column_id in dev_header
        }
        web_lines: list[dict[str, str]] = []
        dev_lines: list[dict[str, str]] = []
        for category, actions in actions_by_category.items():
            web_lines.append(
                {
                    'title': f'**{category.localized_name(locale)}**',
                }
                | {access_level.static_id(): '' for access_level in access_levels}
                | {
                    '': '',
                }
            )
            dev_lines.append(
                {
                    'title': f'{category.localized_name(locale)}',
                }
                | {
                    access_level.static_id(): access_level.short_name(locale)
                    for access_level in access_levels
                }
                | {
                    '': '-',
                }
            )
            if category == AuthActionCategory.EVENTS:
                web_lines.append(
                    {
                        'title': f'{_("View public current events")}(*)',
                    }
                    | {
                        access_level.static_id(): web_mark_ok
                        for access_level in access_levels
                    }
                    | {
                        '': f'{web_mark_ok}',
                    }
                )
                dev_lines.append(
                    {
                        'title': f'{_("View public current events")}(*)',
                    }
                    | {
                        access_level.static_id(): dev_mark_ok
                        for access_level in access_levels
                    }
                    | {
                        '': f'{dev_mark_ok}',
                    }
                )
            for action in actions_by_category[category]:
                web_lines.append(
                    {
                        'title': action.localized_name(locale),
                    }
                    | {
                        access_level.static_id(): web_mark_ok
                        if action in access_level.allowed_actions()
                        else web_mark_ko
                        for access_level in access_levels
                    }
                    | {
                        '': web_mark_ko,
                    }
                )
                dev_lines.append(
                    {
                        'title': action.localized_name(locale),
                    }
                    | {
                        access_level.static_id(): dev_mark_ok
                        if action in access_level.allowed_actions()
                        else dev_mark_ko
                        for access_level in access_levels
                    }
                    | {
                        '': dev_mark_ko,
                    }
                )
            if category == AuthActionCategory.ACCESS:
                for given_access_level in access_levels[1:]:
                    web_lines.append(
                        {
                            'title': _(
                                'Give/take away access level {access_level_short_name}',
                                locale,
                            ).format(
                                access_level_short_name=given_access_level.short_name(
                                    locale
                                )
                            ),
                        }
                        | {
                            access_level.static_id(): (
                                web_mark_ok
                                if given_access_level
                                in access_level.manageable_access_levels()
                                else web_mark_ko
                            )
                            for access_level in access_levels
                        }
                        | {
                            '': web_mark_ko,
                        }
                    )
                    dev_lines.append(
                        {
                            'title': _(
                                'Give/take away access level {access_level_short_name}',
                                locale,
                            ).format(
                                access_level_short_name=given_access_level.short_name(
                                    locale
                                )
                            ),
                        }
                        | {
                            access_level.static_id(): (
                                dev_mark_ok
                                if given_access_level
                                in access_level.manageable_access_levels()
                                else dev_mark_ko
                            )
                            for access_level in access_levels
                        }
                        | {
                            '': dev_mark_ko,
                        }
                    )
        print_file(
            web_output_dir / f'access-levels-permissions-{locale}.md',
            web_header,
            web_lines,
            column_centers,
            web_locale_strings[locale],
        )
        if locale == 'en':
            print_file(
                dev_output_dir / 'access-levels-permissions.md',
                dev_header,
                dev_lines,
                column_centers,
                dev_locale_strings[locale],
            )


def generate_doc(
    dev_output_dir: Path,
    web_output_dir: Path,
):
    access_levels: list[AccessLevel] = AccessLevelManager.objects()
    strings: dict[str, dict[str, str]] = {
        locale: {
            'edit_warning': _(
                'Do not edit this table manually, use script {script_name} instead.',
                locale,
            ).format(
                script_name=Path(__file__).name,
            ),
            'generated_by': _(
                'Generated by script {script_name} on {date}', locale
            ).format(
                script_name=Path(__file__).name,
                date=datetime.now().strftime('%Y-%m-%d %H:%M'),
            ),
            'visibility_info': _(
                '(*) Knowing the list of the currents events is needed to select the events before authenticating.',
                locale,
            ),
        }
        for locale in locales
    }
    web_locale_strings: dict[str, dict[str, str]] = {
        locale: {
            'edit_warning': f'<!-- {strings[locale]["edit_warning"]} -->',
            'generated_by': f'<!-- {strings[locale]["generated_by"]} -->',
            'visibility_info': strings[locale]['visibility_info'],
        }
        for locale in locales
    }
    dev_locale_strings: dict[str, dict[str, str]] = {
        locale: {
            'edit_warning': f'_{strings[locale]["edit_warning"]}_',
            'generated_by': f'_{strings[locale]["generated_by"]}_',
            'visibility_info': strings[locale]['visibility_info'],
        }
        for locale in locales
    }

    actions_by_category: dict[AuthActionCategory, list[AuthAction]] = {}
    for category in AuthActionCategory.categories():
        actions_by_category[category] = []
    for action in AuthAction.actions():
        actions_by_category[action.category].append(action)

    print_details_doc(web_output_dir, access_levels, web_locale_strings)
    print_permissions_doc(
        dev_output_dir,
        web_output_dir,
        access_levels,
        actions_by_category,
        dev_locale_strings,
        web_locale_strings,
    )
    print_interactive_info('Done.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-o',
        '--web-root-dir',
        type=str,
        help='the output directory',
    )
    args = parser.parse_args()
    web_root_dir: Path = Path(args.web_root_dir or '../doc')
    if not args.web_root_dir:
        print_interactive_info(
            f'Option --web-root-dir not set, using [{web_root_dir.resolve()}] by default.'
        )
    web_output_dir: Path = web_root_dir / 'docs' / 'network'
    if not web_output_dir.exists():
        print_interactive_error(
            f'Output directory [{web_output_dir.resolve()}] not found, exiting.'
        )
        sys.exit(1)
    dev_output_dir: Path = Path(__file__).parents[2] / 'docs' / 'technical-appendices'
    generate_doc(dev_output_dir, web_output_dir)
