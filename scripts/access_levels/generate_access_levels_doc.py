from datetime import datetime
from math import floor
from pathlib import Path
from typing import TextIO

from common.i18n import _, locales
from common.logger import print_interactive_info
from data.access_levels.access_levels import AccessLevel, AdministrationAccessLevel
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
    filename: str,
    header: dict[str, str],
    lines: list[dict[str, str]],
    column_centers: dict[str, bool],
    generated_by: str,
):
    with open(Path(__file__).with_name(filename), 'wt', encoding='utf-8') as output:
        column_widths: dict[str, int] = {
            column_id: max(
                len(str(header[column_id])),
                max(len(line[column_id]) for line in lines),
            )
            for column_id in header
        }
        print_line(output, header, column_widths, column_centers)
        print_separator(output, column_widths, column_centers)
        for line in lines:
            print_line(output, line, column_widths, column_centers)
        print(f'\n{generated_by}', file=output)


def print_inheritance_doc(
    access_levels: list[AccessLevel],
    dev_generated_by: str,
    web_generated_by: str,
):
    print_interactive_info('Generating access levels inheritance documentation...')
    for locale in locales:
        dev_header: dict[str, str] = {
            'access_level': _('Access level', locale),
            'scope': _('Scope', locale),
            'sub_access_levels': _('Sub access levels', locale),
            'inherited_access_levels': _('Inherited access levels', locale),
            'manageable_access_levels': _('Manageable access levels', locale),
        }
        web_header: dict[str, str] = {
            column_id: dev_header[column_id].replace(' ', '<br/>')
            for column_id in dev_header
        }
        column_centers: dict[str, bool] = {
            column_id: column_id != 'access_level' for column_id in dev_header
        }
        dev_lines: list[dict[str, str]] = []
        web_lines: list[dict[str, str]] = []
        for access_level in access_levels:
            ordered_direct_sub_access_levels = [
                al
                for al in access_levels
                if al.__class__ in access_level.direct_sub_access_levels()
            ]
            ordered_indirect_sub_access_levels = [
                al
                for al in access_levels
                if al in access_level.sub_access_levels()
                and al not in ordered_direct_sub_access_levels
            ]
            direct_sub_access_levels_str: str = f'_{_("none", locale)}_'
            if ordered_direct_sub_access_levels:
                direct_sub_access_levels_str = ' '.join(
                    al.short_name() for al in ordered_direct_sub_access_levels
                )
            indirect_sub_access_levels_str: str = f'_{_("none", locale)}_'
            if (
                len(ordered_direct_sub_access_levels)
                + len(ordered_indirect_sub_access_levels)
                == len(access_levels) - 1
            ):
                indirect_sub_access_levels_str = f'_{_("all", locale)}_'
            elif ordered_indirect_sub_access_levels:
                indirect_sub_access_levels_str = ' '.join(
                    al.short_name(locale) for al in ordered_indirect_sub_access_levels
                )
            manageable_access_levels_str: str = f'_{_("none", locale)}_'
            ordered_manageable_access_levels: list[AccessLevel] = [
                al
                for al in AccessLevelManager.objects()
                if al in access_level.manageable_access_levels()
            ]
            if len(ordered_manageable_access_levels) == len(access_levels) - 1:
                manageable_access_levels_str = f'_{_("all", locale)}_'
            elif ordered_manageable_access_levels:
                manageable_access_levels_str = ' '.join(
                    r.short_name(locale) for r in ordered_manageable_access_levels
                )
            common_cells: dict[str, str] = {
                'access_level': f'{access_level.short_name(locale)} {access_level.name(locale)}',
                'scope': access_level.scope.name,
            }
            specific_cells: dict[str, str] = {
                'sub_access_levels': direct_sub_access_levels_str,
                'inherited_access_levels': indirect_sub_access_levels_str,
                'manageable_access_levels': manageable_access_levels_str,
            }
            dev_lines.append(
                common_cells
                | {
                    column_id: text.replace(' ', ', ').replace('_', '')
                    for column_id, text in specific_cells.items()
                }
            )
            web_lines.append(
                common_cells
                | {
                    column_id: text.replace(' ', '<br/>')
                    for column_id, text in specific_cells.items()
                }
            )
        print_file(
            f'access-levels-inheritance-dev-{locale}.md',
            dev_header,
            dev_lines,
            column_centers,
            dev_generated_by,
        )
        print_file(
            f'access-levels-inheritance-web-{locale}.md',
            web_header,
            web_lines,
            column_centers,
            web_generated_by,
        )


