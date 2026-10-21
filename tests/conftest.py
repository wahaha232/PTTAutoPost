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
