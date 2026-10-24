# PTT AutoPost 開發進度（Roadmap 階段 1）

- 日期：2026-10-23
- 分支：`dev/roadmap`（自 `main` @ `6d390c4` 建立）
- 基準版本：0.6.2
- 基準測試：`python -m pytest -q`（`QT_QPA_PLATFORM=offscreen`）→ 168 passed
- 目前測試：同一指令 → 402 passed（0.8.7 增量更新）
- 目前版本：0.8.7（2026/10/24）
- 開始時間 T0：2026-10-23 09:13（UTC+8）／2026-10-23 01:13 UTC
- 額度基準 B：**暫不追蹤**

## 階段 1 清單（新順序：B → A → C → J）

| 組 | 內容 | 狀態 |
|---|---|---|
| B | 介面：文章與終端機合併頁、移除訊息區／提示、全螢幕、主題、終端機配色 | 完成（含 0.6.4 追加修改） |
| A | 超連結：偵測、瀏覽器設定、圖片自動開啟、輸入中禁用 | 完成（0.6.5＋0.6.6 追加） |
| C | 終端機文字選取、複製、貼上 | 完成（0.6.7） |
| J | 發佈準備、授權、贊助、打包 | 完成（0.7.0；安裝程式腳本待 Inno Setup 實測） |

## B 組內容（歷史）

1. **文章與終端機合併在同一頁**：
   - 主視窗分頁改為「終端機與文章／草稿／設定」。
   - 合併頁用 `QSplitter`：左側終端機、右側文章面板，可拖曳寬度。
   - 文章面板子分頁：「擷取與欄位」（原文章左欄）與「預覽與輸入」（原文章右欄）；元件與 `self.*` 名稱不變，只搬移位置。
   - 文章面板可收合（按鈕＋`F12`）；收合時終端機佔滿；`self.compact`（螢幕高度 ≤ 800 px）預設收合。
   - 面板寬度與收合狀態存設定，損壞時用預設值且不可影響啟動。
   - 開啟草稿時切到合併頁、展開面板、選到對應子分頁。
   - 面板寬度改變、收合、展開時，終端機的填滿／保持比例都要重新排版。
   - 版面不可把文章面板和單一連線寫死，需預留階段 2 多分頁的介面。
2. 移除終端機底部的 `msg_log` 與提示文字，只留字型列與按鍵列；訊息改到狀態列，必要錯誤用對話框。
3. `F11` 切換全螢幕（選單或設定也可），`Esc` 不搶終端機原本的 Esc。
4. 主題：淺色／深色／跟隨系統（預設跟隨系統），即時套用並儲存；終端機另做淺色配色。

### B 組實作批次（已確認）

1. 合併頁與收合（版面、設定還原、開啟草稿展開、終端機重排）。**已完成（批次 1）**
2. 移除 `msg_log` 與提示文字、全螢幕。**已完成（批次 2）**
3. 主題（淺色／深色／跟隨系統、終端機淺色配色）。**已完成（批次 3）**

### 批次 1 完成內容

- 主分頁改為「終端機與文章／草稿／設定」；合併頁使用 `QSplitter`，文章面板為「擷取與欄位／預覽與輸入」子分頁。
- 原有元件與 `self.*` 名稱保留；原文內文／心得留在「擷取與欄位」。
- 文章面板可用終端機上方按鈕或 `F12` 收合／展開；狀態與寬度寫入 `ui.article_panel_collapsed`、`ui.article_panel_width`。
- 沒有設定值時，`self.compact` 為 True 就預設收合；設定損壞時 fallback，不影響啟動。
- 開啟草稿會切到合併頁、展開面板、選到「預覽與輸入」。
- 簽名檔快照提示移到文章面板上方（子分頁之外），因此在「預覽與輸入」也看得到。
- 面板寬度／收合／splitter 變動後會重新排版終端機。
- 新增 `_article_session()`／`_article_typer()` 存取器，文章流程不再全部直接綁 `self.session`／`self.typer`。
- 新增 7 個 UI 測試；目前全套 175 passed。

### 批次 2 完成內容

- 移除終端機底部 `msg_log` 與提示文字；底部只留字型列與按鍵列。
- `_notice()` 只寫狀態列；新增 `_error()`，草稿儲存失敗、輸入狀態寫入失敗等 critical error 會同時顯示對話框。
- 新增「檢視」選單：顯示文章面板（`F12`）與全螢幕（`F11`）。
- `F11` 由 `QAction` 處理，`changeEvent` 同步勾選狀態；沒有把 `Esc` 設成快捷鍵，終端機 Esc 仍送 `b"\x1b"`。
- 更新所有依賴 `msg_log` 的測試；新增狀態列、critical error、F11/Esc 測試；目前全套 178 passed。

### 批次 3 完成內容

- 新增 `src/ui/theme.py`：淺色／深色主題、跟隨系統解析、QPalette＋QSS、終端機 ANSI palette、對比度計算。
- 設定頁新增「外觀 → 主題」（跟隨系統／淺色／深色，預設跟隨系統）；設定鍵 `ui.theme`，即時套用並保存。
- 跟隨系統時連接 `QStyleHints.colorSchemeChanged`；Unknown 時用目前視窗 palette 的亮度判斷。
- 終端機新增淺色配色（深色前景、淺色 ANSI 背景），所有一般色與 bright 色對預設背景的對比度 ≥ 4.5。
- 狀態列顏色、欄位狀態顏色改由主題語意色提供。
- 新增 `tests/test_theme.py` 與 UI 主題測試；全套 185 passed。
- `src/version.py` bump 到 0.6.3（2026/10/23），README 更新 B 組功能與待驗證事項。

### 0.6.4 追加修改（2026-10-23）

