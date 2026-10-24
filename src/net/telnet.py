"""Strip Telnet command sequences (IAC ...) that PTT's bridge relays in the byte stream.

Observed on the live endpoint: the login screen starts with IAC DO/WILL/SB sequences (0xFF 0xFB/0xFD/0xFA ...).
Left alone, those bytes would be drawn as garbage. We only *remove* them and never answer: the endpoint
works without negotiation replies (same as the user's PttAutoLogin tool), and sending nothing is the safe default.
"""
from __future__ import annotations

IAC, SB, SE = 0xFF, 250, 240
_NEG = {251, 252, 253, 254}          # WILL WONT DO DONT -> IAC cmd opt


class IacFilter:
    def __init__(self):
        self._state = "data"
        self._cmd = 0
        self.stripped = 0

    def feed_with_replies(self, data: bytes) -> tuple[bytes, bytes]:
        """Strip Telnet commands and answer WILL/DO with DONT/WONT (basic, safe negotiation)."""
        out = bytearray()
        replies = bytearray()
        for b in data:
            st = self._state
            if st == "data":
                if b == IAC:
                    self._state = "iac"
                else:
                    out.append(b)
            elif st == "iac":
                if b == IAC:
                    out.append(0xFF)
                    self._state = "data"
                elif b in _NEG:
                    self._cmd = b
                    self._state = "opt"
                    self.stripped += 1
                elif b == SB:
                    self._state = "sb"
                    self.stripped += 1
                else:
                    self._state = "data"
                    self.stripped += 1
            elif st == "opt":
                if self._cmd == 251:                 # server WILL -> we DONT
                    replies += bytes((IAC, 254, b))
                elif self._cmd == 253:               # server DO -> we WONT
                    replies += bytes((IAC, 252, b))
                self._state = "data"
            elif st == "sb":
                if b == IAC:
                    self._state = "sb_iac"
            elif st == "sb_iac":
                self._state = "data" if b == SE else "sb"
        return bytes(out), bytes(replies)

    def feed(self, data: bytes) -> bytes:
        """Strip commands without replying (kept for callers that only need decoded data)."""
        out, _replies = self.feed_with_replies(data)
        return out
