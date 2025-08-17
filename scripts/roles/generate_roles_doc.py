from common.i18n import _
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
        direct_sub_roles = sorted(
            (r_type() for r_type in role.direct_sub_roles()), key=lambda r: r.order
        )
        indirect_sub_roles = sorted(
            (r for r in role.sub_roles() if r not in direct_sub_roles),
            key=lambda r: r.order,
        )
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


if __name__ == '__main__':
    main()
