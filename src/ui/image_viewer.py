"""In-app image viewer for auto-opened / hovered / article images.

The image is downloaded and rendered inside this program; no browser process is
started.  Decoding happens on the GUI thread, downloading in a QRunnable.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QPoint, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QGuiApplication, QImageReader, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..errors import ToolError
from ..logging_setup import get_logger
from ..net.image import MAX_IMAGE_BYTES, ImageData, fetch_image
from ..version import APP_NAME

log = get_logger("image_viewer")
MAX_PIXELS = 40_000_000                    # refuse decompression bombs
MAX_SIDE = 16_384
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_CACHE_ITEMS = 16
_cache: OrderedDict[str, ImageData] = OrderedDict()
_cache_lock = threading.Lock()
_cache_bytes = 0


def cache_get(url: str) -> ImageData | None:
    with _cache_lock:
        data = _cache.get(url)
        if data is not None:
            _cache.move_to_end(url)
        return data


def cache_put(url: str, data: ImageData) -> None:
    global _cache_bytes
    with _cache_lock:
        old = _cache.pop(url, None)
        if old is not None:
            _cache_bytes -= len(old.data)
        _cache[url] = data
        _cache_bytes += len(data.data)
        while _cache and (_cache_bytes > MAX_CACHE_BYTES or len(_cache) > MAX_CACHE_ITEMS):
            _url, dropped = _cache.popitem(last=False)
            _cache_bytes -= len(dropped.data)


def cache_clear() -> None:
    global _cache_bytes
    with _cache_lock:
        _cache.clear()
        _cache_bytes = 0


class _Signals(QObject):
    done = Signal(object)                  # ImageData
    failed = Signal(str, str)              # message, detail


class ImageFetchTask(QRunnable):
    """Download one image off the GUI thread; only bytes cross back through signals."""

    def __init__(self, url: str, strict_host: bool = True):
        super().__init__()
        self.url = url
        self.strict_host = strict_host
        self.signals = _Signals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self):
        try:
            cached = cache_get(self.url)
            if cached is not None:
                if not self._cancel.is_set():
                    self.signals.done.emit(cached)
                return
            data = fetch_image(self.url, max_bytes=MAX_IMAGE_BYTES, cancel=self._cancel,
                               strict_host=self.strict_host)
            cache_put(self.url, data)
            if not self._cancel.is_set():
                self.signals.done.emit(data)
        except ToolError as e:
            if not self._cancel.is_set():
                self.signals.failed.emit(e.message, e.detail)
        except Exception as e:  # noqa: BLE001  (a viewer bug must never kill the app)
            log.exception("unexpected error while fetching an image")
            if not self._cancel.is_set():
                self.signals.failed.emit("讀取圖片時發生未預期的錯誤。", f"{type(e).__name__}: {e}")


def decode_image(data: bytes) -> tuple[QPixmap | None, str]:
    """Decode bytes with Qt's image plugins; returns (pixmap, error message)."""
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    try:
        reader = QImageReader(buf)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and (size.width() > MAX_SIDE or size.height() > MAX_SIDE
                               or size.width() * size.height() > MAX_PIXELS):
            return None, "圖片尺寸過大，已停止顯示。"
        img = reader.read()
        if img.isNull():
            return None, f"無法顯示此圖片（{reader.errorString() or '不支援的格式'}）。"
        if img.width() > MAX_SIDE or img.height() > MAX_SIDE or img.width() * img.height() > MAX_PIXELS:
            return None, "圖片尺寸過大，已停止顯示。"
        return QPixmap.fromImage(img), ""
    finally:
        buf.close()


