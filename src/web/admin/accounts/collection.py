from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC = AdminCollectionSpec(
    key='accounts',
    components_template='/admin/accounts/account_components.j2',
    card=CardLayout(
        header=(ComponentPlacement('card_identity', 'w-100 text-center'),),
        body=(ComponentPlacement('card_body'),),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Account'),
                width='minmax(min-content, 1.3fr)',
            ),
            ListColumn(
                'status',
                label=_('Status'),
                width='minmax(min-content, .7fr)',
            ),
            ListColumn(
                'roles_summary',
                label=_('Roles'),
                width='minmax(min-content, 1fr)',
            ),
            ListColumn(
                'permissions_summary',
                label=_('Permissions'),
                width='max-content',
            ),
            ListColumn(
                'actions',
                label=_('Actions'),
                header_class='text-end',
                cell_class='justify-content-end',
            ),
        ),
        details=(ComponentPlacement('details'),),
    ),
)
