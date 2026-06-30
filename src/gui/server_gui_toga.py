"""
Toga GUI interface for Sharly Chess server.

This module provides a Toga-based GUI that can display server logs and control
the server without duplicating server logic.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Optional, Any
from PIL import Image as PILImage

import toga
from packaging.version import Version
from toga import TextInput
from toga.sources import ListSource
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import qrcode

import web
from common import (
    SHARLY_CHESS_VERSION,
    BASE_DIR,
    LOG_DIR,
    FLATPAK_ID,
    DATA_DIR,
    persist_data_directory,
    DEVEL_ENV,
)
from common.data_recovery import DataRecovery
from common.i18n import _, ngettext
from common.logger import get_logger
from common.version_updater import VersionUpdater
from common import sparkle_updater
from database.sqlite.config.config_database import ConfigDatabase
from gui.gui_logger import GUILogHandler
from web.server_engine import ServerEngine
from common.sharly_chess_config import SharlyChessConfig

logger = get_logger()

# ---------- Minimal ANSI → HTML conversion for WebView ----------
ANSI_SPLIT = r'\x1b\[([0-9;]*)[mK]'


def ansi_to_html(s: str) -> str:
    """
    Convert ANSI string to HTML spans with classes.
    Keeps it simple; anything unknown just resets.
    """

    parts = re.split(f'({ANSI_SPLIT})', s)
    current_classes: list[str] = []
    out: list[str] = []

    def clear_colors(tags: list[str]) -> list[str]:
        return [
            t
            for t in tags
            if t
            not in {
                'red',
                'green',
                'yellow',
                'blue',
                'magenta',
                'cyan',
                'white',
                'bright_red',
                'bright_green',
                'bright_yellow',
                'bright_blue',
                'bright_magenta',
                'bright_cyan',
                'bright_white',
                'dim',
            }
        ]

    def escape_html(string: str) -> str:
        return string.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    i = 0
    while i < len(parts):
        chunk = parts[i]
        if not chunk:
            i += 1
            continue

        if re.fullmatch(ANSI_SPLIT, chunk):
            # This part is the SGR code; next chunk (i+1) is the code string
            code_str = parts[i + 1] or '0'
            codes = [c for c in code_str.split(';') if c != '']
            if not codes:
                codes = ['0']

            for c in codes:
                try:
                    code = int(c)
                except ValueError:
                    code = 0

                if code == 0:
                    current_classes = []
                elif code == 1:
                    if 'bold' not in current_classes:
                        current_classes.append('bold')
                elif code == 2:
                    current_classes = clear_colors(current_classes)
                    if 'dim' not in current_classes:
                        current_classes.append('dim')
                elif code == 22:
                    current_classes = [
                        t for t in current_classes if t not in ('bold', 'dim')
                    ]
                elif code in (30, 31, 32, 33, 34, 35, 36, 37, 39):
                    current_classes = clear_colors(current_classes)
                    color_map = {
                        30: 'dim',
                        31: 'red',
                        32: 'green',
                        33: 'yellow',
                        34: 'blue',
                        35: 'magenta',
                        36: 'cyan',
                        37: 'white',
                        39: None,
                    }
                    tag = color_map[code]
                    if tag:
                        current_classes.append(tag)
                elif code in (90, 91, 92, 93, 94, 95, 96, 97):
                    current_classes = clear_colors(current_classes)
                    bmap = {
                        90: 'dim',
                        91: 'bright_red',
                        92: 'bright_green',
                        93: 'bright_yellow',
                        94: 'bright_blue',
                        95: 'bright_magenta',
                        96: 'bright_cyan',
                        97: 'bright_white',
                    }
                    current_classes.append(bmap[code])
                else:
                    # Unknown → reset
                    current_classes = []
            i += 2  # Skip the code string too
            continue

        # Regular text
        text = escape_html(chunk)
        if current_classes:
            out.append(f'<span class="{" ".join(current_classes)}">{text}</span>')
        else:
            out.append(text)
        i += 1

    return ''.join(out)


# ---------- HTML template for the log WebView ----------

APPEND_LOG_JS = """
    function(ts, html, level) {{
        var cont = document.getElementById('log');
        if (!cont) return;
        var div = document.createElement('div');
        div.className = 'line ' + (level || 'info');
        div.innerHTML = html;
        cont.appendChild(div);
        window.scrollTo(0, document.body.scrollHeight);
    }};
"""

CLEAR_LOG_JS = """
    function clearLog() {{
        const cont = document.getElementById('log');
        cont.innerHTML = '';
    }}
