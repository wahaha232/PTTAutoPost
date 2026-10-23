# PTT AutoPost 開發進度（Roadmap 階段 1）

- 日期：2026-10-23
- 分支：`dev/roadmap`（自 `main` @ `6d390c4` 建立）
- 基準版本：0.6.2
- 基準測試：`python -m pytest -q`（`QT_QPA_PLATFORM=offscreen`）→ 168 passed
- 目前測試：同一指令 → 289 passed（階段 1 審查回饋 0.7.1 完成）
- 目前版本：0.7.1（2026/10/23）
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
- 真實 PTT 登入後畫面仍從未驗證；本階段不需要登入真實帳號。

## 額度與提交紀錄

| 項目 | 數值 |
|---|---|
| 當天開始 B | 暫不追蹤 |
| 目前累計用量 | 暫不追蹤 |
| 最後 commit | `8766a49`（0.7.1 審查回饋完成） |
| 下一次要填的組別 | 階段 1 已完成；階段 2（多分頁）待指示 |

> 本檔只記錄開發進度，不另產出報告檔。
