"""PTT article composition: normalise, wrap, render (news-repost format) and format checks.

Single render function: the preview, the clipboard text and the text typed into the terminal all come
from the same output. "Unknown" is never written into an article -- an empty field stays empty
and produces a warning instead.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()#%][0-9A-Za-z]|\x1b.?")
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")
INVISIBLE = re.compile("[​-‏  ‪-‮⁠-⁤﻿­]")
CLOSING = set("、。，．,.;:!?！？；：）)】〕」』》〉”’…%")
LINE_WIDTH = 76          # wrap target (display cells); PTT terminal is 80 columns wide
MAX_LINE = 78            # warn above this
TITLE_WARN_BYTES = 40    # UNVERIFIED limit (real PTT limit not observed yet) -> warning only
TITLE_ERROR_BYTES = 78


@dataclass
class Issue:
    level: str            # "error" | "warn"
    message: str
    line: int | None = None

    def __str__(self) -> str:
        return ("【錯誤】" if self.level == "error" else "【警告】") + self.message + (f"（第 {self.line} 行）" if self.line else "")


def normalize(text: str) -> tuple[str, list[str]]:
    """Remove what would trigger BBS editor keys or garble the screen. Returns (text, what changed)."""
    notes = []
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    n = len(ANSI.findall(t))
    if n:
        t = ANSI.sub("", t)
        notes.append(f"移除 {n} 個終端機跳脫序列")
    t2 = t.replace("\t", "    ")
    if t2 != t:
        notes.append("Tab 已展開為 4 個空格")
    t = t2.replace("\xa0", " ")
    n = len(CONTROL.findall(t))
    if n:
        t = CONTROL.sub("", t)
        notes.append(f"移除 {n} 個控制字元")
    n = len(INVISIBLE.findall(t))
    if n:
        t = INVISIBLE.sub("", t)
        notes.append(f"移除 {n} 個零寬／不可見字元")
    return t, notes


def char_width(ch: str) -> int:
    if ch.isascii():
        return 1
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1


def display_width(s: str) -> int:
    return sum(char_width(c) for c in s)


def byte_len(s: str) -> int:
    return sum(len(c.encode("cp950", "replace")) for c in s)


_TOKEN = re.compile(r"https?://\S+|[A-Za-z0-9_.,;:!?'\"()\[\]/@#%&*+=<>~$^|\\-]+|\s+|.", re.S)


def wrap_line(line: str, width: int = LINE_WIDTH) -> list[str]:
    if display_width(line) <= width:
        return [line]
    out, cur, w = [], "", 0
    for m in _TOKEN.finditer(line):
        tok = m.group(0)
        tw = display_width(tok)
        if tok.isspace():
            if w == 0:
                continue                      # no leading spaces on a continuation line
            if w + tw > width:
                out.append(cur.rstrip())
                cur, w = "", 0
                continue
        elif w + tw > width:
            if tok[0] in CLOSING and w + tw <= width + 2:     # keep closing punctuation on the previous line
                cur += tok
                w += tw
                continue
            if cur:
                out.append(cur.rstrip())
                cur, w = "", 0
            if tw > width and not tok.startswith("http"):     # a very long word: break by character
                for ch in tok:
                    cw = char_width(ch)
                    if w + cw > width:
                        out.append(cur)
                        cur, w = "", 0
                    cur += ch
                    w += cw
                continue
        cur += tok
        w += tw
    if cur.strip():
        out.append(cur.rstrip())
    return out or [""]


def wrap(text: str, width: int = LINE_WIDTH) -> str:
    return "\n".join(l for line in text.split("\n") for l in wrap_line(line, width))


@dataclass
class Fields:
    post_title: str = ""
    site: str = ""
    author: str = ""
    published: str = ""
    url: str = ""
    news_title: str = ""
    body: str = ""
    notes: str = ""
    signature: str = ""
    use_signature: bool = False


def render(f: Fields, width: int = LINE_WIDTH, do_wrap: bool = True) -> tuple[str, str]:
    """Return (title, body) of the PTT article in the news-repost format."""
    def n(s):
        return normalize(s)[0].strip()

    w = (lambda t: wrap(t, width)) if do_wrap else (lambda t: t)
    parts = [
        f"1.媒體來源: {n(f.site)}",
        f"2.記者署名: {n(f.author)}",
        f"3.完整新聞標題: {n(f.news_title or f.post_title)}",
        "4.完整新聞內文:",
        w(n(f.body)),
        "",
        "5.完整新聞連結 (或短網址):",
        n(f.url),
        "",
        "6.備註:",
        w(n(f.notes)),
    ]
    body = "\n".join(parts).rstrip("\n")
    sig = n(f.signature)
    if f.use_signature and sig:
        body += "\n--\n" + w(sig)                     # system-generated separator line
    return n(f.post_title).replace("\n", " "), body


def check(title: str, body: str, sig_text: str = "", used_signature: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    if not title.strip():
        issues.append(Issue("error", "發文標題是空的。"))
    else:
        b = byte_len(title)
        if b > TITLE_ERROR_BYTES:
            issues.append(Issue("error", f"標題過長（{b} bytes），超過一行可輸入的範圍。"))
        elif b > TITLE_WARN_BYTES:
            issues.append(Issue("warn", f"標題 {b} bytes：PTT 標題長度上限尚未實測，過長可能被截斷（目前以 {TITLE_WARN_BYTES} bytes 提醒）。"))
    if not body.strip():
        issues.append(Issue("error", "內文是空的。"))
    for label, text in (("標題", title), ("內文", body)):
        for i, line in enumerate(text.split("\n"), 1):
            if CONTROL.search(line) or "\x1b" in line:
                issues.append(Issue("error", f"{label}含有控制字元，可能觸發 PTT 快捷鍵。", i))
            for j, ch in enumerate(line):
                try:
                    ch.encode("cp950")
                except UnicodeEncodeError:
                    issues.append(Issue("error", f"{label}含有無法以 Big5 編碼的字元「{ch}」(U+{ord(ch):04X})，PTT 會顯示成亂碼；請改寫。", i))
                    break
    lines = body.split("\n")
    # the system-generated separator is the last exact "--" line (render() appends the signature after it)
    sys_sep = max((n for n, l in enumerate(lines, 1) if l == "--"), default=None) if used_signature else None
    for i, line in enumerate(lines, 1):
        if display_width(line) > MAX_LINE and not re.search(r"https?://\S{20,}", line):
            issues.append(Issue("warn", f"行寬 {display_width(line)} 超過 {MAX_LINE}，PTT 編輯器可能自動折行。", i))
        if line.strip() == "--" and i != sys_sep:
            issues.append(Issue("warn", "單獨一行的「--」會被 PTT 當成簽名檔分隔線。", i))
    if len(lines) > 400:
        issues.append(Issue("warn", f"內文共 {len(lines)} 行，偏長。"))
    for label, prefix in (("媒體來源", "1.媒體來源:"), ("記者署名", "2.記者署名:"), ("完整新聞標題", "3.完整新聞標題:")):
        for line in lines:
            if line.startswith(prefix) and not line[len(prefix):].strip():
                issues.append(Issue("warn", f"「{label}」尚未填寫（不會自動填入「未知」）。"))
    if "5.完整新聞連結 (或短網址):" in body:
        k = lines.index("5.完整新聞連結 (或短網址):")
        if k + 1 < len(lines) and not lines[k + 1].strip():
            issues.append(Issue("warn", "「完整新聞連結」尚未填寫。"))
    if used_signature and sig_text.strip() and "\n--\n" not in body:
        issues.append(Issue("warn", "已勾選套用簽名檔，但預覽中沒有簽名檔（預覽可能被手動改過）。"))
    if sig_text.strip() and any(l.strip() == "--" for l in sig_text.split("\n")):
        issues.append(Issue("error", "簽名檔文字不可含單獨一行的「--」。"))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
