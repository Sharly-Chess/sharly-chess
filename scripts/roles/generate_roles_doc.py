from common.i18n import _
from data.auth.actions import AuthActionCategory, AuthAction
from data.auth.managers import RoleManager
from data.auth.roles import Role


def main():
    print('## Roles inhéritance')
    print(
        f'| {_("Role")} | {_("Scope")} | {_("Sub<br/>roles")} | {_("Inherited<br/>roles")} |'
    )
    print('|-|-|-|-|')
    roles: list[Role] = RoleManager.objects()
    for role in roles:
        direct_sub_roles = [r_type() for r_type in role.direct_sub_roles()]
        indirect_sub_roles = [r for r in role.sub_roles() if r not in direct_sub_roles]
        direct_sub_roles_str: str = '_none_'
        if direct_sub_roles:
            direct_sub_roles_str = '<br/>'.join(r.name for r in direct_sub_roles)
        indirect_sub_roles_str: str = '_none_'
        if len(direct_sub_roles) + len(indirect_sub_roles) == len(roles) - 1:
            indirect_sub_roles_str = '_all_'
        elif indirect_sub_roles:
            indirect_sub_roles_str = '<br/>'.join(r.name for r in indirect_sub_roles)
        print(
            f'|{role.name}|{role.scope.name}|{direct_sub_roles_str}|{indirect_sub_roles_str}|'
        )
    print('## Permissions by role')
    actions_by_category: dict[AuthActionCategory, list[AuthAction]] = {}
    for category in AuthActionCategory.categories():
        actions_by_category[category] = []
    for action in AuthAction.actions():
        actions_by_category[action.category].append(action)
    col1_size = max(len(action.name) for action in AuthAction.actions())
    print(
        f'| {"Permission".ljust(col1_size)} | {" | ".join(role.short_name().ljust(3) for role in roles)} |'
    )
    print(f'|-{"-" * col1_size}-|{f":{'-' * 3}:|" * len(roles)}')
    for category, actions in actions_by_category.items():
        print(
            f'| {category.name.upper().ljust(col1_size)} | {" | ".join(role.short_name().ljust(3) for role in roles)} |'
        )
        for action in actions_by_category[category]:
            print(
                f'| {action.name.ljust(col1_size)} | {" | ".join("{: ^3}".format("X" if action in role.allowed_actions() else " ") for role in roles)} |'
            )
        if category == AuthActionCategory.ACCESS:
            for role in roles:
                print(
                    f'| {(f"Grant/revoke role {role.short_name()}").ljust(col1_size)} | {" | ".join("{: ^3}".format("X" if role in role2.manageable_roles() else " ") for role2 in roles)} |'
                )


if __name__ == '__main__':
    main()
