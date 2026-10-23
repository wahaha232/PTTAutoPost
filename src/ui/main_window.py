"""Main window: terminal tab, article tab (parse / edit / preview / check / copy / type into PTT), drafts tab."""
from __future__ import annotations

import os
import subprocess
import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont, QFontDatabase, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFontComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                               QFileDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QMenu, QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget)

from .. import boards, compose, sites, update
from ..errors import ToolError
from ..links import is_auto_open_image_url, validate_http_url
from ..logging_setup import get_logger
from ..net.client import DEFAULT_URL, State
from ..terminal.detect import Kind
from ..net.poster import PostTyper, Target, preflight
from ..net.session import Login, PttSession
from ..parsers.extract import ParseResult, parse
from ..parsers.fetch import fetch
from ..storage.db import MAX_SIGNATURES, Database
from ..version import APP_NAME, SPONSOR_TEXT, SPONSOR_URL, __version__
from . import browser, theme
from .icon import app_icon, tray_icon
from .terminal_widget import TerminalWidget

log = get_logger("ui")
STATE_TEXT = {"found": "已取得", "missing": "未取得", "inferred": "推定（請確認）", "edited": "已修改", "manual": "手動輸入"}
BODY_TEXT = {"likely_complete": "內文可能完整（仍請對照原網頁）", "suspect_partial": "內文疑似不完整", "insufficient": "內文不足或沒有內文"}
STATUS_TEXT = {"success": "擷取成功", "partial": "部分成功", "failed": "擷取失敗"}
TYPE_HELP = "操作順序：在終端機進到「標題：」提示 → 輸入標題 → 自行按 Enter → 進入編輯畫面 → 輸入內文 → 自行檢查並存檔／發文。"
MAX_AUTO_OPEN_PER_MINUTE = 3
MAX_AUTO_OPEN_PER_SCREEN = 1
FIELDS = ("post_title", "title", "site", "author", "published", "url")
LABELS = {"post_title": "發文標題", "title": "新聞標題", "site": "媒體來源", "author": "記者／作者", "published": "發布時間", "url": "原文網址"}


class _Signals(QObject):
    done = Signal(object, object)    # Fetched, ParseResult
    failed = Signal(str, str)        # message, detail


class FetchTask(QRunnable):
    """Network + parsing off the GUI thread. Only plain data crosses back through signals."""

    def __init__(self, url: str, ignore_robots: bool):
        super().__init__()
        self.url, self.ignore_robots = url, ignore_robots
        self.signals = _Signals()

    def run(self):
        try:
            f = fetch(self.url, ignore_robots=self.ignore_robots)
            self.signals.done.emit(f, parse(f.html, f.final_url, f.warnings))
        except ToolError as e:
            self.signals.failed.emit(e.message, e.detail)
        except Exception as e:  # noqa: BLE001  (a parser bug must never kill the app)
            log.exception("unexpected error while fetching/parsing")
            self.signals.failed.emit("擷取時發生未預期的錯誤。", f"{type(e).__name__}: {e}")


class _UpdateSignals(QObject):
    done = Signal(object)             # update.Release
    failed = Signal(str)


class UpdateCheckTask(QRunnable):
    """GitHub API call off the GUI thread; never downloads in this task."""

    def __init__(self, token: str | None):
        super().__init__()
        self.token = token
        self.signals = _UpdateSignals()

    def run(self):
        try:
            self.signals.done.emit(update.fetch_latest_release(self.token))
        except update.UpdateError as e:
            self.signals.failed.emit(str(e))
        except Exception:  # noqa: BLE001
            log.exception("unexpected error while checking updates")
            self.signals.failed.emit("檢查更新時發生未預期的錯誤。")


class _DownloadSignals(QObject):
    progress = Signal(int, int)
    done = Signal(object)             # update.DownloadResult
    failed = Signal(str)


class UpdateDownloadTask(QRunnable):
    """Download one verified update asset; the UI never executes it automatically."""

    def __init__(self, asset: update.Asset, token: str | None):
        super().__init__()
        self.asset, self.token = asset, token
        self.signals = _DownloadSignals()

    def run(self):
        try:
            result = update.download_asset(self.asset, token=self.token,
                                           progress=lambda done, total: self.signals.progress.emit(done, total))
            self.signals.done.emit(result)
        except update.UpdateError as e:
            self.signals.failed.emit(str(e))
        except Exception:  # noqa: BLE001
            log.exception("unexpected error while downloading an update")
            self.signals.failed.emit("下載更新檔時發生未預期的錯誤。")


class _SiteCheckSignals(QObject):
    done = Signal(bool, str)


class SiteCheckTask(QRunnable):
    """Read-only TCP reachability check; no login bytes are sent."""

    def __init__(self, site: dict):
        super().__init__()
        self.site = site
        self.signals = _SiteCheckSignals()

    def run(self):
        ok, msg = sites.check_site(self.site)
        self.signals.done.emit(ok, msg)


def _mono() -> QFont:
    f = QFont("MingLiU")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(11)
    return f


