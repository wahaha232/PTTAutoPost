from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from conftest import wait_until
from src.errors import FetchError
from src.net.image import ImageData
from src.ui import image_viewer
from src.ui.image_viewer import ImageViewer, decode_image


def _png(width=32, height=24) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#3366cc"))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return data


def test_decode_png_and_junk(qapp):
    pixmap, error = decode_image(_png())
    assert pixmap is not None and error == ""
    assert (pixmap.width(), pixmap.height()) == (32, 24)
    pixmap, error = decode_image(b"not an image")
    assert pixmap is None and "無法顯示" in error


def test_viewer_displays_the_image_inside_the_dialog(qapp, monkeypatch):
    monkeypatch.setattr(image_viewer, "fetch_image",
                        lambda url, **kw: ImageData(url, "image/png", _png()))
    viewer = ImageViewer()
    viewer.show_url("https://i.imgur.com/a.jpg")
    assert wait_until(viewer.has_image)
    assert "32 x 24" in viewer.info.text() and "image/png" in viewer.info.text()
    assert viewer.image_label.pixmap() is not None
    viewer.close()


def test_viewer_reports_a_fetch_error(qapp, monkeypatch):
    def boom(url, **kw):
        raise FetchError("圖片連線逾時（15 秒）。", "timeout")

    monkeypatch.setattr(image_viewer, "fetch_image", boom)
    viewer = ImageViewer()
    viewer.show_url("https://i.imgur.com/a.jpg")
    assert wait_until(lambda: "圖片連線逾時" in viewer.image_label.text())
    viewer.close()


def test_closing_the_viewer_cancels_the_download(qapp, monkeypatch):
    tasks = []

    class SlowTask:
        def __init__(self, url):
            tasks.append(self)
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    viewer = ImageViewer()
    viewer._task = SlowTask("https://i.imgur.com/a.jpg")
    viewer.close()
    assert tasks[0].cancelled and viewer._task is None
