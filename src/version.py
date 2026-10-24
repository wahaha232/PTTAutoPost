"""Single source of truth for the application version (bump it on every delivered change)."""
__version__ = "0.8.9"
BUILD_DATE = "2026/10/24"
APP_NAME = "PTT AutoPost"

# Sponsorship: leave SPONSOR_URL empty to hide the whole block. Must be an http/https URL.
SPONSOR_URL = ""
SPONSOR_TEXT = ""

# newest first; tests/test_version.py enforces: CHANGELOG[0] == (__version__, BUILD_DATE)
CHANGELOG = [
    ("0.8.9", "2026/10/24", [
        "Interface font: changing the interface font/size now updates every existing widget too (menu bar, tabs, "
        "buttons, labels, line edits, article body and preview), not only widgets created after the change; the "
        "terminal still uses its own separate font setting.",
        "PTT article reload: the terminal has a '重新載入文章' button that sends Ctrl+L so PTT redraws the current "
        "article/screen (it does not leave the article), and image links are re-parsed. The article panel's web "
        "reload is renamed '重新載入網頁' to avoid confusion.",
        "Preview & input: personal notes and the signature editor (direct input + apply checkbox) moved to this "
        "tab; the whole tab scrolls on small windows.",
        "Two posting modes with P-coin estimates: '快速貼上' (the normal chunked typer) and '賺 P 幣（逐字配速）' "
        "(one character per ~0.5 s, the 1 P / 2 s rate). The estimate shows both modes, the article cap (1000 P, or "
        "25 P for [新聞]) and the expected duration; the app still never presses save/send.",
        "Image upload: pick images and upload them to an anonymous public host (Catbox permanent, Litterbox 72 h, "
        "uguu 3 h) without registering; the returned URLs are inserted at the body cursor. The original file bytes "
        "are uploaded unchanged, redirects to other hosts are refused, and the user confirms the public upload first.",
        "Right-click menus: Qt's built-in text menus and standard buttons are now Traditional Chinese "
        "(qtbase_zh_TW.qm is shipped with the portable build).",
    ]),
    ("0.8.7", "2026/10/24", [
        "Incremental updates for portable builds: a release can ship a small "
        "PTTAutoPost-<version>-delta-<base>.zip containing only changed files. The app picks the delta matching its "
        "current version, verifies update.json and every file's SHA-256, backs up replaced files under "
        "updates/backup-<version>/, and applies the update with a detached PowerShell helper that waits for exit, "
        "copies, and restarts. Wrong bases, unsafe paths, hash failures and older clients fall back to the full "
        "portable ZIP.",
        "A restart is still required because Windows locks the running exe, so files cannot be hot-swapped "
        "reliably; the app now restarts itself automatically after applying. config/logs/data are never part of a "
        "delta.",
        "Added tools/make_update_bundle.py to build deltas between two portable folders; unknown asset hosts are "
        "still refused.",
    ]),
    ("0.8.6", "2026/10/24", [
        "Article images: extraction is now scoped to the article's own content (nav / related / ad blocks are "
        "excluded), follows lazy data-src and the largest srcset, prefers a linked original, upgrades known "
        "thumbnail URLs (Wikimedia thumbs and CNA WebPhotos 400/800), and sends the article URL as Referer so "
        "hot-link-protected image CDNs work. This is why article auto-open looked broken: the old list mostly held "
        "page chrome and thumbnails.",
        "Article panel: new '重新載入文章' button re-fetches the article's own URL; new '打包下載圖片' downloads every "
        "article image at its original URL into one ZIP (no resizing, duplicate-safe names, per-image failures are "
        "skipped and reported).",
        "Settings: new interface font family and size (menus, buttons, article panel) applied live and saved; the "
        "terminal keeps its own font settings.",
    ]),
    ("0.8.5", "2026/10/24", [
        "Updates: release asset downloads now accept GitHub's current asset CDN host "
        "(release-assets.githubusercontent.com). GitHub redirects browser_download_url there, and the previous "
        "allow-list refused that redirect, so every update download stopped with '下載被重新導向到不允許的網址'. "
        "Verified end to end against the v0.8.4 portable ZIP (size and SHA-256 match); unknown redirect hosts are "
        "still refused.",
    ]),
    ("0.8.4", "2026/10/24", [
        "Image auto-open: a terminal image link now opens as soon as it appears — the app no longer waits for its own "
        "login detection or for automatic typing to finish (the viewer never takes keyboard focus). Auto-open accepts "
        "any public https image URL, either on a known image host or with an image extension "
        "(.jpg/.jpeg/.png/.gif/.webp/.bmp/.avif), and still rejects http, SVG, localhost and private addresses.",
        "New setting: hovering a terminal image link for about half a second shows a small preview next to the "
        "pointer (off by default); moving away hides it. Images are cached in memory, so the same URL is downloaded "
        "once.",
        "New setting: after an article is fetched, its <img> sources and image links open in the in-app gallery (off "
        "by default) with previous/next buttons. Article images may come from any public https host, but are still "
        "fetched with the per-hop SSRF/DNS-pinning checks and image content-type checks.",
    ]),
    ("0.8.3", "2026/10/24", [
        "Image auto-open: links now open in a viewer inside the program instead of an external browser. The image is "
        "downloaded over https from the same known image hosts, with the per-hop SSRF/DNS-pinning checks, no SVG, a "
        "20 MB limit and a pixel cap; the view scales with the window and the viewer never takes keyboard focus from "
        "the terminal.",
        "Packaging: the portable build keeps the JPEG, GIF and WebP image plugins (PNG/BMP are built into Qt), so "
        "auto-opened images actually render in the packaged app.",
    ]),
    ("0.8.2", "2026/10/23", [
        "Security: article fetching now fails closed when DNS resolution fails and pins the validated addresses for "
        "every redirect hop through a Session-scoped urllib3 transport (no process-wide socket patch), closing the "
        "DNS-rebinding window; robots.txt decisions expire (1 hour on success, 60 seconds on failure) and the cache "
        "is bounded.",
        "Reliability: disconnect is immediate and a quick reconnect is always possible; automatic typing and clipboard "
        "paste share one send lock; closing the window cancels the fetch task and cuts its signals; SQLite runs in WAL "
        "mode, pre-migration backups are WAL-consistent, and Settings can write a consistent online database backup.",
        "Safety/UX: Telnet connections require an explicit plaintext warning and the site list labels encrypted vs "
        "plaintext; download messages distinguish a matching SHA-256 from publisher identity; build versions are "
        "recorded in constraints-build.txt.",
        "Extraction: one DOM copy per page instead of re-parsing up to 18 candidate subtrees; candidate containers "
        "inside page-wide forms/navs are preserved; cp950 checks use a single-pass fast path; RIS keeps byte/bell "
        "statistics. Removed the stale 0.6.2 source dump and a leaked local path.",
    ]),
    ("0.8.1", "2026/10/23", [
        "Updates: optional automatic check on startup (packaged builds; silent when there is no update or the check "
        "fails), a progress bar for downloads, a '強制更新' path that re-downloads the current/latest release, and a "
        "'手動下載' action that opens the GitHub Releases page.",
        "Help: added an About dialog (version, build date, license summary, GitHub link) and a Sponsor action in the "
        "menu; the sponsor block still hides itself until SPONSOR_URL is configured.",
    ]),
    ("0.8.0", "2026/10/23", [
        "Updates: Settings and the Help menu can check GitHub Releases, compare versions and download the right "
        "asset (portable ZIP for a folder copy, setup.exe for an installed copy). Downloads use HTTPS, verify "
        "SHA-256 when GitHub provides a digest, and are never executed automatically; a token env var supports "
        "private repositories.",
        "Sites: a new '站台' tab with 13 bookmarks verified on 2026-10-23 (add/edit/delete, copy address, read-only "
        "TCP check). WSS and Telnet sites can be opened in the built-in terminal; SSH entries remain bookmarks.",
        "Telnet: the transport now supports telnet:// URLs through QTcpSocket, with IAC negotiation replies, the same "
        "Big5 screen and a plaintext warning. The assisted login still only sends credentials to ws.ptt.cc.",
        "Packaging: --archive now also writes a portable ZIP (the update asset) alongside the LZMA2 7z.",
    ]),
    ("0.7.2", "2026/10/23", [
        "Article fetch: every successful fetch starts a fresh article context. It detaches the previous draft, clears "
        "personal notes, the opened-draft signature snapshot, preview/manual state and the confirmation/typing "
        "checkboxes, so a second pasted URL no longer carries data from the first article.",
        "Article tab: new '清除全部欄位' button clears all fields, the preview and transient state after confirmation; "
        "saved drafts are kept.",
        "Signatures: choosing an entry from the drop-down now clears the opened draft's signature snapshot and applies "
        "the new choice immediately; previously the snapshot silently kept the old signature.",
        "Settings: new '套用' button re-applies and saves all current settings and shows a success dialog.",
        "Links: every detected hyperlink is underlined, not only the hovered one; hover still thickens it.",
        "Image auto-open: enabling the option processes images already on screen; images seen during typing or assisted "
        "login are no longer marked as handled forever — they are evaluated again when the run/login finishes.",
    ]),
    ("0.7.1", "2026/10/23", [
        "Paste: while a chunked paste is running, the article title/body input buttons, login and 'go to board' are "
        "disabled; their direct handlers and preflight refuse with a status-bar reason. Everything is restored when "
        "the paste ends (login still follows the connection state).",
        "Packaging: make_portable --onefile adds a diagnostic single-file build (onedir remains the default). "
        "PyInstaller filters keep plugins/platforms/qwindows.dll and plugins/tls while keeping only one copy of each "
        "OpenSSL DLL; --verify checks the platform and TLS files, and --archive falls back to ZIP when 7-Zip is absent.",
        "Packaging: the Inno Setup script deletes the old _internal folder on upgrade. LICENSE now explicitly allows "
        "modifying/reverse-engineering LGPL Qt components and states that the document is not legal advice.",
    ]),
    ("0.7.0", "2026/10/23", [
        "Release: the portable package is now an onedir folder instead of a onefile EXE; Qt/PySide6 DLLs stay as "
        "separate replaceable files. Unused Qt components (Quick/QML/Pdf/OpenGL/Svg, translations and image-format "
        "plugins) are removed from the collected files; the unpacked package is about 77 MB and the LZMA2 7z about 22 MB.",
        "Release: added an Inno Setup 6 script (LZMA2, per-user install, user config/logs/data preserved), plus "
        "make_portable --archive and --installer steps; the package now ships LICENSE, THIRD_PARTY_NOTICES.md, "
        "licenses/ and a user-facing README.txt.",
        "Licensing: proprietary LICENSE and third-party notices covering Qt/PySide6 (LGPL-3.0), requests, beautifulsoup4, "
        "lxml, charset-normalizer, Python and PyInstaller; the folder layout keeps Qt replaceable.",
        "Settings: optional sponsorship block, hidden unless SPONSOR_URL in src/version.py is a valid http/https URL; "
        "the default browser is opened only when the user clicks the button.",
    ]),
    ("0.6.7", "2026/10/23", [
        "Terminal: mouse selection by cell (drag, double-click word, triple-click line, optional Alt rectangle), with "
        "double-width characters never split; selected text is drawn with inverted colours. A single click, a screen "
        "update or a key sent to the BBS clears the selection; dragging from a link selects instead of opening it.",
        "Terminal copy: Ctrl+Shift+C or the right-click menu copies the selection (trailing spaces removed per line, "
        "lines joined with newlines), with 'select whole screen' and 'copy whole screen' in the same menu. Copy never "
        "sends bytes, and Ctrl+C without Shift still sends 0x03.",
        "Terminal paste: Ctrl+Shift+V or the right-click menu; blocked with a status-bar reason when offline or while "
        "automatic typing / assisted login holds the terminal. Only strict cp950 text is accepted (no partial paste); "
        "controls are removed, tabs become four spaces and line breaks become CR. More than one line or 200 characters "
        "shows a preview; more than 5000 characters is refused. Text is sent in 100-byte chunks on the article typer's "
        "rhythm, and a disconnect or a lock stops it without retry, reporting how much was sent. Ctrl+V still sends 0x16.",
    ]),
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