class MainWindow(QMainWindow):
    def __init__(self, db: Database, session: PttSession | None = None):
        super().__init__()
        self.db = db
        self.session = session or PttSession(self)
        self.typer = PostTyper(self.session, self)
        self.draft_id: int | None = None
        self.states: dict[str, str] = {f: "missing" for f in FIELDS}
        self._loading = False
        self._preview_manual = False
        self._setting_preview = False
        self._last_result: ParseResult | None = None
        self._busy = False
        self._update_busy = False
        self._update_check_task = None
        self._update_download_task = None
        self._update_asset: update.Asset | None = None
        self._update_token: str | None = None
        self._pending_site_url: str | None = None
        self._site_check_task = None
        self._typing_target: Target | None = None
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 560)                     # freely resizable above this
        self._quitting = False
        self._dirty = False                               # unsaved edits in the current draft
        self._typing_draft_id: int | None = None          # draft that the running typing session belongs to
        self._ack_incomplete: set[int] = set()            # drafts whose partial body the user already confirmed
        self._draft_sig: str | None = None                # signature snapshot of the opened draft (None = use the selected one)
        self._tray: QSystemTrayIcon | None = None
        self._tray_hint_shown = False
        self._theme_choice = self._load_theme_choice()
        self._theme_name = self._resolve_theme(self._theme_choice)
        self._theme_data = theme.get_theme(self._theme_name)
        self._terminal_palette_choice = self._load_terminal_palette_choice()
        self._browser_mode = self._load_browser_mode()
        self._browser_path_value = self.db.get_setting("browser.path", "")
        self._auto_opened: set[str] = set()
        self._auto_open_times: deque[float] = deque()
        self._parse_kind: str | None = None
        self._article_width_timer = QTimer(self)
        self._article_width_timer.setSingleShot(True)
        self._article_width_timer.setInterval(500)
        self._article_width_timer.timeout.connect(self._save_article_width)
        self.compact = self._screen_is_compact()      # typical 1366x768 laptop
        self._init_geometry()
        self._build_article_toggle_action()
        self._build_menu()
        tabs = QTabWidget()
        tabs.addTab(self._build_terminal_article_tab(), "終端機與文章")
        tabs.addTab(self._build_sites_tab(), "站台")
        tabs.addTab(self._build_drafts_tab(), "草稿")
        tabs.addTab(self._build_settings_tab(), "設定")
        self.tabs = tabs
        self.setCentralWidget(tabs)
        self.term.linkActivated.connect(self._open_link)
        self.term.linksChanged.connect(self._on_links_changed)
        self.term.pasteStateChanged.connect(self._on_paste_state)
        self._apply_theme(self._theme_choice, save=False)
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        except AttributeError:                            # older Qt: no live system-theme signal
            pass
        self._build_tray()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(350)
        self._refresh_timer.timeout.connect(self._auto_preview)
        self.session.client.stateChanged.connect(self._on_conn_state)
        self.session.loginChanged.connect(self._on_login_state)
        self.session.notice.connect(self._notice)
        self.typer.started.connect(self._typing_started)
        self.typer.finished.connect(self._typing_finished)
        self.typer.progress.connect(lambda i, n: self.type_status.setText(f"輸入中… {i}/{n} 段"))
        self.new_draft()
        self.db.recover_interrupted_inputs()               # before the first list load, so aborted runs show correctly
        self.reload_drafts()
        self._on_conn_state(self.session.client.state)

    # ================================================================== terminal tab
    @staticmethod
    def _screen_is_compact() -> bool:
        """True on a typical 1366x768 laptop; used as the article-panel default."""
        scr = QGuiApplication.primaryScreen()
        return bool(scr and scr.availableGeometry().height() <= 800)

    def _build_article_toggle_action(self) -> None:
        self.act_toggle_article = QAction("顯示文章面板", self)
        self.act_toggle_article.setCheckable(True)
        self.act_toggle_article.setShortcut(QKeySequence("F12"))
        self.act_toggle_article.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_toggle_article.toggled.connect(self._set_article_panel_visible)
        self.addAction(self.act_toggle_article)

    def _build_menu(self) -> None:
        view = self.menuBar().addMenu("檢視")
        view.addAction(self.act_toggle_article)
        self.act_fullscreen = QAction("全螢幕", self)
        self.act_fullscreen.setCheckable(True)
        self.act_fullscreen.setShortcut(QKeySequence("F11"))
        self.act_fullscreen.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.act_fullscreen.toggled.connect(self._set_fullscreen)
        self.addAction(self.act_fullscreen)
        view.addSeparator()
        view.addAction(self.act_fullscreen)
        help_menu = self.menuBar().addMenu("說明")
        self.act_check_update = QAction("檢查更新…", self)
        self.act_check_update.triggered.connect(self.check_updates)
        help_menu.addAction(self.act_check_update)

    def _set_fullscreen(self, on: bool) -> None:
        if on and not self.isFullScreen():
            self.showFullScreen()
        elif not on and self.isFullScreen():
            self.showNormal()

    def _build_terminal_article_tab(self) -> QWidget:
        """One page: terminal on the left, the article panel on the right (collapsible)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.terminal_panel = self._build_terminal_tab()
        self.article_panel = self._build_article_tab()
        self.article_panel.setMinimumWidth(320)
        self.main_splitter.addWidget(self.terminal_panel)
        self.main_splitter.addWidget(self.article_panel)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)
        lay.addWidget(self.main_splitter)
        self._restore_article_panel_state()
        return page

    def _build_terminal_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.url_box = QComboBox()
        self.url_box.setEditable(True)
        self.url_box.addItem(DEFAULT_URL)
        self.url_box.setMinimumWidth(240)
        self.btn_connect = QPushButton("連線")
        self.btn_disconnect = QPushButton("斷線")
        self.account = QLineEdit()
        self.account.setPlaceholderText("PTT 帳號")
        self.account.setFixedWidth(130)
        self.password = QLineEdit()
        self.password.setPlaceholderText("密碼（不會被儲存或記錄）")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setFixedWidth(190)
        self.btn_login = QPushButton("登入")
        self.btn_article_toggle = QPushButton("文章面板")
        self.btn_article_toggle.setCheckable(True)
        self.btn_article_toggle.setToolTip("顯示／收合文章面板（F12）")
        self.btn_article_toggle.toggled.connect(self._set_article_panel_visible)
        for x in (QLabel("端點"), self.url_box, self.btn_connect, self.btn_disconnect, QLabel("帳號"), self.account, self.password, self.btn_login,
                  self.btn_article_toggle):
            bar.addWidget(x)
        bar.addStretch(1)
        lay.addLayout(bar)
        st = QHBoxLayout()
        self.lbl_conn = QLabel()
        self.lbl_login = QLabel()
        st.addWidget(self.lbl_conn)
        st.addWidget(self.lbl_login)
        st.addStretch(1)
        lay.addLayout(st)
        fam = self.db.get_setting("terminal.font", "")
        try:
            px = min(96, max(6, int(self.db.get_setting("terminal.font_px", "17") or 17)))
        except ValueError:                                # corrupt setting: fall back instead of failing at startup
            px = 17
        fill = self.db.get_setting("terminal.fill", "1") == "1"      # default: fit the window
        self.term = TerminalWidget(self.session, family=fam, px=px, fill=fill)
        self.term.set_stretch(self.db.get_setting("terminal.stretch", "0") == "1")
        self.term.notice.connect(self._notice)
        self.term_holder = QGridLayout()
        self.term_holder.addWidget(self.term, 0, 0)
        self._align_terminal()
        lay.addLayout(self.term_holder, 1)
        fb = QHBoxLayout()
        self.tb_font = QFontComboBox()
        self.tb_font.setCurrentFont(QFont(self.term.font_.family()))
        self.tb_font.setMaximumWidth(260)
        self.tb_size = QSpinBox()
        self.tb_size.setRange(8, 64)
        self.tb_size.setSuffix(" px")
        self.tb_size.setValue(self.term.font_.pixelSize())
        self.tb_fill = QCheckBox("自動符合視窗大小")
        self.tb_fill.setChecked(self.term.fill)
        self.tb_stretch = QCheckBox("拉伸填滿")
        self.tb_stretch.setToolTip("字元拉寬／拉高到完全填滿視窗（會變形）；關閉時維持字元比例並置中。")
        self.tb_stretch.setChecked(self.term.stretch)
        self.tb_dfyuan = QPushButton("華康中圓體")
        for x in (QLabel("PTT 字型"), self.tb_font, self.tb_dfyuan, QLabel("大小"), self.tb_size, self.tb_fill, self.tb_stretch):
            fb.addWidget(x)
        fb.addStretch(1)
        lay.addLayout(fb)
        self.keybar = QWidget()
        kb = QHBoxLayout(self.keybar)
        kb.setContentsMargins(0, 0, 0, 0)
        kb.addWidget(QLabel("按鍵"))
        for label_, seq in (("Esc", b"\x1b"), ("←", b"\x1b[D"), ("↑", b"\x1b[A"), ("↓", b"\x1b[B"), ("→", b"\x1b[C"),
                            ("PgUp", b"\x1b[5~"), ("PgDn", b"\x1b[6~"), ("Home", b"\x1b[1~"), ("End", b"\x1b[4~")):
            b = QPushButton(label_)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setMaximumWidth(56)
            b.clicked.connect(lambda _c=False, q=seq: self._send_key(q))
            kb.addWidget(b)
        kb.addStretch(1)
        lay.addWidget(self.keybar)
        self.keybar.setVisible(self._keybar_default())
        self.tb_font.currentFontChanged.connect(lambda _f: self._apply_terminal_settings(bar=True))
        self.tb_dfyuan.clicked.connect(self.use_dfyuan)
        self.tb_size.valueChanged.connect(lambda _v: self._apply_terminal_settings(bar=True))
        self.tb_fill.toggled.connect(lambda _c: self._apply_terminal_settings(bar=True))
        self.tb_stretch.toggled.connect(lambda _c: self._apply_terminal_settings(bar=True))
        self.btn_connect.clicked.connect(lambda: self.session.connect_to(self.url_box.currentText().strip() or DEFAULT_URL))
        self.btn_disconnect.clicked.connect(self.session.disconnect_)
        self.btn_login.clicked.connect(self._do_login)
        self.password.returnPressed.connect(self._do_login)
        return w

    def _align_terminal(self):
        """Fixed-size terminal is centred; in fill mode it takes the whole area."""
        self.term_holder.setAlignment(self.term, Qt.AlignmentFlag(0) if self.term.fill else Qt.AlignmentFlag.AlignCenter)

    # ================================================================== article panel layout
    @staticmethod
    def _read_int_setting(raw: str, default: int, low: int, high: int) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    def _restore_article_panel_state(self) -> None:
        self._article_width = self._read_int_setting(
            self.db.get_setting("ui.article_panel_width", ""), 620, 320, 1600)
        raw_collapsed = self.db.get_setting("ui.article_panel_collapsed", "")
        if raw_collapsed in ("0", "1"):
            collapsed = raw_collapsed == "1"
        else:
            collapsed = self.compact                 # no saved state: collapsed on a short screen
        self._article_collapsed = collapsed
        if collapsed:
            self.article_panel.hide()
        else:
            self.article_panel.show()
        self._update_article_toggle_ui()
        QTimer.singleShot(0, self._apply_article_panel_sizes)

    def _apply_article_panel_sizes(self) -> None:
        if not hasattr(self, "main_splitter"):
            return
        if getattr(self, "_article_collapsed", True):
            self.main_splitter.setSizes([1, 0])
            return
        total = max(self.main_splitter.width(), self.width())
        width = max(320, min(self._article_width, max(320, total - 320)))
        self._article_width = width
        self.main_splitter.setSizes([max(1, total - width), width])

    def _set_article_panel_visible(self, visible: bool) -> None:
        if not hasattr(self, "article_panel") or not hasattr(self, "main_splitter"):
            return
        visible = bool(visible)
        if visible == (not getattr(self, "_article_collapsed", True)):
            self._update_article_toggle_ui()
            return
        if visible:
            self._article_collapsed = False
            self.article_panel.show()
            self._apply_article_panel_sizes()
        else:
            sizes = self.main_splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 0:
                self._article_width = sizes[1]
            self._article_collapsed = True
            self.article_panel.hide()
            self.main_splitter.setSizes([1, 0])
        self.db.set_setting("ui.article_panel_collapsed", "1" if self._article_collapsed else "0")
        if not self._article_collapsed:
            self.db.set_setting("ui.article_panel_width", str(self._article_width))
        self._update_article_toggle_ui()
        QTimer.singleShot(0, self._relayout_after_panel_change)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if not getattr(self, "_article_collapsed", True):
            sizes = self.main_splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 0:
                self._article_width = sizes[1]
                self._article_width_timer.start()      # one write ~500 ms after the user stops dragging
        QTimer.singleShot(0, self._relayout_after_panel_change)

    def _save_article_width(self) -> None:
        if not getattr(self, "_article_collapsed", True):
            self.db.set_setting("ui.article_panel_width", str(getattr(self, "_article_width", 620)))

    def _relayout_after_panel_change(self) -> None:
        self.term._relayout()

    def _update_article_toggle_ui(self) -> None:
        on = not getattr(self, "_article_collapsed", True)
        for widget in (getattr(self, "btn_article_toggle", None), getattr(self, "act_toggle_article", None)):
            if widget is not None:
                widget.blockSignals(True)
                widget.setChecked(on)
                widget.blockSignals(False)

    def _save_article_panel_state(self) -> None:
        if hasattr(self, "_article_width_timer"):
            self._article_width_timer.stop()
        self.db.set_setting("ui.article_panel_collapsed", "1" if getattr(self, "_article_collapsed", True) else "0")
        if not getattr(self, "_article_collapsed", True):
            self.db.set_setting("ui.article_panel_width", str(getattr(self, "_article_width", 620)))

    def _article_session(self) -> PttSession:
        """Seam for stage 2: the article panel follows the active connection, not a hard-coded one."""
        return self.session

    def _article_typer(self) -> PostTyper:
        return self.typer

    # ================================================================== settings tab
    def _load_browser_mode(self) -> str:
        raw = self.db.get_setting("browser.mode", "system")
        return raw if raw in browser.BROWSER_KEYS else "system"

    def _reload_browser_combo(self, select: str) -> None:
        self._browser_paths = browser.detect_browsers()
        combo = self.browser_combo
        combo.blockSignals(True)
        combo.clear()
        for key in ("system", "chrome", "edge", "firefox", "custom"):
            label = browser.BROWSER_LABELS[key]
            if key in ("chrome", "edge", "firefox") and key not in self._browser_paths:
                label += "（找不到）"
            combo.addItem(label, key)
        idx = combo.findData(select if select in browser.BROWSER_KEYS else "system")
        combo.setCurrentIndex(max(0, idx))
        combo.blockSignals(False)
        self._sync_browser_ui()

    def _sync_browser_ui(self) -> None:
        custom = self.browser_combo.currentData() == "custom"
        self.browser_path.setEnabled(custom)
        self.btn_browser_browse.setEnabled(custom)

    def _browser_mode_changed(self, _index: int) -> None:
        self._browser_mode = self.browser_combo.currentData() or "system"
        self._browser_path_value = self.browser_path.text()
        self.db.set_setting("browser.mode", self._browser_mode)
        if self._browser_mode == "custom":
            self.db.set_setting("browser.path", self._browser_path_value)
        self._sync_browser_ui()

    def _save_browser_path(self) -> None:
        self._browser_path_value = self.browser_path.text().strip()
        self.db.set_setting("browser.path", self._browser_path_value)

    def _browse_browser(self) -> None:
        start = str(Path(self.browser_path.text()).parent) if self.browser_path.text().strip() else ""
        f, _ = QFileDialog.getOpenFileName(self, "選擇瀏覽器執行檔", start, "程式 (*.exe);;所有檔案 (*)")
        if not f:
            return
        self.browser_path.setText(f)
        idx = self.browser_combo.findData("custom")
        if idx >= 0:
            self.browser_combo.setCurrentIndex(idx)
        self._save_browser_path()
        self._browser_mode_changed(self.browser_combo.currentIndex())

    def _detect_browsers(self) -> None:
        self._reload_browser_combo(self._browser_mode)
        self._notice("已重新偵測瀏覽器（找不到的項目會標示）。")

    def _auto_image_toggled(self, on: bool) -> None:
        self.db.set_setting("links.image_auto_open", "1" if on else "0")
        if on and hasattr(self, "term"):
            self._on_links_changed(self.term.links())          # apply to images already on screen
        self._notice("已開啟圖片連結自動開啟；圖床會看到您的 IP。" if on else "已關閉圖片連結自動開啟。")

    def _open_sponsor(self) -> bool:
        url = SPONSOR_URL.strip()
        if not url:
            self._notice("未設定贊助連結。")
            return False
        ok, msg = browser.open_url(url, "system")
        self._notice(msg)
        return ok

    def _open_link(self, url: str, auto: bool = False) -> bool:
        mode = self.browser_combo.currentData() if hasattr(self, "browser_combo") else "system"
        path = self.browser_path.text().strip() if hasattr(self, "browser_path") else ""
        ok, msg = browser.open_url(url, mode or "system", path)
        if ok:
            self._auto_opened.add(url)                 # a manual click also counts for this connection
        if ok and auto:
            msg = "已自動開啟圖片連結。"
        self._notice(msg)
        return ok

    def _on_links_changed(self, links) -> None:
        if not (hasattr(self, "chk_auto_image") and self.chk_auto_image.isChecked()):
            return
        session, typer = self._article_session(), self._article_typer()
        images = [link for link in links if is_auto_open_image_url(link.url)]
        if not images:
            return
        if not session.logged_in or typer.running or session.login_state is Login.LOGGING_IN:
            return                                        # evaluate again when typing/login finishes
        now = time.monotonic()
        while self._auto_open_times and now - self._auto_open_times[0] >= 60:
            self._auto_open_times.popleft()
        opened = 0
        skipped = 0
        for link in images:
            if link.url in self._auto_opened:
                continue
            self._auto_opened.add(link.url)           # never retry the same URL in this connection
            if opened >= MAX_AUTO_OPEN_PER_SCREEN or len(self._auto_open_times) >= MAX_AUTO_OPEN_PER_MINUTE:
                skipped += 1
                continue
            if self._open_link(link.url, auto=True):
                self._auto_open_times.append(now)
                opened += 1
        if skipped:
            self._notice(f"已達自動開啟上限，略過 {skipped} 個圖片連結；可手動點擊開啟。")

    # ================================================================== settings tab
    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        ap = QGroupBox("外觀")
        af = QFormLayout(ap)
        self.theme_combo = QComboBox()
        for key, label in theme.CHOICES:
            self.theme_combo.addItem(label, key)
        idx = self.theme_combo.findData(self._theme_choice)
        self.theme_combo.setCurrentIndex(max(0, idx))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo)
        af.addRow("主題", self.theme_combo)
        af.addRow(QLabel("「跟隨系統」會依 Windows 的淺色／深色設定即時切換。"))
        self.terminal_palette_combo = QComboBox()
        for key, label in theme.TERMINAL_PALETTE_CHOICES:
            self.terminal_palette_combo.addItem(label, key)
        idx = self.terminal_palette_combo.findData(self._terminal_palette_choice)
        self.terminal_palette_combo.setCurrentIndex(max(0, idx))
        self.terminal_palette_combo.currentIndexChanged.connect(self._on_terminal_palette_combo)
        af.addRow("終端機配色", self.terminal_palette_combo)
        af.addRow(QLabel("只影響終端機；「永遠深色」固定黑底，「跟隨主題」在淺色主題使用淺色配色。"))
        lay.addWidget(ap)

        bg = QGroupBox("連結與瀏覽器")
        bf = QFormLayout(bg)
        self.browser_combo = QComboBox()
        self.browser_path = QLineEdit(self._browser_path_value)
        self.browser_path.setPlaceholderText("自訂瀏覽器執行檔路徑（僅在「自訂執行檔」時使用）")
        self.btn_browser_browse = QPushButton("瀏覽…")
        self.btn_browser_detect = QPushButton("重新偵測")
        row_b = QHBoxLayout()
        row_b.addWidget(self.browser_path, 1)
        row_b.addWidget(self.btn_browser_browse)
        row_b.addWidget(self.btn_browser_detect)
        self.chk_auto_image = QCheckBox("自動開啟圖片連結")
        self.chk_auto_image.setChecked(self.db.get_setting("links.image_auto_open", "0") == "1")
        self.lbl_auto_image_note = QLabel("預設關閉。只自動開啟 imgur 等已知圖床的 https 連結；自動開啟會讓圖床看到您的 IP，同一連線同一網址只開一次，且有每分鐘上限。")
        self.lbl_auto_image_note.setWordWrap(True)
        bf.addRow("瀏覽器", self.browser_combo)
        bf.addRow("自訂路徑", row_b)
        bf.addRow("", self.chk_auto_image)
        bf.addRow("", self.lbl_auto_image_note)
        lay.addWidget(bg)
        self._browser_paths: dict[str, str] = {}
        self._reload_browser_combo(self._browser_mode)
        self.browser_combo.currentIndexChanged.connect(self._browser_mode_changed)
        self.browser_path.editingFinished.connect(self._save_browser_path)
        self.btn_browser_browse.clicked.connect(self._browse_browser)
        self.btn_browser_detect.clicked.connect(self._detect_browsers)
        self.chk_auto_image.toggled.connect(self._auto_image_toggled)
        self._sync_browser_ui()

        g = QGroupBox("終端機顯示")
        form = QFormLayout(g)
        self.set_font = QFontComboBox()
        self.set_font.setCurrentFont(QFont(self.term.font_.family()))
        self.set_size = QSpinBox()
        self.set_size.setRange(8, 64)
        self.set_size.setSuffix(" px")
        self.set_size.setValue(self.term.font_.pixelSize())
        self.set_fill = QCheckBox("自動符合視窗大小（填滿可視畫面；字型大小隨視窗自動調整，此時上方「字型大小」只在關閉此項時使用）")
        self.set_fill.setChecked(self.term.fill)
        self.set_stretch = QCheckBox("拉伸填滿（字元拉寬／拉高到完全沒有黑邊，字形會變形；關閉時維持字元比例並置中）")
        self.set_stretch.setChecked(self.term.stretch)
        self.btn_font_default = QPushButton("還原預設")
        self.set_dfyuan = QPushButton("華康中圓體")
        row_f = QHBoxLayout()
        row_f.addWidget(self.set_font, 1)
        row_f.addWidget(self.set_dfyuan)
        form.addRow("字型", row_f)
        form.addRow("字型大小", self.set_size)
        form.addRow("", self.set_fill)
        form.addRow("", self.set_stretch)
        form.addRow("", self.btn_font_default)
        lay.addWidget(g)
        tg = QGroupBox("視窗與系統匣")
        tl = QVBoxLayout(tg)
        self.chk_tray_min = QCheckBox("最小化時縮到系統匣（工作列不顯示，從系統匣圖示還原）")
        self.chk_tray_close = QCheckBox("按視窗關閉鈕（X）時縮到系統匣（要真正結束請在系統匣圖示按右鍵選「離開」）")
        self.chk_keybar = QCheckBox("終端機下方顯示按鍵列（Esc、方向鍵、PgUp／PgDn、Home／End；筆電沒有這些鍵時使用）")
        self.chk_keybar.setChecked(not self.keybar.isHidden())
        self.chk_keybar.toggled.connect(self._keybar_toggled)
        tl.addWidget(self.chk_keybar)
        self.lbl_tray_note = QLabel("")
        self.lbl_tray_note.setWordWrap(True)
        tl.addWidget(self.chk_tray_min)
        tl.addWidget(self.chk_tray_close)
        tl.addWidget(self.lbl_tray_note)
        lay.addWidget(tg)
        self.chk_tray_min.setChecked(self.db.get_setting("tray.minimize", "0") == "1")
        self.chk_tray_close.setChecked(self.db.get_setting("tray.close", "0") == "1")
        self.chk_tray_min.toggled.connect(lambda _c: self._tray_settings_changed())
        self.chk_tray_close.toggled.connect(lambda _c: self._tray_settings_changed())
        lg = QGroupBox("PTT 登入小幫手（外部程式，獨立執行）")
        ll_ = QVBoxLayout(lg)
        lrow = QHBoxLayout()
        self.pttlogin_path = QLineEdit(self.db.get_setting("pttlogin.path", "") or self._find_pttlogin())
        self.pttlogin_path.setPlaceholderText("PttAutoLogin.exe 的完整路徑")
        self.btn_pttlogin_browse = QPushButton("瀏覽…")
        self.btn_pttlogin_open = QPushButton("開啟登入小幫手")
        lrow.addWidget(self.pttlogin_path, 1)
        lrow.addWidget(self.btn_pttlogin_browse)
        lrow.addWidget(self.btn_pttlogin_open)
        ll_.addLayout(lrow)
        ll_.addWidget(QLabel("以獨立程式啟動，帳號密碼與排程仍由登入小幫手自己管理；本程式不讀取、不保存其帳密。"))
        lay.addWidget(lg)
        self.btn_pttlogin_browse.clicked.connect(self._browse_pttlogin)
        self.btn_pttlogin_open.clicked.connect(self.launch_pttlogin)
        self.pttlogin_path.editingFinished.connect(lambda: self.db.set_setting("pttlogin.path", self.pttlogin_path.text().strip()))
        ug = QGroupBox("更新")
        ul = QVBoxLayout(ug)
        self.lbl_update_status = QLabel(f"目前版本 {__version__}。從 GitHub Releases 檢查更新；攜帶版下載 ZIP，安裝版下載 setup.exe。程式只會下載並驗證檔案，不會自動執行。")
        self.lbl_update_status.setWordWrap(True)
        urow = QHBoxLayout()
        self.btn_update_check = QPushButton("檢查更新")
        self.btn_update_folder = QPushButton("開啟更新資料夾")
        urow.addWidget(self.btn_update_check)
        urow.addWidget(self.btn_update_folder)
        urow.addStretch(1)
        ul.addWidget(self.lbl_update_status)
        ul.addLayout(urow)
        lay.addWidget(ug)
        self.btn_update_check.clicked.connect(self.check_updates)
        self.btn_update_folder.clicked.connect(self.open_update_folder)
        sg = QGroupBox("贊助作者")
        sl = QVBoxLayout(sg)
        sponsor_note = QLabel("贊助出於自願，不影響任何功能；程式不會追蹤或上傳資料，只會在您按下按鈕時用預設瀏覽器開啟贊助頁。")
        sponsor_note.setWordWrap(True)
        self.btn_sponsor = QPushButton(SPONSOR_TEXT.strip() or "贊助作者")
        self.btn_sponsor.clicked.connect(self._open_sponsor)
        sl.addWidget(sponsor_note)
        sl.addWidget(self.btn_sponsor)
        self.sponsor_box = sg
        sg.setVisible(bool(SPONSOR_URL.strip() and validate_http_url(SPONSOR_URL.strip())))
        lay.addWidget(sg)
        note = QLabel("終端機是等寬格線（80×24），中文字佔 2 格；建議使用 MingLiU、NSimSun 等等寬中文字型。變更會立即套用並儲存在本機，也可按「套用」一次確認並儲存。")
        note.setWordWrap(True)
        lay.addWidget(note)
        apply_row = QHBoxLayout()
        apply_row.addStretch(1)
        self.btn_apply_settings = QPushButton("套用")
        self.btn_apply_settings.setToolTip("套用目前所有設定、儲存到本機，並顯示成功訊息。")
        apply_row.addWidget(self.btn_apply_settings)
        lay.addLayout(apply_row)
        lay.addStretch(1)
        self.btn_apply_settings.clicked.connect(self.apply_settings)
        self.set_font.currentFontChanged.connect(lambda _f: self._apply_terminal_settings())
        self.set_size.valueChanged.connect(lambda _v: self._apply_terminal_settings())
        self.set_fill.toggled.connect(lambda _c: self._apply_terminal_settings())
        self.set_stretch.toggled.connect(lambda _c: self._apply_terminal_settings())
        self.btn_font_default.clicked.connect(self._reset_terminal_settings)
        self.set_dfyuan.clicked.connect(self.use_dfyuan)
        return w

    def _apply_terminal_settings(self, bar: bool = False):
        src = (self.tb_font, self.tb_size, self.tb_fill, self.tb_stretch) if bar else (self.set_font, self.set_size, self.set_fill, self.set_stretch)
        dst = (self.set_font, self.set_size, self.set_fill, self.set_stretch) if bar else (self.tb_font, self.tb_size, self.tb_fill, self.tb_stretch)
        fam, px, fill, stretch = src[0].currentFont().family(), src[1].value(), src[2].isChecked(), src[3].isChecked()
        for wdg in dst:
            wdg.blockSignals(True)
        dst[0].setCurrentFont(QFont(fam))
        dst[1].setValue(px)
        dst[2].setChecked(fill)
        dst[3].setChecked(stretch)
        for wdg in dst:
            wdg.blockSignals(False)
        self.term.apply_font(fam, px)
        self.term.set_stretch(stretch)
        self.term.set_fill(fill)
        self._align_terminal()
        self.db.set_setting("terminal.font", fam)
        self.db.set_setting("terminal.font_px", str(px))
        self.db.set_setting("terminal.fill", "1" if fill else "0")
        self.db.set_setting("terminal.stretch", "1" if stretch else "0")

    DFYUAN_FAMILIES = ("DFYuanMedium-B5", "華康中圓體", "DFPYuanMedium-B5")

    def use_dfyuan(self):
        """Select 華康中圓體 (DFKai/DynaFont Yuan Medium) if it is installed; the font itself is not bundled."""
        have = set(QFontDatabase.families())
        fam = next((f for f in self.DFYUAN_FAMILIES if f in have), "")
        if not fam:
            self._notice("此電腦未安裝華康中圓體（DFYuanMedium-B5），請先安裝該字型後再選用。")
            return
        self.set_font.setCurrentFont(QFont(fam))      # triggers _apply_terminal_settings and syncs the bar
        self._notice(f"終端機字型已設為 {fam}。")

    def _reset_terminal_settings(self):
        for wdg in (self.set_font, self.set_size, self.set_fill, self.set_stretch):
            wdg.blockSignals(True)
        self.set_font.setCurrentFont(QFont(TerminalWidget.default_family()))
        self.set_size.setValue(17)
        self.set_fill.setChecked(True)
        self.set_stretch.setChecked(False)
        for wdg in (self.set_font, self.set_size, self.set_fill, self.set_stretch):
            wdg.blockSignals(False)
        self._apply_terminal_settings()

    def apply_settings(self):
        self._apply_theme(self.theme_combo.currentData() or "system")
        palette = self.terminal_palette_combo.currentData()
        self._terminal_palette_choice = palette if palette in theme.TERMINAL_PALETTE_KEYS else "dark"
        self.term.set_theme(self._terminal_theme_name())
        self.db.set_setting("ui.terminal_palette", self._terminal_palette_choice)
        self._browser_mode_changed(self.browser_combo.currentIndex())
        self._save_browser_path()
        self.db.set_setting("links.image_auto_open", "1" if self.chk_auto_image.isChecked() else "0")
        if self.chk_auto_image.isChecked():
            self._on_links_changed(self.term.links())
        self._apply_terminal_settings()
        self._tray_settings_changed()
        self.db.set_setting("pttlogin.path", self.pttlogin_path.text().strip())
        QMessageBox.information(self, "設定已套用", "設定已成功套用並儲存。")
        self._notice("設定已套用並儲存。")

    def _set_update_busy(self, on: bool) -> None:
        self._update_busy = bool(on)
        for widget in (getattr(self, "btn_update_check", None), getattr(self, "act_check_update", None)):
            if widget is not None:
                widget.setEnabled(not on)

    def check_updates(self) -> None:
        if self._update_busy:
            self._notice("已有更新檢查或下載進行中。")
            return
        self._set_update_busy(True)
        if hasattr(self, "lbl_update_status"):
            self.lbl_update_status.setText("正在向 GitHub 檢查更新…")
        self._notice("正在向 GitHub 檢查更新…")
        self._update_token = update.github_token()
        task = UpdateCheckTask(self._update_token)
        task.signals.done.connect(self._on_update_release)
        task.signals.failed.connect(self._on_update_error)
        self._update_check_task = task
        QThreadPool.globalInstance().start(task)

    def _on_update_release(self, release: update.Release) -> None:
        self._set_update_busy(False)
        if not update.is_newer(release.version, __version__):
            if hasattr(self, "lbl_update_status"):
                self.lbl_update_status.setText(f"已是最新版本（{__version__}）。")
            self._notice(f"已是最新版本（{__version__}）。")
            QMessageBox.information(self, "檢查更新", f"目前版本 {__version__}，已是最新版本。")
            return
        installed = update.is_installed()
        asset = update.choose_asset(release.assets, installed)
        if asset is None:
            need = "setup.exe" if installed else "portable ZIP（或 7z）"
            msg = (f"發現新版本 {release.version}，但 Release 沒有適合"
                   f"{'安裝版' if installed else '攜帶版'}的更新檔（需要 {need}）。\n\n"
                   f"請到 Release 頁面手動下載：\n{release.html_url or '(沒有頁面網址)'}")
            if hasattr(self, "lbl_update_status"):
                self.lbl_update_status.setText(f"發現 {release.version}，但找不到適合的更新檔。")
            self._notice("找到新版本，但 Release 缺少適合此版本的更新檔。")
            QMessageBox.information(self, "缺少更新檔", msg)
            return
        notes = release.notes.strip()
        if len(notes) > 1200:
            notes = notes[:1200] + "…"
        size = f"{asset.size / 1024 / 1024:.1f} MB" if asset.size else "大小未知"
        target = "安裝版 setup.exe" if installed else "攜帶版壓縮檔"
        msg = (f"目前版本 {__version__}，最新版本 {release.version}。\n\n"
               f"更新檔（{target}）：{asset.name}（{size}）\n\n{notes}\n\n"
               "下載後不會自動安裝或執行；完成後請關閉本程式，再依指示更新。\n\n要下載嗎？")
        if hasattr(self, "lbl_update_status"):
            self.lbl_update_status.setText(f"發現新版本 {release.version}，等待下載確認。")
        self._notice(f"發現新版本 {release.version}。")
        if QMessageBox.question(self, "發現更新", msg,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            if hasattr(self, "lbl_update_status"):
                self.lbl_update_status.setText(f"已取消下載 {release.version}。")
            return
        self._start_update_download(asset)

    def _start_update_download(self, asset: update.Asset) -> None:
        self._update_asset = asset
        self._set_update_busy(True)
        if hasattr(self, "lbl_update_status"):
            self.lbl_update_status.setText(f"下載更新檔中… {asset.name}")
        self._notice(f"下載更新檔中… {asset.name}")
        task = UpdateDownloadTask(asset, self._update_token)
        task.signals.progress.connect(self._on_update_progress)
        task.signals.done.connect(self._on_update_downloaded)
        task.signals.failed.connect(self._on_update_error)
        self._update_download_task = task
        QThreadPool.globalInstance().start(task)

    def _on_update_progress(self, done: int, total: int) -> None:
        if not hasattr(self, "lbl_update_status"):
            return
        mb = done / 1024 / 1024
        text = f"{mb:.1f} / {total / 1024 / 1024:.1f} MB" if total else f"{mb:.1f} MB"
        self.lbl_update_status.setText(f"下載更新檔中… {text}")

    def _on_update_downloaded(self, result: update.DownloadResult) -> None:
        self._set_update_busy(False)
        verified = "SHA-256 驗證通過" if result.verified else "GitHub 未提供 digest，僅完成下載"
        asset = self._update_asset
        if asset is not None and asset.name.lower().endswith("-setup.exe"):
            how = "請關閉本程式，執行下載的 setup.exe。安裝程式會保留 config／logs／data。"
        else:
            how = ("請關閉本程式，將壓縮檔解壓縮覆蓋目前資料夾（保留 config／logs／data），"
                   "或解壓到新的資料夾。")
        if hasattr(self, "lbl_update_status"):
            self.lbl_update_status.setText(f"更新檔已下載：{result.path.name}（{verified}）")
        self._notice(f"更新檔已下載：{result.path}")
        QMessageBox.information(self, "更新檔已下載",
                                f"更新檔已下載：\n{result.path}\n\n{verified}。\n\n{how}\n\n"
                                "程式不會自動執行下載檔。")

    def _on_update_error(self, msg: str) -> None:
        self._set_update_busy(False)
        if hasattr(self, "lbl_update_status"):
            self.lbl_update_status.setText("更新檢查或下載失敗。")
        self._notice(msg)
        QMessageBox.warning(self, "更新失敗", msg)

    def open_update_folder(self) -> None:
        try:
            folder = update.updates_dir()
        except update.UpdateError as e:
            QMessageBox.warning(self, "更新資料夾", str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self._notice(f"已開啟更新資料夾：{folder}")

    def _paste_active(self) -> bool:
        return bool(getattr(getattr(self, "term", None), "pasting", False))

    def _do_login(self):
        if self._paste_active():
            self.password.clear()
            self._notice("貼上進行中，已暫停登入；請等貼上結束。")
            return
        try:
            ok = self.session.login(self.account.text(), self.password.text())
        finally:
            self.password.clear()                     # never keep the password around in the widget, even after an error
        if ok:
            self._notice("已送出登入資訊，等待伺服器回應…")

    def _on_conn_state(self, st: State):
        self.lbl_conn.setText(f"連線：{st.value}")
        c = st is State.CONNECTED
        self.btn_connect.setEnabled(st is State.DISCONNECTED)
        self.btn_disconnect.setEnabled(st is not State.DISCONNECTED)
        self.btn_login.setEnabled(c and not self._paste_active())
        if st is State.CONNECTED:
            self._auto_opened.clear()
            self._auto_open_times.clear()
        self._update_tray(c)
        self._update_type_buttons()
        if st is State.DISCONNECTED and self._pending_site_url:
            url, self._pending_site_url = self._pending_site_url, None
            self.session.connect_to(url)

    def _on_paste_state(self, on: bool) -> None:
        """Pasting owns the connection text stream: pause every other text/navigation action."""
        self._update_type_buttons()
        connected = self.session.client.state is State.CONNECTED
        self.btn_login.setEnabled(connected and not on)
        self._sync_board_fav_button()
        if on:
            self._notice("貼上進行中：已暫停輸入標題／內文、登入與前往看板。")

    def _update_input_lock(self) -> None:
        """The terminal keyboard is paused while automatic typing or the assisted login owns the connection."""
        self.term.locked = bool(self._article_typer().running or self._article_session().login_state is Login.LOGGING_IN)

    def _on_login_state(self, st: Login):
        self._update_input_lock()
        self.lbl_login.setText(f"登入：{st.value}")
        self._update_type_buttons()
        if st is Login.LOGGED_IN and hasattr(self, "term"):
            self._on_links_changed(self.term.links())

    def _notice(self, msg: str):
        self.statusBar().showMessage(msg, 20000)

    def _error(self, msg: str):
        """Critical error: status bar plus a dialog (removing msg_log must not hide failures)."""
        self._notice(msg)
        QMessageBox.warning(self, "錯誤", msg)

    # ------------------------------------------------------------------ theme
    def _load_theme_choice(self) -> str:
        raw = self.db.get_setting("ui.theme", "system")
        return raw if raw in theme.CHOICE_KEYS else "system"

    def _resolve_theme(self, choice: str) -> str:
        return theme.resolve_theme(choice, QGuiApplication.styleHints().colorScheme())

    def _load_terminal_palette_choice(self) -> str:
        raw = self.db.get_setting("ui.terminal_palette", "dark")
        return raw if raw in theme.TERMINAL_PALETTE_KEYS else "dark"

    def _terminal_theme_name(self) -> str:
        return "dark" if self._terminal_palette_choice == "dark" else self._theme_name

    def _apply_theme(self, choice: str, save: bool = True) -> None:
        choice = choice if choice in theme.CHOICE_KEYS else "system"
        self._theme_choice = choice
        self._theme_name = self._resolve_theme(choice)
        self._theme_data = theme.get_theme(self._theme_name)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, self._theme_name)
        if hasattr(self, "term"):
            self.term.set_theme(self._terminal_theme_name())
        combo = getattr(self, "theme_combo", None)
        if combo is not None:
            idx = combo.findData(choice)
            if idx >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
        for name in FIELDS:
            if hasattr(self, "state_lbl") and name in self.state_lbl:
                self._paint_state(name)
        if hasattr(self, "parse_status"):
            self._paint_parse_status()
        tcombo = getattr(self, "terminal_palette_combo", None)
        if tcombo is not None:
            idx = tcombo.findData(self._terminal_palette_choice)
            if idx >= 0:
                tcombo.blockSignals(True)
                tcombo.setCurrentIndex(idx)
                tcombo.blockSignals(False)
        if save:
            self.db.set_setting("ui.theme", choice)

    def _on_terminal_palette_combo(self, _index: int) -> None:
        choice = self.terminal_palette_combo.currentData()
        self._terminal_palette_choice = choice if choice in theme.TERMINAL_PALETTE_KEYS else "dark"
        self.term.set_theme(self._terminal_theme_name())
        self.db.set_setting("ui.terminal_palette", self._terminal_palette_choice)
        self._notice(f"終端機配色已設為「{theme.TERMINAL_PALETTE_LABELS[self._terminal_palette_choice]}」。")

    def _on_theme_combo(self, _index: int) -> None:
        self._apply_theme(self.theme_combo.currentData() or "system")
        self._notice(f"主題已切換為「{theme.CHOICE_LABELS.get(self._theme_choice, self._theme_choice)}」。")

    def _on_system_scheme_changed(self, _scheme) -> None:
        if self._theme_choice == "system":
            self._apply_theme("system", save=False)

    def _paint_parse_status(self) -> None:
        d = self._theme_data
        color = {"success": d.success, "partial": d.warning, "failed": d.error, "info": d.info}.get(
            getattr(self, "_parse_kind", None), d.muted)
        self.parse_status.setStyleSheet(f"color:{color}")

    # ================================================================== article tab
    def _build_article_tab(self) -> QWidget:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        self.article_tabs = QTabWidget()
        self.sig_snap_bar = QWidget()
        self.sig_snap_layout = QHBoxLayout(self.sig_snap_bar)
        self.sig_snap_layout.setContentsMargins(0, 0, 0, 0)
        self.sig_snap_bar.setVisible(False)
        outer.addWidget(self.sig_snap_bar)
        outer.addWidget(self.article_tabs)

        left = QWidget()
        ll = QVBoxLayout(left)
        row = QHBoxLayout()
        self.url_in = QLineEdit()
        self.url_in.setPlaceholderText("貼上新聞或文章網址（http／https）")
        self.btn_fetch = QPushButton("擷取")
        self.chk_robots = QCheckBox("忽略 robots.txt")
        self.chk_robots.setToolTip("預設遵守 robots.txt；勾選表示由您自行確認可存取該頁面。")
        row.addWidget(self.url_in, 1)
        row.addWidget(self.btn_fetch)
        row.addWidget(self.chk_robots)
        self.btn_clear = QPushButton("清除全部欄位")
        self.btn_clear.setToolTip("清除所有欄位、預覽與程式暫存狀態；不會刪除已儲存的草稿。")
        row.addWidget(self.btn_clear)
        ll.addLayout(row)
        self.parse_status = QLabel("尚未擷取")
        self.parse_status.setWordWrap(True)
        ll.addWidget(self.parse_status)
        self.parse_warn = QPlainTextEdit()
        self.parse_warn.setReadOnly(True)
        self.parse_warn.setFixedHeight(80)
        ll.addWidget(self.parse_warn)
        brow = QHBoxLayout()
        self.board_combo = QComboBox()
        self.board_combo.setEditable(True)
        self.board_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.board_combo.lineEdit().setPlaceholderText("看板英文名稱，例如 Gossiping")
        self.btn_board_fav = QPushButton("☆ 加入最愛")
        self.btn_board_go = QPushButton("前往看板")
        self.btn_board_go.setToolTip("在已登入且位於主功能表時，替您輸入「s」、看板名稱與 Enter 進入看板；不會發文。")
        brow.addWidget(QLabel("貼文看板"))
        brow.addWidget(self.board_combo, 1)
        brow.addWidget(self.btn_board_fav)
        brow.addWidget(self.btn_board_go)
        ll.addLayout(brow)
        self._reload_boards(self.db.get_setting("board.last", ""))
        form = QFormLayout()
        self.w: dict[str, QLineEdit] = {}
        self.state_lbl: dict[str, QLabel] = {}
        for f in FIELDS:
            e = QLineEdit()
            e.textEdited.connect(lambda _t, name=f: self._field_edited(name))
            lab = QLabel("未取得")
            h = QHBoxLayout()
            h.addWidget(e, 1)
            h.addWidget(lab)
            form.addRow(LABELS[f], h)
            self.w[f], self.state_lbl[f] = e, lab
        ll.addLayout(form)
        ll.addWidget(QLabel("原文內文（可修改；與下方個人心得分開）"))
        self.body = QPlainTextEdit()
        self.body.textChanged.connect(self._body_changed)
        ll.addWidget(self.body, 3)
        ll.addWidget(QLabel("個人心得"))
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(90)
        self.notes.textChanged.connect(self._schedule_preview)
        ll.addWidget(self.notes, 1)
        sg = QGroupBox(f"簽名檔（最多 {MAX_SIGNATURES} 則，保存在本機）")
        sl = QVBoxLayout(sg)
        row1 = QHBoxLayout()
        self.sig_combo = QComboBox()
        self.sig_name = QLineEdit()
        self.sig_name.setPlaceholderText("簽名檔名稱")
        self.btn_sig_new = QPushButton("新增")
        self.btn_sig_del = QPushButton("刪除")
        row1.addWidget(self.sig_combo, 1)
        row1.addWidget(self.sig_name, 1)
        row1.addWidget(self.btn_sig_new)
        row1.addWidget(self.btn_sig_del)
        sl.addLayout(row1)
        self.sig_edit = QPlainTextEdit()
        self.sig_edit.setFixedHeight(64)
        row2 = QHBoxLayout()
        self.btn_sig_save = QPushButton("儲存簽名檔")
        self.chk_sig = QCheckBox("此草稿套用簽名檔")
        row2.addWidget(self.btn_sig_save)
        row2.addWidget(self.chk_sig)
        self.lbl_sig_snap = QLabel("使用草稿儲存時的簽名檔（與目前選取的不同）")
        self.btn_sig_current = QPushButton("改用目前簽名檔")
        self.lbl_sig_snap.setVisible(False)
        self.btn_sig_current.setVisible(False)
        self.sig_snap_layout.addWidget(self.lbl_sig_snap)
        self.sig_snap_layout.addWidget(self.btn_sig_current)
        self.sig_snap_layout.addStretch(1)
        row2.addStretch(1)
        self._sig_idx = -1
        self._reload_signatures(self.db.active_signature_index)
        sl.addWidget(self.sig_edit)
        sl.addLayout(row2)
        ll.addWidget(sg)
        self.article_tabs.addTab(left, "擷取與欄位")

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("PTT 發文預覽（可直接編輯；手動修改後不會被欄位變更覆蓋）"))
        self.preview = QPlainTextEdit()
        self.preview.setFont(_mono())
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview.textChanged.connect(self._preview_changed)
        rl.addWidget(self.preview, 4)
        self.lbl_preview = QLabel("")
        rl.addWidget(self.lbl_preview)
        r1 = QHBoxLayout()
        self.btn_regen = QPushButton("重新產生預覽")
        self.btn_check = QPushButton("檢查")
        self.btn_copy_all = QPushButton("複製全文（標題＋內文）")
        self.btn_copy_body = QPushButton("複製內文")
        self.btn_copy_title = QPushButton("複製標題")
        for b in (self.btn_regen, self.btn_check, self.btn_copy_all, self.btn_copy_body, self.btn_copy_title):
            r1.addWidget(b)
        rl.addLayout(r1)
        self.issues = QPlainTextEdit()
        self.issues.setReadOnly(True)
        self.issues.setFixedHeight(110)
        rl.addWidget(self.issues)
        r2 = QHBoxLayout()
        self.btn_new = QPushButton("新增草稿")
        self.btn_save = QPushButton("儲存草稿")
        r2.addWidget(self.btn_new)
        r2.addWidget(self.btn_save)
        self.lbl_draft = QLabel("未儲存")
        r2.addWidget(self.lbl_draft, 1)
        rl.addLayout(r2)
        tg = QGroupBox("輸入到已登入的 PTT 終端機（只輸入文字；不會按 Enter／Ctrl-X／存檔／送出）")
        tl = QVBoxLayout(tg)
        self.chk_confirm = QCheckBox("我已確認這篇文章的內容（預覽、檢查）")
        self.chk_nonempty = QCheckBox("允許輸入到非空白的標題欄／編輯區（進階，可能插入到既有內容）")
        self.chk_retype = QCheckBox("此草稿曾輸入過；我已確認編輯區已清空，允許重新輸入")
        tl.addWidget(self.chk_confirm)
        tl.addWidget(self.chk_nonempty)
        tl.addWidget(self.chk_retype)
        r3 = QHBoxLayout()
        self.btn_type_title = QPushButton("輸入標題")
        self.btn_type_body = QPushButton("輸入內文")
        self.btn_type_cancel = QPushButton("取消輸入")
        for b in (self.btn_type_title, self.btn_type_body, self.btn_type_cancel):
            r3.addWidget(b)
        tl.addLayout(r3)
        self.type_status = QLabel(TYPE_HELP)
        self.type_status.setWordWrap(True)
        tl.addWidget(self.type_status)
        rl.addWidget(tg)
        self.article_tabs.addTab(right, "預覽與輸入")

        self.btn_fetch.clicked.connect(self.start_fetch)
        self.btn_clear.clicked.connect(self.clear_all_fields)
        self.url_in.returnPressed.connect(self.start_fetch)
        self.btn_regen.clicked.connect(self.regen_preview)
        self.btn_check.clicked.connect(self.run_checks)
        self.btn_copy_all.clicked.connect(lambda: self.copy("all"))
        self.btn_copy_body.clicked.connect(lambda: self.copy("body"))
        self.btn_copy_title.clicked.connect(lambda: self.copy("title"))
        self.btn_new.clicked.connect(self.new_draft)
        self.btn_save.clicked.connect(self.save_draft)
        self.btn_sig_save.clicked.connect(self.save_signature)
        self.btn_board_fav.clicked.connect(self.toggle_board_favorite)
        self.btn_board_go.clicked.connect(self.goto_board)
        self.board_combo.activated.connect(lambda _i: self._board_changed())
        self.board_combo.lineEdit().editingFinished.connect(self._board_changed)
        self.btn_sig_current.clicked.connect(self.use_current_signature)
        self.btn_sig_new.clicked.connect(self.new_signature)
        self.btn_sig_del.clicked.connect(self.delete_signature)
        self.sig_combo.activated.connect(self._pick_signature)
        self.chk_sig.toggled.connect(lambda _c: self._schedule_preview())
        self.sig_edit.textChanged.connect(lambda: self._schedule_preview(False))
        self.btn_type_title.clicked.connect(lambda: self.type_into_ptt(Target.TITLE))
        self.btn_type_body.clicked.connect(lambda: self.type_into_ptt(Target.BODY))
        self.btn_type_cancel.clicked.connect(lambda: self._article_typer().cancel())
        for c in (self.chk_confirm,):
            c.toggled.connect(lambda _x: self._update_type_buttons())
        return root

    # ---------------------------------------------------------------- fetching
    def start_fetch(self):
        if self._busy:
            return
        url = self.url_in.text().strip()
        if not url:
            self._notice("請先輸入網址。")
            return
        if not self._confirm_unsaved("擷取（會覆蓋目前欄位）"):
            return
        self._busy = True
        self.btn_fetch.setEnabled(False)
        self.parse_status.setText("擷取中…（背景執行，可繼續操作）")
        self._parse_kind = "info"
        self._paint_parse_status()
        task = FetchTask(url, self.chk_robots.isChecked())
        task.signals.done.connect(self._fetch_done)
        task.signals.failed.connect(self._fetch_failed)
        self._task = task
        QThreadPool.globalInstance().start(task)

    def _fetch_failed(self, msg: str, detail: str):
        self._busy = False
        self.btn_fetch.setEnabled(True)
        self.parse_status.setText(f"擷取失敗：{msg}")
        self._parse_kind = "failed"
        self._paint_parse_status()
        self.parse_warn.setPlainText("程式不會嘗試繞過登入、付費牆或存取限制。您可以改在瀏覽器取得內容後，手動貼到下方欄位。")
        log.info("fetch failed: %s | %s", msg, detail)

    def _fetch_done(self, fetched, res: ParseResult):
        self._busy = False
        self.btn_fetch.setEnabled(True)
        self._refresh_timer.stop()
        self.draft_id = None
        if not self._article_typer().running:
            self._typing_target = None
            self._typing_draft_id = None
        self._draft_sig = None
        self._sync_sig_snapshot_ui()
        self.chk_confirm.setChecked(False)
        self.chk_nonempty.setChecked(False)
        self.chk_retype.setChecked(False)
        self.type_status.setText(TYPE_HELP)
        self.lbl_draft.setText("未儲存（新擷取）")
        self._last_result = res
        self._loading = True
        try:
            for name in ("title", "site", "author", "published", "url"):
                f = getattr(res, name)
                self.w[name].setText(f.value or "")
                self.states[name] = f.status if f.value else "missing"
            self.body.setPlainText(res.body.value or "")
            self.notes.setPlainText("")
            self.states["body"] = res.body.status if res.body.value else "missing"
            t = res.title.value or ""
            self.w["post_title"].setText("" if not t else t if t.lstrip().startswith("[") else "[新聞] " + t)
            self.states["post_title"] = "edited" if res.title.value else "missing"
            self.url_in.setText(fetched.url)
        finally:
            self._loading = False
        for name in FIELDS:
            self._paint_state(name)
        text = STATUS_TEXT[res.status]
        extra = f"｜{BODY_TEXT[res.body_status]}" + ("" if res.page_class == "article" else f"｜頁面型態：{res.page_class}")
        self.parse_status.setText(f"{text}{extra}｜內文 {len(res.body.value or '')} 字｜編碼 {fetched.charset}")
        self._parse_kind = res.status
        self._paint_parse_status()
        self.parse_warn.setPlainText("\n".join(res.warnings) or "（沒有警告；仍請對照原網頁確認全文）")
        self.preview_manual_reset()
        self.render_preview(force=True)
        self._dirty = True                                 # fetched content is not saved yet
        self.db.event("fetch", self.draft_id, f"{res.status}/{res.body_status}")

    # ---------------------------------------------------------------- editing / state labels
    def _paint_state(self, name: str):
        st = self.states.get(name, "missing")
        lab = self.state_lbl[name]
        lab.setText(STATE_TEXT.get(st, st))
        d = self._theme_data
        color = {"found": d.success, "missing": d.error, "inferred": d.warning}.get(st, d.info)
        lab.setStyleSheet(f"color:{color}")
        if name in ("site", "author", "published", "url", "title") and st == "found" and self._last_result:
            src = getattr(self._last_result, name).source
            if src:
                lab.setText(f"已取得（{src}）")

    def _field_edited(self, name: str):
        if self._loading:
            return
        self.states[name] = "edited" if self.w[name].text().strip() else "missing"
        self._paint_state(name)
        self._schedule_preview()

    def _body_changed(self):
        if not self._loading:
            self.states["body"] = "edited" if self.body.toPlainText().strip() else "missing"
        self._schedule_preview()

    # ---------------------------------------------------------------- preview / checks / copy
    def fields(self) -> compose.Fields:
        return compose.Fields(post_title=self.w["post_title"].text(), site=self.w["site"].text(), author=self.w["author"].text(),
                              published=self.w["published"].text(), url=self.w["url"].text(), news_title=self.w["title"].text(),
                              body=self.body.toPlainText(), notes=self.notes.toPlainText(), signature=self._sig_text(),
                              use_signature=self.chk_sig.isChecked())

    def _schedule_preview(self, dirty: bool = True):
        if not self._loading:
            if dirty:
                self._dirty = True
            self._refresh_timer.start()

    def _auto_preview(self):
        if self._preview_manual:
            self.lbl_preview.setText("預覽已手動修改：欄位變更不會自動覆蓋。按「重新產生預覽」會捨棄手動修改。")
        else:
            self.render_preview()

    def render_preview(self, force: bool = False):
        if self._preview_manual and not force:
            return
        _t, body = compose.render(self.fields())
        self._setting_preview = True
        self.preview.setPlainText(body)
        self._setting_preview = False
        self._preview_manual = False
        self.lbl_preview.setText("")

    def _sig_text(self) -> str:
        """Signature text for preview / checks / saving: the opened draft's snapshot, else the selected signature."""
        return self._draft_sig if self._draft_sig is not None else self.sig_edit.toPlainText()

    def _sync_sig_snapshot_ui(self) -> None:
        on = self._draft_sig is not None
        self.sig_snap_bar.setVisible(on)
        self.lbl_sig_snap.setVisible(on)
        self.btn_sig_current.setVisible(on)

    def use_current_signature(self) -> None:
        self._draft_sig = None
        self._sync_sig_snapshot_ui()
        self._dirty = True
        self._schedule_preview(False)

    def regen_preview(self):
        if self._preview_manual and QMessageBox.question(
                self, "重新產生預覽", "預覽已被手動修改，重新產生會捨棄這些修改。確定？") != QMessageBox.StandardButton.Yes:
            return
        self.render_preview(force=True)

    def _confirm_unsaved(self, what: str) -> bool:
        """True when it is fine to continue: nothing unsaved, or the user chose to save / discard."""
        if not self._dirty:
            return True
        r = QMessageBox.question(self, "尚未儲存", f"目前草稿有未儲存的修改。{what}前要先儲存嗎？",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                 QMessageBox.StandardButton.Save)
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Save:
            return self.save_draft() is not None
        return True

    def preview_manual_reset(self):
        self._preview_manual = False

    def _preview_changed(self):
        if not self._setting_preview:
            self._preview_manual = True
            self._dirty = True
            self.lbl_preview.setText("預覽已手動修改：欄位變更不會自動覆蓋。按「重新產生預覽」會捨棄手動修改。")

    def current_texts(self) -> tuple[str, str]:
        """(title, body) exactly as they will be copied / typed."""
        if not self._preview_manual:                      # never read a stale preview (debounce timer still pending)
            self._refresh_timer.stop()
            self.render_preview()
        title = compose.normalize(self.w["post_title"].text())[0].replace("\n", " ").strip()
        return title, self.preview.toPlainText().rstrip("\n")

    def run_checks(self) -> list[compose.Issue]:
        title, body = self.current_texts()
        used = self.chk_sig.isChecked() and bool(self._sig_text().strip())
        issues = compose.check(title, body, self._sig_text(), used)
        if self._last_result is not None and self._last_result.body_status != "likely_complete":
            issues.append(compose.Issue("warn", "擷取內文" + BODY_TEXT[self._last_result.body_status] + "，請對照原網頁確認。"))
        lines = [str(i) for i in issues] or ["通過基本檢查（標題、內文、編碼、控制字元、行寬）。"]
        lines.append(f"標題 {compose.byte_len(title)} bytes｜內文 {len(body.splitlines())} 行 / {compose.byte_len(body)} bytes")
        self.issues.setPlainText("\n".join(lines))
        return issues

    def copy(self, what: str):
        title, body = self.current_texts()
        issues = self.run_checks()
        if compose.has_errors(issues):
            self._notice("有「錯誤」等級的檢查項目，已拒絕複製（請先修正）。")
            return
        text = {"all": f"{title}\n\n{body}", "body": body, "title": title}[what]
        cb = QApplication.clipboard()
        cb.setText(text)
        ok = cb.text().replace("\r\n", "\n") == text
        self._notice(("已複製" if ok else "複製可能失敗（剪貼簿內容與預期不符）") + f"（{len(text)} 字元）。請自行貼到 PTT，並自行確認／送出。")
        self.db.event("copy", self.draft_id, what)

    # ---------------------------------------------------------------- boards
    def current_board(self) -> str:
        return boards.board_id(self.board_combo.currentText())

    def _reload_boards(self, select: str) -> None:
        """Favorites (★) first, then the preset boards; keeps any typed board name selected."""
        favs = self.db.favorite_boards()
        low = {f.lower() for f in favs}
        self.board_combo.blockSignals(True)
        self.board_combo.clear()
        for b in favs:
            self.board_combo.addItem("★ " + boards.label(b))
        for b, _zh in boards.PRESET_BOARDS:
            if b.lower() not in low:
                self.board_combo.addItem(boards.label(b))
        idx = next((i for i in range(self.board_combo.count()) if boards.board_id(self.board_combo.itemText(i)).lower() == select.lower()), -1) if select else -1
        if idx >= 0:
            self.board_combo.setCurrentIndex(idx)
        else:
            self.board_combo.setCurrentIndex(-1)
            self.board_combo.setEditText(select)
        self.board_combo.blockSignals(False)
        self._sync_board_fav_button()

    def _sync_board_fav_button(self) -> None:
        b = self.current_board()
        fav = bool(b) and b.lower() in {f.lower() for f in self.db.favorite_boards()}
        self.btn_board_fav.setText("★ 移出最愛" if fav else "☆ 加入最愛")
        self.btn_board_fav.setEnabled(bool(b))
        self.btn_board_go.setEnabled(bool(b) and not self._paste_active())

    def _board_changed(self) -> None:
        b = self.current_board()
        if b:
            self.db.set_setting("board.last", b)
        self._sync_board_fav_button()

    def toggle_board_favorite(self) -> None:
        b = self.current_board()
        if not b:
            self._notice("請先選擇或輸入有效的看板名稱（英數字、底線、連字號，最多 12 字）。")
            return
        on = b.lower() not in {f.lower() for f in self.db.favorite_boards()}
        self.db.set_board_favorite(b, on)
        self._reload_boards(b)
        self._notice(f"看板 {b} 已{'加入' if on else '移出'}我的最愛。")

    def goto_board(self) -> None:
        """User-initiated navigation only: 's' + board id + Enter from the main menu. Never posts anything."""
        if self._paste_active():
            self._notice("貼上進行中，已暫停前往看板；請等貼上結束。")
            return
        b = self.current_board()
        if not b:
            self._notice("請先選擇或輸入有效的看板名稱。")
            return
        session = self._article_session()
        if not session.logged_in or session.kind is not Kind.MAIN_MENU:
            self._notice("需要已登入且畫面停在「主功能表」才能前往看板；請先在終端機回到主功能表。")
            return
        if QMessageBox.question(self, "前往看板", f"將在終端機輸入「s」、「{b}」與 Enter 進入看板。不會發文。確定？") != QMessageBox.StandardButton.Yes:
            return
        session.send_user_bytes(b"s" + b.encode("ascii") + b"\r")      # one frame: no ordering race
        self.db.event("goto_board", self.draft_id, b)
        self._notice(f"已送出前往看板 {b}；請在終端機確認畫面（可能需要按任意鍵），發文仍由您自行操作。")

    # ---------------------------------------------------------------- signature
    def save_signature(self):
        text = compose.normalize(self.sig_edit.toPlainText())[0]
        if any(l.strip() == "--" for l in text.split("\n")):
            self._notice("簽名檔不可含單獨一行的「--」。")
            return
        try:
            idx = self.db.save_signature_entry(self._sig_idx, self.sig_name.text(), text)
        except ValueError as e:
            self._notice(f"{e}，請先刪除不用的簽名檔。")
            return
        self._reload_signatures(idx)
        self._notice("簽名檔已儲存。")
        self._schedule_preview(False)

    def _reload_signatures(self, select: int) -> None:
        """Refill the drop-down from the DB and show entry `select` (-1 = empty new entry)."""
        items = self.db.signatures()
        self.sig_combo.blockSignals(True)
        self.sig_combo.clear()
        for i, it in enumerate(items):
            self.sig_combo.addItem(f"{i + 1}. {it['name']}")
        self.sig_combo.setCurrentIndex(select if 0 <= select < len(items) else -1)
        self.sig_combo.blockSignals(False)
        self._show_signature(select if 0 <= select < len(items) else -1)

    def _show_signature(self, idx: int) -> None:
        items = self.db.signatures()
        self._sig_idx = idx if 0 <= idx < len(items) else -1
        if self._sig_idx >= 0:
            self.sig_name.setText(items[idx]["name"])
            self.sig_edit.setPlainText(items[idx]["text"])
        else:
            self.sig_name.setText(f"簽名檔{len(items) + 1}")
            self.sig_edit.setPlainText("")

    def _pick_signature(self, idx: int) -> None:
        had_snapshot = self._draft_sig is not None
        self._draft_sig = None
        self._sync_sig_snapshot_ui()
        self.db.set_active_signature(idx)
        self._show_signature(idx)
        if had_snapshot:
            self._dirty = True
        self._schedule_preview(False)

    def new_signature(self):
        if len(self.db.signatures()) >= MAX_SIGNATURES:
            self._notice(f"簽名檔最多 {MAX_SIGNATURES} 則，請先刪除不用的簽名檔。")
            return
        self.sig_combo.blockSignals(True)
        self.sig_combo.setCurrentIndex(-1)
        self.sig_combo.blockSignals(False)
        self._show_signature(-1)

    def delete_signature(self, confirm: bool = True):
        if self._sig_idx < 0:
            self._notice("目前是尚未儲存的新簽名檔，沒有可刪除的項目。")
            return
        name = self.db.signatures()[self._sig_idx]["name"]
        if confirm and QMessageBox.question(self, "刪除簽名檔", f"確定刪除簽名檔「{name}」？此動作無法復原。") != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_signature_entry(self._sig_idx)
        self._reload_signatures(self.db.active_signature_index)
        self._notice("簽名檔已刪除。")
        self._schedule_preview(False)

    # ================================================================== drafts
    def _build_sites_tab(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        left = QVBoxLayout()
        left.addWidget(QLabel("站台書籤（預設清單為 2026-10-23 唯讀連線實測結果）"))
        self.site_list = QListWidget()
        self.site_list.currentRowChanged.connect(self._site_selected)
        self.site_list.itemDoubleClicked.connect(lambda _i: self.connect_site())
        left.addWidget(self.site_list, 1)
        self.lbl_site_status = QLabel("")
        self.lbl_site_status.setWordWrap(True)
        left.addWidget(self.lbl_site_status)
        hint = QLabel("WSS 與 Telnet 可使用內建終端機連線；SSH 目前只保存書籤，連線功能待後續版本。"
                      "Telnet 是明文傳輸，請避免在公用網路輸入重要密碼。測試連線只建立 TCP 連線，不送出帳密或任何 BBS 指令。")
        hint.setWordWrap(True)
        left.addWidget(hint)
        outer.addLayout(left, 1)

        box = QGroupBox("站台資料")
        form = QFormLayout(box)
        self.site_name = QLineEdit()
        self.site_protocol = QComboBox()
        for key in sites.PROTOCOLS:
            self.site_protocol.addItem(sites.PROTOCOL_LABELS[key], key)
        self.site_host = QLineEdit()
        self.site_host.setPlaceholderText("例如 ws.ptt.cc 或 bbs.example.edu.tw")
        self.site_port = QSpinBox()
        self.site_port.setRange(1, 65535)
        self.site_port.setValue(443)
        self.site_path = QLineEdit()
        self.site_path.setPlaceholderText("WSS 路徑，例如 /bbs")
        self.site_note = QLineEdit()
        self.site_note.setPlaceholderText("備註（選填）")
        form.addRow("名稱", self.site_name)
        form.addRow("協定", self.site_protocol)
        form.addRow("主機", self.site_host)
        form.addRow("連接埠", self.site_port)
        form.addRow("路徑", self.site_path)
        form.addRow("備註", self.site_note)
        browse = QHBoxLayout()
        self.btn_site_connect = QPushButton("連線此站台")
        self.btn_site_test = QPushButton("測試連線")
        self.btn_site_copy = QPushButton("複製位址")
        for b in (self.btn_site_connect, self.btn_site_test, self.btn_site_copy):
            browse.addWidget(b)
        form.addRow(browse)
        manage = QHBoxLayout()
        self.btn_site_add = QPushButton("新增書籤")
        self.btn_site_save = QPushButton("儲存變更")
        self.btn_site_delete = QPushButton("刪除")
        for b in (self.btn_site_add, self.btn_site_save, self.btn_site_delete):
            manage.addWidget(b)
        form.addRow(manage)
        self.lbl_site_test = QLabel("")
        self.lbl_site_test.setWordWrap(True)
        form.addRow(self.lbl_site_test)
        outer.addWidget(box, 1)

        self.btn_site_connect.clicked.connect(self.connect_site)
        self.btn_site_test.clicked.connect(self.test_site)
        self.btn_site_copy.clicked.connect(self.copy_site)
        self.btn_site_add.clicked.connect(self.add_site_bookmark)
        self.btn_site_save.clicked.connect(self.save_site_bookmark)
        self.btn_site_delete.clicked.connect(self.delete_site_bookmark)
        self._reload_sites()
        return w

    def _reload_sites(self, select: int = 0) -> None:
        items = self.db.site_bookmarks()
        self.site_list.blockSignals(True)
        self.site_list.clear()
        for site in items:
            label = sites.PROTOCOL_LABELS.get(site["protocol"], site["protocol"])
            it = QListWidgetItem(f"{site['name']}  [{label}]\n{sites.site_address(site)}")
            it.setData(Qt.ItemDataRole.UserRole, dict(site))
            it.setToolTip(site.get("note", ""))
            self.site_list.addItem(it)
        self.site_list.blockSignals(False)
        self.lbl_site_status.setText(f"共 {len(items)} 個站台書籤。")
        if items:
            self.site_list.setCurrentRow(max(0, min(select, len(items) - 1)))
        else:
            self._clear_site_form()

    def _clear_site_form(self) -> None:
        self.site_name.clear()
        self.site_protocol.setCurrentIndex(0)
        self.site_host.clear()
        self.site_port.setValue(443)
        self.site_path.setText("/bbs")
        self.site_note.clear()

    def _site_selected(self, row: int) -> None:
        if row < 0:
            return
        site = self.site_list.item(row).data(Qt.ItemDataRole.UserRole)
        if not isinstance(site, dict):
            return
        self.site_name.setText(site.get("name", ""))
        idx = self.site_protocol.findData(site.get("protocol"))
        self.site_protocol.setCurrentIndex(max(0, idx))
        self.site_host.setText(site.get("host", ""))
        self.site_port.setValue(int(site.get("port") or 443))
        self.site_path.setText(site.get("path", ""))
        self.site_note.setText(site.get("note", ""))

    def _site_from_form(self) -> dict:
        return sites.normalize_site({
            "name": self.site_name.text(), "protocol": self.site_protocol.currentData(),
            "host": self.site_host.text(), "port": self.site_port.value(),
            "path": self.site_path.text(), "note": self.site_note.text(),
        })

    def _site_error(self, msg: str) -> None:
        self.lbl_site_test.setText(f"錯誤：{msg}")
        self._notice(msg)

    def add_site_bookmark(self) -> None:
        site = self._site_from_form()
        err = sites.validate_site(site["name"], site["protocol"], site["host"], site["port"], site["path"], site["note"])
        if err:
            self._site_error(err)
            return
        items = self.db.site_bookmarks()
        if any(s["protocol"] == site["protocol"] and s["host"].lower() == site["host"].lower()
               and int(s["port"]) == site["port"] for s in items):
            self._site_error("已有相同協定、主機與連接埠的書籤。")
            return
        items.append(site)
        self.db.save_site_bookmarks(items)
        self._reload_sites(len(items) - 1)
        self._notice(f"已新增站台書籤：{site['name']}。")

    def save_site_bookmark(self) -> None:
        row = self.site_list.currentRow()
        if row < 0:
            self._site_error("請先選擇要儲存的書籤。")
            return
        site = self._site_from_form()
        err = sites.validate_site(site["name"], site["protocol"], site["host"], site["port"], site["path"], site["note"])
        if err:
            self._site_error(err)
            return
        items = self.db.site_bookmarks()
        items[row] = site
        self.db.save_site_bookmarks(items)
        self._reload_sites(row)
        self._notice(f"已儲存站台書籤：{site['name']}。")

    def delete_site_bookmark(self) -> None:
        row = self.site_list.currentRow()
        if row < 0:
            self._site_error("請先選擇要刪除的書籤。")
            return
        site = self.db.site_bookmarks()[row]
        if QMessageBox.question(self, "刪除站台書籤", f"確定刪除「{site['name']}」？") != QMessageBox.StandardButton.Yes:
            return
        items = self.db.site_bookmarks()
        del items[row]
        self.db.save_site_bookmarks(items)
        self._reload_sites(max(0, row - 1))
        self._notice(f"已刪除站台書籤：{site['name']}。")

    def copy_site(self) -> None:
        site = self._site_from_form()
        address = sites.site_address(site)
        QGuiApplication.clipboard().setText(address)
        self.lbl_site_test.setText(f"已複製：{address}")
        self._notice(f"已複製站台位址：{address}")

    def test_site(self) -> None:
        site = self._site_from_form()
        err = sites.validate_site(site["name"], site["protocol"], site["host"], site["port"], site["path"], site["note"])
        if err:
            self._site_error(err)
            return
        self.lbl_site_test.setText("測試連線中…")
        task = SiteCheckTask(site)
        task.signals.done.connect(self._on_site_checked)
        self._site_check_task = task
        QThreadPool.globalInstance().start(task)

    def _on_site_checked(self, ok: bool, msg: str) -> None:
        self.lbl_site_test.setText(msg)
        self._notice(msg)

    def connect_site(self) -> None:
        site = self._site_from_form()
        err = sites.validate_site(site["name"], site["protocol"], site["host"], site["port"], site["path"], site["note"])
        if err:
            self._site_error(err)
            return
        if site["protocol"] not in ("wss", "telnet"):
            self._notice("此版本尚未支援 SSH 連線；站台書籤仍保留，可手動使用其他 SSH 客戶端。")
            self.lbl_site_test.setText("SSH 連線尚未支援；書籤資料保留。")
            return
        url = sites.site_address(site)
        self.url_box.setEditText(url)
        if self.session.client.state is not State.DISCONNECTED:
            self._pending_site_url = url
            self.session.disconnect_()
        else:
            self.session.connect_to(url)
        self.tabs.setCurrentIndex(0)
        if site["protocol"] == "telnet":
            self._notice(f"正在以 Telnet（明文）連線 {site['name']}：{url}；請勿在公用網路輸入重要密碼。")
        else:
            self._notice(f"正在連線 {site['name']}：{url}")

    def _build_drafts_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋標題、內文、心得、來源…")
        row.addWidget(self.search, 1)
        self.btn_open = QPushButton("開啟")
        self.btn_delete = QPushButton("刪除")
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_delete)
        lay.addLayout(row)
        self.draft_list = QListWidget()
        lay.addWidget(self.draft_list, 1)
        self.search.textChanged.connect(lambda _t: self.reload_drafts())
        self.btn_open.clicked.connect(self.open_selected)
        self.draft_list.itemDoubleClicked.connect(lambda _i: self.open_selected())
        self.btn_delete.clicked.connect(self.delete_selected)
        return w

    def reload_drafts(self):
        self.draft_list.clear()
        for d in self.db.list_drafts(self.search.text()):
            ts = d["updated_at"].replace("T", " ").rstrip("Z")
            it = QListWidgetItem(f"#{d['id']}  {d['post_title'] or d['title'] or '(無標題)'}    [{d['input_state']}]  {ts} UTC")
            it.setData(Qt.ItemDataRole.UserRole, d["id"])
            self.draft_list.addItem(it)

    def new_draft(self):
        if self._article_typer().running:
            self._notice("輸入進行中，請先取消輸入再切換草稿。")
            return
        if not self._confirm_unsaved("新增草稿"):
            return
        self._reset_article_fields()

    def clear_all_fields(self):
        if self._article_typer().running:
            self._notice("輸入進行中，請先取消輸入再清除欄位。")
            return
        if self._busy:
            self._notice("擷取進行中，請等擷取結束再清除欄位。")
            return
        if QMessageBox.question(self, "清除全部欄位",
                                "確定要清除所有欄位、預覽與程式暫存狀態嗎？\n已儲存的草稿不會被刪除。",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._reset_article_fields()
        self._notice("已清除所有欄位與預覽暫存；已儲存的草稿未刪除。")

    def _reset_article_fields(self):
        self._refresh_timer.stop()
        self.draft_id = None
        self._typing_target = None
        self._typing_draft_id = None
        self.chk_nonempty.setChecked(False)
        self._loading = True
        try:
            for f in FIELDS:
                self.w[f].setText("")
                self.states[f] = "missing"
            self.body.setPlainText("")
            self.notes.setPlainText("")
            self.url_in.setText("")
            self.chk_sig.setChecked(bool(self.db.signature.strip()))
        finally:
            self._loading = False
        self._draft_sig = None
        self._sync_sig_snapshot_ui()
        self._last_result = None
        self._preview_manual = False
        for f in FIELDS:
            self._paint_state(f)
        self.parse_status.setText("尚未擷取")
        self._parse_kind = None
        self._paint_parse_status()
        self.parse_warn.setPlainText("")
        self.chk_confirm.setChecked(False)
        self.chk_retype.setChecked(False)
        self.type_status.setText(TYPE_HELP)
        self.lbl_draft.setText("未儲存")
        self.render_preview(force=True)
        self._dirty = False
        self._update_type_buttons()

    def save_draft(self) -> int | None:
        title, _body = self.current_texts()
        data = {f: self.w[f].text() for f in FIELDS}
        data.update(board=self.current_board(), body=self.body.toPlainText(), notes=self.notes.toPlainText(), use_signature=self.chk_sig.isChecked(),
                    signature_text=self._sig_text() if self.chk_sig.isChecked() else "",
                    preview_override=self.preview.toPlainText() if self._preview_manual else None,
                    parse_status=self._last_result.status if self._last_result else "",
                    body_status=self._last_result.body_status if self._last_result else "",
                    field_states=",".join(f"{k}={v}" for k, v in self.states.items()))
        try:
            self.draft_id = self.db.save_draft(data, self.draft_id)
        except ToolError as e:
            self._error(f"儲存失敗：{e.message}")
            return None
        self._dirty = False
        self.lbl_draft.setText(f"草稿 #{self.draft_id} 已儲存")
        self.reload_drafts()
        self._notice(f"草稿 #{self.draft_id} 已儲存。")
        return self.draft_id

    def open_selected(self):
        it = self.draft_list.currentItem()
        if it is None:
            return
        if self._article_typer().running:
            self._notice("輸入進行中，請先取消輸入再切換草稿。")
            return
        if not self._confirm_unsaved("開啟其他草稿"):
            return
        self.chk_nonempty.setChecked(False)
        d = self.db.get_draft(it.data(Qt.ItemDataRole.UserRole))
        if d is None:
            self._notice("找不到該草稿。")
            return
        self.draft_id = d["id"]
        self._loading = True
        for f in FIELDS:
            self.w[f].setText(d[f])
        self.body.setPlainText(d["body"])
        self.notes.setPlainText(d["notes"])
        self.url_in.setText(d["url"])
        self.chk_sig.setChecked(bool(d["use_signature"]))
        snap = d.get("signature_text", "")
        cur = compose.normalize(self.sig_edit.toPlainText())[0]
        self._draft_sig = snap if (d["use_signature"] and snap.strip() and snap != cur) else None
        self._sync_sig_snapshot_ui()
        if d["board"]:
            self._reload_boards(d["board"])
        states = dict(kv.split("=", 1) for kv in d["field_states"].split(",") if "=" in kv)
        for f in FIELDS:
            self.states[f] = states.get(f, "edited" if d[f] else "missing")
        self._loading = False
        self._last_result = None
        for f in FIELDS:
            self._paint_state(f)
        self.parse_status.setText(f"已載入草稿（原擷取狀態：{d['parse_status'] or '無'}／{d['body_status'] or '無'}）")
        self._parse_kind = None
        self._paint_parse_status()
        self._preview_manual = False
        if d["preview_override"]:
            self._setting_preview = True
            self.preview.setPlainText(d["preview_override"])
            self._setting_preview = False
            self._preview_manual = True
            self.lbl_preview.setText("此草稿的預覽曾被手動修改，已還原。")
        else:
            self.render_preview(force=True)
        self.chk_confirm.setChecked(False)
        self.chk_retype.setChecked(False)
        self.lbl_draft.setText(f"草稿 #{self.draft_id}（輸入狀態：{d['input_state']}）")
        self.tabs.setCurrentIndex(0)
        self._set_article_panel_visible(True)
        self.article_tabs.setCurrentIndex(1)
        self._update_type_buttons()

    def delete_selected(self):
        it = self.draft_list.currentItem()
        if it is None:
            return
        did = it.data(Qt.ItemDataRole.UserRole)
        if self._article_typer().running:
            self._notice("輸入進行中，無法刪除草稿。")
            return
        if QMessageBox.question(self, "刪除草稿", f"確定刪除草稿 #{did}？此動作無法復原。") != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_draft(did)
        if self.draft_id == did:
            self.new_draft()
        self.reload_drafts()

    # ================================================================== typing into PTT
    def _update_type_buttons(self):
        session, typer = self._article_session(), self._article_typer()
        connected = session.client.state is State.CONNECTED
        ok = (connected and session.logged_in and self.chk_confirm.isChecked()
              and not typer.running and not self._paste_active())
        self.btn_type_title.setEnabled(ok)
        self.btn_type_body.setEnabled(ok)
        self.btn_type_cancel.setEnabled(typer.running)

    def type_into_ptt(self, target: Target):
        typer = self._article_typer()
        if typer.running:
            return
        if self._paste_active():
            self._notice("貼上進行中，已暫停輸入標題／內文；請等貼上結束。")
            self.type_status.setText("貼上進行中，已暫停輸入；請等貼上結束後再試。")
            return
        title, body = self.current_texts()
        issues = self.run_checks()
        if compose.has_errors(issues):
            self._notice("有「錯誤」等級的檢查項目，已拒絕輸入（請先修正）。")
            return
        did = self.save_draft()                           # one save; also persists the exact text that will be typed
        if did is None:
            return
        d = self.db.get_draft(did)
        if d is None:
            self._notice("找不到目前的草稿（可能已被刪除），已取消輸入。")
            return
        if target is Target.BODY and d["input_state"] != "none" and not self.chk_retype.isChecked():
            self._notice(f"此草稿的輸入狀態為「{d['input_state']}」：為避免重複輸入整篇文章，已拒絕。請先在終端機確認／清空編輯區，再勾選允許重新輸入。")
            return
        text = title if target is Target.TITLE else body
        if (target is Target.BODY and d["body_status"] in ("suspect_partial", "insufficient") and did not in self._ack_incomplete):
            if QMessageBox.question(self, "內文可能不完整",
                                    "這篇文章擷取到的內文疑似不完整（截斷、登入牆／付費牆或內容過少）。\n\n請確認您已對照原網頁、確定要輸入的內容是完整的。仍要繼續嗎？") != QMessageBox.StandardButton.Yes:
                self._notice("已取消輸入：內文疑似不完整。")
                return
            self._ack_incomplete.add(did)
        why = preflight(self._article_session(), target, text, self.chk_nonempty.isChecked(), self._paste_active())
        if why:
            self._notice("無法輸入：" + why)
            self.type_status.setText("無法輸入：" + why)
            return
        what = "標題" if target is Target.TITLE else f"內文（{len(text.splitlines())} 行）"
        if QMessageBox.question(self, "輸入到 PTT 終端機",
                                f"將把{what}輸入到目前已登入的終端機。\n\n程式不會按 Enter、Ctrl-X、存檔或送出；輸入完成後請在終端機自行檢查並決定是否發文。\n\n確定開始？") != QMessageBox.StandardButton.Yes:
            self._notice("已取消輸入。")
            return
        self._typing_target = target
        self._typing_draft_id = did
        if target is Target.BODY:                         # write-ahead gate: no byte is sent unless "started" is durably recorded
            try:
                self.db.set_input_state(did, "started")
            except ToolError as e:
                self._typing_draft_id = None
                self._error(f"無法記錄輸入狀態，已取消輸入（未送出任何內容）：{e.message}")
                return
        reason = typer.start(target, text, self.chk_nonempty.isChecked())
        if reason:
            self._typing_draft_id = None
            if target is Target.BODY:
                try:
                    self.db.set_input_state(did, d["input_state"])      # refused: put the previous state back
                except ToolError:
                    pass
            self._notice("無法輸入：" + reason)
            return
        self._update_type_buttons()

    def _typing_started(self, target: Target):
        self._update_input_lock()
        self.type_status.setText("輸入中…（可按「取消輸入」；取消不會清除已輸入的內容）")
        self._update_type_buttons()

    def _typing_finished(self, ok: bool, msg: str):
        self._update_input_lock()
        if self._typing_target is Target.BODY and self._typing_draft_id:
            try:
                self.db.set_input_state(self._typing_draft_id, "done" if ok else "aborted")
            except ToolError as e:
                self._error(f"輸入狀態無法寫入資料庫（{e.message}）。請在終端機人工核對內容，避免重複輸入。")
            self.reload_drafts()
        self._typing_draft_id = None
        self.chk_nonempty.setChecked(False)               # the "non-empty" allowance never outlives one typing run
        self.type_status.setText(msg)
        self._on_links_changed(self.term.links())
        self._notice(msg)                                 # keep the typing result in front of an auto-open notice
        self.chk_retype.setChecked(False)
        self._update_type_buttons()

    # ================================================================== laptop / desktop adaptation
    @staticmethod
    def _has_battery() -> bool:
        """True on laptops / tablets (a battery is present); desktops report none."""
        try:
            import ctypes

            class SPS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                            ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            st = SPS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
                return st.BatteryFlag not in (128, 255)
        except Exception:                                  # not Windows / API missing: assume desktop
            pass
        return False

    def _keybar_default(self) -> bool:
        v = self.db.get_setting("ui.keybar", "")
        return v == "1" if v else self._has_battery()      # laptops often lack PgUp/PgDn/Home/End

    def _keybar_toggled(self, on: bool) -> None:
        self.db.set_setting("ui.keybar", "1" if on else "0")
        self.keybar.setVisible(on)

    def _send_key(self, data: bytes) -> None:
        if self.term.locked or self.term.pasting:
            self._notice("自動輸入／登入／貼上進行中，按鍵已暫停。")
            return
        if not self.session.send_user_bytes(data):
            self._notice("尚未連線，按鍵未送出。")
        else:
            self.term.clear_selection()

    # ================================================================== external PTT login helper
    @staticmethod
    def _find_pttlogin() -> str:
        """PttAutoLogin.exe next to this program or in a sibling/parent folder; '' when not found (never a fixed path)."""
        from ..paths import runtime_base_dir
        base = Path(runtime_base_dir())
        for d in (base, base.parent, base.parent.parent):
            for rel in ("PttAutoLogin.exe", "PTTLOGIN/release/PttAutoLogin.exe", "PttAutoLogin/PttAutoLogin.exe"):
                if (d / rel).is_file():
                    return str(d / rel)
        return ""

    def _browse_pttlogin(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "選擇 PttAutoLogin.exe", str(Path(self.pttlogin_path.text()).parent), "程式 (*.exe)")
        if f:
            self.pttlogin_path.setText(f)
            self.db.set_setting("pttlogin.path", f)

    def launch_pttlogin(self) -> bool:
        """Start the separate PTT login helper (its own process, working dir = its folder so its Data/Logs stay there)."""
        path = Path(self.pttlogin_path.text().strip() or self._find_pttlogin() or "PttAutoLogin.exe")
        if path.suffix.lower() != ".exe" or not path.is_file():
            self._notice(f"找不到登入小幫手：{path}。請在「設定」分頁指定 PttAutoLogin.exe 的位置。")
            return False
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True, creationflags=flags if os.name == "nt" else 0)
        except OSError as e:
            self._notice(f"無法啟動登入小幫手：{e}")
            return False
        self.db.set_setting("pttlogin.path", str(path))
        self._notice("已啟動 PTT 登入小幫手（獨立程式）。")
        return True

    # ================================================================== window geometry / tray
    def _init_geometry(self) -> None:
        """Adapt to the device: restore the last window geometry when it still fits a connected screen, otherwise
        size the window to the current screen (never larger than 92% of it) and centre it."""
        raw = self.db.get_setting("window.geometry", "")
        if raw and self.restoreGeometry(QByteArray.fromBase64(raw.encode("ascii"))):
            return
        scr = QGuiApplication.primaryScreen()
        area = scr.availableGeometry() if scr else None
        w, h = 1280, 860
        if area is not None:
            w, h = min(w, int(area.width() * 0.92)), min(h, int(area.height() * 0.92))
        self.resize(max(w, self.minimumWidth()), max(h, self.minimumHeight()))
        if area is not None:
            self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)

    def _save_geometry(self) -> None:
        self.db.set_setting("window.geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        self._save_article_panel_state()

    def showEvent(self, e):
        super().showEvent(e)
        if hasattr(self, "main_splitter"):
            QTimer.singleShot(0, self._apply_article_panel_sizes)
        wh = self.windowHandle()
        if wh is not None and not getattr(self, "_screen_hooked", False):
            self._screen_hooked = True
            wh.screenChanged.connect(lambda _s: QTimer.singleShot(0, self.term._relayout))   # other monitor / DPI

    def _build_tray(self) -> None:
        self._tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
        if not self._tray_ok:
            return
        t = QSystemTrayIcon(tray_icon(False), self)
        menu = QMenu(self)
        act_show = QAction("顯示主視窗", menu)
        act_show.triggered.connect(self.restore_from_tray)
        act_login = QAction("開啟 PTT 登入小幫手", menu)
        act_login.triggered.connect(self.launch_pttlogin)
        act_quit = QAction("離開", menu)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_show)
        menu.addAction(act_login)
        menu.addSeparator()
        menu.addAction(act_quit)
        t.setContextMenu(menu)
        t.activated.connect(lambda r: self.restore_from_tray() if r in (QSystemTrayIcon.ActivationReason.Trigger,
                                                                        QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        self._tray, self._tray_menu = t, menu
        self._update_tray(False)
        self._tray_settings_changed()

    def _tray_settings_changed(self) -> None:
        self.db.set_setting("tray.minimize", "1" if self.chk_tray_min.isChecked() else "0")
        self.db.set_setting("tray.close", "1" if self.chk_tray_close.isChecked() else "0")
        usable = self._tray is not None
        for c in (self.chk_tray_min, self.chk_tray_close):
            c.setEnabled(usable)
        self.lbl_tray_note.setText("" if usable else "這個環境沒有系統匣，無法使用此功能。")
        if usable:
            self._tray.setVisible(self.chk_tray_min.isChecked() or self.chk_tray_close.isChecked() or not self.isVisible())

    def _update_tray(self, connected: bool) -> None:
        if self._tray is not None:
            self._tray.setIcon(tray_icon(connected))
            self._tray.setToolTip(f"{APP_NAME} {__version__}\n{'已連線' if connected else '未連線'}")

    def _to_tray(self) -> None:
        if self._tray is None:
            return
        self._save_geometry()
        self._tray.setVisible(True)
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self._tray.showMessage(APP_NAME, "程式仍在執行，點系統匣圖示可還原；按右鍵可選「離開」。",
                                   QSystemTrayIcon.MessageIcon.Information, 4000)

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._tray_settings_changed()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange and hasattr(self, "act_fullscreen"):
            self.act_fullscreen.blockSignals(True)
            self.act_fullscreen.setChecked(self.isFullScreen())
            self.act_fullscreen.blockSignals(False)
        if (e.type() == QEvent.Type.WindowStateChange and self.isMinimized() and self._tray is not None
                and self.chk_tray_min.isChecked()):
            QTimer.singleShot(0, self._to_tray)

    # ================================================================== lifecycle
    def closeEvent(self, e):
        if (not self._quitting and self._tray is not None and self.chk_tray_close.isChecked()):
            e.ignore()
            self._to_tray()
            return
        if not self._confirm_unsaved("關閉程式"):
            self._quitting = False
            e.ignore()
            return
        if self.typer.running:
            self.typer.cancel()
        self._save_geometry()
        if self._tray is not None:
            self._tray.hide()
        self.session.disconnect_()
        self.db.close()
        super().closeEvent(e)
