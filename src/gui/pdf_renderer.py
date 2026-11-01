"""PDF rendering of print documents with the web engine of the platform.

The page is loaded in a web view of a window that is never shown, then printed
to a file as the print of a browser does: on A4 paper, with the print styles of
the page.
"""

import asyncio
import base64
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import toga

from data.print_documents.page_margins import PageMargins
from data.print_documents.pdf_rendering import PdfRenderer, PdfRenderingError

_A4_WIDTH_MM = 210
_A4_HEIGHT_MM = 297
_MM_PER_INCH = 25.4
_POINTS_PER_INCH = 72
_POINTS_PER_MM = _POINTS_PER_INCH / _MM_PER_INCH
_TIMEOUT = 90


class TogaPdfRenderer(PdfRenderer):
    def __init__(self, gui_loop: asyncio.AbstractEventLoop):
        self.gui_loop = gui_loop
        self.window: toga.Window | None = None
        self.web_view: toga.WebView | None = None
        self.lock: asyncio.Lock | None = None

    async def render(self, url: str, margins: PageMargins) -> bytes:
        # The rendering runs on the loop of the interface, which the time
        # limit, taken here, cancels.
        future = asyncio.run_coroutine_threadsafe(
            self._render(url, margins), self.gui_loop
        )
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), _TIMEOUT)
        except TimeoutError as error:
            raise PdfRenderingError('The page took too long to render.') from error

    async def _render(self, url: str, margins: PageMargins) -> bytes:
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            web_view = self._web_view()
            try:
                _ = await web_view.load_url(url)
                await _until_drawn(web_view)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'document.pdf'
                    await _print(web_view, path, margins)
                    return path.read_bytes()
            finally:
                web_view.url = None

    def _web_view(self) -> toga.WebView:
        if self.web_view is None:
            self.web_view = toga.WebView()
            self.window = toga.Window(
                title='PDF',
                size=(
                    round(_A4_WIDTH_MM * 96 / _MM_PER_INCH),
                    round(_A4_HEIGHT_MM * 96 / _MM_PER_INCH),
                ),
            )
            self.window.content = self.web_view
            if toga.platform.current_platform == 'windows':
                # WebView2 starts once its control has a window handle, which
                # a window that is not shown gets only when asked for it.
                _ = self.window._impl.native.Handle
                _ = self.web_view._impl.native.Handle
        return self.web_view


async def _until_drawn(web_view: toga.WebView) -> None:
    """Wait for the fonts of the page, then for the page to be drawn with
    them: a page printed before is blank."""
    for _ in range(100):
        if await web_view.evaluate_javascript('document.fonts.status') == 'loaded':
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)


async def _print(web_view: toga.WebView, path: Path, margins: PageMargins) -> None:
    match toga.platform.current_platform:
        case 'macOS':
            await _print_cocoa(web_view, path, margins)
        case 'windows':
            await _print_winforms(web_view, path, margins)
        case 'linux':
            await _print_gtk(web_view, path, margins)
        case platform:
            raise PdfRenderingError(f'No PDF rendering on [{platform}].')


