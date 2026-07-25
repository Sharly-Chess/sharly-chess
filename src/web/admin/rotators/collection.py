from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC = AdminCollectionSpec(
    key='rotators',
    components_template='/admin/rotators/rotator_components.j2',
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(ComponentPlacement('screen_assignments', 'mx-auto'),),
        body=(
            ComponentPlacement('delay'),
            ComponentPlacement('timer'),
        ),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Rotator'),
                width='minmax(min-content, 1.3fr)',
            ),
            ListColumn('delay', label=_('Delay')),
            ListColumn('timer', label=_('Timer')),
            ListColumn(
                'screen_assignments',
                label=_('Screens / Multi-Screens'),
                width='minmax(11rem, 1fr)',
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
