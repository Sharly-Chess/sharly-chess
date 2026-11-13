from web.admin.collection import (
    AdminCollectionSpec,
    CardLayout,
    ComponentPlacement,
    ListColumn,
    ListLayout,
)
from web.admin.label import _


COLLECTION_SPEC: AdminCollectionSpec = AdminCollectionSpec(
    key='display-controllers',
    components_template=('/admin/display_controllers/display_controller_components.j2'),
    card_href_component='row_href',
    row_href_component='row_href',
    preview_template='/admin/common/collection_previews.html',
    card=CardLayout(
        header=(ComponentPlacement('identity', 'flex-grow-1 min-width-0'),),
        summary=(ComponentPlacement('screen_counts', 'mx-auto'),),
        body=(ComponentPlacement('assignment'),),
        details=(ComponentPlacement('details'),),
        footer=(ComponentPlacement('actions'),),
    ),
    list=ListLayout(
        columns=(
            ListColumn(
                'identity',
                label=_('Channel'),
                width='minmax(min-content, 1.2fr)',
            ),
            ListColumn(
                'assignment',
                label=_('Showing now'),
                width='minmax(min-content, 1.5fr)',
            ),
            ListColumn('screen_counts', label=_('Screens')),
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