class ImageViewer(QDialog):
    """Modeless, non-activating preview window owned by the main window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"圖片預覽 - {APP_NAME}")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)   # never steal terminal keystrokes
        self.setModal(False)
        self.resize(880, 660)
        self._pixmap: QPixmap | None = None
        self._task: ImageFetchTask | None = None
        self._urls: list[str] = []
        self._index = 0
        self._strict = True

        self.image_label = QLabel("載入中…")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(320, 240)
        self.image_label.setStyleSheet("background: #202020; color: #dddddd;")
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.prev_button = QPushButton("上一張")
        self.next_button = QPushButton("下一張")
        self.count_label = QLabel("")
        self.close_button = QPushButton("關閉")
        self.prev_button.clicked.connect(self.show_previous)
        self.next_button.clicked.connect(self.show_next)
        self.close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.addWidget(self.prev_button)
        buttons.addWidget(self.next_button)
        buttons.addWidget(self.count_label)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        lay = QVBoxLayout(self)
        lay.addWidget(self.image_label, 1)
        lay.addWidget(self.info)
        lay.addLayout(buttons)
        self._update_nav()

    # ------------------------------------------------------------------ public
    def show_url(self, url: str) -> None:
        self.show_images([url])

    def show_images(self, urls: list[str], strict: bool = True) -> None:
        """Show one image or a gallery; duplicates are removed and the first image is loaded."""
        unique = list(dict.fromkeys(u for u in urls if u))
        if not unique:
            return
        self._urls, self._index, self._strict = unique, 0, strict
        self._update_nav()
        self.show()
        self.raise_()
        self._load_current()

    def current_url(self) -> str:
        return self._urls[self._index] if self._urls else ""

    def has_image(self) -> bool:
        return self._pixmap is not None

    def show_previous(self) -> None:
        if len(self._urls) > 1:
            self._index = (self._index - 1) % len(self._urls)
            self._load_current()

    def show_next(self) -> None:
        if len(self._urls) > 1:
            self._index = (self._index + 1) % len(self._urls)
            self._load_current()

    # ------------------------------------------------------------------ internals
    def _update_nav(self) -> None:
        many = len(self._urls) > 1
        self.prev_button.setEnabled(many)
        self.next_button.setEnabled(many)
        self.count_label.setText(f"{self._index + 1} / {len(self._urls)}" if many else "")

    def _load_current(self) -> None:
        self._cancel_task()
        url = self.current_url()
        self._pixmap = None
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("載入中…")
        self.info.setText(url)
        self._update_nav()
        task = ImageFetchTask(url, self._strict)
        task.signals.done.connect(lambda data, t=task: self._on_done(t, data))
        task.signals.failed.connect(lambda msg, detail, t=task: self._on_failed(t, msg, detail))
        self._task = task
        QThreadPool.globalInstance().start(task)

    def _on_done(self, task: ImageFetchTask, data: ImageData) -> None:
        if self._task is not task:
            return                                         # a newer image replaced this download
        self._task = None
        pixmap, error = decode_image(data.data)
        if pixmap is None:
            self.image_label.setText(error)
            self.info.setText(f"{error}\n{data.url}")
            return
        self._pixmap = pixmap
        self._update_pixmap()
        self.info.setText(f"{pixmap.width()} x {pixmap.height()} · {len(data.data) / 1024:.0f} KB · "
                          f"{data.content_type}\n{data.url}")

    def _on_failed(self, task: ImageFetchTask, message: str, detail: str) -> None:
        if self._task is not task:
            return
        self._task = None
        self.image_label.setText(message)
        self.info.setText(f"{message}\n{self.current_url()}" + (f"\n{detail}" if detail else ""))

    # ------------------------------------------------------------------ geometry
    def _update_pixmap(self) -> None:
        if self._pixmap is None:
            return
        area = self.image_label.size()
        if area.width() < 2 or area.height() < 2:
            return
        if self._pixmap.width() <= area.width() and self._pixmap.height() <= area.height():
            self.image_label.setPixmap(self._pixmap)
            return
        self.image_label.setPixmap(self._pixmap.scaled(
            area, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_pixmap()

    def _cancel_task(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            self._disconnect(task)

    @staticmethod
    def _disconnect(task) -> None:
        signals = getattr(task, "signals", None)
        if signals is not None:
            try:
                signals.done.disconnect()
                signals.failed.disconnect()
            except (RuntimeError, TypeError):
                pass

    def closeEvent(self, e):
        self._cancel_task()
        self._pixmap = None
        self.image_label.clear()
        super().closeEvent(e)


class ImageHoverPreview(QWidget):
    """Small frameless preview that follows the pointer over an image link."""

    MAX_WIDTH = 360
    MAX_HEIGHT = 280

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: #111111; color: #eeeeee; border: 1px solid #666666;")
        self.label = QLabel("載入中…", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: none;")
        self.resize(self.MAX_WIDTH, 200)
        self._task: ImageFetchTask | None = None
        self._url = ""
        self._pixmap: QPixmap | None = None

    def show_url(self, url: str, pos: QPoint | None = None) -> None:
        if url == self._url and self.isVisible():
            if pos is not None:
                self._move_to(pos)
            return
        self._cancel_task()
        self._url = url
        self._pixmap = None
        self.label.setPixmap(QPixmap())
        self.label.setText("載入中…")
        self.resize(self.MAX_WIDTH, 120)
        if pos is not None:
            self._move_to(pos)
        self.show()
        self.raise_()
        task = ImageFetchTask(url, strict_host=True)
        task.signals.done.connect(lambda data, t=task: self._on_done(t, data))
        task.signals.failed.connect(lambda msg, detail, t=task: self._on_failed(t, msg, detail))
        self._task = task
        QThreadPool.globalInstance().start(task)

    def hide_preview(self) -> None:
        self._cancel_task()
        self._url = ""
        self._pixmap = None
        self.label.clear()
        self.hide()

    def _on_done(self, task: ImageFetchTask, data: ImageData) -> None:
        if self._task is not task:
            return
        self._task = None
        pixmap, error = decode_image(data.data)
        if pixmap is None:
            self._show_error(error)
            return
        self._pixmap = pixmap
        scaled = pixmap.scaled(self.MAX_WIDTH - 8, self.MAX_HEIGHT - 8,
                               Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.label.setText("")
        self.label.setPixmap(scaled)
        self.resize(scaled.width() + 8, scaled.height() + 8)
        self._move_to(self.pos() - QPoint(16, 16))

    def _on_failed(self, task: ImageFetchTask, message: str, detail: str) -> None:
        if self._task is not task:
            return
        self._task = None
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.label.setPixmap(QPixmap())
        self.label.setText(message)
        self.resize(260, 60)

    def _move_to(self, pos: QPoint) -> None:
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = scr.availableGeometry() if scr is not None else None
        x, y = pos.x() + 16, pos.y() + 16
        if area is not None:
            x = min(max(x, area.left()), area.right() - self.width() + 1)
            y = min(max(y, area.top()), area.bottom() - self.height() + 1)
        self.move(x, y)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.label.setGeometry(self.rect().adjusted(4, 4, -4, -4))

    def _cancel_task(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            ImageViewer._disconnect(task)

    def closeEvent(self, e):
        self._cancel_task()
        super().closeEvent(e)
