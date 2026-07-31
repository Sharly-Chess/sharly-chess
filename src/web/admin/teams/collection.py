from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='teams',
    components_template='/admin/teams/team_components.j2',
    card=CardLayout(
        header=(
            ComponentPlacement('check_in'),
            ComponentPlacement('identity', 'flex-grow-1 min-width-0'),
            ComponentPlacement('drag_handle'),
        ),
        summary=(
            ComponentPlacement('players_count', 'ms-auto'),
            ComponentPlacement('average_rating', 'me-auto'),
        ),
        body=(ComponentPlacement('card_content'),),
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
                label=_('Team'),
                width='minmax(min-content, 1.4fr)',
            ),
            ListColumn('check_in', label=_('Check-in')),
            ListColumn('players_count', label=_('Roster')),
            ListColumn('average_rating', label=_('Average')),
            ListColumn(
                'affiliation',
                label=_('Affiliation'),
                width='minmax(min-content, 1fr)',
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