def _completion() -> tuple[asyncio.Future[None], Callable[[bool, str], None]]:
    """A future, and the function completing it from the native callback of a
    print."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[None] = loop.create_future()

    def complete(success: bool, message: str) -> None:
        def set_result() -> None:
            if future.done():
                return
            if success:
                future.set_result(None)
            else:
                future.set_exception(PdfRenderingError(message))

        loop.call_soon_threadsafe(set_result)

    return future, complete


_cocoa_print_delegate_class: Any = None


def _cocoa_print_delegate(complete: Callable[[bool, str], None]) -> Any:
    from rubicon.objc import NSObject, ObjCInstance, objc_method

    global _cocoa_print_delegate_class
    if _cocoa_print_delegate_class is None:

        class PdfPrintDelegate(NSObject):
            @objc_method
            def printOperationDidRun_success_contextInfo_(
                self, operation: ObjCInstance, success: bool, context: ObjCInstance
            ) -> None:
                self.complete(bool(success), 'The print operation failed.')

        _cocoa_print_delegate_class = PdfPrintDelegate
    delegate = _cocoa_print_delegate_class.alloc().init()
    delegate.complete = complete
    return delegate


async def _print_cocoa(
    web_view: toga.WebView, path: Path, margins: PageMargins
) -> None:
    from rubicon.objc import SEL, NSMakeRect, NSMakeSize, ObjCClass

    ns_print_info = ObjCClass('NSPrintInfo')
    ns_url = ObjCClass('NSURL')
    info = ns_print_info.sharedPrintInfo.copy()
    info.paperSize = NSMakeSize(
        _A4_WIDTH_MM * _POINTS_PER_MM, _A4_HEIGHT_MM * _POINTS_PER_MM
    )
    info.topMargin = margins.top
    info.rightMargin = margins.right
    info.bottomMargin = margins.bottom
    info.leftMargin = margins.left
    info.horizontallyCentered = False
    info.verticallyCentered = False
    info.jobDisposition = 'NSPrintSaveJob'
    info.dictionary().setObject(
        ns_url.fileURLWithPath(str(path)), forKey='NSJobSavingURL'
    )
    # A print to the printer of the computer is never started.
    if str(info.jobDisposition) != 'NSPrintSaveJob':
        raise PdfRenderingError('The print could not be made to a file.')
    future, complete = _completion()
    delegate = _cocoa_print_delegate(complete)
    operation = web_view._impl.native.printOperationWithPrintInfo(info)
    operation.showsPrintPanel = False
    operation.showsProgressPanel = False
    # The printing view of a web view has no size of its own.
    operation.view.frame = NSMakeRect(
        0, 0, _A4_WIDTH_MM * _POINTS_PER_MM, _A4_HEIGHT_MM * _POINTS_PER_MM
    )
    window = web_view.window
    assert window is not None
    operation.runOperationModalForWindow(
        window._impl.native,
        delegate=delegate,
        didRunSelector=SEL('printOperationDidRun:success:contextInfo:'),
        contextInfo=None,
    )
    await future


async def _print_winforms(
    web_view: toga.WebView, path: Path, margins: PageMargins
) -> None:
    from System import Action, String  # type: ignore[import-not-found]
    from System.Threading.Tasks import (  # type: ignore[import-not-found]
        Task,
        TaskScheduler,
    )

    # The print of the DevTools protocol returns the PDF file, or the reason
    # of its failure, where the print to a file of WebView2 tells only that it
    # failed.
    parameters = json.dumps(
        {
            'paperWidth': _A4_WIDTH_MM / _MM_PER_INCH,
            'paperHeight': _A4_HEIGHT_MM / _MM_PER_INCH,
            'marginTop': margins.top / _POINTS_PER_INCH,
            'marginRight': margins.right / _POINTS_PER_INCH,
            'marginBottom': margins.bottom / _POINTS_PER_INCH,
            'marginLeft': margins.left / _POINTS_PER_INCH,
            'printBackground': True,
            'displayHeaderFooter': False,
            'preferCSSPageSize': False,
        }
    )
    future, complete = _completion()

    def completed(task: Any) -> None:
        if task.IsFaulted:
            complete(False, f'The print to PDF failed: {task.Exception}')
            return
        try:
            path.write_bytes(base64.b64decode(json.loads(str(task.Result))['data']))
        except (OSError, ValueError, KeyError, TypeError) as error:
            complete(False, f'The PDF file could not be read: {error}')
        else:
            complete(True, '')

    web_view._impl.native.CoreWebView2.CallDevToolsProtocolMethodAsync(
        'Page.printToPDF', parameters
    ).ContinueWith(
        Action[Task[String]](completed),
        TaskScheduler.FromCurrentSynchronizationContext(),
    )
    await future


async def _print_gtk(web_view: toga.WebView, path: Path, margins: PageMargins) -> None:
    from toga_gtk.libs import Gtk, WebKit2

    operation = WebKit2.PrintOperation.new(web_view._impl.native)
    settings = Gtk.PrintSettings.new()
    settings.set_printer('Print to File')
    settings.set(Gtk.PRINT_SETTINGS_OUTPUT_FILE_FORMAT, 'pdf')
    settings.set(Gtk.PRINT_SETTINGS_OUTPUT_URI, path.as_uri())
    operation.set_print_settings(settings)
    page_setup = Gtk.PageSetup.new()
    page_setup.set_paper_size(Gtk.PaperSize.new(Gtk.PAPER_NAME_A4))
    page_setup.set_top_margin(margins.top, Gtk.Unit.POINTS)
    page_setup.set_right_margin(margins.right, Gtk.Unit.POINTS)
    page_setup.set_bottom_margin(margins.bottom, Gtk.Unit.POINTS)
    page_setup.set_left_margin(margins.left, Gtk.Unit.POINTS)
    operation.set_page_setup(page_setup)
    future, complete = _completion()
    operation.connect('finished', lambda _operation: complete(True, ''))
    operation.connect(
        'failed', lambda _operation, error: complete(False, str(error.message))
    )
    # PyGObject may name the method print_, print being a Python builtin.
    print_page = getattr(operation, 'print_', None) or operation.print
    print_page()
    await future