"""


LOG_HTML = f"""<!doctype html>
<html>
    <head>
        <meta charset="utf-8">
        <title>Sharly Chess Logs</title>
        <style>
            html, body {{ background: #000; color: #d0d0d0; font-family: Menlo, Monaco, monospace; margin: 0; padding: 0; }}
            .wrap {{ padding: 8px 10px; }}
            .line {{ white-space: pre-wrap; word-break: break-word; }}
            .ts {{ color: #888; }}

            /* Level tags */
            .info {{ color: #d0d0d0; }}
            .warning {{ color: #ffd166; }}
            .error {{ color: #ff6666; }}
            .debug {{ color: #a0a0a0; }}
            .success {{ color: #66ff99; }}

            /* ANSI-ish classes */
            .bold {{ font-weight: bold; }}
            .dim {{ color: #888; }}
            .red {{ color: #ff6666; }}
            .green {{ color: #66ff66; }}
            .yellow {{ color: #ffff66; }}
            .blue {{ color: #66aaff; }}
            .magenta {{ color: #ff66ff; }}
            .cyan {{ color: #66ffff; }}
            .white {{ color: #d0d0d0; }}
            .bright_red {{ color: #ff7777; }}
            .bright_green {{ color: #77ff77; }}
            .bright_yellow {{ color: #ffff77; }}
            .bright_blue {{ color: #7777ff; }}
            .bright_magenta {{ color: #ff77ff; }}
            .bright_cyan {{ color: #77ffff; }}
            .bright_white {{ color: #ffffff; }}
            .muted {{ color: #999; }}
        </style>
    </head>
    <body>
        <div class="wrap" id="log"></div>
        <script>
            {APPEND_LOG_JS}
            {CLEAR_LOG_JS}
        </script>
    </body>
</html>
"""

# Fix a Windows Toga issue in v0.52 - _on_gain_focus is called by doesn't exist
if not hasattr(toga.Window, '_on_gain_focus'):

    def _noop_gain(self, *_, **__):  # bound method signature (self will be bound)
        pass

    toga.Window._on_gain_focus = _noop_gain

if not hasattr(toga.Window, '_on_lose_focus'):

    def _noop_lose(self, *_, **__):
        pass

    toga.Window._on_lose_focus = _noop_lose


def make_qr_pil(data: str) -> PILImage.Image:
    qr = qrcode.QRCode(
        box_size=10,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
    )
    qr.add_data(data)
    qr.make()
    return qr.make_image(fill_color='black', back_color='white')


def pil_to_toga_image(pil_img: PILImage.Image) -> toga.Image:
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    return toga.Image(src=buf.getvalue())


class SharlyChessServerToga(toga.App):
    """Main Toga GUI app for Sharly Chess server."""

    instance: Optional['SharlyChessServerToga'] = None

    def __init__(self, *, debug: bool = False, port: int | None = None):
        SharlyChessServerToga.instance = self
        icon_file_name: str | None = None
        web_dir = BASE_DIR / 'src' / 'web'
        match sys.platform:
            case 'win32':
                icon_file_name = 'sharly-chess.ico'
            case 'darwin':
                icon_file_name = 'sharly-chess.icns'
            case 'linux':
                icon_file_name = 'sharly-chess.png'
                web_dir = Path(web.__file__).parent
            case _:
                raise NotImplementedError(f'{sys.platform=}')

        # Resolve icon path dynamically to support both dev and installed environments
        icon_path = web_dir / 'static' / 'images' / icon_file_name

        # Use FLATPAK_ID if available to match the sandbox ID
        app_id = FLATPAK_ID or 'com.sharlychess.app'

        super().__init__(
            formal_name='Sharly Chess',
            app_id=app_id,
            icon=icon_path,
            home_page='https://sharly-chess.com',
            version=str(SHARLY_CHESS_VERSION),
        )
        self.gui_loop = asyncio.get_event_loop()
        self.server_loop = asyncio.SelectorEventLoop()
        self.debug = debug
        self.port = port

        self._logview_ready = False
        self._pending_js: list[str] = []

        # State
        self.server_thread: Optional[threading.Thread] = None
        self.serve_task: asyncio.Task | None = None
        self.server_running = False

        # Thread-safe communication
        self.message_queue: queue.Queue[tuple[str, str, Optional[str]]] = queue.Queue()
        self.compact_size = (450, 100)
        self.expanded_size = (1200, 700)

        # Styles
        self.menu_button_style = Pack(
            font_weight='bold',
            font_size=10,
        )
        self.active_menu_button_style = Pack(
            font_weight='bold',
            font_size=10,
            background_color='#0078d7',
            color='#ffffff',
        )
        self.button_style = Pack()
        self.active_button_style = Pack(
            background_color='#0078d7',
            color='#ffffff',
        )

        # GUI elements (initialized in startup)
        self.main_box: Optional[toga.Box] = None

        # Menu buttons
        self.menu_home_btn: Optional[toga.Button] = None
        self.menu_networks_btn: Optional[toga.Button] = None
        self.menu_logs_btn: Optional[toga.Button] = None
        self.menu_settings_btn: Optional[toga.Button] = None
        self.active_view_name: str | None = None

        # Home view
        self.home_view: Optional[toga.Box] = None
        self.server_state_container: Optional[toga.Box] = None
        self.update_available_box: Optional[toga.Box] = None
        self.home_main_label: Optional[toga.Label] = None
        self.home_progress_bar: Optional[toga.ProgressBar] = None

        # Networks view
        self.networks_view: Optional[toga.Box] = None
        self.lan_ifaces: list[dict[str, str]] | None = None

        # Logs view
        self.logs_view: Optional[toga.Box] = None
        self.html_view: Optional[toga.WebView] = None
        self.log_settings_btn: Optional[toga.Button] = None
        self.log_settings_container: Optional[toga.Box] = None
        self.log_settings: Optional[toga.Box] = None
        self.log_level_select: Optional[toga.Selection] = None
        self.log_color_switch: Optional[toga.Switch] = None
        self.show_log_level_switch: Optional[toga.Switch] = None
        self.show_log_time_switch: Optional[toga.Switch] = None

        # Settings view
        self.settings_view: Optional[toga.Box] = None
        self.launch_browser_switch: Optional[toga.Switch] = None
        self.data_path_input: Optional[TextInput] = None
        self.data_path_edit_button: Optional[toga.Button] = None
        self.check_beta_switch: Optional[toga.Switch] = None
        self.latest_version_label: Optional[toga.Label] = None
        self.latest_version_btn: Optional[toga.Button] = None
        self.version_search_ongoing = False
        self.recover_button: Optional[toga.Button] = None
        self.recover_box: Optional[toga.Box] = None

    @property
    def menu_buttons(self) -> list:
        return [
            self.menu_home_btn,
            self.menu_networks_btn,
            self.menu_logs_btn,
            self.menu_settings_btn,
        ]

    @property
    def menu_views(self) -> list:
        return [
            self.home_view,
            self.networks_view,
            self.logs_view,
            self.settings_view,
        ]

    # --- Toga lifecycle ---
    def startup(self):
        SharlyChessConfig().load_and_set_env()

        # Menu buttons
        self.menu_home_btn = toga.Button(
            _('Home'),
            style=self.active_menu_button_style,
            on_press=self._show_home_view,
        )
        self.menu_networks_btn = toga.Button(
            _('Networks'),
            style=self.menu_button_style,
            enabled=False,
            on_press=self._show_networks_view,
        )
        self.menu_logs_btn = toga.Button(
            _('Logs'),
            style=self.menu_button_style,
            on_press=self._show_logs_view,
            enabled=False,
        )
        self.menu_settings_btn = toga.Button(
            _('Settings'),
            style=self.menu_button_style,
            on_press=self._show_settings_view,
            enabled=False,
        )

        # Home View
        self.home_view = toga.Box(
            style=Pack(direction=COLUMN, margin=10, gap=7, align_items='center'),
        )

        self.update_available_box = toga.Box(
            children=[
                toga.Label(_('A new version is available!'), font_weight='bold'),
                toga.Button(
                    _('Install'),
                    on_press=self._show_update_dialog,
                    font_weight='bold',
                ),
                toga.Button(
                    _('Changelog'),
                    on_press=self._open_changelog,
                    font_weight='bold',
                ),
            ],
            align_items='center',
            gap=2,
        )
        self.home_main_label = toga.Label(
            _('Application startup...'), text_align='center'
        )
        self.server_state_container = toga.Box(
            style=Pack(direction=COLUMN, align_items='center')
        )
        self.home_progress_bar = toga.ProgressBar()
        self.home_progress_bar.max = None
        self.server_state_container.add(self.home_progress_bar)
        help_label = toga.Label(_('Need help?'))
        doc_btn = toga.Button(_('Documentation'), on_press=self._open_documentation)
        discord_btn = toga.Button('Discord', on_press=self._open_discord)
        mail_btn = toga.Button(_('Mail'), on_press=self._open_mail)
        self.home_view.add(
            self.home_main_label,
            self.server_state_container,
            toga.Divider(style=Pack(margin=(5, 0))),
            toga.Box(
                children=[help_label, doc_btn, discord_btn, mail_btn],
                gap=5,
                align_items='center',
            ),
            toga.Box(
                children=[
                    toga.Label(f'Sharly Chess {SHARLY_CHESS_VERSION}'),
                ],
                align_items='center',
            ),
        )

        # Networks view
        self.networks_view = toga.Box(
            style=Pack(direction=COLUMN, margin=10, align_items='center')
        )

        # Log view: WebView with HTML for ANSI color support
        self.html_view = toga.WebView(
            style=Pack(flex=1), on_webview_load=self._on_logview_load
        )
        self.logs_view = toga.Box(style=Pack(direction=COLUMN, flex=1))
        log_buttons = toga.Box(style=Pack(direction=ROW, margin=(10, 0), gap=5))
        self.log_settings_btn = toga.Button(
            text=_('Log settings'),
            style=self.button_style,
            on_press=self._toggle_log_settings,
        )
        clear_logs_btn = toga.Button(text=_('Clear logs'), on_press=self._clear_log)
        log_files_btn = toga.Button(_('Access log files'), on_press=self._open_logs_dir)
        log_buttons.add(self.log_settings_btn, clear_logs_btn, log_files_btn)
        self.logs_view.add(log_buttons)
        config = SharlyChessConfig()
        log_level_options = [
            {'level': console_log_level, 'text': console_log_level_str}
            for console_log_level, console_log_level_str in config.console_log_levels.items()
        ]
        self.log_level_select = toga.Selection(
            items=log_level_options,
            accessor='text',
            on_change=self._on_level_change,
        )
        log_level = toga.Box(
            children=[
                toga.Label(_('Minimum level:')),
                self.log_level_select,
            ],
            margin_right=5,
            gap=2,
            align_items='center',
        )
        assert isinstance(self.log_level_select.items, ListSource)
        self.log_level_select.value = self.log_level_select.items.find(
            data={'level': config.console_log_level}
        )
        self.log_color_switch = toga.Switch(
            text=_('Level specific colors'),
            value=config.console_color,
            on_change=self._on_log_color_switch_change,
        )
        self.show_log_level_switch = toga.Switch(
            text=_('Show level'),
            value=config.console_show_level,
            on_change=self._on_show_log_level_switch_change,
        )
        self.show_log_time_switch = toga.Switch(
            text=_('Date and time'),
            value=config.console_show_date,
            on_change=self._on_show_date_switch_change,
        )
        self.log_settings = toga.Box(
            direction=ROW,
            margin_bottom=10,
            visibility='hidden',
            align_items='center',
            gap=20,
        )
        self.log_settings.add(
            log_level,
            self.log_color_switch,
            self.show_log_level_switch,
            self.show_log_time_switch,
        )
        self.log_settings_container = toga.Box()
        self.logs_view.add(self.log_settings_container)
        self.logs_view.add(self.html_view)

        # Settings view
        self.settings_view = toga.Box(
            direction=COLUMN,
            margin=10,
            gap=7,
            align_items='center',
        )
        self.launch_browser_switch = toga.Switch(
            text=_('Launch a browser on startup'),
            value=config.launch_browser,
            on_change=self._on_launch_browser_switch_change,
        )

        self.data_path_input = toga.TextInput(
            value=self._shorten_path(str(DATA_DIR.absolute())),
            readonly=True,
            flex=1,
        )
        data_path_buttons = [
            toga.Button(_('Open'), on_press=self._open_data_path_explorer)
        ]
        if FLATPAK_ID:
            self.data_path_input.enabled = False
        else:
            self.data_path_edit_button = toga.Button(
                _('Edit'), on_press=self._handle_data_path_selection
            )
            data_path_buttons.append(self.data_path_edit_button)
        self.check_beta_switch = toga.Switch(
            text=_('Include beta versions in updates'),
            value=config.check_beta_versions,
            on_change=self._on_check_beta_switch_change,
        )
        self.latest_version_label = toga.Label(
            '', text_align='center'
        )  # initialized later
        self.latest_version_btn = toga.Button(
            _('Search for updates'), on_press=self._search_for_updates
        )
        changelog_button = toga.Button(_('Changelog'), on_press=self._open_changelog)
        self.recover_button = toga.Button(
            _('Recover a previous version'), on_press=self._toggle_recover_box
        )
        self.recover_box = toga.Box(direction=COLUMN, gap=7, align_items='center')
        title_style = Pack(font_weight='bold', font_size=10, text_align='center')
        self.settings_view.add(
            toga.Label(_('General'), style=title_style),
            toga.Box(children=[self.launch_browser_switch]),
            toga.Divider(margin=(5, 0)),
            toga.Label(_('Data folder'), style=title_style),
            self.data_path_input,
            toga.Box(
                direction=ROW,
                children=data_path_buttons,
                gap=10,
            ),
            toga.Divider(margin=(5, 0)),
            toga.Label(_('Version'), style=title_style),
            toga.Label(f'Sharly Chess {SHARLY_CHESS_VERSION}', text_align='center'),
            self.latest_version_label,
            toga.Box(
                children=[self.latest_version_btn, changelog_button],
                gap=10,
            ),
            toga.Box(children=[self.check_beta_switch]),
        )

        # Layout container
        self.main_box = toga.Box(style=Pack(direction=COLUMN, margin=(5, 10, 10, 10)))
        btn_row = toga.Box(style=Pack(direction=ROW, gap=7))
        for button in self.menu_buttons:
            btn_row.add(button)
        self.main_box.add(btn_row)
        self.main_box.add(self.home_view)

        # Window class used instead of MainWindow to avoid having a toolbar
        # See https://github.com/beeware/toga/issues/1870#issuecomment-2272534628
        self.main_window = toga.Window(  # type: ignore
            title='Sharly Chess',
            size=self.compact_size,
            content=self.main_box,
            resizable=False,
        )

        assert isinstance(self.main_window, toga.Window)
        self.main_window.show()

    def update_from_sharly_chess_config(self):
        config = SharlyChessConfig()
        assert self.launch_browser_switch is not None
        self.launch_browser_switch.value = config.launch_browser
        assert self.log_level_select is not None and isinstance(
            self.log_level_select.items, ListSource
        )
        self.log_level_select.value = self.log_level_select.items.find(
            data={'level': config.console_log_level}
        )
        assert self.log_color_switch is not None
        self.log_color_switch.value = config.console_color
        assert self.show_log_level_switch is not None
        self.show_log_level_switch.value = config.console_show_level
        assert self.show_log_time_switch is not None
        self.show_log_time_switch.value = config.console_show_date

    def _show_view(self, name: str, is_compact_window: bool = True):
        if self.active_view_name == name:
            return
        assert self.main_box is not None
        for menu_view in self.menu_views:
            if menu_view in self.main_box.children:
                self.main_box.remove(menu_view)
        view: toga.Box = getattr(self, f'{name}_view')
        self.main_box.add(view)
        for btn in self.menu_buttons:
            btn.style = self.menu_button_style
        view_btn: toga.Button = getattr(self, f'menu_{name}_btn')
        view_btn.style = self.active_menu_button_style
        self.active_view_name = name
        assert isinstance(self.main_window, toga.Window)
        self.main_window.size = (
            self.compact_size if is_compact_window else self.expanded_size
        )

    def _show_home_view(self, widget):
        self._show_view('home')

    def _show_logs_view(self, widget):
        self._show_view('logs', is_compact_window=False)
        assert self.html_view is not None
        self.html_view.refresh()

    def _show_networks_view(self, widget):
        self._show_view('networks')
        self._refresh_networks_view(hard_refresh=False)

    def _show_settings_view(self, widget):
        self._show_view('settings')
        self._update_latest_version_components()

    def _toggle_log_settings(self, widget):
        assert self.log_settings_container is not None
        assert self.log_settings is not None
        assert self.log_settings_btn is not None
        if self.log_settings in self.log_settings_container.children:
            self.log_settings_container.remove(self.log_settings)
            self.log_settings_btn.style = self.button_style
        else:
            self.log_settings_container.add(self.log_settings)
            self.log_settings_btn.style = self.active_button_style

    def _toggle_recover_box(self, widget):
        assert self.settings_view is not None
        assert self.recover_box is not None
        assert self.recover_button is not None
        assert isinstance(self.main_window, toga.Window)
        if self.recover_box in self.settings_view.children:
            self.settings_view.remove(self.recover_box)
            self.recover_button.style = self.button_style
            self.main_window.size = self.compact_size
        else:
            self.settings_view.add(self.recover_box)
            self.recover_button.style = self.active_button_style

    @staticmethod
    def _shorten_path(path: str, max_len: int = 50) -> str:
        """Middle-ellipsis a path so both the root and the final folder name
        stay visible when it is too long for the field."""
        if len(path) <= max_len:
            return path
        head = (max_len - 1) // 2
        tail = max_len - 1 - head
        return f'{path[:head]}…{path[-tail:]}'

    def _open_data_path_explorer(self, widget):
        self._open_dir_in_explorer(DATA_DIR)

    async def _handle_data_path_selection(self, widget):
        folder_dialog = toga.SelectFolderDialog('')
        assert isinstance(self.main_window, toga.Window)
        path: Path | None = await self.main_window.dialog(folder_dialog)
        if path is None or path == DATA_DIR:
            return

        error: str | None = None
        if any(path.iterdir()):
            # Directory is not empty
            error = _('This folder is not empty.')
        if not os.access(path, os.W_OK):
            # directory is not writable
            error = _('You do not have write permission on this folder.')
        if DATA_DIR in path.parents:
            error = _('The folder should not be contained in the current data folder.')
        if error:
            error_dialog = toga.ErrorDialog(
                _('Invalid folder'), error.format(folder=path)
            )
            await self.main_window.dialog(error_dialog)
            return
        confirm_dialog = toga.ConfirmDialog(
            _('Data folder'),
            _('Confirm the new data folder "{folder}"?').format(folder=path)
            + '\n'
            + _('Restarting will be required to apply the change.'),
        )
        if not await self.main_window.dialog(confirm_dialog):
            return
        persist_data_directory(path, DATA_DIR)

        assert self.settings_view is not None
        assert self.data_path_input is not None
        assert self.data_path_edit_button is not None
        self.data_path_input.enabled = False
        self.data_path_edit_button.enabled = False
        self.settings_view.index(self.data_path_input)
        self.settings_view.insert(
            self.settings_view.index(self.data_path_input) + 2,
            toga.Label(
                _('Modified, restart to apply'),
                color='red',
                font_weight='bold',
                text_align='center',
            ),
        )

    @staticmethod
    def _last_search_message(last_search_at: datetime) -> str:
        search_delta = datetime.now() - last_search_at
        minutes = search_delta.seconds // 60
        hours = minutes // 60
        if hours:
            return ngettext(
                'last search an hour ago',
                'last search {count} hours ago',
                hours,
            ).format(count=hours)
        if not minutes:
            return _('last search just now')
        return ngettext(
            'last search a minute ago',
            'last search {count} minutes ago',
            minutes,
        ).format(count=minutes)

    def _update_latest_version_components(self):
        assert self.latest_version_btn is not None
        assert self.latest_version_label is not None
        assert self.update_available_box is not None
        assert self.home_view is not None

        skip_settings = self.active_view_name != 'settings'
        latest = VersionUpdater.LATEST_VERSION
        search_ongoing = self.version_search_ongoing
        searched_at = VersionUpdater.LATEST_VERSION_SEARCHED_AT
        if search_ongoing:
            message = _('Searching for updates...')
        elif not latest or not searched_at:
            message = _('Latest version never searched (no internet)')
        else:
            if latest > SHARLY_CHESS_VERSION:
                message = _('A new version is available!')
                if self.update_available_box not in self.home_view.children:
                    self.home_view.insert(0, self.update_available_box)
                if not skip_settings:
                    self.latest_version_label.style.font_weight = 'bold'
                    self.latest_version_btn.text = _('Install')
                    self.latest_version_btn.on_press = self._show_update_dialog
            else:
                if latest == SHARLY_CHESS_VERSION:
                    message = _('You have the latest version')
                else:
                    message = _('You have the latest unofficial version')
                message = f'{message} ({self._last_search_message(searched_at)})'

        if not skip_settings:
            self.latest_version_label.text = message
            self.latest_version_label.enabled = not search_ongoing
            self.latest_version_btn.enabled = not search_ongoing

    async def _search_for_updates(
        self,
        widget: toga.Widget | None = None,
        is_startup: bool = False,
    ):
        if self.version_search_ongoing:
            return

        self.version_search_ongoing = True
        self._update_latest_version_components()

        async def run_search():
            config = SharlyChessConfig()
            try:
                check_beta = config.check_beta_versions
                VersionUpdater.search_for_latest_version(check_beta)
            finally:
                self.version_search_ongoing = False
                self._update_latest_version_components()
            if not is_startup or DEVEL_ENV:
                return
            latest = VersionUpdater.LATEST_VERSION
            last_notif = config.last_notified_version
            if (
                latest
                and latest > SHARLY_CHESS_VERSION
                and (not last_notif or last_notif < latest)
            ):
                self._update_config('last_notified_version', str(latest))
                await self._show_update_dialog(None)

        asyncio.run_coroutine_threadsafe(run_search(), self.gui_loop)

    async def _show_update_dialog(self, widget):
        assert isinstance(self.main_window, toga.Window)
        if DEVEL_ENV:
            error_dialog = toga.ErrorDialog(
                title='Sharly Chess Error',
                message=(
                    'Sharly Chess is currently running in '
                    'development and does not support updating.'
                ),
            )
            await self.main_window.dialog(error_dialog)
            return
        latest = VersionUpdater.LATEST_VERSION
        assert latest is not None
        # On a macOS build, Sparkle owns the confirm / download / verify /
        # install / relaunch flow. Elsewhere (and in dev) fall back to the
        # legacy external updater.
        if sparkle_updater.check_for_update(latest):
            return
        message = _('Sharly Chess {latest} is available, you have {current}.').format(
            latest=latest, current=SHARLY_CHESS_VERSION
        )
        message += '\n' + _('Do you want to install it now?')
        question_dialog = toga.QuestionDialog(
            title=_('A new version is available!'), message=message
        )
        if not await self.main_window.dialog(question_dialog):
            return
        await self._exit_and_run_version_updater(latest)

    async def _show_recovery_dialog(self, widget, version: Version):
        assert isinstance(self.main_window, toga.Window)
        if DEVEL_ENV:
            error_dialog = toga.ErrorDialog(
                title='Sharly Chess Error',
                message=(
                    'Sharly Chess is currently running in development '
                    'and does not support version recovery.' + str(version)
                ),
            )
            await self.main_window.dialog(error_dialog)
            return
        message = _(
            'Warning: recovering a previous version is irreversible, '
            'all the data you have modified since then will be lost.'
        )
        message += '\n' + _(
            'Do you confirm wanting to recover version {version}?'
        ).format(version=version)
        question_dialog = toga.QuestionDialog(
            title=_('Recover a previous version'), message=message
        )
        if not await self.main_window.dialog(question_dialog):
            return
        await self._exit_and_run_version_updater(version)

    async def _exit_and_run_version_updater(self, version: Version):
        assert isinstance(self.main_window, toga.Window)
        updater_path = VersionUpdater.version_updater_path()
        if not updater_path.exists():
            error_dialog = toga.ErrorDialog(
                title=_('Sharly Chess Error'),
                message=_(
                    'The updater file is missing at [{path}].\n'
                    'The application needs to be re-installed manually.'
                ).format(path=updater_path),
            )
            await self.main_window.dialog(error_dialog)
        self.quit_app(
            post_exit_task=partial(VersionUpdater.run_version_updater, version=version)
        )

    def on_running(self):
        # Logging handler
        assert self.html_view is not None
        self.html_view.set_content('about:blank', LOG_HTML)
        self.gui_handler = GUILogHandler(self)
        self.gui_handler.setLevel(logging.DEBUG)

        assert self.home_progress_bar is not None
        self.home_progress_bar.value = 1
        self.home_progress_bar.start()
        # Look for updates. Run asynchronously to speed up server startup
        asyncio.run_coroutine_threadsafe(
            self._search_for_updates(is_startup=True), self.server_loop
        )
        # Start message processing and kick the server immediately
        asyncio.create_task(self._process_message_queue())
        if not self.server_running:
            self._on_start_server(None)

    def make_link_button(self, url: str) -> toga.Label:
        button = toga.Button(url, style=Pack(align_items='center', margin_top=5))
        button.on_press = lambda widget, **kwargs: webbrowser.open(url)
        return button

    def on_server_ready(self):
        assert self.home_main_label is not None
        assert self.home_progress_bar is not None
        assert self.server_state_container is not None
        self.home_progress_bar.stop()
        self.home_main_label.text = _(
            'Warning: closing this window will stop Sharly Chess.'
        )
        self.server_state_container.clear()
        self.server_state_container.add(
            toga.Box(
                style=Pack(direction=ROW, align_items='center'),
                children=[
                    toga.Button(
                        _('Open application (browser)'),
                        on_press=self._open_browser,
                    ),
                ],
            )
        )
        if DataRecovery.RECOVERABLE_VERSIONS:
            assert self.settings_view is not None
            assert self.recover_button is not None
            assert self.recover_box is not None
            self.settings_view.add(
                toga.Box(children=[self.recover_button]),
            )
            self.recover_box.add(
                toga.Label(
                    _('Warning: recovering a version is irreversible!'),
                    color='red',
                    text_align='center',
                    font_weight='bold',
                ),
                toga.Box(
                    children=[
                        toga.Button(
                            _('Recover version {version}').format(version=version),
                            on_press=partial(
                                self._show_recovery_dialog, version=version
                            ),
                        )
                        for version in DataRecovery.RECOVERABLE_VERSIONS
                    ],
                    gap=10,
                    align_items='center',
                ),
            )

        for button in self.menu_buttons:
            button.enabled = True

    def _refresh_networks_view(
        self, widget: Any = None, hard_refresh: bool = True, **kwargs
    ):
        assert self.networks_view is not None
        config = SharlyChessConfig()
        lan_ifaces = SharlyChessConfig().lan_ifaces
        if (
            not hard_refresh
            and self.lan_ifaces is not None
            and lan_ifaces == self.lan_ifaces
        ):  # don't do anything if networks did not change
            return
        self.lan_ifaces = lan_ifaces
        self.networks_view.clear()

        if lan_ifaces:
            self.networks_view.add(
                toga.Label(
                    text=_(
                        'You may also connect to this server from other devices using'
                    ),
                    align_items='center',
                    text_align='center',
                )
            )
            self.networks_view.add(
                toga.Label(
                    text=_(
                        'the server address on the networks to which it is connected:'
                    ),
                    align_items='center',
                    text_align='center',
                )
            )
            network_section = toga.Box(style=Pack(direction=ROW, margin_top=15, gap=10))
            self.networks_view.add(network_section)
            for item in self.lan_ifaces:
                url = config.app_url(item['ip'])
                network_item = toga.Box(
                    style=Pack(direction=COLUMN, gap=5, align_items='center')
                )
                pil_img = make_qr_pil(url)
                toga_img = pil_to_toga_image(pil_img)
                label = item['label']
                type = item['type'] if 'type' in item else None
                if type and type != label:
                    label = f'{label} ({type})'

                qr_widget = toga.ImageView(
                    image=toga_img, style=Pack(width=120, height=120)
                )
                network_item.add(qr_widget)
                network_item.add(self.make_link_button(url))
                network_item.add(toga.Label(text=label, align_items='center'))
                network_section.add(network_item)
        else:
            self.networks_view.add(
                toga.Label(
                    text=_(
                        'No network detected, use the Refresh button when connected.'
                    ),
                    margin_top=10,
                    align_items='center',
                    text_align='center',
                )
            )
        refresh_box = toga.Box(style=Pack(direction=ROW, align_items='center'))
        refresh_box.add(
            toga.Button(
                text=_('Refresh networks'),
                on_press=self._refresh_networks_view,
                style=Pack(margin_top=10, font_weight='bold'),
            )
        )
        self.networks_view.add(refresh_box)
        assert isinstance(self.main_window, toga.Window)
        self.main_window.size = self.compact_size

    def _noop(self, widget: toga.Widget):
        pass

    # ------- Public API used by handler / background code -------
    def add_log_message(self, message: str, tag: Optional[str] = None):
        self.message_queue.put(('log', message, tag))

    # ------- Internals -------
    async def _process_message_queue(self):
        """Background task to process pending messages from other threads."""
        while True:
            try:
                while True:
                    msg_type, content, extra = self.message_queue.get_nowait()
                    if msg_type == 'log':
                        self._append_log_message(content, extra)
            except queue.Empty:
                pass

            await asyncio.sleep(0.1)

    def _append_log_message(self, message: str, level: Optional[str]):
        ts = datetime.now().strftime('%H:%M:%S')

        if '\x1b[' in message:
            html = ansi_to_html(message)
        else:
            html = (
                message.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            )

        # Use json.dumps to make safe JS string literals
        ts_js = json.dumps(ts)
        html_js = json.dumps(html)
        level_js = json.dumps((level or ''))

        js = f"""
        (function() {{
            if (typeof appendLog !== 'function') {{
                window.appendLog = {APPEND_LOG_JS}
            }}
            appendLog({ts_js}, {html_js}, {level_js});
        }})();"""

        self._eval_or_buffer_js(js)

    def _on_start_server(self, widget: Any | None = None, **kwargs) -> None:
        """Start the server in a background thread."""
        if self.server_running:
            self.add_log_message(_('Server is already running!'), 'warning')
            return

        self.server_running = True

        # Start server in background thread
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

    def _run_server(self) -> None:
        # IMPORTANT: bypass Toga's event-loop policy in this *background* thread
        loop = self.server_loop
        if sys.platform != 'linux':
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            asyncio.set_event_loop(loop)

        def schedule_ready():
            self.gui_loop.call_soon_threadsafe(self.on_server_ready)

        engine = ServerEngine(
            debug=self.debug,
            port=self.port,
            loop=loop,
            handle_signals=False,
            on_port_chosen=schedule_ready,
        )
        self.serve_task = loop.create_task(engine.serve())

        try:
            loop.run_forever()
        finally:
            # Graceful shutdown
            tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for t in tasks:
                t.cancel()
            try:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()
                assert self.app is not None
                self.gui_loop.call_soon_threadsafe(self.app.exit)

    def _open_browser(self, widget: Any = None, **kwargs) -> None:
        try:
            url = SharlyChessConfig().local_url
            webbrowser.open(url)
            self.add_log_message(f'Opening browser: {url}', 'success')
        except Exception as e:
            self.add_log_message(f'Failed to open browser: {e}', 'error')

    @staticmethod
    def _open_documentation(widget: Any = None, **kwargs) -> None:
        webbrowser.open(_('*** Doc Link'))

    @staticmethod
    def _open_changelog(widget: Any = None, **kwargs) -> None:
        webbrowser.open(_('*** Changelog Link'))

    @staticmethod
    def _open_discord(widget):
        webbrowser.open('https://discord.gg/ezvxaCwUmw')

    @staticmethod
    def _open_mail(widget):
        webbrowser.open('mailto:support@sharly-chess.com')

    def _clear_log(self, widget: Any = None, **kwargs) -> None:
        try:
            while True:
                self.message_queue.get_nowait()
        except queue.Empty:
            pass

        js = f"""
            (function() {{
                if (typeof clearLog !== 'function') {{
                    window.clearLog = {CLEAR_LOG_JS}
                }}
                clearLog();
            }})();"""

        self._eval_or_buffer_js(js)

    @staticmethod
    def _open_dir_in_explorer(dir_path: Path):
        match sys.platform:
            case 'win32':
                subprocess.Popen(f'explorer "{dir_path}"')
            case 'darwin':
                subprocess.Popen(['open', str(dir_path)])
            case 'linux':
                subprocess.Popen(['xdg-open', str(dir_path)])

    @classmethod
    def _open_logs_dir(cls, widget):
        cls._open_dir_in_explorer(LOG_DIR)

    @staticmethod
    def _update_config(field: str, value):
        stored_config = SharlyChessConfig().stored_config
        setattr(stored_config, field, value)
        with ConfigDatabase(write=True) as config_database:
            config_database.update_stored_config(stored_config)
        SharlyChessConfig().load_and_set_env()

    def _on_level_change(self, widget: toga.Selection, **kwargs):
        self._update_config('console_log_level', getattr(widget.value, 'level'))

    def _on_log_color_switch_change(self, widget: toga.Switch, **kwargs):
        self._update_config('console_color', widget.value)

    def _on_show_log_level_switch_change(self, widget: toga.Switch, **kwargs):
        self._update_config('console_show_level', widget.value)

    def _on_show_date_switch_change(self, widget: toga.Switch, **kwargs):
        self._update_config('console_show_date', widget.value)

    def _on_launch_browser_switch_change(self, widget: toga.Switch, **kwargs):
        self._update_config('launch_browser', widget.value)

    def _on_check_beta_switch_change(self, widget: toga.Switch, **kwargs):
        self._update_config('check_beta_versions', widget.value)

    # --- Interactive prompts ---
    def handle_interactive_yn(
        self, title: str, question: str, yes_is_default: bool
    ) -> bool:
        """Blocking Yes/No prompt callable from background threads."""
        text = question + '?'

        async def _ask_on_ui():
            # Show the dialog on the main window; returns True/False
            assert isinstance(self.main_window, toga.Window)
            dialog = toga.QuestionDialog(title=title, message=text)
            return await self.main_window.dialog(dialog)

        # Schedule the coroutine on the UI loop and wait for the result
        fut = asyncio.run_coroutine_threadsafe(_ask_on_ui(), self.loop)
        try:
            return bool(fut.result())
        except Exception:
            return yes_is_default

    def handle_interactive_choices(
        self, title: str, question: str, choices: dict[str, str], default: str
    ) -> str | None:
        """
        Blocking wrapper callable from worker threads.
        Shows a Toga dialog on the UI loop and returns the selected KEY (or None).
        """

        async def _ask_on_ui() -> str | None:
            # Build a transient window as a custom dialog
            win = toga.Window(title=title, closable=False, size=(100, 100))

            # Map keys <-> display texts
            keys = list(choices.keys())
            texts = [choices[k] for k in keys]

            # Selection widget (dropdown)
            sel = toga.Selection(items=texts, style=Pack(flex=1))

            # Set default if present
            if default in choices:
                sel.value = choices[default]

            # Result future to complete when user acts
            loop = asyncio.get_running_loop()
            finished: asyncio.Future[str | None] = loop.create_future()

            def do_ok(widget, **kwargs):
                try:
                    val_text = sel.value
                    # Map back to key
                    selected_key = None
                    if val_text is not None:
                        assert isinstance(val_text, str)
                        try:
                            idx = texts.index(val_text)
                            selected_key = keys[idx]
                        except ValueError:
                            selected_key = None
                    if not finished.done():
                        finished.set_result(selected_key)
                finally:
                    win.close()

            # Layout
            question_lbl = toga.Label(question, style=Pack(margin_bottom=10))
            btn_ok = toga.Button('OK', on_press=do_ok, style=Pack(margin_top=6))

            btn_row = toga.Box(
                children=[btn_ok],
                style=Pack(direction=ROW, width=500, align_items='end'),
            )
            content = toga.Box(
                children=[question_lbl, sel, btn_row],
                style=Pack(direction=COLUMN, width=400, margin=10),
            )
            win.content = content

            # Show and wait
            win.show()
            return await finished

        # Schedule on UI loop and block here (worker thread)
        fut = asyncio.run_coroutine_threadsafe(_ask_on_ui(), self.loop)
        try:
            return fut.result()
        except Exception:
            return None

    def handle_interactive_message(self, message: str) -> bool:
        """Blocking Yes/No prompt callable from background threads."""

        async def _message_on_ui():
            # Show the dialog on the main window; returns True/False
            assert isinstance(self.main_window, toga.Window)
            dialog = toga.InfoDialog(
                title='Sharly Chess',
                message=message,
            )
            return await self.main_window.dialog(dialog)

        # Schedule the coroutine on the UI loop and wait for the result
        fut = asyncio.run_coroutine_threadsafe(_message_on_ui(), self.loop)
        try:
            return fut.result() is None
        except Exception:
            return False

    def quit_app(self, post_exit_task: Callable | None = None) -> None:
        loop = self.server_loop
        if loop is None or loop.is_closed():
            return

        def _stop() -> None:
            # Cancel the main server task
            if ServerEngine.server:
                asyncio.run_coroutine_threadsafe(ServerEngine.server.shutdown(), loop)
            task = self.serve_task
            if task is not None and not task.done():
                task.cancel()
            loop.stop()
            self.exit()
            if post_exit_task:
                post_exit_task()

        loop.call_soon_threadsafe(_stop)

    def _on_logview_load(self, widget, **kwargs: Any):
        # Wait one loop turn so the inline <script> in LOG_HTML actually runs
        async def _mark_ready_and_flush():
            await asyncio.sleep(0)  # next iteration guarantees <script> executed
            self._logview_ready = True
            if self._pending_js:
                # Flush safely; ignore individual eval errors
                for js in self._pending_js:
                    try:
                        assert self.html_view is not None
                        self.html_view.evaluate_javascript(js)
                    except Exception:
                        pass
                self._pending_js.clear()

        asyncio.create_task(_mark_ready_and_flush())

    def _eval_or_buffer_js(self, js: str):
        if self._logview_ready:
            try:
                assert self.html_view is not None
                self.html_view.evaluate_javascript(js)
            except Exception as e:
                print(e)
                pass
        else:
            self._pending_js.append(js)
