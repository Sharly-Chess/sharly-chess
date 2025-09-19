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
import platform
import queue
import re
import threading
import webbrowser
from datetime import datetime
from typing import Optional, Any
from PIL import Image as PILImage

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import qrcode

from common import BASE_DIR, SHARLY_CHESS_VERSION
from common.i18n import _
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

    def escape_html(text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

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

    def __init__(self):
        system = platform.system()
        match system:
            case 'Windows':
                icon_file_name = 'sharly-chess.ico'
            case 'Darwin':
                icon_file_name = 'sharly-chess.icns'
            case 'Linux':
                raise NotImplementedError()
            case _:
                raise NotImplementedError(f'{system=}')
        super().__init__(
            formal_name='Sharly Chess',
            app_id='com.sharlychess.app',
            icon=BASE_DIR / 'src' / 'web' / 'static' / 'images' / icon_file_name,
            home_page='https://sharly-chess.com',
            version=str(SHARLY_CHESS_VERSION),
        )

        self._logview_ready = False
        self._pending_js: list[str] = []

        # State
        self.server_thread: Optional[threading.Thread] = None
        self.server_running = False
        self.sharly_chess_config: SharlyChessConfig = SharlyChessConfig()

        # Thread-safe communication
        self.message_queue: queue.Queue[tuple[str, str, Optional[str]]] = queue.Queue()
        self.log_cleared = False
        self.log_visible = False
        self.compact_size = (500, 100)
        self.expanded_size = (1200, 700)

        # GUI elements (initialized in startup)
        self.main_box: toga.Box
        self.browser_btn: toga.Button
        self.website_btn: toga.Button
        self.clear_btn: toga.Button
        self.toggle_log_btn: toga.Button
        self.log_view: toga.WebView
        self.info_view: toga.Box
        self.networks_section: toga.Box

        # Logging handler
        self.gui_handler = GUILogHandler(self)
        self.gui_handler.setLevel(logging.DEBUG)

    # --- Toga lifecycle ---
    def startup(self):
        SharlyChessConfig().load_and_set_env()
        # Delete unused menus
        for cmd in list(self.commands):
            grp = getattr(cmd, 'group', None)
            id_ = getattr(cmd, 'id', None)
            if id_ and grp is not toga.Group.APP:
                del self.commands[id_]

        # Toolbar (buttons row)
        btn_row = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 8, 0)))
        self.browser_btn = toga.Button(
            text=_('Open Admin Interface'), on_press=self._open_browser
        )
        self.website_btn = toga.Button(
            text=_('Open documentation'), on_press=self._open_website
        )
        self.clear_btn = toga.Button(text=_('Clear Log'), on_press=self._clear_log)
        self.clear_btn.style.visibility = 'hidden'
        self.toggle_log_btn = toga.Button(
            text=_('Show Log'),
            on_press=self._toggle_log_view,
        )

        for b in (
            self.browser_btn,
            self.website_btn,
            self.clear_btn,
            self.toggle_log_btn,
        ):
            b.style.margin_right = 4

        btn_row.add(self.website_btn)
        btn_row.add(self.toggle_log_btn)
        btn_row.add(self.clear_btn)

        # Log view: WebView with HTML for ANSI color support
        self.log_view = toga.WebView(
            style=Pack(flex=1), on_webview_load=self._on_logview_load
        )

        self.info_view = toga.Box(
            style=Pack(direction=COLUMN, margin=10, align_items='center')
        )
        self.info_view.add(
            toga.Label(text=_('Sharly Chess Server'), style=Pack(margin_bottom=7))
        )
        self.info_view.add(
            toga.Label(
                text=_('Version: {version}').format(version=SHARLY_CHESS_VERSION),
                style=Pack(margin_bottom=7),
            )
        )
        self.info_view.add(
            toga.Label(
                text=_('Warning: closing this window will stop Sharly Chess.'),
                style=Pack(margin_bottom=7),
            )
        )
        self.networks_section = toga.Box(
            style=Pack(direction=COLUMN, margin_top=10, align_items='center')
        )
        self.networks_section.add(self.browser_btn)
        self.info_view.add(self.networks_section)

        # Layout container
        self.main_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self.main_box.add(btn_row)
        self.main_box.add(self.info_view)

        self.main_window = toga.MainWindow(
            title=_('Sharly Chess server'),
            size=self.compact_size,
            content=self.main_box,
            on_gain_focus=self._noop,
            on_lose_focus=self._noop,
        )

        assert isinstance(self.main_window, toga.MainWindow)
        self.main_window.show()

    def on_running(self):
        self.log_view.set_content('about:blank', LOG_HTML)
        # Start message processing and kick the server immediately
        asyncio.create_task(self._process_message_queue())
        if not self.server_running:
            self._on_start_server(None)

    def make_link_button(self, url: str) -> toga.Label:
        button = toga.Button(url, style=Pack(align_items='center', margin_top=5))
        button.on_press = lambda widget, **kwargs: webbrowser.open(url)
        return button

    def on_server_ready(self):
        config = SharlyChessConfig()
        network_interfaces = config.lan_ifaces
        if network_interfaces := network_interfaces:
            self.networks_section.add(
                toga.Label(
                    text=_(
                        'You may also connect to this server from other devices using\nthe address of this server on your available networks:'
                    ),
                    margin_top=20,
                    align_items='center',
                    text_align='center',
                )
            )

            self.networks_view = toga.Box(
                style=Pack(direction=ROW, margin_top=15, gap=10)
            )
            self.networks_section.add(self.networks_view)
            for item in config.lan_ifaces:
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
                self.networks_view.add(network_item)

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
        asyncio.set_event_loop(loop)

        def schedule_ready():
            self.gui_loop.call_soon_threadsafe(self.on_server_ready)

        engine = ServerEngine(
            loop=loop, handle_signals=False, on_port_chosen=schedule_ready
        )
        loop.create_task(engine.serve())

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

    def _open_browser(self, widget: Any = None, **kwargs) -> None:
        try:
            url = self.sharly_chess_config.local_url
            webbrowser.open(url)
            self.add_log_message(f'Opening browser: {url}', 'success')
        except Exception as e:
            self.add_log_message(f'Failed to open browser: {e}', 'error')

    def _open_website(self, widget: Any = None, **kwargs) -> None:
        webbrowser.open(_('*** Doc Link'))

    def _toggle_log_view(self, widget: Any = None, **kwargs):
        self.log_visible = not self.log_visible

        # Show/hide log view
        self.log_view.style.visibility = 'visible' if self.log_visible else 'hidden'
        self.clear_btn.style.visibility = 'visible' if self.log_visible else 'hidden'
        self.log_view.refresh()

        # Update button label
        self.toggle_log_btn.text = _('Hide Log') if self.log_visible else _('Show Log')

        # Resize window to fit content
        assert isinstance(self.main_window, toga.MainWindow)
        if self.log_visible:
            if self.log_view not in self.main_box.children:
                self.main_box.add(self.log_view)
            if self.info_view in self.main_box.children:
                self.main_box.remove(self.info_view)
            self.main_window.size = self.expanded_size
        else:
            if self.log_view in self.main_box.children:
                self.main_box.remove(self.log_view)
            if self.info_view not in self.main_box.children:
                self.main_box.add(self.info_view)
            self.main_window.size = self.compact_size

    def _clear_log(self, widget: Any = None, **kwargs) -> None:
        self.log_cleared = True
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

    # --- Interactive prompts ---
    def handle_interactive_yn(self, question: str, yes_is_default: bool) -> bool:
        """Blocking Yes/No prompt callable from background threads."""
        text = question + '?'

        async def _ask_on_ui():
            # Show the dialog on the main window; returns True/False
            assert isinstance(self.main_window, toga.MainWindow)
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

    def _on_logview_load(self, widget, **kwargs: Any):
        # Wait one loop turn so the inline <script> in LOG_HTML actually runs
        async def _mark_ready_and_flush():
            await asyncio.sleep(0)  # next iteration guarantees <script> executed
            self._logview_ready = True
            if self._pending_js:
                # Flush safely; ignore individual eval errors
                for js in self._pending_js:
                    try:
                        self.log_view.evaluate_javascript(js)
                    except Exception:
                        pass
                self._pending_js.clear()

        asyncio.create_task(_mark_ready_and_flush())

    def _eval_or_buffer_js(self, js: str):
        if self._logview_ready:
            try:
                self.log_view.evaluate_javascript(js)
            except Exception as e:
                print(e)
                pass
        else:
            self._pending_js.append(js)
