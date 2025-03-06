import pluggy  # type: ignore

from common import APP_NAME

hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)

class AppHookSpecs:
    """Holds all hookspecs for this application"""

    @hookspec
    def test(self) -> str:
        """A test hook"""
