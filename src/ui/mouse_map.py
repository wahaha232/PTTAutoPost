"""Mouse browsing options for the terminal (modelled on PTT Star's mouse settings).

Every action only sends the same bytes as an ordinary navigation key, so nothing can post, save
or confirm on the user's behalf.  The defaults keep the earlier behaviour (wheel = arrow keys,
right button = copy/paste menu, side buttons unused).
"""
from __future__ import annotations

UP, DOWN, LEFT, RIGHT = b"\x1b[A", b"\x1b[B", b"\x1b[D", b"\x1b[C"
HOME, END, PGUP, PGDN = b"\x1b[1~", b"\x1b[4~", b"\x1b[5~", b"\x1b[6~"

# setting key -> (default, ((value, label), ...))
WHEEL = ("arrows", (("arrows", "↑／↓（一次一行或一項）"), ("page", "PageUp／PageDown（一次一頁）")))
RIGHT_WHEEL = ("none", (("none", "不使用"), ("home_end", "Home／End（跳到第一項／最後一項）"),
                        ("page", "PageUp／PageDown")))
SIDE = ("none", (("none", "不使用"), ("leave_enter", "上一頁鍵＝← 離開、下一頁鍵＝→ 進入")))
MIDDLE = ("none", (("none", "不使用"), ("enter", "Enter（進入／確認選取的項目）")))

LEFT_CLICK = ("open", (("open", "點一下文章／看板列表的項目就進入"), ("none", "不使用（左鍵只用來選取文字）")))

SETTINGS = {"mouse.wheel": WHEEL, "mouse.right_wheel": RIGHT_WHEEL, "mouse.side": SIDE, "mouse.middle": MIDDLE,
            "mouse.left_click": LEFT_CLICK}


def valid(key: str, value: str) -> str:
    """Stored value if it is one of the choices, otherwise the default."""
    default, choices = SETTINGS[key]
    return value if value in dict(choices) else default


def wheel_bytes(mode: str, steps: int) -> bytes:
    """steps > 0 = wheel up.  Arrow mode repeats up to 5 lines; page mode sends one page per notch (max 3)."""
    if not steps or mode == "none":
        return b""
    if mode in ("page", "home_end"):
        if mode == "home_end":
            return HOME if steps > 0 else END
        return (PGUP if steps > 0 else PGDN) * min(abs(steps), 3)
    return (UP if steps > 0 else DOWN) * min(abs(steps), 5)


def side_bytes(mode: str, forward: bool) -> bytes:
    if mode == "leave_enter":
        return RIGHT if forward else LEFT
    return b""


def middle_bytes(mode: str) -> bytes:
    return b"\r" if mode == "enter" else b""
