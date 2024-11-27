from gettext import gettext, ngettext
from os import urandom
from pathlib import Path
from typing import Sequence

from jinja2 import Environment
from litestar import Router
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.static_files import create_static_files_router
from litestar.template import TemplateConfig
from litestar.types import ControllerRouterHandler, Middleware

from web.controllers.admin.chessevent_admin_controller import ChessEventAdminController
from web.controllers.admin.event_admin_controller import EventAdminController
from web.controllers.admin.family_admin_controller import FamilyAdminController
from web.controllers.admin.index_admin_controller import IndexAdminController
from web.controllers.admin.rotator_admin_controller import RotatorAdminController
from web.controllers.admin.screen_admin_controller import ScreenAdminController
from web.controllers.admin.timer_admin_controller import TimerAdminController
from web.controllers.admin.tournament_admin_controller import TournamentAdminController
from web.controllers.background_controller import BackgroundController
from web.controllers.index_controller import IndexController
from web.controllers.user.event_user_controller import EventUserController
from web.controllers.user.index_user_controller import IndexUserController
from web.controllers.user.screen_user_controller import ScreenUserController
from web.controllers.user.tournament_user_controller import CheckInUserController, IllegalMoveUserController, \
    ResultUserController, DownloadUserController

BASE_DIR = Path(__file__).resolve().parent.parent

static_files_folders = [
    BASE_DIR / 'web' / 'static',
    # a direct web access to these folders is not needed at this time (2.4.11)
    # since the background images are delivered by the /background URL.
    # PapiWebConfig.custom_path,
    # PapiWebConfig.embedded_custom_path,
]

static_files_router: Router = create_static_files_router(
    path='/static',
    directories=static_files_folders,
    name='static',
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
    ChessEventAdminController,
    TournamentAdminController,
    ScreenAdminController,
    TimerAdminController,
    FamilyAdminController,
    RotatorAdminController,
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

# create the Jinja config that will be passed to the Litestar app
template_config: TemplateConfig = TemplateConfig(
    directory=BASE_DIR / 'web' / 'templates',
    engine=JinjaTemplateEngine,
    # engine_callback=register_template_callables,
)

# add the Jinja i18n extension and register the gettext callables
jinja_engine: JinjaTemplateEngine = template_config.engine_instance
jinja_env: Environment = jinja_engine.engine
jinja_env.add_extension('jinja2.ext.i18n')
jinja_env.install_gettext_callables(gettext=gettext, ngettext=ngettext, newstyle=True)

middlewares: Sequence[Middleware] = [
    CookieBackendConfig(secret=urandom(16)).middleware,
]
