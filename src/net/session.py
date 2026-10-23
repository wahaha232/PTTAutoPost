"""PTT session: transport + screen emulation + (optional) assisted login.

Safety rules implemented here:
* The account/password given to `login()` are sent exactly once, never stored, never logged.
* The assisted login only answers prompts it positively recognises; the duplicate-login
  question is always answered "n" (never kicks another connection). On any unknown screen it
  stops and tells the user to continue by hand in the terminal.
* Connection loss is surfaced, never retried.
"""
from __future__ import annotations

import enum
import hashlib

from PySide6.QtCore import QObject, QTimer, Signal

from ..logging_setup import get_logger
from ..terminal.detect import Kind, classify
from ..terminal.screen import Screen
from .client import PttClient, State, login_host_trusted
from .sendlock import SendLock

log = get_logger("session")


class Login(enum.Enum):
    OFFLINE = "未連線"
    AT_LOGIN = "等待登入"
    LOGGING_IN = "登入中"
    LOGGED_IN = "已登入"
    FAILED = "登入失敗"
    MANUAL = "請在終端機手動繼續"


_ANSWERS = {
    Kind.DUP_LOGIN: b"n\r",          # never kick the user's other connection
    Kind.CLEAR_ERRLOG: b"n\r",       # keep failed-attempt records untouched
    Kind.PRESS_ANY_KEY: b"\r",
}
SETTLE_MS = 150
LOGIN_TIMEOUT_MS = 45000
MAX_ACTIONS = 8


