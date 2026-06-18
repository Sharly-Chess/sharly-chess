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
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from PIL import Image as PILImage

import toga
from toga.sources import ListSource
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import qrcode

import web
from common import SHARLY_CHESS_VERSION, BASE_DIR
from common.i18n import _
from database.sqlite.config.config_database import ConfigDatabase
from gui.gui_logger import GUILogHandler
from web.server_engine import ServerEngine
from common.sharly_chess_config import SharlyChessConfig

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
        app_id = os.environ.get('FLATPAK_ID', 'com.sharlychess.app')

        super().__init__(
            formal_name='Sharly Chess',
            app_id=app_id,
            icon=icon_path,
            home_page='https://sharly-chess.com',
            version=str(SHARLY_CHESS_VERSION),
        )
        self.debug = debug
        self.port = port

        self._logview_ready = False
        self._pending_js: list[str] = []

        # State
        self.server_thread: Optional[threading.Thread] = None
        self.serve_task: asyncio.Task | None = None
        self.server_running = False
        self.sharly_chess_config: SharlyChessConfig = SharlyChessConfig()

        # Thread-safe communication
        self.message_queue: queue.Queue[tuple[str, str, Optional[str]]] = queue.Queue()
        self.compact_size = (400, 100)
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
        self.server_start_progress_bar: Optional[toga.ProgressBar] = None

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
        config = SharlyChessConfig()

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
            style=Pack(direction=COLUMN, margin=10, gap=5, align_items='center'),
        )
        self.server_state_container = toga.Box(
            style=Pack(direction=COLUMN, align_items='center')
        )
        self.server_start_progress_bar = toga.ProgressBar()
        self.server_start_progress_bar.max = None
        self.server_state_container.add(self.server_start_progress_bar)
        doc_btn = toga.Button(_('Open documentation'), on_press=self._open_website)
        self.home_view.add(
            toga.Label(
                _('Warning: closing this window will stop Sharly Chess.'),
                text_align='center',
            ),
            self.server_state_container,
            toga.Divider(style=Pack(margin=(5, 0))),
            toga.Box(children=[doc_btn]),
            toga.Box(
                style=Pack(align_items='center'),
                children=[
                    toga.Label(f'Sharly Chess {SHARLY_CHESS_VERSION} -'),
                    toga.Button(_('Support us')),
                ],
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
        log_buttons.add(self.log_settings_btn, clear_logs_btn)
        self.logs_view.add(log_buttons)
        config = SharlyChessConfig()
        log_level_options = [
            {'level': console_log_level, 'text': console_log_level_str}
            for console_log_level, console_log_level_str in config.console_log_levels.items()
        ]
        level_label = toga.Label(_('Minimum level:'), margin_top=2)
        self.log_level_select = toga.Selection(
            items=log_level_options,
            accessor='text',
            on_change=self._on_level_change,
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
        switch_container = toga.Box(
            margin_top=2,
            children=[
                self.log_color_switch,
                self.show_log_level_switch,
                self.show_log_time_switch,
            ],
            gap=10,
            margin_left=20,
        )
        self.log_settings = toga.Box(
            style=Pack(direction=ROW, margin_bottom=10, visibility='hidden')
        )
        self.log_settings.add(level_label, self.log_level_select, switch_container)
        self.log_settings_container = toga.Box()
        self.logs_view.add(self.log_settings_container)
        self.logs_view.add(self.html_view)

        # Settings view
        self.settings_view = toga.Box(
            style=Pack(
                direction=COLUMN,
                margin=10,
                gap=7,
                align_items='center',
            )
        )
        self.launch_browser_switch = toga.Switch(
            text=_('Launch a browser on startup'),
            value=config.launch_browser,
            on_change=self._on_launch_browser_switch_change,
        )
        self.settings_view.add(
            toga.Box(children=[self.launch_browser_switch]),
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
        self.compact_size = self.main_window.size

    def update_from_sharly_chess_config(self):
        sharly_chess_config: SharlyChessConfig = SharlyChessConfig()
        assert self.launch_browser_switch is not None
        self.launch_browser_switch.value = sharly_chess_config.launch_browser
        assert self.log_level_select is not None and isinstance(
            self.log_level_select.items, ListSource
        )
        self.log_level_select.value = self.log_level_select.items.find(
            data={'level': sharly_chess_config.console_log_level}
        )
        assert self.log_color_switch is not None
        self.log_color_switch.value = sharly_chess_config.console_color
        assert self.show_log_level_switch is not None
        self.show_log_level_switch.value = sharly_chess_config.console_show_level
        assert self.show_log_time_switch is not None
        self.show_log_time_switch.value = sharly_chess_config.console_show_date

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

    def on_running(self):
        # Logging handler
        assert self.html_view is not None
        self.html_view.set_content('about:blank', LOG_HTML)
        self.gui_handler = GUILogHandler(self)
        self.gui_handler.setLevel(logging.DEBUG)

        assert self.server_start_progress_bar is not None
        self.server_start_progress_bar.value = 1
        self.server_start_progress_bar.start()

        # Start message processing and kick the server immediately
        asyncio.create_task(self._process_message_queue())
        if not self.server_running:
            self._on_start_server(None)

    def make_link_button(self, url: str) -> toga.Label:
        button = toga.Button(url, style=Pack(align_items='center', margin_top=5))
        button.on_press = lambda widget, **kwargs: webbrowser.open(url)
        return button

    def on_server_ready(self):
        assert self.server_start_progress_bar is not None
        assert self.server_state_container is not None
        self.server_start_progress_bar.stop()
        self.server_state_container.clear()
        self.server_state_container.add(
            toga.Box(
                style=Pack(direction=ROW, align_items='center'),
                children=[
                    toga.Label(_('{string}:').format(string=_('Home page'))),
                    toga.Button(
                        SharlyChessConfig().local_url, on_press=self._open_browser
                    ),
                ],
            )
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
                    text=_('the address of this server on your available networks:'),
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
        self.gui_loop = asyncio.get_event_loop()
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

    def _run_server(self) -> None:
        # IMPORTANT: bypass Toga's event-loop policy in this *background* thread
        self.server_loop = asyncio.SelectorEventLoop()
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
            url = self.sharly_chess_config.local_url
            webbrowser.open(url)
            self.add_log_message(f'Opening browser: {url}', 'success')
        except Exception as e:
            self.add_log_message(f'Failed to open browser: {e}', 'error')

    def _open_website(self, widget: Any = None, **kwargs) -> None:
        webbrowser.open(_('*** Doc Link'))

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

    def _update_config(self, field: str, value):
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

    # --- Interactive prompts ---
    def handle_interactive_yn(self, question: str, yes_is_default: bool) -> bool:
        """Blocking Yes/No prompt callable from background threads."""
        text = question + '?'

        async def _ask_on_ui():
            # Show the dialog on the main window; returns True/False
            assert isinstance(self.main_window, toga.Window)
            dialog = toga.QuestionDialog(
                title=_('Server Setup'),
                message=text,
            )
            return await self.main_window.dialog(dialog)

        # Schedule the coroutine on the UI loop and wait for the result
        fut = asyncio.run_coroutine_threadsafe(_ask_on_ui(), self.loop)
        try:
            return bool(fut.result())
        except Exception:
            return yes_is_default

    def handle_interactive_choices(
        self, question: str, choices: dict[str, str], default: str
    ) -> str | None:
        """
        Blocking wrapper callable from worker threads.
        Shows a Toga dialog on the UI loop and returns the selected KEY (or None).
        """

        async def _ask_on_ui() -> str | None:
            # Build a transient window as a custom dialog
            win = toga.Window(title=_('Server Setup'), closable=False, size=(100, 100))

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

    def quit_app(self) -> None:
        loop = self.server_loop
        if loop is None or loop.is_closed():
            return

        def _stop() -> None:
            # Cancel the main server task
            task = self.serve_task
            if task is not None and not task.done():
                task.cancel()
            loop.stop()

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
