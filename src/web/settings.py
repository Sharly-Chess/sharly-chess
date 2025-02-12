import os
import posixpath
import typing as t
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from litestar import Router
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.datastructures import CacheControlHeader
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.static_files import create_static_files_router
from litestar.stores.file import FileStore
from litestar.template import TemplateConfig
from litestar.types import ControllerRouterHandler, Middleware

from common import BASE_DIR, TMP_DIR
from common.i18n import gettext, ngettext
from web.controllers.admin.event_admin_controller import EventAdminController
from web.controllers.admin.family_admin_controller import FamilyAdminController
from web.controllers.admin.index_admin_controller import IndexAdminController
from web.controllers.admin.player_admin_controller import PlayerAdminController
from web.controllers.admin.rotator_admin_controller import RotatorAdminController
from web.controllers.admin.screen_admin_controller import ScreenAdminController
from web.controllers.admin.timer_admin_controller import TimerAdminController
from web.controllers.admin.tournament_admin_controller import TournamentAdminController
from web.controllers.background_controller import BackgroundController
from web.controllers.index_controller import IndexController
from web.controllers.search.ffe_search_controller import FfeSearchController
from web.controllers.user.event_user_controller import EventUserController
from web.controllers.user.index_user_controller import IndexUserController
from web.controllers.user.screen_user_controller import ScreenUserController
from web.controllers.user.tournament_user_controller import (
    CheckInUserController,
    IllegalMoveUserController,
    ResultUserController,
    DownloadUserController,
)

static_files_base_dir = BASE_DIR / 'src/web/static'

static_files_folders = [
    static_files_base_dir,
]

static_files_router: Router = create_static_files_router(
    path='/static',
    directories=static_files_folders,
    name='static',
    # TODO using cache_control did not cache, make it work!
    # https://github.com/litestar-org/litestar/issues/3129
    cache_control=CacheControlHeader(max_age=3600),
)


route_handlers: Sequence[ControllerRouterHandler] = [
    IndexController,
    BackgroundController,
    IndexUserController,
    EventUserController,
    ScreenUserController,
    ResultUserController,
    CheckInUserController,
    IllegalMoveUserController,
    DownloadUserController,
    IndexAdminController,
    EventAdminController,
    TournamentAdminController,
    ScreenAdminController,
    TimerAdminController,
    FamilyAdminController,
    RotatorAdminController,
    PlayerAdminController,
    FfeSearchController,
    static_files_router,
]

# Keep this here for the day we need to add extra functions to templates
# def template_test_function(ctx: dict[str, Any], param: str) -> str:
#     request: HTMXRequest = ctx["request"]
#     return f'le résultat de template_test_function(): string=[{param}], session=[{request.session}]'
#
# def register_template_callables(engine: JinjaTemplateEngine) -> None:
#     engine.register_template_callable(
#         key="callable_test_function",
#         template_callable=template_test_function,
#     )


class FileSystemLoaderWithRelativePath(FileSystemLoader):
    """override super().get_source() to allow .. in the template."""

    def get_source(
        self,
        environment: Environment,
        template: str,
    ) -> t.Tuple[str, str, t.Callable[[], bool]]:
        # pieces = self.split_template_path(template)
        pieces: list[str] = template.split('/')

        for searchpath in self.searchpath:
            # Use posixpath even on Windows to avoid "drive:" or UNC
            # segments breaking out of the search directory.
            filename = posixpath.join(searchpath, *pieces)
            if os.path.isfile(filename):
                break
        else:
            plural = 'path' if len(self.searchpath) == 1 else 'paths'
            paths_str = ', '.join(repr(p) for p in self.searchpath)
            raise TemplateNotFound(
                template,
                f'{template!r} not found in search {plural}: {paths_str}',
            )

        with open(filename, encoding=self.encoding) as f:
            contents = f.read()

        mtime = os.path.getmtime(filename)

        def uptodate() -> bool:
            try:
                return os.path.getmtime(filename) == mtime
            except OSError:
                return False

        # Use normpath to convert Windows altsep to sep.
        return contents, os.path.normpath(filename), uptodate


template_dir: Path = BASE_DIR / 'src/web/templates'


class PapiWebEnvironment(Environment):
    """Override to:
    - have a join_path() method that accepts relative path from the template that call %include, %extends and %from
    - use a loader that accepts relative path with ..
    - load the gettext methods"""

    def __init__(
        self,
        directory: Path,
    ) -> None:
        template_loader: FileSystemLoader = FileSystemLoaderWithRelativePath(
            searchpath=[directory]
        )
        super().__init__(
            loader=template_loader,
            autoescape=True,
        )
        self.add_extension('jinja2.ext.i18n')
        self.install_gettext_callables(
            gettext=gettext, ngettext=ngettext, newstyle=True
        )

    def join_path(self, template: str, parent: str) -> str:
        return str(Path(parent).parent / template)


template_engine: JinjaTemplateEngine = JinjaTemplateEngine(
    engine_instance=PapiWebEnvironment(template_dir),
)

# create the Jinja config that will be passed to the Litestar app
template_config: TemplateConfig = TemplateConfig(
    engine=template_engine,
    # engine_callback=register_template_callables,
)

sessions_dir: Path = TMP_DIR / 'sessions'
sessions_dir.mkdir(parents=True, exist_ok=True)

stores: dict[str, FileStore] = {'sessions': FileStore(path=sessions_dir)}

middlewares: Sequence[Middleware] = [
    ServerSideSessionConfig().middleware,
]