- **終端機配色獨立選項**：設定頁「外觀 → 終端機配色」提供「永遠深色（黑底）」與「跟隨主題」，預設永遠深色；設定鍵 `ui.terminal_palette`（`dark`／`theme`）。只影響終端機；程式主題仍依 `ui.theme`。設定缺漏或損壞一律 fallback 到 `dark`。
- **splitter 寬度寫入去抖動**：拖曳時只更新記憶體中的 `_article_width` 並重排終端機；停止拖曳約 500 ms 後由單次 `QTimer` 寫入一次；關閉程式仍由 `_save_article_panel_state` 保存。
- **快捷鍵改為 F12**：文章面板改用 `F12`，避免 Qt 攔截 `Ctrl+Shift+A`；終端機有焦點時 `Ctrl+Shift+A` 會恢復送出 `b"\x01"`。README、選單、按鈕提示同步更新。
- 新增/更新測試：終端機配色預設黑底、淺色主題＋永遠深色、淺色主題＋跟隨主題、損壞設定 fallback、拖曳去抖動、關閉儲存寬度、F12 與 Ctrl+Shift+A 送 0x01。
- `src/version.py` bump 到 **0.6.4**（2026/10/23）。

## A 組完成內容（0.6.5；0.6.6 追加）

### 批次 1：網址偵測純邏輯

- 新增 `src/links.py`：`Link`、`find_links()`、`is_image_url()`、`validate_http_url()`。
- 直接從 `Screen.grid` 換算 cell 座標，中文雙格寬正確。
- 只認單列 http/https；被換行切斷的網址不接續、不猜。
- 拒絕其他 scheme、含 `user:pass@` 的網址、控制字元與無 host 網址。
- 新增 `tests/test_links.py`（7 項）。

### 批次 2：瀏覽器設定與安全開啟

- 新增 `src/ui/browser.py`：偵測 Chrome／Edge／Firefox、系統瀏覽器、自訂執行檔。
- 外部瀏覽器以 `[exe, url]` 單一參數啟動，`shell=False`，不經 shell。
- 設定頁新增「連結與瀏覽器」：瀏覽器選擇、自訂路徑、瀏覽／重新偵測、圖片自動開啟（預設關閉＋IP 警告）。
- 設定鍵 `browser.mode`、`browser.path`、`links.image_auto_open`；缺漏或損壞 fallback。
- 新增 `tests/test_browser.py`（6 項）與 2 項 UI 設定測試。

### 批次 3：終端機 hover／點擊／拖曳

- `TerminalWidget` 新增 `linkActivated`、`linksChanged`、`link_at()`、hover 底線與手形游標。
- 左鍵按下不立即開啟；移動超過 drag distance 視為拖曳；原地放開才開啟。
- 滑鼠事件不送出任何 BBS bytes，並保留 C 組選取的拖曳語意。
- 新增 `tests/test_terminal_links.py`（4 項）。

### 批次 4：圖片自動開啟

- 只在已連線、已登入、非自動輸入／非登入輔助時生效；手動點擊不受限。
- 同一網址同一次連線只開一次；每次畫面最多 1 個；每分鐘最多 3 個（滾動 60 秒）。
- 自動輸入／登入／速率上限跳過的網址記為已處理；非圖片網址不自動開。
- 連線狀態變成 `CONNECTED` 時清空紀錄。
- 新增 6 項 UI 自動開啟測試。

### 版本與測試

- `src/version.py` bump 到 **0.6.5**（2026/10/23），CHANGELOG 與 README 已更新。
- 全套 **216 passed**。

### 0.6.6 追加修改（2026-10-23，安全性）

- 新增 `is_auto_open_image_url()`：自動開啟只接受 **https**、主機為已知圖床（完全相同或子網域）、且通過 `validate_http_url()`。
- 只靠副檔名判斷的網址不再自動開啟；`.svg` 從 `_IMAGE_EXTENSIONS` 移除，且自動開啟另外排除 `.svg`。
- 主機為 IP、`localhost`／`.localhost`、或 IP 屬於非 global（內網／loopback 等）時不自動開啟；只用字串判斷，**不做 DNS 查詢**。
- `is_image_url()` 保留給其他用途；`_on_links_changed()` 改用 `is_auto_open_image_url()`。
- 因每畫面或每分鐘上限略過圖片時，狀態列提示一次「已達自動開啟上限，略過 N 個圖片連結；可手動點擊開啟」，同一畫面不重複提示。
- 設定頁說明補上「只自動開啟 imgur 等已知圖床的 https 連結」。
- 新增/更新測試：http 任意網站、https 任意網站、imgur https/http、`.svg`、IP、localhost、子網域、上限提示；全套 **219 passed**。
- `src/version.py` bump 到 **0.6.6**（2026/10/23），README 已更新。

## C 組完成內容（0.6.7）

### 批次 1：選取純邏輯

- 新增 `src/terminal/selection.py`：格座標選取範圍、雙格寬字元邊界展開（不切半）、連續選取（首列起點→行尾、中間整列、末列行首→終點）、Alt 矩形選取、詞選取、整列選取。
- 複製文字逐行去掉行尾空白、以 `\n` 連接，並移除尾端空白行；整畫面文字同樣處理。
- 新增 `tests/test_selection.py`（10 項）。

### 批次 2：終端機拖曳選取與反白

- `TerminalWidget` 支援左鍵拖曳選取、雙擊選詞、三擊整列、按住 Alt 矩形選取。
- 反白採前景／背景反轉；雙格寬字元整字反白。
- 原地單擊、畫面被伺服器更新、送出按鍵／滾輪／IME 時清除選取。
- 起點在連結上時拖曳＝選取、不開啟連結；原本的原地點擊開連結行為保留。
- 新增 `tests/test_terminal_selection.py` 選取相關 10 項。

