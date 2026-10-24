"""A scripted fake PTT (WebSocket server) that records every byte it receives.

It is the ground truth for the "what was actually typed" assertions: the code under test only
ever talks to this local server -- never to the real PTT.
"""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer

PROXY = b"HTTP/1.1 200 OK\r\n\r\n"
CLS = b"\x1b[2J\x1b[H"


def b5(s: str) -> bytes:
    return s.encode("cp950")


LOGIN = CLS + b5("批踢踢實業坊 (fake)\r\n\r\n請輸入代號，或以 guest 參觀，或以 new 註冊: ")
PASSWORD = CLS + b5("請輸入您的密碼: ")
BAD = CLS + b5("密碼不對或無此帳號。程式結束\r\n")
DUP = CLS + b5("您想刪除其他重複登入的連線嗎？[Y/n]")
ANYKEY = CLS + b5("請按任意鍵繼續")
MENU = CLS + b5("【主功能表】 批踢踢實業坊\r\n\r\n(A)nnounce (F)avorite (C)lass\r\n")
WEIRD = CLS + b5("這是一個不認得的畫面\r\n")
TITLE = CLS + b5("看板 Test\r\n\r\n標題：")
EDITOR = (CLS + b"\x1b[24;1H\x1b[34;46m" + b5(" 編輯文章  (^Z/F1)說明 (^P/^G)插入符號/範本 (^X/^Q)離開") + b"\x1b[K\x1b[m\x1b[1;1H")
REPLY_EDITOR = (CLS + b5("※ 引述《tester (暱稱)》之銘言：\r\n: 原文第一行\r\n: 原文第二行\r\n")
                + b"\x1b[24;1H\x1b[34;46m" + b5(" 編輯文章  (^Z/F1)說明 (^P/^G)插入符號/範本 (^X/^Q)離開")
                + b"\x1b[K\x1b[m\x1b[1;1H")


class FakeBBS(QObject):
    def __init__(self, scenario: str = "normal", parent=None):
        super().__init__(parent)
        self.scenario = scenario
        self.srv = QWebSocketServer("fake-ptt", QWebSocketServer.SslMode.NonSecureMode, self)
        self.srv.newConnection.connect(self._on_conn)
        assert self.srv.listen(QHostAddress.SpecialAddress.LocalHost, 0)
        self.ws = None
        self.state = "login"
        self.received = bytearray()   # every byte ever received
        self.after_login = bytearray()  # bytes received after the menu was reached
        self.line = bytearray()
        self.connections = 0
        self.origin_seen = None

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.srv.serverPort()}/bbs"

    # --------------------------------------------------------------- server side
    def push(self, data: bytes) -> None:
        if self.ws is not None:
            self.ws.sendBinaryMessage(data)

    def drop(self) -> None:
        if self.ws is not None:
            self.ws.abort()

    def goto(self, state: str) -> None:
        self.state = state
        self.push({"menu": MENU, "title": TITLE, "editor": EDITOR, "login": LOGIN}[state])

    def _on_conn(self) -> None:
        self.ws = self.srv.nextPendingConnection()
        self.connections += 1
        self.origin_seen = self.ws.origin()
        self.ws.binaryMessageReceived.connect(self._on_bytes)
        self.state = "login"
        self.ws.sendBinaryMessage(PROXY + LOGIN)

    def _on_bytes(self, data) -> None:
        data = bytes(data)
        self.received += data
        if self.state in ("menu", "title", "editor", "saveprompt"):
            self.after_login += data
        for b in data:
            self._byte(b)

    def _byte(self, b: int) -> None:
        st = self.state
        if st in ("login", "password", "dup", "anykey"):
            if b == 0x0D:
                self._line(bytes(self.line))
                self.line.clear()
            else:
                self.line.append(b)
        elif st == "menu":
            if b == 0x10:                       # Ctrl-P: start a new post
                self.state = "title"
                self.push(TITLE)
        elif st == "title":
            if b == 0x0D:
                self.state = "editor"
                self.push(EDITOR)
            else:
                self.push(bytes([b]))
        elif st == "editor":
            if b == 0x18:                       # Ctrl-X: leave editor -> save prompt (a user action)
                self.state = "saveprompt"
                self.push(b"\x1b[24;1H\x1b[K" + b5("(S)儲存 (A)放棄 (E)繼續？[S]"))
            elif b == 0x0D:
                self.push(b"\r\n")
            else:
                self.push(bytes([b]))

    def _line(self, text: bytes) -> None:
        st = self.state
        if st == "login":
            self.state = "password"
            self.push(PASSWORD)
        elif st == "password":
            sc = self.scenario
            if sc == "badpass":
                self.push(BAD)
                self.state = "login"
            elif sc == "weird":
                self.push(WEIRD)
                self.state = "weird"
            elif sc == "dup":
                self.state = "dup"
                self.push(DUP)
            elif sc == "anykey":
                self.state = "anykey"
                self.push(ANYKEY)
            else:
                self.state = "menu"
                self.push(MENU)
        elif st == "dup":
            self.push(MENU if text.strip().lower() == b"n" else CLS + b5("(Y answered — would have kicked another session)"))
            self.state = "menu" if text.strip().lower() == b"n" else "kicked"
        elif st == "anykey":
            self.state = "menu"
            self.push(MENU)
