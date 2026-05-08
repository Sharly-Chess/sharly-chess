from common.i18n import _
from data.columns.column import Column
from data.tournament import Tournament


class SCECheckInColumn(Column[Tournament]):
    @property
    def header_content(self) -> str:
        return 'Sharly-Chess.com'

    @property
    def header_tooltip(self) -> str:
        return _('Enable player check-in from Sharly-Chess.com.')

    @property
    def shared_classes(self) -> str:
        return 'text-center'

    @property
    def cell_template(self) -> str | None:
        return '/sce_check_in_table_cell.html'