### 批次 3：複製與右鍵選單

- `Ctrl+Shift+C` 複製選取；`Ctrl+C`（不含 Shift）仍送 `0x03`；複製不送任何 bytes。
- 右鍵選單：複製、全選畫面、複製整個畫面；沒有選取時「複製」停用且快捷鍵不做事。
- 新增 5 項複製／選單測試。

### 批次 4：安全貼上

- 新增 `src/net/paster.py`：
  - `sanitize_paste()`：換行統一為 `\n`、`\t`→4 空白、移除 ESC 與 Cc 控制字元。
  - `paste_stats()`／`paste_preview()`：字數（不含換行）、行數、前 5 行預覽。
  - `PasteSender`：沿用 `poster.CHUNK_BYTES`（100 bytes）、`IDLE_MS`、`MAX_WAIT_MS` 的分批節奏；每段送出前檢查連線與鎖定，斷線／鎖定即停、不重送，`finished` 回報已送出字數與段數。
- `TerminalWidget` 貼上流程：`Ctrl+Shift+V`／右鍵「貼上」；離線或 `term.locked` 時拒絕並在狀態列說明。
- `poster.encode_big5()` 嚴格檢查，無法編碼時對話框列出前 5 個字元並取消（不做部分貼上）。
- 超過 1 行或 200 字先顯示預覽確認；超過 5000 字直接拒絕；換行傳送為 CR。
- 貼上期間鍵盤與滾輪暫停，避免與分批傳送交錯；`Ctrl+V`（不含 Shift）仍送 `0x16`。
- 新增 `tests/test_terminal_paste.py`（20 項，含假連線 frame 記錄與 offscreen 剪貼簿）。

### 批次 5：版本與文件

- 主視窗按鍵列在貼上期間停用，成功送出後清除選取。
- `src/version.py` bump 到 **0.6.7**（2026/10/23），CHANGELOG、README 快捷鍵與限制已更新。
- 全套 **264 passed**。

### 0.7.1 追加（審查回饋）

- `TerminalWidget` 新增 `pasteStateChanged(bool)`；貼上開始／結束（含失敗、斷線、鎖定中止）都會通知主視窗。
- 貼上期間主視窗暫停「輸入標題／內文」、登入與「前往看板」：
  - `_update_type_buttons()` 判斷 `term.pasting`。
  - `_do_login()` 直接呼叫也拒絕並清空密碼欄；狀態列說明。
  - `goto_board()` 直接呼叫也拒絕並在狀態列說明。
  - `type_into_ptt()` 直接呼叫也拒絕；`preflight(..., pasting=True)` 回傳暫停原因。
  - 登入按鈕依連線狀態與 pasting 恢復；看板按鈕依看板有效性與 pasting 恢復。
- 新增 `tests/test_paste_locks.py`（4 項，含真實貼上開始／結束的按鈕切換）、終端機 `pasteStateChanged` 測試與 `preflight` pasting 測試。

### 未完成項目

- 無（Alt 矩形、雙擊、三擊皆已完成）。實際桌面手感與貼上到 PTT 編輯器的行為待使用者驗證。

## J 組完成內容（0.7.0）

### J1：贊助區塊

- `src/version.py` 新增 `SPONSOR_URL`、`SPONSOR_TEXT`；`SPONSOR_URL` 留空或不是有效 http/https（含帳密）時，設定頁的「贊助作者」區塊整個隱藏。
- 區塊只在使用者按下按鈕時用系統預設瀏覽器開啟連結；說明贊助自願、不影響功能、程式不追蹤或上傳資料。
- 新增 `tests/test_sponsor.py`（4 項：未設定、無效 scheme、含帳密、顯示與開啟）。
- 贊助連結與顯示文字仍待使用者提供；目前區塊隱藏。

### J2：授權與使用者文件

- 新增 `LICENSE`：專有授權聲明（個人非商業使用、不得散布／修改／商用，第三方元件依其授權）。
- 新增 `THIRD_PARTY_NOTICES.md`：PySide6／Qt／shiboken6（LGPL-3.0）、requests（Apache-2.0）、beautifulsoup4／charset-normalizer（MIT）、lxml（BSD-3-Clause）、Python（PSF）、PyInstaller（GPL-2.0＋exception）。
- 新增 `licenses/`：LGPL-3.0、GPL-3.0、各相依元件與 Python／PyInstaller 授權全文。
- 新增 `USER_README.txt`：可攜版啟動、SmartScreen、安全設計、快捷鍵、資料位置、授權與指令列；打包時填入版本與日期。
- 新增 `tests/test_packaging.py` 文件與打包流程測試。

### J3：資料夾版打包與體積精簡

