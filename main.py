"""PTT AutoPost entry point.

    python main.py              start the desktop app
    python main.py --selftest   headless smoke test (offscreen Qt, exits 0 on success, no window shown)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def selftest() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import tempfile

    os.environ.setdefault("PTTAUTOPOST_HOME", tempfile.mkdtemp(prefix="pttpost_selftest_"))
    from PySide6.QtWidgets import QApplication

    from src import compose
    from src.net.session import PttSession
    from src.parsers.extract import parse
    from src.storage.db import Database
    from src.ui.main_window import MainWindow
    from src.version import __version__

    app = QApplication([])
    db = Database(os.path.join(os.environ["PTTAUTOPOST_HOME"], "selftest.db"))
    win = MainWindow(db, PttSession())
    r = parse("<html><head><title>測試</title></head><body><article>" + "<p>這是一段足夠長的測試內容，用來確認解析器可以運作。</p>" * 6 + "</article></body></html>", "https://x.test/a")
    win.body.setPlainText(r.body.value or "")
    win.w["post_title"].setText("[新聞] 自我測試")
    win.render_preview(force=True)
    pix = win.term.grab()
    assert not pix.isNull(), "terminal widget did not paint"
    title, body = win.current_texts()
    assert not compose.has_errors(compose.check(title, body)), "selftest article failed its own checks"
    did = win.save_draft()
    assert did and db.get_draft(did)["post_title"] == "[新聞] 自我測試"
    print(f"SELFTEST OK version={__version__} frozen={getattr(sys, 'frozen', False)} platform={app.platformName()} draft={did}")
    win.session.disconnect_()
    return 0


def probe() -> int:
    """Read-only live check: connect to the endpoint, wait for the login prompt, disconnect. Sends nothing."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import tempfile

    os.environ.setdefault("PTTAUTOPOST_HOME", tempfile.mkdtemp(prefix="pttpost_probe_"))
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from src.net.client import DEFAULT_URL, State
    from src.net.session import PttSession
    from src.terminal.detect import Kind

    _app = QApplication([])
    s = PttSession()
    url = next((a for a in sys.argv[1:] if a.startswith(("ws://", "wss://"))), DEFAULT_URL)

    def wait(cond, ms):
        loop, t, n = QEventLoop(), QTimer(), [0]
        t.setInterval(20)

        def tick():
            n[0] += 20
            if cond() or n[0] >= ms:
                loop.quit()
        t.timeout.connect(tick)
        t.start()
        loop.exec()
        t.stop()
        return cond()

    s.connect_to(url)
    connected = wait(lambda: s.client.state is State.CONNECTED, 12000)
    prompt = wait(lambda: s.kind is Kind.LOGIN_PROMPT, 8000)
    sent = s.client.bytes_sent
    s.disconnect_()
    wait(lambda: s.client.state is State.DISCONNECTED, 3000)
    print(f"PROBE url={url} connected={connected} login_prompt={prompt} bytes_received={s.client.bytes_received} bytes_sent={sent}")
    return 0 if connected and prompt and sent == 0 else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if "--probe" in sys.argv:
        return probe()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from src.logging_setup import get_logger
    from src.net.session import PttSession
    from src.storage.db import Database
    from src.ui.main_window import MainWindow
    from src.version import APP_NAME, __version__

    log = get_logger()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)   # 125% / 150% stay crisp
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    log.info("start %s %s", APP_NAME, __version__)
    win = MainWindow(Database(), PttSession())
    win.show()
    code = app.exec()
    log.info("exit code=%s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
