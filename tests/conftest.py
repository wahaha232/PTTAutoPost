import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # never open real windows during tests
os.environ.setdefault("PTTAUTOPOST_HOME", tempfile.mkdtemp(prefix="pttpost_test_"))  # keep logs/data out of the project
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_until(cond, timeout_ms=4000, step_ms=10):
    """Spin the Qt event loop until cond() is true (or time out)."""
    loop = QEventLoop()
    t = QTimer()
    t.setInterval(step_ms)
    waited = [0]

    def tick():
        waited[0] += step_ms
        if cond() or waited[0] >= timeout_ms:
            loop.quit()

    t.timeout.connect(tick)
    t.start()
    if not cond():
        loop.exec()
    t.stop()
    return bool(cond())


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def bbs_factory(qapp):
    made = []

    def make(scenario="normal"):
        from fake_bbs import FakeBBS
        b = FakeBBS(scenario)
        made.append(b)
        return b

    yield make
    for b in made:
        b.srv.close()


@pytest.fixture(autouse=True)
def _dispose_windows():
    """Delete every top-level window a test left behind.

    Leaked MainWindows piled up across the suite and made each app.setStyleSheet() re-polish all of
    them, so the theme tests ran for many minutes.  hide()+deleteLater() skips closeEvent (no
    unsaved-changes dialog or tray hand-off during teardown).
    """
    yield
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        w.hide()
        w.deleteLater()
    pump(0)


@pytest.fixture(autouse=True)
def _allow_loopback_fetch(monkeypatch):
    """Tests serve pages from 127.0.0.1; the SSRF guard has its own tests that switch this off."""
    import src.parsers.fetch as fm
    monkeypatch.setattr(fm, "ALLOW_PRIVATE_HOSTS", True)
