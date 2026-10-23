"""Single source of truth for the application version (bump it on every delivered change)."""
__version__ = "0.6.6"
BUILD_DATE = "2026/10/23"
APP_NAME = "PTT AutoPost"

# newest first; tests/test_version.py enforces: CHANGELOG[0] == (__version__, BUILD_DATE)
CHANGELOG = [
    ("0.6.6", "2026/10/23", [
        "Links/security: image auto-open now requires https and a known image host (exact host or subdomain); "
        "extension-only URLs are never auto-opened. .svg is excluded, and IP, localhost and private/loopback hosts are "
        "rejected without DNS lookups. Manual link clicks are unchanged.",
        "Links: when the per-screen or per-minute auto-open limit skips images, the status bar shows one notice per "
        "screen with the number skipped; the notice is not repeated for the same screen.",
    ]),
    ("0.6.5", "2026/10/23", [
        "Links: detect single-row http/https URLs on the terminal grid (correct cell positions for Chinese "
        "double-width text); wrapped URLs are deliberately not guessed. Other schemes and URLs with userinfo are rejected.",
        "Links: hovering underlines the URL and shows a hand cursor; a click opens the browser only when the pointer is "
        "released without dragging. Link clicks never send bytes to the BBS. Browser selection supports system, Chrome, "
        "Edge, Firefox or a custom executable, always passed the URL as one argument without a shell.",
        "Links: optional image-link auto-open (default off) with an IP warning; once per URL per connection, at most one "
        "per screen update and three per rolling minute; disabled while automatic typing or assisted login is active "
        "(manual clicks still work). Invalid settings fall back to safe defaults.",
    ]),
    ("0.6.4", "2026/10/23", [
        "UI: terminal palette is now a separate option (always dark / follow theme; default always dark), applied live "
        "and persisted as ui.terminal_palette; missing or invalid values fall back to dark",
        "UI: dragging the article splitter updates only the in-memory width and writes the setting once about 500 ms after "
        "dragging stops (and on close), instead of writing on every splitterMoved event",
        "UI: the article-panel shortcut is F12, so Ctrl+Shift+A is no longer intercepted and reaches the terminal as 0x01",
    ]),
    ("0.6.3", "2026/10/23", [
        "UI: the terminal and the article panel now share one page in a draggable splitter; the article panel has "
        "'擷取與欄位' / '預覽與輸入' sub-tabs, a collapse button and Ctrl+Shift+A, remembers its width and collapsed state, "
        "and is collapsed by default on screens up to 800 px high",
        "UI: removed the message log and hint below the terminal; notices go to the status bar and critical save/typing-state "
        "errors also use a dialog; F11 toggles full screen from the View menu (Esc is still sent to the terminal)",
        "Themes: light / dark / follow-system (default), applied live and persisted; a separate light ANSI palette keeps the "
        "terminal readable; status and field colours follow the theme",
        "UI: opening a draft switches to the merged page, expands the panel and selects the preview sub-tab; the signature "
        "snapshot notice is visible above the sub-tabs; the article panel uses session/typer accessors ready for stage 2",
    ]),
    ("0.6.2", "2026/10/16", [
        "Security: robots.txt redirects get the same per-hop SSRF checks; endpoints must be wss:// (ws:// only for loopback testing), the "
        "assisted login only sends credentials to ws.ptt.cc; WebSocket frame/message size limits; CSI sequence length and repeat-count limits",
        "Typing: 'started' must be durably saved before the first byte is sent; every title chunk re-checks the title prompt; partial/"
        "incomplete bodies need a confirmation; failures to save the final state are reported",
        "Robustness: absurdly nested JSON-LD, corrupt font-size setting, IME control characters, folder-creation failure at startup, "
        "database backup before an upgrade, WebSocket socket cleanup in one place",
        "Fetch: only text/html and application/xhtml+xml are accepted (no SVG / feeds); User-Agent carries the real version; "
        "profile lookup uses the longest domain suffix",
    ]),
    ("0.6.1", "2026/10/16", [
        "Fetch: redirects are followed by the program hop by hop; every hop is checked for scheme, user:password@ and for loopback / LAN / "
        "metadata addresses (SSRF guard), robots.txt and request spacing are re-applied when the host changes; ignoring robots no longer "
        "requests robots.txt; robots.txt size is limited",
        "Title: an article title that already starts with a [category] is not prefixed with [新聞] again",
        "Login input: control characters and over-long values are refused (nothing is sent); screen de-duplication uses SHA-256",
        "Database: busy timeout for a second instance, literal % and _ in draft search; connection: PTT proxy status line split across frames, "
        "text frames ignored (PTT sends binary only); terminal: 256/true-colour SGR skipped, cursor repaint on focus change, IME send check",
        "Cleanup: fetch failure detail is logged, lint warnings fixed",
    ]),
    ("0.6.0", "2026/10/16", [
        "Drafts keep a snapshot of the signature text they were saved with (database schema v2, migrated automatically); opening a draft "
        "shows it with a 'use current signature' button",
        "Terminal keyboard / wheel / key bar are paused while automatic typing or the assisted login runs",
        "Connection: cancelling while connecting can no longer be undone by a late 'connected' signal; signals of replaced sockets are ignored",
        "Fetch: URLs with user:password@ are refused; a connection drop while downloading is reported as a fetch error; hostname only in logs",
        "Parser: no module-level / function-attribute state (time-zone note and truncation flag are per parse)",
        "Settings JSON that is corrupt or has an unexpected shape no longer crashes startup; database init errors are StorageError and the "
        "connection is always closed; startup errors show a dialog and unhandled exceptions are logged",
        "Typing finished message now says the data was sent, not that the server confirmed it; key bar checkbox and draft recovery order fixed",
        "requirements.txt added; README updated",
    ]),
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
