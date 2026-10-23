"""BBS site bookmarks: defaults verified on 2026-10-23, validation and a read-only TCP check.

Only WSS is supported by the current client. Telnet/SSH entries are kept as bookmarks for
the planned connection abstraction; the UI says so instead of pretending to connect.
"""
from __future__ import annotations

import re
import socket

PROTOCOLS = ("wss", "telnet", "ssh")
PROTOCOL_LABELS = {"wss": "WSS（加密）", "telnet": "Telnet（明文）", "ssh": "SSH（加密）"}
VERIFIED = "2026-10-23"

DEFAULT_SITES = (
    {"name": "臺大批踢踢實業坊（PTT）", "protocol": "wss", "host": "ws.ptt.cc", "port": 443,
     "path": "/bbs", "note": f"{VERIFIED} TCP/TLS 有回應；實際登入未驗證"},
    {"name": "臺大批踢踢兔（PTT2）", "protocol": "wss", "host": "ws.ptt2.cc", "port": 443,
     "path": "/bbs", "note": f"{VERIFIED} TCP/TLS 有回應；WebSocket 握手 403，實際連線待驗證"},
    {"name": "成大夢之大地", "protocol": "telnet", "host": "bbs.ccns.ncku.edu.tw", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連"},
    {"name": "清華資工楓橋驛站", "protocol": "telnet", "host": "bbs.cs.nthu.edu.tw", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連"},
    {"name": "臺灣電玩站 巴哈姆特", "protocol": "telnet", "host": "bbs.gamer.com.tw", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連"},
    {"name": "紫丁香社區", "protocol": "telnet", "host": "lilacbbs.com", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連"},
    {"name": "新水木清華", "protocol": "telnet", "host": "newsmth.net", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連"},
    {"name": "臺大未來最舊小棧", "protocol": "telnet", "host": "ofo.tw", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連"},
    {"name": "華年小集", "protocol": "telnet", "host": "138.197.204.42", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連（pttbbs 測試／新站）"},
    {"name": "網際新世界", "protocol": "telnet", "host": "209.141.35.127", "port": 23,
     "path": "", "note": f"{VERIFIED} TCP 可連；3 秒內無 banner"},
    {"name": "交大淒美燈塔", "protocol": "ssh", "host": "43.224.33.158", "port": 22,
     "path": "", "note": f"{VERIFIED} SSH 可連；BBS 入口待確認"},
    {"name": "中山七月七日晴", "protocol": "ssh", "host": "77bbs.com", "port": 22,
     "path": "", "note": f"{VERIFIED} SSH 可連；BBS 入口待確認"},
    {"name": "臺大資管鳴蟬", "protocol": "ssh", "host": "bbs.im.ntu.edu.tw", "port": 22,
     "path": "", "note": f"{VERIFIED} SSH 可連；BBS 入口待確認"},
)

_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|[0-9A-Fa-f:]+")


def site_address(site: dict) -> str:
    host, port = site.get("host", ""), int(site.get("port") or 0)
    proto = site.get("protocol", "")
    if proto == "wss":
        path = site.get("path") or "/bbs"
        return f"wss://{host}:{port}{path}" if port != 443 else f"wss://{host}{path}"
    return f"{proto}://{host}:{port}"


def validate_site(name: str, protocol: str, host: str, port: int, path: str = "", note: str = "") -> str | None:
    if not name.strip() or len(name.strip()) > 60:
        return "名稱需為 1～60 個字元。"
    if protocol not in PROTOCOLS:
        return "協定必須是 WSS、Telnet 或 SSH。"
    h = host.strip()
    if not h or h != host or not _HOST_RE.fullmatch(h):
        return "主機名稱不正確（不可含空白、帳密或斜線）。"
    if not 1 <= int(port) <= 65535:
        return "連接埠需在 1～65535。"
    p = path.strip()
    if protocol == "wss":
        if p and not p.startswith("/"):
            return "WSS 路徑需以 / 開頭。"
        if any(c.isspace() for c in p):
            return "WSS 路徑不可含空白。"
    elif p:
        return "Telnet／SSH 不使用路徑。"
    if len(note) > 200:
        return "備註最多 200 個字元。"
    return None


def normalize_site(site: dict) -> dict:
    return {"name": str(site.get("name", "")).strip(), "protocol": str(site.get("protocol", "")),
            "host": str(site.get("host", "")).strip(), "port": int(site.get("port") or 0),
            "path": str(site.get("path", "")).strip(), "note": str(site.get("note", "")).strip()}


def check_site(site: dict, timeout: float = 5) -> tuple[bool, str]:
    """Read-only reachability check. Sends no login data and reads no BBS content."""
    host, port = site.get("host", ""), int(site.get("port") or 0)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP {host}:{port} 可連線（唯讀檢查，未送出任何資料）。"
    except OSError as e:
        return False, f"無法連線 {host}:{port}：{type(e).__name__}: {e}"
