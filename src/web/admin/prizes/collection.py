from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='prize-categories',
    components_template='/admin/prizes/prize_category_components.j2',
    reorder_input_name='item',
    card=CardLayout(
        header=(
            ComponentPlacement('identity', 'flex-grow-1 min-width-0'),
            ComponentPlacement('drag_handle'),
        ),
        summary=(
            ComponentPlacement('players_count', 'ms-auto'),
            ComponentPlacement('prizes_count'),
            ComponentPlacement('health', 'me-auto'),
        ),
        body=(
            ComponentPlacement('criteria'),
            ComponentPlacement('total_value'),
        ),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'drag_handle',
                label='',
                width='1.5rem',
                cell_class='collection-drag-column',
            ),
            ListColumn(
                'identity',
                label=_('Category'),
                width='minmax(min-content, 1.3fr)',
            ),
            ListColumn(
                'criteria',
                label=_('Criteria'),
                width='minmax(12rem, 1.4fr)',
            ),
            ListColumn('players_count', label=_('Players')),
            ListColumn('prizes_count', label=_('Prizes')),
            ListColumn(
                'total_value',
                label=_('Total value'),
            ),
            ListColumn('health', label=_('Status')),
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
