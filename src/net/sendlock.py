"""Exclusive ownership of the BBS text stream.

Automatic typing and clipboard pasting both write raw bytes to the same connection.  A
single owner flag makes the mutual exclusion explicit instead of relying only on UI
button state, so two senders can never interleave their chunks.
"""
from __future__ import annotations

import threading

TYPING = "typing"
PASTE = "paste"
_LABELS = {TYPING: "自動輸入", PASTE: "貼上"}


class SendLock:
    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._owner: str | None = None

    def owner(self) -> str | None:
        with self._mutex:
            return self._owner

    def owned_by(self, owner: str) -> bool:
        with self._mutex:
            return self._owner == owner

    def acquire(self, owner: str) -> bool:
        with self._mutex:
            if self._owner is not None:
                return False
            self._owner = owner
            return True

    def release(self, owner: str) -> None:
        with self._mutex:
            if self._owner == owner:
                self._owner = None

    def label(self) -> str:
        with self._mutex:
            return _LABELS.get(self._owner or "", "其他傳送工作")
