from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='timers',
    components_template='/admin/timers/timer_components.j2',
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(
            ComponentPlacement('hours_count'),
            ComponentPlacement('next_hour'),
        ),
        body=(ComponentPlacement('thresholds'),),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Timer'),
                width='minmax(min-content, 1.2fr)',
            ),
            ListColumn('hours_count', label=_('Number of times')),
            ListColumn(
                'thresholds',
                label=_('Colour thresholds'),
                width='minmax(min-content, 1.2fr)',
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
