"""In-app image viewer for links that the terminal auto-opens.

The image is downloaded and rendered inside this program; no browser process is
started.  Decoding happens on the GUI thread, downloading in a QRunnable.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..errors import ToolError
from ..logging_setup import get_logger
from ..net.image import MAX_IMAGE_BYTES, ImageData, fetch_image
from ..version import APP_NAME

log = get_logger("image_viewer")
MAX_PIXELS = 40_000_000                    # refuse decompression bombs
MAX_SIDE = 16_384


class _Signals(QObject):
    done = Signal(object)                  # ImageData
    failed = Signal(str, str)              # message, detail


class ImageFetchTask(QRunnable):
    """Download one image off the GUI thread; only bytes cross back through signals."""

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.signals = _Signals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self):
        try:
            data = fetch_image(self.url, max_bytes=MAX_IMAGE_BYTES, cancel=self._cancel)
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
        self._url = ""

        self.image_label = QLabel("載入中…")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(320, 240)
        self.image_label.setStyleSheet("background: #202020; color: #dddddd;")
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.close_button = QPushButton("關閉")
        self.close_button.clicked.connect(self.close)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        lay = QVBoxLayout(self)
        lay.addWidget(self.image_label, 1)
        lay.addWidget(self.info)
        lay.addLayout(buttons)

    # ------------------------------------------------------------------ public
    def show_url(self, url: str) -> None:
        """Download and show one image, replacing any previous one."""
        self._cancel_task()
        self._url = url
        self._pixmap = None
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("載入中…")
        self.info.setText(url)
        self.show()
        self.raise_()
        task = ImageFetchTask(url)
        task.signals.done.connect(lambda data, t=task: self._on_done(t, data))
        task.signals.failed.connect(lambda msg, detail, t=task: self._on_failed(t, msg, detail))
        self._task = task
        QThreadPool.globalInstance().start(task)

    def current_url(self) -> str:
        return self._url

    def has_image(self) -> bool:
        return self._pixmap is not None

    # ------------------------------------------------------------------ slots
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
        self.info.setText(f"{message}\n{self._url}" + (f"\n{detail}" if detail else ""))

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
