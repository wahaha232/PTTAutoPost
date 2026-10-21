PTT AutoPost (portable) -- unzip anywhere and double-click PTTAutoPost.exe.
config/ logs/ data/ are created next to the exe; nothing is written to the registry.
Command line:  PTTAutoPost.exe --selftest   (headless smoke test)
               PTTAutoPost.exe --probe      (read-only check of wss://ws.ptt.cc/bbs; sends nothing)
The program never logs in on its own, never presses save/send in PTT, and never stores your password.