class PttSession(QObject):
    screenChanged = Signal()
    loginChanged = Signal(object)    # Login
    notice = Signal(str)             # user-facing message (errors, hints)

    def __init__(self, parent=None, client: PttClient | None = None):
        super().__init__(parent)
        self.client = client or PttClient(self)
        self.send_lock = SendLock()          # one writer at a time: automatic typing vs clipboard paste
        self.screen = Screen()
        self.login_state = Login.OFFLINE
        self.logged_in = False
        self._seen_login_screen = False
        self._creds: list | None = None     # [account, password] while a login is in flight
        self._stage = 0                      # 0 idle, 1 account sent, 2 password sent
        self._actions = 0
        self._acted_on: tuple | None = None
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self._login_step)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._login_timeout)
        self.client.dataReceived.connect(self._on_data)
        self.client.stateChanged.connect(self._on_state)
        self.client.failed.connect(self.notice)

    # ----------------------------------------------------------------- public API
    @property
    def kind(self) -> Kind:
        return classify(self.screen)

    def connect_to(self, url: str) -> None:
        self.screen = Screen()
        self._reset_login()
        self.client.connect_to(url)

    def disconnect_(self) -> None:
        self._reset_login()
        self.client.close()

    def send_user_bytes(self, data: bytes) -> bool:
        """Keys typed by the user in the terminal widget."""
        return self.client.send(data)

    def login(self, account: str, password: str) -> bool:
        """User-initiated, assisted login. Returns False (nothing sent) if preconditions fail."""
        account = account.strip()
        if self.client.state is not State.CONNECTED:
            self.notice.emit("尚未連線，無法登入。")
            return False
        if self.kind is not Kind.LOGIN_PROMPT:
            self.notice.emit("目前畫面不是登入畫面（請求輸入代號），已停止；請在終端機中自行操作。")
            return False
        if not login_host_trusted(self.client.url):
            self.notice.emit("目前連線的不是 PTT 官方端點（ws.ptt.cc），輔助登入已停用，帳密不會由程式送出；如需登入請自行在終端機輸入。")
            return False
        if not account or not password:
            self.notice.emit("請輸入帳號與密碼。")
            return False
        if (not (account.isascii() and password.isascii() and account.isprintable() and password.isprintable())
                or len(account) > 64 or len(password) > 128):
            self.notice.emit("帳號或密碼含有不支援的字元（僅支援可顯示的 ASCII 字元，不可含控制字元）或長度過長。")
            return False
        self._creds = [account, password]
        self._stage, self._actions, self._acted_on = 0, 0, None
        self._set_login(Login.LOGGING_IN)
        self._deadline.start(LOGIN_TIMEOUT_MS)
        self._login_step()
        return True

    # ----------------------------------------------------------------- internals
    def _on_state(self, st: State) -> None:
        if st is State.DISCONNECTED:
            self._reset_login()
        elif st is State.CONNECTED:
            self._set_login(Login.AT_LOGIN)

    def _reset_login(self) -> None:
        self._creds = None
        self._stage = 0
        self.logged_in = False
        self._seen_login_screen = False
        self._settle.stop()
        self._deadline.stop()
        self._set_login(Login.OFFLINE if self.client.state is not State.CONNECTED else Login.AT_LOGIN)

    def _set_login(self, st: Login) -> None:
        if st is not self.login_state:
            self.login_state = st
            self.loginChanged.emit(st)

    def _on_data(self, data: bytes) -> None:
        self.screen.feed(data)
        self.screenChanged.emit()
        k = self.kind
        if k in (Kind.LOGIN_PROMPT, Kind.PASSWORD_PROMPT):
            self._seen_login_screen = True
        if k is Kind.MAIN_MENU and (self._seen_login_screen or self._stage) and not self.logged_in:
            self._mark_logged_in()
        if self._creds is not None:
            self._settle.start()

    def _mark_logged_in(self) -> None:
        self.logged_in = True
        self._creds = None
        self._deadline.stop()
        self._set_login(Login.LOGGED_IN)
        log.info("login confirmed (main menu on screen)")

    def _login_timeout(self) -> None:
        if self._creds is not None:
            self._stop_manual("登入逾時或畫面不明，已停止自動處理；請在終端機中查看並手動繼續。")

    def _stop_manual(self, why: str) -> None:
        self._creds = None
        self._deadline.stop()
        self._set_login(Login.MANUAL)
        self.notice.emit(why)
        log.warning("assisted login stopped: %s", why)

    def _login_step(self) -> None:
        if self._creds is None or self.client.state is not State.CONNECTED:
            return
        k = self.kind
        key = (k, hashlib.sha256(self.screen.text().encode("utf-8", "replace")).hexdigest())
        if key == self._acted_on:
            return                                    # already answered this exact screen
        if k is Kind.MAIN_MENU:
            self._mark_logged_in()
            return
        if k is Kind.CRED_FAILURE:
            self._creds = None
            self._deadline.stop()
            self._set_login(Login.FAILED)
            self.notice.emit("登入失敗：密碼不對或無此帳號。程式不會自動重試。")
            return
        if k in (Kind.OVERLOAD, Kind.DEL_OLDEST, Kind.TELNET_DEPRECATED):
            self._stop_manual(f"登入流程遇到需要您自行決定的畫面（{k.value}），已停止。")
            return
        if self._actions >= MAX_ACTIONS:
            self._stop_manual("自動處理的步驟過多，已停止；請在終端機中手動繼續。")
            return
        if k is Kind.LOGIN_PROMPT and self._stage == 0:
            acct = self._creds[0]
            self._acted_on = key
            self._actions += 1
            self._stage = 1
            self.client.send(acct.encode("ascii") + b"\r")
        elif k is Kind.PASSWORD_PROMPT and self._stage == 1:
            pw = self._creds[1]
            self._acted_on = key
            self._actions += 1
            self._stage = 2
            self._creds[1] = ""                       # drop our copy right after sending
            self.client.send(pw.encode("ascii") + b"\r")
            pw = None  # noqa: F841
        elif k in _ANSWERS and self._stage == 2:
            self._acted_on = key
            self._actions += 1
            self.client.send(_ANSWERS[k])
        elif k is Kind.LOGIN_PROMPT and self._stage == 2:
            self._stop_manual("伺服器又回到登入畫面，已停止；請在終端機中確認。")
        else:
            self._stop_manual("停留在非預期畫面，已停止自動處理；請在終端機中手動繼續。")
