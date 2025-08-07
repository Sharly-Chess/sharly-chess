from common.i18n import _
from common.logger import print_interactive_error
from common.sharly_chess_config import SharlyChessConfig
from common.tool_installer import (
    WebLibInstaller,
    WebLibArchiveInstaller,
    WebLibFileInstaller,
    BbpPairingsInstaller,
    ExecutableInstaller,
    PapiConverterInstaller,
)


class InstallationChecker:
    """A class to check the installation of all the needed tools and libs."""

    web_lib_installers: list[WebLibInstaller] = [
        WebLibArchiveInstaller(
            'Bootstrap',
            SharlyChessConfig.bootstrap_version,
            'bootstrap',
            'bootstrap-{version}-dist',
            [
                'js/bootstrap.bundle.min.js',
                'js/bootstrap.bundle.min.js.map',
                'css/bootstrap.min.css',
                'css/bootstrap.min.css.map',
            ],
            'https://github.com/twbs/bootstrap/releases/download/v{version}/bootstrap-{version}-dist.zip',
            'bootstrap-{version}-dist.zip',
            licence_type="MIT",
        ),
        WebLibArchiveInstaller(
            'Bootstrap icons',
            SharlyChessConfig.bootstrap_icons_version,
            'bootstrap-icons',
            'bootstrap-icons-{version}',
            [
                'font/bootstrap-icons.min.css',
                'font/fonts/bootstrap-icons.woff',
                'font/fonts/bootstrap-icons.woff2',
            ],
            'https://github.com/twbs/icons/releases/download/v{version}/bootstrap-icons-{version}.zip',
            'bootstrap-icons-{version}.zip',
            licence_type="MIT",
        ),
        WebLibArchiveInstaller(
            'Sortable',
            SharlyChessConfig.sortable_version,
            'Sortable',
            'Sortable-{version}',
            [
                'Sortable.min.js',
            ],
            'https://github.com/SortableJS/Sortable/archive/refs/tags/{version}.zip',
            'Sortable-{version}.zip',
            licence_type="MIT",
        ),
        WebLibArchiveInstaller(
            'jsTree',
            SharlyChessConfig.jstree_version,
            'jstree',
            'jstree-{version}',
            [
                'dist/jstree.min.js',
                'dist/themes/default/style.min.css',
                'dist/themes/default/32px.png',
                'dist/themes/default/40px.png',
                'dist/themes/default/throbber.gif',
            ],
            'https://github.com/vakata/jstree/archive/refs/tags/{version}.zip',
            'jstree-{version}.zip',
            licence_type="MIT",
        ),
        WebLibArchiveInstaller(
            'MorphDom',
            SharlyChessConfig.morphdom_version,
            'morphdom',
            'morphdom-{version}',
            [
                'dist/morphdom-umd.min.js',
            ],
            'https://github.com/patrick-steele-idem/morphdom/archive/refs/tags/v{version}.zip',
            'morphdom-{version}.zip',
            licence_type="MIT",
        ),
        WebLibArchiveInstaller(
            'Select2',
            SharlyChessConfig.select2_version,
            'select2',
            'select2-{version}',
            [
                'dist/js/select2.full.min.js',
                'dist/css/select2.min.css',
            ],
            'https://github.com/select2/select2/archive/refs/tags/{version}.zip',
            'select2-{version}.zip',
            licence_type="MIT",
        ),
        WebLibFileInstaller(
            'Select2 Bootstrap Theme',
            SharlyChessConfig.select2_bootstrap_theme_version,
            'https://cdn.jsdelivr.net/npm/select2-bootstrap-5-theme@{version}'
            '/dist/select2-bootstrap-5-theme.min.css',
            'select2/themes/bootstrap-5-{version}.min.css',
            licence_type="MIT",
        ),
        WebLibFileInstaller(
            'jQuery',
            SharlyChessConfig.jquery_version,
            'https://code.jquery.com/jquery-{version}.min.js',
            'jquery/jquery-{version}.min.js',
            licence_type="MIT",
        ),
        WebLibFileInstaller(
            'HTMX',
            SharlyChessConfig.htmx_version,
            'https://unpkg.com/htmx.org@{version}/dist/htmx.min.js',
            'htmx/htmx-{version}/htmx.min.js',
            licence_type="Zero-Clause BSD",
        ),
        WebLibFileInstaller(
            'HTMX Preload extension',
            SharlyChessConfig.htmx_preload_version,
            'https://unpkg.com/htmx-ext-preload@{version}',
            'htmx/preload-{version}/preload.js',
            licence_type="Zero-Clause BSD",
        ),
        WebLibFileInstaller(
            'HTMX Remove me extension',
            SharlyChessConfig.htmx_remove_me_version,
            'https://unpkg.com/htmx-ext-remove-me@{version}',
            'htmx/remove-me-{version}/remove-me.js',
            licence_type="Zero-Clause BSD",
        ),
        WebLibFileInstaller(
            'HTMX Multi swap extension',
            SharlyChessConfig.htmx_multi_swap_version,
            'https://unpkg.com/htmx-ext-multi-swap@{version}',
            'htmx/multi-swap-{version}/multi-swap.js',
            licence_type="Zero-Clause BSD",
        ),
        WebLibFileInstaller(
            'HTMX SSE extension',
            SharlyChessConfig.htmx_sse_version,
            'https://unpkg.com/htmx-ext-sse@{version}',
            'htmx/sse-{version}/sse.js',
        ),
    ]

    executable_installers: list[ExecutableInstaller] = [
        BbpPairingsInstaller(),
        PapiConverterInstaller(),
    ]

    @classmethod
    def check(cls) -> bool:
        error: bool = False
        for installer in cls.web_lib_installers + cls.executable_installers:
            if not installer.check_installation():
                error = True
        if error:
            print_interactive_error(_('Incorrect installation, exiting.'))
        return not error
