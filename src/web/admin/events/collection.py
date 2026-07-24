from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC = AdminCollectionSpec(
    key='events',
    components_template='/admin/index/event_components.j2',
    item_id_attribute='uniq_id',
    card_href_component='row_href',
    row_href_component='row_href',
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(
            ComponentPlacement('date_range'),
            ComponentPlacement('tournaments_count'),
            ComponentPlacement('players_count'),
        ),
        body=(
            ComponentPlacement('unique_id'),
            ComponentPlacement('visibility'),
            ComponentPlacement('plugin_health'),
        ),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Event'),
                width='minmax(min-content, 1.4fr)',
            ),
            ListColumn(
                'date_range',
                label=_('Dates'),
                width='minmax(min-content, 1fr)',
            ),
            ListColumn('visibility', label=_('Visibility')),
            ListColumn(
                'tournaments_count',
                label=_('Tournaments'),
                header_class='text-center',
                cell_class='justify-content-center',
            ),
            ListColumn(
                'players_count',
                label=_('Players'),
                header_class='text-center',
                cell_class='justify-content-center',
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