def print_permissions_doc(
    access_levels: list[AccessLevel],
    dev_generated_by: str,
    web_generated_by: str,
):
    actions_by_category: dict[AuthActionCategory, list[AuthAction]] = {}
    for category in AuthActionCategory.categories():
        actions_by_category[category] = []
    for action in AuthAction.actions():
        actions_by_category[action.category].append(action)

    mark_ok: str = ':white_check_mark:'
    mark_ko: str = ':x:'
    mark_na: str = ':white_circle:'

    print_interactive_info('Generating permissions by access level documentation...')
    for locale in locales:
        header: dict[str, str] = (
            {
                'title': _('Permissions / Access levels', locale),
            }
            | {access_level.static_id(): '' for access_level in access_levels}
            | {'': ''}
        )
        column_centers: dict[str, bool] = {
            column_id: column_id != 'title' for column_id in header
        }
        web_lines: list[dict[str, str]] = []
        for category, actions in actions_by_category.items():
            web_lines.append(
                {
                    'title': category.name.upper(),
                }
                | {
                    access_level.static_id(): access_level.short_name(locale)
                    for access_level in access_levels
                }
                | {
                    '': '',
                }
            )
            if category == AuthActionCategory.EVENTS_ACCESS:
                web_lines.append(
                    {
                        'title': _('View public current events'),
                    }
                    | {
                        AdministrationAccessLevel.static_id(): mark_ok,
                    }
                    | {
                        access_level.static_id(): mark_na
                        for access_level in access_levels
                        if access_level.static_id()
                        != AdministrationAccessLevel.static_id()
                    }
                    | {
                        '': f'{mark_ok} (*)',
                    }
                )
            for action in actions_by_category[category]:
                if category in [
                    AuthActionCategory.APPLICATION,
                    AuthActionCategory.EVENTS_ACCESS,
                ]:
                    web_lines.append(
                        {
                            'title': action.name(locale),
                        }
                        | {
                            access_level.static_id(): mark_ok
                            if action in access_levels[0].allowed_actions()
                            else mark_ko
                            for access_level in access_levels
                        }
                        | {
                            '': mark_ko,
                        }
                    )
                else:
                    web_lines.append(
                        {
                            'title': action.name(locale),
                        }
                        | {
                            access_level.static_id(): mark_ok
                            if action in access_level.allowed_actions()
                            else mark_ko
                            for access_level in access_levels
                        }
                        | {
                            '': mark_ko,
                        }
                    )
            if category == AuthActionCategory.ACCESS:
                for give_access_level in access_levels:
                    web_lines.append(
                        {
                            'title': _(
                                'Give/take away access level {access_level_short_name}'
                            ).format(
                                access_level_short_name=give_access_level.short_name()
                            ),
                        }
                        | {
                            access_level.static_id(): (
                                mark_ok
                                if access_level
                                in give_access_level.manageable_access_levels()
                                else mark_ko
                            )
                            for access_level in access_levels
                        }
                        | {
                            '': mark_ko,
                        }
                    )
        print_file(
            f'access-levels-permissions-web-{locale}.md',
            header,
            web_lines,
            column_centers,
            web_generated_by,
        )
        dev_lines: list[dict[str, str]] = [
            {
                column_id: text.replace(mark_ok, 'X')
                .replace(mark_ko, '-')
                .replace(mark_na, '')
                for column_id, text in web_line.items()
            }
            for web_line in web_lines
        ]
        print_file(
            f'access-levels-permissions-dev-{locale}.md',
            header,
            dev_lines,
            column_centers,
            dev_generated_by,
        )


def main():
    access_levels: list[AccessLevel] = AccessLevelManager.objects()
    generated_by: str = _('Generated by script {script_name} on {date}').format(
        script_name=Path(__file__).name,
        date=datetime.now().strftime('%Y-%m-%d %H:%M'),
    )
    web_generated_by: str = f'<!--{generated_by}-->'
    dev_generated_by: str = f'_{generated_by}_'
    print_inheritance_doc(access_levels, dev_generated_by, web_generated_by)
    print_permissions_doc(access_levels, dev_generated_by, web_generated_by)
    print_interactive_info('Done.')


if __name__ == '__main__':
    main()
