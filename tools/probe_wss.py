"""Phase 1 probe: connect to the PTT WebSocket endpoint and record what really happens.

Read-only: connects, listens for ~5 s, closes politely. It NEVER sends any data
(no account, no password, no keys). Usage:
    python -X utf8 tools/probe_wss.py [wss-url]
"""
import json
import re
import sys
import time

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketHandshakeOptions

URL = sys.argv[1] if len(sys.argv) > 1 else "wss://ws.ptt.cc/bbs"
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Za-z0-9]|\x1b.")


def probe(origin, subprotocols, listen_ms=5000, connect_ms=10000):
    res = {"origin": origin, "subprotocols_requested": subprotocols, "connected": False,
           "negotiated_subprotocol": None, "error": None, "bytes": 0, "msgs": 0,
           "first_text": None, "close_code": None, "elapsed_ms": None}
    ws = QWebSocket(origin)
    buf = bytearray()
    loop = QEventLoop()
    t0 = time.time()

    ws.connected.connect(lambda: (res.update(connected=True, negotiated_subprotocol=ws.subprotocol()),
                                  QTimer.singleShot(listen_ms, loop.quit)))
    ws.errorOccurred.connect(lambda e: (res.update(error="%s | %s" % (e, ws.errorString())), loop.quit()))
    ws.binaryMessageReceived.connect(lambda b: (buf.extend(bytes(b)), res.update(msgs=res["msgs"] + 1)))
    ws.textMessageReceived.connect(lambda s: (buf.extend(s.encode("utf-8", "replace")), res.update(msgs=res["msgs"] + 1)))
    QTimer.singleShot(connect_ms + listen_ms, loop.quit)  # hard cap

    opts = QWebSocketHandshakeOptions()
    if subprotocols:
        opts.setSubprotocols(subprotocols)
    ws.open(QNetworkRequest(QUrl(URL)), opts)
    loop.exec()
    res["elapsed_ms"] = int((time.time() - t0) * 1000)
    res["bytes"] = len(buf)
    if buf:
        text = ANSI.sub(b"", bytes(buf))
        res["first_text"] = text.decode("cp950", "replace")[:400]
        res["head_hex"] = bytes(buf)[:48].hex()
    # polite close (close frame), then wait up to 3 s for the server to acknowledge
    if ws.state().name == "ConnectedState":
        done = QEventLoop()
        ws.disconnected.connect(done.quit)
        QTimer.singleShot(3000, done.quit)
        ws.close()
        done.exec()
        res["close_code"] = int(ws.closeCode().value) if hasattr(ws.closeCode(), "value") else int(ws.closeCode())
    return res


def main():
    app = QCoreApplication([])
    assert app is not None
    out = []
    for origin, subs in [("https://term.ptt.cc", ["binary"]), ("https://term.ptt.cc", []),
                         ("https://term.ptt.cc", ["telnet"]), ("", [])]:
        out.append(probe(origin, subs))
        time.sleep(3)
    print(json.dumps(out, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
