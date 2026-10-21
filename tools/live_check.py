"""Live check against the REAL endpoint (read-only): connect, wait for the login prompt via our own
PttSession/Screen/detect code, then close politely. Sends nothing (asserts bytes_sent == 0)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from src.net.client import DEFAULT_URL, State
from src.net.session import PttSession
from src.terminal.detect import Kind

app = QApplication([])
s = PttSession()
notes = []
s.notice.connect(notes.append)


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


url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
s.connect_to(url)
ok_conn = wait(lambda: s.client.state is State.CONNECTED, 12000)
ok_prompt = wait(lambda: s.kind is Kind.LOGIN_PROMPT, 8000)
print("connected:", ok_conn, "| login prompt detected:", ok_prompt, "| kind:", s.kind.value)
print("bytes received:", s.client.bytes_received, "| bytes sent:", s.client.bytes_sent)
print("proxy prefix stripped:", "HTTP/1.1" not in s.screen.text())
print("last non-blank rows (escaped):")
for y in range(max(0, s.screen.last_nonblank_row() - 3), s.screen.last_nonblank_row() + 1):
    print("  ", y, s.screen.row_text(y).encode("unicode_escape").decode()[:150])
print("cursor:", (s.screen.cur.x, s.screen.cur.y))
assert s.client.bytes_sent == 0
s.disconnect_()
wait(lambda: s.client.state is State.DISCONNECTED, 4000)
print("closed:", s.client.state.value, "| notices:", notes)
