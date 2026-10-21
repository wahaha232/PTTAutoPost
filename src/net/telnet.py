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
        self.stripped = 0

    def feed(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            st = self._state
            if st == "data":
                if b == IAC:
                    self._state = "iac"
                else:
                    out.append(b)
            elif st == "iac":
                if b == IAC:
                    out.append(0xFF)                 # escaped 0xFF data byte
                    self._state = "data"
                elif b in _NEG:
                    self._state = "opt"
                    self.stripped += 1
                elif b == SB:
                    self._state = "sb"
                    self.stripped += 1
                else:
                    self._state = "data"             # 2-byte command (NOP, GA, ...)
                    self.stripped += 1
            elif st == "opt":
                self._state = "data"
            elif st == "sb":
                if b == IAC:
                    self._state = "sb_iac"
            elif st == "sb_iac":
                self._state = "data" if b == SE else "sb"
        return bytes(out)
