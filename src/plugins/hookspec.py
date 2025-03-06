import pluggy  # type: ignore
from typing import NamedTuple, Any
from collections.abc import Iterable, Callable

from common import APP_NAME
from data.util import PrintDocument

hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)

class ExtraColumn(NamedTuple):
    insertion_index: int
    title: str
    classes: str
    value: Callable[
        [Any], str
    ]
class AppHookSpecs:
    """Holds all hookspecs for this application"""

    @hookspec
    def get_extra_print_view_columns(self, document: PrintDocument) -> Iterable[Iterable[ExtraColumn] | None]:
        """Provide extra columns for the print view"""
