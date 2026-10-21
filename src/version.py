"""Single source of truth for the application version (bump it on every delivered change)."""
__version__ = "0.5.4"
BUILD_DATE = "2026/10/16"
APP_NAME = "PTT AutoPost"

# newest first; tests/test_version.py enforces: CHANGELOG[0] == (__version__, BUILD_DATE)
CHANGELOG = [
    ("0.5.4", "2026/10/16", [
        "Fix: check() no longer crashes on a ' -- ' line when a signature is used",
        "Fix: copy / check / typing always use a freshly rebuilt preview (no stale text within the 350 ms refresh delay)",
        "New: unsaved-changes prompt (save / discard / cancel) before new draft, opening a draft, fetching and closing",
        "Fix: typing session stays bound to its own draft; draft switching is blocked while typing; 'allow non-empty' resets after each run",
        "Fix: typing a missing draft shows an error instead of raising",
        "Cleanup: ESC bytes written as escapes, 'go to board' sent as one frame, no hard-coded developer path for the login helper, "
        "broader log redaction (quoted dict/list forms), fetch caches guarded by a lock, one HTML parse less",
    ]),
    ("0.5.3", "2026/10/16", [
        "Terminal: new 'stretch to fill' option (terminal bar and settings) that stretches the characters so the screen fills the whole "
        "area with no black margin; off by default (aspect-preserving, centred)",
    ]),
    ("0.5.2", "2026/10/16", [
        "Desktop / laptop adaptation: on-screen key bar (Esc, arrows, PgUp/PgDn, Home/End; shown by default on laptops, switchable in "
        "settings), touchpad/mouse-wheel scrolling in the terminal, compact layout on screens up to 800 px high, fractional DPI "
        "scaling (125% / 150%) rendered crisp",
    ]),
    ("0.5.1", "2026/10/16", [
        "PTT login helper (separate program) can be started from the settings tab and the tray menu; path is configurable; nothing is shared",
    ]),
    ("0.5.0", "2026/10/16", [
        "System tray: settings to minimize / close to the tray icon (right-click menu: show, exit); new tray icon that turns green "
        "when connected and grey when not",
        "New application icon (EXE and window)",
        "Adapts to the device: window size is limited to the screen, last size/position is restored (clamped if the screen "
        "changed), terminal re-fits when moved to another monitor or DPI",
    ]),
    ("0.4.1", "2026/10/16", [
        "Terminal: characters no longer spread out on wide windows (glyph aspect kept, at most 1.25x wide, rest is an even black margin); "
        "block / shade / triangle / box-drawing characters are drawn geometrically so ASCII art fills its cells exactly",
    ]),
    ("0.4.0", "2026/10/16", [
        "Boards: choose the target board (preset popular boards or any typed board id), save boards as favorites (starred, listed first), "
        "board is stored in the draft; optional 'go to board' button sends s + board id + Enter from the main menu (never posts)",
    ]),
    ("0.3.2", "2026/10/16", [
        "App icon: new icon applied to the EXE file and the window (assets/icon.ico, regenerate with tools/make_icon.py)",
    ]),
    ("0.3.1", "2026/10/16", [
        "Fonts: one-click button to select the installed Hua-Kang Yuan Medium font (DFYuanMedium-B5) in the terminal bar and the settings tab",
    ]),
    ("0.3.0", "2026/10/16", [
        "Signatures: up to 10 saved signatures, picked from a drop-down, each with a name; edit, save, add and delete in the app; "
        "the old single signature becomes entry 1 automatically",
    ]),
    ("0.2.1", "2026/10/16", [
        "Fix: media source and reporter were often empty -- media source now falls back to meta publisher, a known-host table, the title "
        "suffix and finally the domain (marked as inferred); reporter now also comes from author elements in the page and from more "
        "byline layouts (label/name/bar, name|role, place + date wire line, photo credit); labels such as the editor/translator prefix "
        "and trailing section words are removed from author names; organisation names are still never used as a reporter",
        "Fix: article bodies were lost on pages whose container class merely contains a word like 'promoted', and on pages without "
        "<article>/<p> tags (CSS-in-JS class names) -- noise filtering is token based and never removes the main content; "
        "paragraph-dense blocks are now body candidates",
    ]),
    ("0.2.0", "2026/10/16", [
        "Fix: Big5 characters split by a colour escape (lead byte, ESC[..m, trail byte) are decoded as one character -- "
        "the PTT login art and any coloured block graphics no longer show stray letters and question marks",
        "Terminal: font family / size settings (settings tab and a bar under the terminal), live apply, saved locally",
        "Terminal: fit mode -- the 80x24 grid fills the window and the font size follows the window size (default on)",
        "Terminal: cell width derived from the Chinese glyph; ASCII glyphs wider than a cell are squeezed, not overlapped",
        "Main window: freely resizable (minimum 760x560)",
        "Packaging: versioned output folders (dist/PTTAutoPost-<version>-portable) so a running copy never blocks a build",
    ]),
    ("0.1.0", "2026/10/15", [
        "First usable version: WSS terminal, article extraction, drafts + global signature, typing into PTT (never submits), portable EXE",
    ]),
]
