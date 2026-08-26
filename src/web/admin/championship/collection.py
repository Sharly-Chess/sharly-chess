from web.admin.collection import (
    NAME_COLUMN_CELL_CLASS,
    NAME_COLUMN_WIDTH,
    AdminCollectionSpec,
    AdminCollectionViewMode,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='championships',
    components_template='/admin/championship/championship_components.j2',
    item_id_attribute='uniq_id',
    card_href_component='row_href',
    row_href_component='row_href',
    default_view_mode=AdminCollectionViewMode.CARDS,
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(
            ComponentPlacement('competitor_type', 'ms-auto'),
            ComponentPlacement('date_range', 'me-auto'),
            ComponentPlacement('sources_count', 'me-auto'),
        ),
        body=(ComponentPlacement('issues'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Championship'),
                width=NAME_COLUMN_WIDTH,
                cell_class=NAME_COLUMN_CELL_CLASS,
            ),
            ListColumn('competitor_type', label=_('Competitors')),
            ListColumn('date_range', label=_('Date')),
            ListColumn(
                'sources_count',
                label=_('Tournaments'),
                header_class='text-center',
                cell_class='justify-content-center',
            ),
            ListColumn('issues', label=_('Issues'), width='minmax(8rem, 1fr)'),
            ListColumn(
                'actions',
                label=_('Actions'),
                header_class='text-end',
                cell_class='justify-content-end',
            ),
        )
    ),
)

SOURCE_COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='championship-sources',
    components_template='/admin/championship/source_components.j2',
    default_view_mode=AdminCollectionViewMode.CARDS,
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(
            ComponentPlacement('event', 'w-100 text-center'),
            ComponentPlacement('date', 'me-auto'),
            ComponentPlacement('coefficient', 'w-100 text-end'),
        ),
        body=(ComponentPlacement('issues'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Tournament'),
                width=NAME_COLUMN_WIDTH,
                cell_class=NAME_COLUMN_CELL_CLASS,
            ),
            ListColumn('event', label=_('Event'), width='minmax(10rem, 1fr)'),
            ListColumn('date', label=_('Date')),
            ListColumn(
                'coefficient',
                label=_('Coefficient'),
                header_class='text-center',
                cell_class='justify-content-center',
            ),
            ListColumn('issues', label=_('Issues'), width='minmax(8rem, 1fr)'),
            ListColumn(
                'actions',
                label=_('Actions'),
                header_class='text-end',
                cell_class='justify-content-end',
            ),
        )
    ),
)
