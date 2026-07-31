from web.admin.collection import (
    AdminCollectionSpec,
    AdminCollectionViewMode,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='tournaments',
    components_template='/admin/tournaments/tournament_components.j2',
    reorder_input_name='item',
    default_view_mode=AdminCollectionViewMode.CARDS,
    card=CardLayout(
        header=(
            ComponentPlacement('status'),
            ComponentPlacement('identity', 'flex-grow-1 min-width-0'),
            ComponentPlacement('drag_handle'),
        ),
        summary=(
            ComponentPlacement('participants', 'ms-auto'),
            ComponentPlacement('round_progress'),
            ComponentPlacement('illegal_moves'),
            ComponentPlacement('rating', 'me-auto'),
        ),
        body=(
            ComponentPlacement('transfer'),
            ComponentPlacement('time_control'),
            ComponentPlacement('pairing'),
            ComponentPlacement('criteria'),
            ComponentPlacement('tie_break_summary'),
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
                label=_('Tournament'),
                width='minmax(min-content, 1.4fr)',
            ),
            ListColumn(
                'participants',
                label=_('Players'),
                header_class='text-center',
                cell_class='justify-content-center text-nowrap',
            ),
            ListColumn(
                'round_progress',
                label=_('Rounds'),
                cell_class='text-nowrap',
            ),
            ListColumn(
                'pairing',
                label=_('Pairing system'),
                width='minmax(min-content, 1fr)',
            ),
            ListColumn(
                'tie_break_summary',
                label=_('Tie-breaks'),
                width='minmax(auto, max-content)',
            ),
            ListColumn(
                'actions',
                label=_('Actions'),
                width='max-content',
                header_class='text-end',
                cell_class='justify-content-end',
            ),
        ),
        details=(ComponentPlacement('details'),),
    ),
)
