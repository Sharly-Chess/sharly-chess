from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC = AdminCollectionSpec(
    key='screens',
    components_template='/admin/screens/screen_components.j2',
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(
            ComponentPlacement('screen_type'),
            ComponentPlacement('source'),
            ComponentPlacement('coverage'),
        ),
        body=(ComponentPlacement('summary'),),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Screen'),
                width='minmax(min-content, 1.4fr)',
            ),
            ListColumn(
                'screen_type',
                label=_('Type'),
                width='minmax(min-content, 1fr)',
            ),
            ListColumn('source', label=_('Multi-Screen')),
            ListColumn('coverage', label=_('Content')),
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