- `PTTAutoPost.spec` 改為 **onedir／COLLECT**，Qt／PySide6 DLL 以獨立檔案放在 `_internal\`，可由使用者替換（LGPL 較易符合）。
- 從 PyInstaller 收集結果剔除未使用的 Qt Quick／QML／Pdf／OpenGL／Svg、`opengl32sw.dll`、translations、imageformats、iconengines；保留平台外掛（含 offscreen 供 selftest）、TLS、styles、IME 外掛。
- `tools/make_portable.py`：onedir build → 複製整個應用程式資料夾 + `LICENSE`／`THIRD_PARTY_NOTICES.md`／`licenses/`／`README.txt` → `--verify` 檢查 selftest、版本、frozen、corpus、文件、可替換 Qt DLL、未使用 Qt 檔。
- 新增 `--archive`（7-Zip LZMA2）與 `--installer`（Inno Setup 6）；`tools/PTTAutoPost.iss` 採 `lzma2/max`、每位使用者安裝（`PrivilegesRequired=lowest`）、不覆蓋 config／logs／data、附授權頁。
- 本機實際建置 0.7.0：資料夾版 **76.6 MB**、LZMA2 7z **22.2 MB**；`--selftest` OK、corpus 0、文件齊全、Qt DLL 可替換、未使用 Qt 檔 0。
- 本機未安裝 Inno Setup，`--installer` 只完成腳本，尚未產出 setup.exe。

### J4：版本與文件

- `src/version.py` bump 到 **0.7.0**（2026/10/23），CHANGELOG、README（打包、授權、贊助、已驗證項目）更新。
- 全套 **278 passed**。

### 0.7.1 追加（審查回饋）

- `tools/make_portable.py` 新增 `--onefile`（診斷用單檔版，預設仍為 onedir）；spec 依 `PTTAUTOPOST_ONEFILE` 切換 EXE／COLLECT。0.7.1 單檔版實際建置 **33.1 MB**，`--selftest` OK。
- 新增 `tools/spec_filters.py`：集中 PyInstaller 過濾規則；剔除未使用 Qt 元件，但**保留 `plugins/platforms/qwindows.dll` 與 `plugins/tls/*`**；`libcrypto-3.dll`／`libssl-3.dll` 只保留一份（優先根層）。
- `--verify` 新增檢查 `_internal\PySide6\plugins\platforms\qwindows.dll` 與 `plugins\tls\*.dll`；`layout_report()` 可單獨測試。
- 找不到 7-Zip 時，`--archive` 改用 `shutil.make_archive` 產生 ZIP（非 LZMA2，僅備援）；本機有 7-Zip，實際仍產 LZMA2 7z。
- `LICENSE` 的反向工程限制明確排除 LGPL 第三方元件（可為除錯、修改或替換 Qt 而反向工程），並新增「不構成法律建議」。
- `tools/PTTAutoPost.iss` 新增 `[InstallDelete]`，升級時先刪除舊 `_internal`，再安裝新檔。
- 0.7.1 實際重建：資料夾版 **76.6 MB**、LZMA2 7z **22.2 MB**；`--verify` OK（qwindows／tls 均存在、未使用 Qt 檔 0）；單檔版 33.1 MB。
- 全套 **289 passed**。

### 未完成項目

- 安裝程式實測（需先安裝 Inno Setup 6）。
- 無 7-Zip 環境的 ZIP 備援尚未實機驗證（單元測試已涵蓋產生 ZIP）；本機為 7-Zip 路徑。
- 贊助連結與顯示文字（目前 `SPONSOR_URL` 留空，區塊隱藏）。
- 專有授權與第三方授權文件的法律覆核（本專案只做工程整理，不構成法律建議）。

## 0.7.2 追加修正（使用者回報）

### 第二次擷取與欄位清除

- 每次成功擷取都視為新文章：解除舊 `draft_id`、清空心得、草稿簽名快照、確認／輸入勾選、輸入狀態文字與手動預覽；已儲存的草稿保留。
- 「擷取與欄位」新增 **清除全部欄位** 按鈕：確認後清空所有欄位、預覽與暫存狀態（`draft_id`、`_dirty`、`_preview_manual`、解析狀態），不刪除已儲存草稿；輸入或擷取進行中會拒絕。

### 簽名檔

- `_pick_signature()` 改選簽名檔時會清除草稿的簽名快照與提示列，立即套用新選擇；若原本有快照則標記草稿為已修改。
- 修正「完成貼文後改選簽名檔沒有作用」：先前 `_sig_text()` 一直回傳舊快照，選單看起來無效。

### 設定頁

- 新增 **套用** 按鈕：重新套用主題、終端機配色、瀏覽器／路徑、圖片自動開啟、字型、系統匣與登入小幫手路徑並寫入 DB，完成後以對話框顯示「設定已成功套用並儲存」。

### 超連結

- 所有偵測到的連結一律畫底線（不再只在 hover 時顯示）；滑鼠移入仍會加粗並顯示手形游標。

### 自動開啟圖片

- 在設定頁勾選開啟時，會立即評估目前畫面上的圖片連結（先前要等下一次畫面更新）。
- 輸入／登入輔助期間先略過，不再把網址永久標記為已處理；輸入完成或登入完成後會重新評估目前畫面。輸入完成的狀態訊息會保留在自動開啟提示之後。原有 https／已知圖床、IP／localhost／內網、`.svg`、每畫面 1 個、每分鐘 3 個限制不變。
- 新增實際終端機畫面、登入完成、輸入完成與開啟設定當下的測試。

### 測試

- 全套 **298 passed**；0.7.2 新增 9 項 UI／連結測試。

## 0.8.0 追加（雲端更新、站台書籤、Telnet）

### 雲端更新

- 新增 `src/update.py`：讀取 `wahaha232/PTTAutoPost` 的 GitHub Releases、版本比較、依安裝型態選擇資產（資料夾版 `-portable.zip`／`-portable.7z`、安裝版 `-setup.exe`）。
- 下載只接受 HTTPS 與允許的 GitHub 主機；串流上限 300 MB，GitHub 有 `digest` 時驗證 SHA-256（沒有 digest 會明確標示未驗證），下載到 `updates\`（不可寫時改用 `%LOCALAPPDATA%\PTT AutoPost\updates`）。
- 下載後**不自動執行**：資料夾版顯示解壓縮指示，安裝版顯示 setup.exe 指示；設定頁可開啟更新資料夾。私人儲存庫可用 `PTTAUTOPOST_GITHUB_TOKEN`（只讀環境變數，不寫日誌）。
- UI：設定頁「更新」區塊、「說明 → 檢查更新…」；背景執行檢查／下載，狀態列與更新區塊顯示進度。
- `--archive` 現在同時產出 LZMA2 `.7z` 與更新用 `.zip`。
- 注意：目前尚未在 GitHub 建立 Release，實際端到端下載／安裝待驗證。

### 站台書籤（2026-10-23 實測）

- 新增「站台」分頁與 `src/sites.py`、DB `sites.bookmarks`（預設 13 站；可新增／修改／刪除／複製位址／唯讀 TCP 測試）。
- 實測結果（只做 DNS／TCP／TLS，未登入、未送帳密）：
  - PTT `ws.ptt.cc:443/bbs`：TCP/TLS 有回應；WebSocket 握手以測試腳本送 403，實際連線仍需內建客戶端驗證。
  - PTT2 `ws.ptt2.cc:443/bbs`：TCP/TLS 有回應；WebSocket 握手 403，實際連線待驗證。
  - 夢之大地、楓橋驛站、巴哈姆特、紫丁香、新水木清華、未來最舊小棧、華年小集、網際新世界：TCP 23 可連（網際新世界 3 秒內無 banner）。
  - 淒美燈塔、七月七日晴、鳴蟬：TCP 22 可連，SSH banner 正常；BBS 入口待確認。
- 13 站全部加入預設書籤；主機與備註記在 `src/sites.py`。

### Telnet 傳輸

- `PttClient` 支援 `telnet://host[:port]`，使用 `QTcpSocket`；`endpoint_problem()` 允許 Telnet、仍拒絕帳密與其他 scheme。
- `IacFilter` 新增 `feed_with_replies()`：過濾 IAC 並以 DONT／WONT 回應伺服器 WILL／DO，避免 Telnet 協商卡住。
- 終端機、Big5 畫面、輸入與貼上流程沿用；Telnet 為**明文**，連線時狀態列提示，且在公用網路輸入重要密碼的風險由使用者承擔。
- 輔助登入仍只信任 `ws.ptt.cc`，不會把帳密送到 Telnet 站台。
- SSH 目前僅保存書籤，尚未實作傳輸；非 Big5 站台可能亂碼。

### 測試

- 新增 `tests/test_update.py`、`tests/test_update_ui.py`、`tests/test_sites.py`、`tests/test_net_telnet.py`；更新分頁數量與既有測試。
- 新增 `tools/make_source_listing.py`：輸出純文字原始碼清單（`dist\PTTAutoPost-0.8.0-source.txt`，78 個檔案、862.9 KB），供審閱／備份。
- 全套 **332 passed**。
- 本機 0.8.0 建置：資料夾版 76.6 MB、LZMA2 7z 22.2 MB、更新用 ZIP 33.1 MB；`--selftest` OK。
- Telnet 唯讀實測：`telnet://bbs.ccns.ncku.edu.tw:23` 成功連線，7 秒內收到 3,399 bytes Big5／ANSI 畫面資料；未登入、未送帳密。

### 未完成／待辦

- GitHub Release 尚未建立，更新功能沒有真實 Release 可測；建 Release 時請上傳 `PTTAutoPost-<版本>-portable.zip` 與 `PTTAutoPost-<版本>-setup.exe`。
- 私人儲存庫的 Token 流程與速率限制未實測。
- Telnet 站台的實際登入、按鍵、Big5 顯示與非 Big5 站台編碼待使用者實測；SSH 連線尚未實作。
- 圖片／多媒體（開圖模式、GIF、內嵌播放、圖床、YouTube）與 IP 地理位置／Proxy／VPN 等功能尚未開始，屬於後續階段。

## 0.8.1 追加（更新／贊助介面）

- 設定頁「更新」新增：
  - 啟動時自動檢查更新（預設開啟；只在 `sys.frozen` 的打包版執行，背景查詢 GitHub，沒更新或查詢失敗只更新狀態列，不跳對話框）。
  - 下載進度條；下載中顯示 bytes 進度。
  - 「強制更新」：即使目前版本與 Release 相同，也重新下載最新版（不下載較舊版本）。
  - 「手動下載」：以系統瀏覽器開啟 GitHub Releases 最新頁。
- 說明選單新增：
  - 「關於 PTT AutoPost」：版本、建置日期、授權摘要與 GitHub 連結。
  - 「贊助 PTT AutoPost」：呼叫既有贊助流程；`SPONSOR_URL` 未設定時顯示說明對話框，設定後才開系統瀏覽器。
- 新增測試：自動檢查靜默、背景失敗靜默、強制更新同版本、進度條、手動下載、關於、贊助選單。
- 全套 **339 passed**。
- 本機 0.8.1 建置：資料夾版 76.6 MB、7z 22.2 MB、更新用 ZIP 33.1 MB；`--selftest` OK。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.1-source.txt`（78 檔、871.0 KB）。

## 0.8.2 修正（安全／可靠性）

- 擷取：DNS 解析失敗改為 fail-closed；每個 redirect hop 都重新驗證，並透過 Session 專屬的 urllib3 transport pin 住已驗證 IP（防 DNS rebinding）。不再全域替換 `socket.getaddrinfo`。
- robots.txt：成功快取 1 小時、失敗 60 秒，快取上限 128 筆；`requests.Session` 以 context manager 關閉。
- 連線：`PttClient.close()` 立即進入 `DISCONNECTED`，可馬上重連；輔助登入只接受精確的官方 WSS 端點（scheme/host/port/path）。
- 輸入：新增 `SendLock`，自動輸入與剪貼簿貼上共用同一個 writer，避免 bytes 交錯。
- 關閉：`closeEvent` 取消背景 `FetchTask` 並斷開所有背景訊號；等待中的 polite delay 可被取消。
- 資料：SQLite 啟用 WAL／`synchronous=NORMAL`；遷移前備份與設定頁「備份資料…」都使用 `Connection.backup()`，包含 WAL 中已提交的資料；文件中加入備份／還原步驟。
- 安全提示：Telnet 連線前顯示明文警告（可取消），站台清單標示「加密／明文」；更新下載訊息區分「已核對 SHA-256」與「發布者身分」。
- 解析：每頁只做一次 DOM 複製；表單／導覽容器若包住候選內文不會被誤刪；Big5 檢查走整段快路徑。
- 終端機：`ESC c` 重設保留 `bytes_fed`／`bell` 統計；空白列統一由 `_blank_row()` 建立。
- 專案：移除 0.6.2 舊彙整快照、加入 `.gitignore`、移除文件中的本機路徑；新增 `constraints-build.txt` 記錄可重現建置版本。
- 全套 **351 passed**；`--selftest` OK。
- 驗收環境：Windows 11 10.0.26200、Python 3.12.10、PySide6 6.11.2、pytest 9.1.1（2026-10-23）。
- 本機 0.8.2 建置：資料夾版 76.6 MB、7z 22.2 MB、更新用 ZIP 33.1 MB；凍結版 `--selftest` 回報 0.8.2。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.2-source.txt`（79 檔、695.0 KB）。
- 實際以 pinned transport 擷取 `https://example.com/`：HTTP 200、577 bytes；凍結版 `--selftest` 回報 0.8.2。
- 本次 0.8.2 變更尚未 commit。

## 0.8.3 修正（圖片自動開啟改在程式內）

- 圖片自動開啟改由程式內建的 `ImageViewer` 顯示，不再呼叫系統或外部瀏覽器；手動點擊連結仍依瀏覽器設定開啟。
- 圖片在背景執行緒下載，套用與文章擷取相同的 https／已知圖床／每一跳 SSRF 檢查與 DNS pin；拒絕 SVG，限制 20 MB 與 4000 萬像素，內容型別必須是 `image/*`。
- 檢視視窗不會搶走終端機焦點（`WA_ShowWithoutActivating`），依視窗大小等比例縮放；同一時間只保留一個檢視視窗，關閉視窗或程式縮到系統匣時會取消下載。
- 打包：保留 JPEG／GIF／WebP 影像外掛（PNG／BMP 內建於 Qt），避免資料夾版無法顯示圖片。
- 新增測試：影像下載政策（http／非圖床／SVG／redirect／大小／型別／取消）、解碼、檢視視窗顯示與錯誤、UI 不再開瀏覽器；全套 **375 passed**。
- 本機 0.8.3 建置：資料夾版 77.8 MB、7z 22.6 MB、更新用 ZIP 33.6 MB；凍結版 `--selftest` 新增 PNG／JPEG 編碼後解碼檢查（確認影像外掛在打包版可用），回報 0.8.3。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.3-source.txt`（83 檔、718.3 KB）。

## 0.8.4 修正（自動開圖、懸停預覽、文章圖片）

- 修正自動開圖失效：不再要求程式的 `logged_in`（手動登入或直接進主選單時不會被誤判為未登入），也不再因自動輸入中而延後；圖片檢視視窗不搶焦點，看到連結就開。
- 自動開圖範圍：只要是公開主機的 https 圖片（已知圖床，或 .jpg／.jpeg／.png／.gif／.webp／.bmp／.avif 副檔名）就開；仍拒絕 http、SVG、localhost、內網與 IP 位址。
- 新設定「滑鼠移到圖片連結時預覽」（預設關閉）：游標停在終端機圖片連結約 0.45 秒後，在游標旁顯示小 preview；移開即消失。下載在背景執行緒，成功圖片快取在記憶體（64 MB／16 張），同一網址只下載一次。
- 新設定「文章內有圖片連結時直接顯示」（預設關閉）：擷取文章後解析 `<img>`（含 `data-src`／`srcset`）與圖片連結，放進同一個檢視視窗，提供「上一張／下一張」與張數；文章圖片可用任何公開 https 主機，但仍套用每一跳 SSRF／DNS pin 與 `image/*` 內容檢查、SVG 拒絕、20 MB 與像素上限。
- 新增測試：自動開圖不依賴登入／輸入狀態、放寬後的 URL 政策、文章圖片解析（相對路徑／srcset／追蹤像素／SVG／http）、懸停預覽顯示與隱藏、文章圖片畫廊切換與快取；全套 **384 passed**。
- 本機 0.8.4 建置：資料夾版 77.8 MB、7z 22.6 MB、更新用 ZIP 33.6 MB；凍結版 `--selftest` OK（含 PNG／JPEG 編碼再解碼）。
- 更新器：儲存庫已改為公開；未帶 `PTTAUTOPOST_GITHUB_TOKEN` 實測 `update.fetch_latest_release()` 可取得 `v0.8.4` 與攜帶版 ZIP，不再出現私人儲存庫的 404。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.4-source.txt`（83 檔、738.5 KB）。

## 0.8.5 修正（更新檔下載 CDN）

- 原因：GitHub 的 `browser_download_url` 會 302 到 `release-assets.githubusercontent.com`，但 `ALLOWED_HOSTS` 只有舊的 `objects.githubusercontent.com`／`github-releases.githubusercontent.com`，所以下載階段以「下載被重新導向到不允許的網址」中止。
- 修正：允許 `release-assets.githubusercontent.com`；其他未知的重新導向主機仍會拒絕，SHA-256 與大小驗證不變。
- 實測：未帶 Token 從 `v0.8.4` Release 下載 `PTTAutoPost-0.8.4-portable.zip`，35,203,929 bytes、SHA-256 與 Release digest 相符。
- 注意：0.8.4（含）以前的版本仍有同樣的 allow-list，無法自動下載 0.8.5；請先手動下載 0.8.5 攜帶版更換，之後的更新即可自動下載。
- 新增測試：目前 CDN 主機可通過、未知重新導向主機被拒；全套 **386 passed**。
- 本機 0.8.5 建置：資料夾版 77.8 MB、7z 22.6 MB、更新用 ZIP 33.6 MB；凍結版 `--selftest` OK。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.5-source.txt`（83 檔、740.0 KB）。

## 0.8.6 修正（文章圖片、重新載入、打包下載、介面字型）

- 文章圖片自動開啟失效的原因：舊版把整頁（含導覽、相關新聞、廣告）的 `<img>` 都收進來，而且只取 `src` 的第一個候選，常拿到縮圖或廣告圖。現在：
  - 只在文章內容容器（`article`／`main`／解析出的內文節點）內找圖，排除 nav／aside／footer／header／form 與 ad／logo／icon／related 等 class。
  - 支援 `data-src`／`data-original`／`data-lazy-src`、`srcset`／`data-srcset`（取最大寬度或 2x），若圖片外包 `<a>` 且連結是原圖則優先原圖。
  - 已知縮圖會升級：Wikimedia `/thumb/.../NNNpx-` 改抓原檔；CNA `/WebPhotos/400|800/` 改抓 `/WebPhotos/1024/`；升級後若格式不合法（例如來源是 SVG）則保留可顯示的 PNG 縮圖。
  - 下載與檢視都帶文章網址作 `Referer`，避免圖床防盜連結擋下。
  - 找不到內容圖片時才用 `og:image`／`twitter:image` 當備援；完全沒有圖片會在狀態列說明。
- 文章面板新增「重新載入文章」：使用已擷取的原文網址重新擷取，不必重貼；擷取中會停用。
- 文章面板新增「打包下載圖片」：把文章內所有圖片以原始網址下載成 ZIP（不縮圖、不改寫影像），檔名去除不安全字元並自動避開重複，單張失敗會略過並回報，總量上限 300 MB，完成後顯示張數與路徑。
- 設定 → 外觀新增「介面字型」「介面字級」（8–24 pt）：即時套用到選單、按鈕與文章面板並存入 DB；終端機字型仍由「終端機顯示」獨立控制。
- 新增測試：文章圖片容器範圍／廣告排除／srcset 最大／連結原圖／Wikimedia 與 CNA 升級、ZIP 原圖位元組與檔名去重／失敗略過、重新載入網址選擇、介面字型套用與保存；全套 **396 passed**。
- 實測：CNA 文章解析出 5 張 `WebPhotos/1024` 原圖並在程式內畫廊顯示（1024×576、121 KB），ZIP 下載 5 張、580,007 bytes；Wikimedia 縮圖升級為 `upload.wikimedia.org` 原檔。
- 本機 0.8.6 建置：資料夾版 77.8 MB、7z 22.6 MB、更新用 ZIP 33.6 MB；凍結版 `--selftest` OK。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.6-source.txt`（83 檔、763.3 KB）。

## 0.8.7 新增（增量更新）

- 新增 `tools/make_update_bundle.py`：比較兩個攜帶版資料夾，只把變更／新增的檔案放進 `PTTAutoPost-<新版>-delta-<舊版>.zip`，內含 `update.json`（版本、來源版本、每個檔案 SHA-256／大小、刪除清單）；`config`／`data`／`logs`／`updates` 永不納入。
- 更新器：攜帶版優先找與目前版本相符的 delta；下載後驗證 GitHub digest、`update.json`、每個檔案雜湊與大小，並拒絕絕對路徑／`..`／未知來源版本。驗證失敗或沒有相符 delta 時改用完整 ZIP。
- 套用方式：在下載驗證後詢問；確認後產生 PowerShell 輔助程式，等待本程式結束 → 備份被覆蓋的舊檔到 `updates\backup-<版本>` → 覆蓋變更檔案 → 自動啟動新版 → 清除暫存。Windows 無法覆蓋執行中的 EXE，因此**一定要重新啟動**（程式會自動重啟）；`config／logs／data` 不會被動到。
- 第一次從 0.8.6（含）以前更新到 0.8.7 仍得用完整 ZIP（舊版不認識 delta）；之後的版本才能只下載變更檔。
- 新增測試：delta 資產選擇（版本相符／不符／非攜帶版）、`update.json` 與檔案雜湊驗證、路徑逃逸拒絕、helper 產生與啟動、UI 套用／取消流程；全套 **402 passed**。
- 實測：0.8.6 → 0.8.7 delta 為 **4.2 MB**（3 個檔案：`PTTAutoPost.exe`、`README.txt`、`_internal/base_library.zip`），套用到 0.8.6 資料夾副本後 `--selftest` 回報 0.8.7，原有 `config` 保留。
- 本機 0.8.7 建置：資料夾版 77.8 MB、完整 7z 22.6 MB、完整 ZIP 33.6 MB、delta×3 各 4.2 MB；凍結版 `--selftest` OK。
- 純文字原始碼清單：`dist\PTTAutoPost-0.8.7-source.txt`（84 檔、783.7 KB）。
- 之後每次發布若要支援增量更新，建置後執行：
  `python tools/make_update_bundle.py --new dist\PTTAutoPost-<新版>-portable --base dist\PTTAutoPost-<前一版>-portable`
  並把 `dist\PTTAutoPost-<新版>-delta-<前一版>.zip` 一起上傳 Release。

## 待使用者驗證（不在本次自動測試範圍）

- B 組已完成項目：實際桌面（含 1366×768）的合併頁比例、面板收合／還原、`F12`、開啟草稿後的面板展開。
- F11 與選單在實際桌面的行為；主題跟隨系統的即時效果。
- 終端機配色預設黑底、切換「跟隨主題」時淺色配色的實際效果（含真實 PTT 畫面）。
- `F12` 收合面板在實際桌面／終端機有焦點時的行為。
- A 組：實際桌面系統／Chrome／Edge／Firefox／自訂瀏覽器開啟；圖片自動開啟只限已知圖床 https 的行為與 IP／隱私效果；每分鐘上限與略過提示；真實 PTT 畫面中的網址位置、hover 與點擊；被換行切斷的網址目前只認單列，請確認可接受。
- A 組 0.6.6：實際確認 `.svg`、IP／localhost／內網主機不會自動開啟，但手動點擊仍可開啟。
- C 組：實際桌面的拖曳選取手感、跨行選取、雙擊選詞／三擊整列／Alt 矩形；反白在黑底與淺色主題下的可讀性。
- C 組：真實 PTT 畫面持續更新時選取是否過快被清除（目前規則：任何伺服器畫面更新即清除）；單擊空白處清除。
- C 組：`Ctrl+Shift+C`／`Ctrl+Shift+V` 與 Windows／輸入法快捷鍵是否衝突；終端機有焦點時複製不送 `0x03`、貼上不送 `0x16`。
- C 組：貼上到 PTT 編輯器的實際結果（換行轉 CR 是否正確斷行）、預覽／取消、Big5 無法編碼的對話框、5000 字上限。
- C 組：長文字分批貼上的節奏與畫面回顯；中途斷線或自動輸入／登入輔助接手時是否停止並回報已送出數量；貼上期間鍵盤暫停是否符合期待。
- J 組：實際桌面從 `dist\PTTAutoPost-0.7.1-portable\` 啟動、SmartScreen 提示、防毒掃描、`config`／`logs`／`data` 寫入位置；以 7z 解壓後的完整性。
- J 組：在沒有 7-Zip 的機器執行 `--archive`，確認 ZIP 備援檔可解壓與下載說明；`--onefile` 僅為診斷版，確認不需要納入正式散布。
- J 組：Qt DLL 替換流程（LGPL）與 `_internal` 結構；未使用 Qt 元件剔除後，實際操作（檔案對話框、系統匣、IME、字型、WebSocket 連線）是否仍正常。
- J 組：Inno Setup 6 安裝／升級／移除後 config／logs／data 是否保留（本機無 ISCC，尚未產出 setup.exe）。
- J 組：贊助連結與顯示文字（提供後設定 `SPONSOR_URL`／`SPONSOR_TEXT` 並確認只開系統瀏覽器）；專有授權與第三方授權文件請做法律覆核。
- 0.7.2：連續貼上兩個不同網址，確認第二篇欄位、心得、簽名與確認狀態都是新的，且第一篇草稿仍保留。
- 0.7.2：開啟舊草稿後改選簽名檔（含完成貼文後）確認預覽與實際輸入都使用新簽名；設定頁「套用」的實際桌面對話框。
- 0.7.2：真實 PTT 畫面的超連結底線是否清楚、選取反白時是否仍可辨識；圖片自動開啟在「已登入、捲動到圖片」與「輸入完成後」的實際行為與隱私提醒。
- 0.8.0：建立 GitHub Release 後，分別用資料夾版與安裝版測試「檢查更新 → 下載 → SHA-256 → 自行安裝／解壓」；私人儲存庫請測 `PTTAUTOPOST_GITHUB_TOKEN`。
- 0.8.0：實際從「站台」連 PTT／PTT2（WSS）與至少一個 Telnet 站台，確認連線、登入畫面、Big5 顯示、鍵盤／貼上與斷線；SSH 書籤目前不連線。
- 0.8.0：Telnet 明文風險提示與非 Big5 站台（例如新水木清華）的編碼限制是否符合期待。
- 0.8.1：打包版啟動 5 秒後的自動檢查（設定開／關、無 Release／私人儲存庫、無更新時是否安靜）；強制更新與手動下載；更新進度條；關於與贊助選單的實際桌面顯示。
- 0.8.3：真實 PTT 畫面出現 imgur 等圖片連結時，確認在程式內視窗顯示、不搶焦點、不開瀏覽器；JPEG／GIF／WebP 在打包版都能顯示，並確認縮放與關閉取消下載。
- 0.8.4：手動登入或直接進主選單時，終端機圖片連結會立即開圖；懸停預覽的位置／延遲與移開消失；文章擷取後圖片畫廊的張數、上一張／下一張與隱私提醒是否符合期待。
- 0.8.5：先手動更新到 0.8.5，再讓程式檢查 0.8.6（或下一版）並完成下載，確認不再出現「重新導向到不允許的網址」。
- 0.8.6：用真實新聞文章確認自動開圖是文章內容圖（不是廣告／相關新聞縮圖）、畫廊張數與原圖尺寸；「重新載入文章」「打包下載圖片」的 ZIP 內容與檔名；介面字型與字級在選單、按鈕、文章面板的實際顯示。
- 0.8.7：先手動換到 0.8.7；下一版發布後確認只下載 delta、備份舊檔、套用後自動重啟且版本正確，`config／logs／data` 保留。
- 真實 PTT 登入後畫面仍從未驗證；本階段不需要登入真實帳號。

## 額度與提交紀錄

| 項目 | 數值 |
|---|---|
| 當天開始 B | 暫不追蹤 |
| 目前累計用量 | 暫不追蹤 |
| 最後 commit | `d6e9278`（0.8.6 文章圖片／重新載入／打包下載／介面字型；v0.8.6 已發布） |
| 下一次要填的組別 | 階段 1 已完成；階段 2（多分頁）待指示 |

> 本檔只記錄開發進度，不另產出報告檔。
