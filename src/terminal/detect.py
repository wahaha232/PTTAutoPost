"""Screen-state recognition on the *emulated screen grid* (not on the raw byte stream).

The login-related markers come from the user's own working login tool (PttAutoLogin); the
posting markers (title prompt / editor status line) are taken from the public term.ptt.cc front end.
None of the posting markers has been verified against a logged-in real PTT session; every
caller therefore treats "no match" as "stop", never as "carry on".
"""
from __future__ import annotations

import enum

from .screen import Screen


class Kind(enum.Enum):
    UNKNOWN = "unknown"
    LOGIN_PROMPT = "login_prompt"          # 請輸入代號
    PASSWORD_PROMPT = "password_prompt"    # 請輸入您的密碼
    CRED_FAILURE = "credential_failure"    # 密碼不對或無此帳號
    DUP_LOGIN = "duplicate_login"          # 刪除其他重複登入的連線?
    DEL_OLDEST = "delete_oldest"           # 已達上限, 刪除最舊連線?
    CLEAR_ERRLOG = "clear_error_log"       # 刪除以上錯誤嘗試的記錄?
    PRESS_ANY_KEY = "press_any_key"        # 請按任意鍵繼續
    OVERLOAD = "overload"
    MAIN_MENU = "main_menu"                # 主功能表
    TITLE_PROMPT = "title_prompt"          # 標題：
    EDITOR = "editor"                      # 編輯文章
    TELNET_DEPRECATED = "telnet_deprecated"


def classify(s: Screen) -> Kind:
    t = s.text()
    if not t.strip():
        return Kind.UNKNOWN
    if "編輯文章" in s.row_text(s.rows - 1):
        return Kind.EDITOR
    cur = s.row_text(s.cur.y).lstrip()
    if cur.startswith(("標題:", "標題：")):
        return Kind.TITLE_PROMPT
    if "主功能表" in t:
        return Kind.MAIN_MENU
    if "關閉無加密的 telnet" in t:
        return Kind.TELNET_DEPRECATED
    if "密碼不對" in t or "無此帳號" in t:
        return Kind.CRED_FAILURE
    if "系統過載" in t or "人數已達上限" in t or "流量過大" in t:
        return Kind.OVERLOAD
    if "刪除最舊" in t:
        return Kind.DEL_OLDEST
    if "重複登入" in t or "是否要踢掉" in t or "您想踢掉" in t or "刪除其他重複" in t:
        return Kind.DUP_LOGIN
    if "刪除以上錯誤嘗試" in t:
        return Kind.CLEAR_ERRLOG
    if "任意鍵" in t:
        return Kind.PRESS_ANY_KEY
    if "請輸入您的密碼" in t or s.row_text(s.cur.y).lstrip().startswith("密碼"):
        return Kind.PASSWORD_PROMPT
    if "請輸入代號" in t:
        return Kind.LOGIN_PROMPT
    return Kind.UNKNOWN


def title_prompt_is_empty(s: Screen) -> bool:
    """True when the title prompt line has nothing typed after the prompt."""
    row = s.row_text(s.cur.y).lstrip()
    for prefix in ("標題：", "標題:"):
        if row.startswith(prefix):
            return row[len(prefix):].strip() == ""
    return False


def editor_is_empty(s: Screen) -> bool:
    """Editor text area (all rows above the status line) blank and cursor at the top-left."""
    return all(not s.row_text(y) for y in range(s.rows - 1)) and (s.cur.x, s.cur.y) == (0, 0)


def reply_editor_ready(s: Screen) -> bool:
    """True for PTT's reply editor: cursor at the top-left above a prefilled quote.

    The quote markers are deliberately conservative; if PTT changes the format the user can still
    use the advanced 'non-empty editor' allowance, but nothing is typed by surprise.
    """
    if (s.cur.x, s.cur.y) != (0, 0):
        return False
    for y in range(s.rows - 1):
        line = s.row_text(y)
        if "※ 引述" in line or "引述《" in line or "之銘言" in line:
            return True
        if line.lstrip().startswith((":", "：")):
            return True
    return False
