"""Board (看板) helpers: preset popular boards and name validation. Names are public PTT board IDs."""
from __future__ import annotations

import re

# (board id, Chinese title) -- convenience list only; any valid board id can be typed in.
PRESET_BOARDS: tuple[tuple[str, str], ...] = (
    ("Gossiping", "八卦"), ("HatePolitics", "政黑"), ("Baseball", "棒球"), ("Stock", "股票"), ("NBA", "NBA"),
    ("Lifeismoney", "省錢"), ("Tech_Job", "科技工作"), ("movie", "電影"), ("Military", "軍事"), ("car", "汽車"),
    ("MobileComm", "行動通訊"), ("Japandrama", "日劇"), ("China-Drama", "陸劇"), ("KoreaStar", "韓星"), ("Beauty", "表特"),
    ("home-sale", "房屋買賣"), ("Option", "選擇權"), ("Finance", "金融"), ("Gamesale", "遊戲交易"), ("C_Chat", "希洽"),
    ("LoL", "英雄聯盟"), ("PC_Shopping", "電腦購物"), ("Travel", "旅遊"), ("Food", "美食"), ("sex", "兩性"),
    ("WomenTalk", "女孩"), ("Boy-Girl", "男女"), ("Tennis", "網球"), ("Basketball", "籃球"), ("Soft_Job", "軟體工作"),
)
_NAMES = dict(PRESET_BOARDS)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,11}")


def valid_board(name: str) -> bool:
    return bool(_ID.fullmatch(name or ""))


def board_id(text: str) -> str:
    """Board id from combo text such as 'Gossiping（八卦）' or 'Gossiping'; '' when it is not a valid id."""
    t = (text or "").replace("★", "").strip()
    m = _ID.match(t)
    rest = t[m.end():].strip() if m else "x"
    return m.group(0) if m and (not rest or rest[0] in "（(") else ""


def label(name: str) -> str:
    zh = _NAMES.get(name) or next((v for k, v in PRESET_BOARDS if k.lower() == name.lower()), "")
    return f"{name}（{zh}）" if zh else name
