"""Background QRunnables used by the main window.

Kept out of main_window.py so the window only wires UI events to plain-data signals;
none of these tasks touches widgets directly.
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from .. import sites, update
from ..errors import ToolError
from ..logging_setup import get_logger
from ..net.image import download_images_zip
from ..net.image_meta import strip_metadata
from ..net.shortener import shorten_url
from ..net.upload import upload_images
from ..parsers.extract import parse
from ..parsers.fetch import fetch

log = get_logger("ui.tasks")


class _Signals(QObject):
    done = Signal(object, object)    # Fetched, ParseResult
    failed = Signal(str, str)        # message, detail


class FetchTask(QRunnable):
    """Network + parsing off the GUI thread. Only plain data crosses back through signals."""

    def __init__(self, url: str, ignore_robots: bool):
        super().__init__()
        self.url, self.ignore_robots = url, ignore_robots
        self.signals = _Signals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Ask a running fetch to stop at the next safe point (sleep / chunk boundary)."""
        self._cancel.set()

    def run(self):
        try:
            f = fetch(self.url, ignore_robots=self.ignore_robots, cancel=self._cancel)
            if self._cancel.is_set():                         # the window is closing: do not touch anything
                return
            res = parse(f.html, f.final_url, f.warnings)
            self.signals.done.emit(f, res)
        except ToolError as e:
            if not self._cancel.is_set():
                self.signals.failed.emit(e.message, e.detail)
        except Exception as e:  # noqa: BLE001  (a parser bug must never kill the app)
            log.exception("unexpected error while fetching/parsing")
            if not self._cancel.is_set():
                self.signals.failed.emit("擷取時發生未預期的錯誤。", f"{type(e).__name__}: {e}")


class _UpdateSignals(QObject):
    done = Signal(object)             # update.Release
    failed = Signal(str)


class UpdateCheckTask(QRunnable):
    """GitHub API call off the GUI thread; never downloads in this task."""

    def __init__(self, token: str | None):
        super().__init__()
        self.token = token
        self.signals = _UpdateSignals()

    def run(self):
        try:
            self.signals.done.emit(update.fetch_latest_release(self.token))
        except update.UpdateError as e:
            self.signals.failed.emit(str(e))
        except Exception:  # noqa: BLE001
            log.exception("unexpected error while checking updates")
            self.signals.failed.emit("檢查更新時發生未預期的錯誤。")


class _DownloadSignals(QObject):
    progress = Signal(int, int)
    done = Signal(object)             # update.DownloadResult
    failed = Signal(str)


class UpdateDownloadTask(QRunnable):
    """Download one verified update asset; the UI never executes it automatically."""

    def __init__(self, asset: update.Asset, token: str | None):
        super().__init__()
        self.asset, self.token = asset, token
        self.signals = _DownloadSignals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self):
        try:
            result = update.download_asset(self.asset, token=self.token,
                                           cancel=self._cancel,
                                           progress=lambda done, total: self.signals.progress.emit(done, total))
            if not self._cancel.is_set():
                self.signals.done.emit(result)
        except update.UpdateError as e:
            if not self._cancel.is_set():
                self.signals.failed.emit(str(e))
        except Exception:  # noqa: BLE001
            log.exception("unexpected error while downloading an update")
            if not self._cancel.is_set():
                self.signals.failed.emit("下載更新檔時發生未預期的錯誤。")


class _SiteCheckSignals(QObject):
    done = Signal(bool, str)


class SiteCheckTask(QRunnable):
    """Read-only TCP reachability check; no login bytes are sent."""

    def __init__(self, site: dict):
        super().__init__()
        self.site = site
        self.signals = _SiteCheckSignals()

    def run(self):
        ok, msg = sites.check_site(self.site)
        self.signals.done.emit(ok, msg)


class _ZipSignals(QObject):
    progress = Signal(int, int)
    done = Signal(object)                  # image.ZipResult
    failed = Signal(str)


class ArticleImagesZipTask(QRunnable):
    """Download the article's original images into one ZIP off the GUI thread."""

    def __init__(self, urls: list[str], target: Path, referer: str):
        super().__init__()
        self.urls, self.target, self.referer = urls, target, referer
        self.signals = _ZipSignals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self):
        try:
            result = download_images_zip(
                self.urls, self.target, referer=self.referer, cancel=self._cancel,
                progress=lambda done, total: self.signals.progress.emit(done, total))
            if not self._cancel.is_set():
                self.signals.done.emit(result)
        except ToolError as e:
            if not self._cancel.is_set():
                self.signals.failed.emit(e.message)
        except Exception as e:  # noqa: BLE001
            log.exception("unexpected error while zipping article images")
            if not self._cancel.is_set():
                self.signals.failed.emit(f"打包圖片時發生未預期的錯誤（{type(e).__name__}）。")


class _UploadSignals(QObject):
    progress = Signal(int, int, str)
    done = Signal(object)                  # UploadBatch
    failed = Signal(str)


class ImageUploadTask(QRunnable):
    """Upload selected local images to an anonymous public host, one at a time."""

    def __init__(self, paths: list[str], host_key: str, strip_exif: bool = False):
        super().__init__()
        self.paths, self.host_key, self.strip_exif = paths, host_key, strip_exif
        self.signals = _UploadSignals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self):
        temp = None
        try:
            paths, errors = self.paths, []
            if self.strip_exif:
                temp = tempfile.TemporaryDirectory(prefix="pttpost-upload-")
                paths = []
                for i, path in enumerate(self.paths):
                    try:
                        dest = Path(temp.name) / str(i) / Path(path).name
                        paths.append(str(strip_metadata(path, dest)))
                    except Exception:  # noqa: BLE001
                        log.exception("could not strip image metadata: %s", path)
                        errors.append((Path(path).name, "無法移除 EXIF／中繼資料，已跳過上傳。"))
            batch = upload_images(
                paths, self.host_key, cancel=self._cancel,
                progress=lambda i, n, name: self.signals.progress.emit(i, n, name))
            batch.errors[:0] = errors
            if not self._cancel.is_set():
                self.signals.done.emit(batch)
        except ToolError as e:
            if not self._cancel.is_set():
                self.signals.failed.emit(e.message)
        except Exception as e:  # noqa: BLE001
            log.exception("unexpected error while uploading images")
            if not self._cancel.is_set():
                self.signals.failed.emit(f"上傳圖片時發生未預期的錯誤（{type(e).__name__}）。")
        finally:
            if temp is not None:
                temp.cleanup()


class _ShortenSignals(QObject):
    done = Signal(str)
    failed = Signal(str)


class ShortenTask(QRunnable):
    """Shorten one URL off the UI thread; the caller updates fields only on success."""

    def __init__(self, service_key: str, url: str):
        super().__init__()
        self.service_key, self.url = service_key, url
        self.signals = _ShortenSignals()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self):
        try:
            short = shorten_url(self.service_key, self.url, cancel=self._cancel)
            if not self._cancel.is_set():
                self.signals.done.emit(short)
        except ToolError as e:
            if not self._cancel.is_set():
                self.signals.failed.emit(e.message)
        except Exception as e:  # noqa: BLE001
            log.exception("unexpected error while shortening a URL")
            if not self._cancel.is_set():
                self.signals.failed.emit(f"縮網址時發生未預期的錯誤（{type(e).__name__}）。")


