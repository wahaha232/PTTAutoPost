# PTT PO 文專案重啟｜Phase 0 唯讀稽核報告

> **歷史文件（2026-10-15，實作前設計）**：內容已落後於 0.6.2 實作與 2026-10-22 的決定，僅供參考。現況以程式碼、`ESTIMATE_2026-10-22.md`、`ROADMAP_2026-10-22.md`、`PHASE0_RESTART_AUDIT_2026-10-22.md` 為準。

- 稽核日期：2026-10-15
- 專案名稱：PTT-POST-EXTENSION（沿用名稱，**不代表繼續使用瀏覽器外掛**）
- 專案路徑：`D:\Claude\PTTAUTOPOST`
- 本階段性質：唯讀稽核與規劃。**未修改任何應用程式原始碼、設定、依賴、建置腳本；未建置 EXE；未連線 PTT 伺服器**（唯一的外部動作是對 `term.ptt.cc` 公開靜態檔案的 HTTP GET，見 §9.1）。
- 配套文件：[PHASE0_IMPLEMENTATION_PLAN.md](PHASE0_IMPLEMENTATION_PLAN.md)（本報告內文所稱「IMPLEMENTATION_PLAN」皆指此檔；原檔名 `IMPLEMENTATION_PLAN.md` 已於 2026-10-15 讓給新版開發計畫）
- **歷史文件註記（2026-10-15）**：使用者已確認舊專案全部刪除、不復原、不依賴舊原始碼。本報告中的 EXT／GEM／SRS v1.x 描述僅作為「需求知識與稽核證據」保存；新版規格見 [SRS.md](SRS.md)，新版計畫見 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)。

---

## 0. 先講最重要的三件事

| # | 發現 | 影響 |
|---|------|------|
| **K1** | **`D:\Claude\PTTAUTOPOST` 是空目錄**（無檔案、無 `.git`），建立時間 2026-10-15 15:49。原專案 `D:\Claude\PTT-POST-EXTENSION` 與四份規格／程式檔（`PTT_SRS_v1.0.docx`、`PTT_SRS_v1.3.txt`、`PTT_SRS_v1.4.txt`、`CODE_GEMINI4.txt`，原位於 `PTTAUTOPOST\`）**都在今天 15:48–15:49 被移到資源回收筒**（回收筒中繼資料 `$I*` 檔可證）。 | 本次稽核的實際對象是**回收筒內的檔案**（唯讀讀取，未還原、未搬移、未清空）。不確定刪除是否為使用者本意，也不知道回收筒是否會被清空。**需要使用者決定是否還原（決策 D-00）**。 |
| **K2** | **SRS 最新版是 v1.4（2026-10-14），不是任務書所說的 v1.0／v1.1。** 實際找到 v1.0（docx）、v1.3、v1.4；**v1.1、v1.2 全機搜尋不到**。 | 任務書「v1.0、v1.1 為基線」與實際不符；以 v1.4 為最新需求基線，但 v1.4 仍標示「待核准」。 |
| **K3** | **SRS v1.4 的核心（Adapter 自動登入、自動存檔發文、SUBMITTING 階段表、遠端重複檢查閘門、憑證管理）與本次新決策直接衝突**（程式不得自動送出、不得自動登入、Mode B 只操作使用者已開啟的視窗）。v1.4 約三分之一的需求（FR-013／015／017／027／028 與 8.2／8.3 狀態機）需重新定義。 | 需另發 SRS v1.5（本階段不改 SRS 正文）。衝突清單見附錄 A。 |

另外：舊外掛專案**沒有任何 Git 提交**（`master` 分支零 commit，所有檔案 untracked），所以沒有歷史可追溯；任何版本管理資訊都只能靠檔案時間戳。

---

## 1. 稽核範圍、方法與證據等級

**讀取的來源**（皆唯讀）：

| 代號 | 來源 | 實際位置 |
|------|------|----------|
| **EXT** | 舊 Chrome MV3 外掛專案（原 `D:\Claude\PTT-POST-EXTENSION`） | `D:\$RECYCLE.BIN\S-1-5-21-…-19908\$RK2N4Q2\`（1.2 MB，含 `.git`） |
| **SRS** | SRS v1.0 / v1.3 / v1.4 | 回收筒：`$RCH30M1.docx`、`$RU2GQJ5.txt`、`$RM049RK.txt`（另有 `$R3EKA0J.txt`，與 v1.4 同為 85,701 bytes，原位於 Downloads） |
| **GEM** | 「CODE_GEMINI4」：依 SRS v1.3 產生的 Python 單檔參考實作（2,086 行） | 回收筒：`$RTUUAD3.txt` |
| **LOGIN** | 既有 C# 工具 PttAutoLogin（與本專案無關，但屬相鄰資產） | `D:\Claude\PTTLOGIN\`（`src` 與 `release`） |
| **SITE** | `term.ptt.cc` 公開前端（HTTP GET，下載到 `%TEMP%`，未進專案） | §9.1 |
| **ENV** | 本機工具鏈（`python --version`、`pip list`、`dotnet --list-sdks`） | §3.4 |

**證據等級**（本報告各處標註）：

| 標記 | 意義 |
|------|------|
| **[C]** | 讀過實際程式碼／測試檔／檔案清單（靜態閱讀，**未執行**任何測試或程式） |
| **[D]** | 僅見於文件（README／TEST_REPORT／舊報告）的宣稱，本次未獨立驗證 |
| **[S]** | 本次重新讀取 `term.ptt.cc` 公開檔案所得 |
| **[E]** | 本機環境檢查所得 |
| **[推論]** | 由程式碼閱讀推得，未實際執行 |
| **待實測** | 沒有證據，不得視為事實 |

**未做的事**：沒有執行 EXT 的 `npm test`（會啟動 headless Chrome、寫入 `.cache/`）、沒有執行 GEM 的 pytest（會寫檔且需 pip 依賴）、沒有登入 PTT、沒有操作任何已登入視窗。因此下列「測試通過」皆為 **[D]**（文件宣稱）；測試**數量**以 grep 核對過 **[C]**。

---

## 2. 專案現況與 Git 資訊

| 項目 | 結果 |
|------|------|
| 專案目錄 `D:\Claude\PTTAUTOPOST` | 空目錄；非 Git 儲存庫 [C] |
| 本工作階段所在 Git（`D:\eddie-wu\Downloads`） | 分支 `HEAD`、零 commit、乾淨；與本專案無關 |
| `D:\` 根目錄 | **不是** Git 儲存庫（`git rev-parse` 失敗）；任務啟動時 gitStatus 所指為 Downloads |
| EXT 儲存庫（回收筒內） | 分支 `master`、**零 commit**、無 stash、無其他分支；`.gitignore README.md docs/ manifest.json package.json src/ tests/ tools/` 全為 untracked [C]（以 `git --no-optional-locks status` 唯讀查詢） |
| EXT 最後修改 | `docs/` 2026-10-14 18:00；資料夾本身 2026-10-14 16:47 |
| 先前開發階段成果 | EXT（Phase 1–2 完成度見 §5）；GEM（單檔參考實作）；SRS v1.0→v1.4；**EXT 內已有一份舊的 `PHASE0_AUDIT.md`／`IMPLEMENTATION_PLAN.md`／`TEST_REPORT.md`**（外掛架構時期，見下）|
| 其他 Claude Code 工作階段成果 | 記憶檔（`ptt-post-extension-project.md`）記載 2026-10-14 Phase 1 完成、Phase 2 填入為 EXPERIMENTAL、真實 PTT 驗證 BLOCKED、使用者選擇「維持半自動」。與 EXT 內容一致 [C]。 |
| 建置腳本／EXE 產物／發布紀錄 | EXT：無建置步驟（零依賴、載入未封裝項目）；無 EXE。GEM：無打包腳本。LOGIN：有 `release\PttAutoLogin.exe`（113 MB，2026-09-14）[E]，與本專案無關 |
| 依賴／設定 | EXT：`package.json` 僅 scripts，**零 npm 依賴** [C]；GEM：`requests`、`PyYAML`、`beautifulsoup4`、選用 `trafilatura`、`PySide6`（GUI 內匯入）、`pytest` [C] |

**舊 `docs/` 處理**：新專案目錄原本沒有 `docs/`，因此本次兩份文件為**新增**，沒有覆蓋任何東西。舊外掛時期三份文件仍在回收筒；其有價值的內容（對 `term.ptt.cc` 的 F1–F18 事實與 A1–A8 假設）已在 §9 帶入並標註出處與證據等級。

---

## 3. 實際技術架構與檔案結構

### 3.1 EXT — Chrome MV3 外掛（**與新架構衝突，整體淘汰為產品架構**）

- 型態：`manifest_version 3`；`side_panel` 面板 + 兩支 content script（`bridge.js` isolated world、`main-world.js` `world:"MAIN"`）+ 極簡 `background.js` [C]。
- 權限：`storage sidePanel activeTab scripting`；`host_permissions` 僅 `https://term.ptt.cc/*`；`optional_host_permissions` `http(s)://*/*`（逐站授權抓網址）[C]。
- 儲存：`chrome.storage.local`（`drafts / signatures / settings / schemaVersion`）[C: `src/lib/storage.js`]。
- 規模：`src/` 約 75 KB（`panel.js` 23.8 KB、`main-world.js` 18.3 KB、`checks.js` 10 KB…）；`tests/` 約 80 KB；`tools/` 約 30 KB（靜態檢查、假 BBS、CDP 驅動）[C]。
- 測試檔與 `it/test` 數量（grep 核對）：單元 20+14+5+7 = **46**；整合 20+13+10+10 = **53**；與 TEST_REPORT 宣稱一致 [C]。執行結果「全數通過」為 **[D]**。

```
manifest.json  package.json  README.md  docs/{PHASE0_AUDIT,IMPLEMENTATION_PLAN,TEST_REPORT}.md
src/background.js
src/panel/{panel.html,panel.css,panel.js}          ← 草稿/簽名檔/預覽/複製/填入 UI
src/content/{bridge.js,main-world.js}              ← 存取 term.ptt.cc 頁內 window.app（外掛專屬）
src/lib/{compose,checks,storage,text,big5,hash,extract,url-import}.js
tests/{unit,integration}/…
tools/{check-manifest.mjs, fetch-site-copy.mjs, try-url.mjs, lib/{mock-bbs,cdp,tls,big5-codec}.mjs}
```

### 3.2 GEM — Python 單檔參考實作（SRS v1.3 對應）

- `CODE_GEMINI4.txt`：2,086 行；PySide6 GUI + SQLite + 模擬 Adapter；七個「模組」寫在同一檔 [C]。
- 結構：日誌遮蔽（§1）→ 格式化/URL/編碼/雜湊（§2）→ SQLite Repository + 狀態機（§3）→ 三階段擷取器（§4）→ Adapter 抽象 + `SafePublisherEngine`（§5）→ GUI（§6，約 600 行，2 個分頁：草稿編輯、佇列/UNKNOWN 處置）→ **4 個 pytest 測試**（§7，僅涵蓋 AC-01、02、04、06–08；檔頭卻宣稱「涵蓋 AC-01 ~ AC-18」）[C]。
- **只有 `SimulatedPttAdapter`，沒有任何真實 PTT 連線程式** [C]。
- 資料庫路徑為相對路徑 `ptt_poster.db`（取決於工作目錄；違反 SRS v1.4 NFR-012）[C]。

### 3.3 LOGIN — PttAutoLogin（C# / .NET 9 WinForms，相鄰資產）

- `net9.0-windows` WinForms；Core 專案另引用 `System.Text.Encoding.CodePages`、`ProtectedData`（DPAPI）；測試為 xUnit，共約 77 個 `[Fact]/[Theory]` [C]。
- 已有「透過 `wss://ws.ptt.cc/bbs` 直連 PTT」的實作（`PttWebSocketSession.cs`，Big5 解碼/編碼、不取消進行中的 `ReceiveAsync` 以免連線被標為 Aborted 等實務經驗）與 `PttScreenParser`（以字串 `Contains` 辨識登入畫面、ANSI 剝除）[C]。
- 發行形態：`release\PttAutoLogin.exe` 單檔 113 MB + 同層 `Data\`、`Logs\` 目錄 → **已是「Portable EXE + 同層資料目錄」的實例** [E]。
- **這是自動登入工具**，其 `Data\credentials.dat` 為憑證檔——**本次未讀取**。其定位與「不自動登入」的新決策不同，只作為技術參考，不納入本專案。

### 3.4 本機工具鏈（ENV）[E]

| 工具 | 狀態 |
|------|------|
| Python | 3.12.10 |
| PySide6 | 6.11.2（Essentials/Addons 皆已安裝） |
| PyInstaller | 6.22.2（已安裝）；Nuitka 未安裝 |
| pytest | 9.1.1 |
| 其他 Python 套件 | beautifulsoup4 4.15.0、requests 2.34.2、PyYAML 6.0.3、pywin32 312、opencv-python-headless 5.0.0.93；**未安裝** trafilatura、pywinauto、uiautomation、pyperclip、pyautogui、pytesseract、winsdk |
| .NET SDK | 9.0.317 |
| Node | v24.20.0 |
| 瀏覽器 | Chrome 155、Edge 155 |

結論：Python+PySide6+PyInstaller 與 .NET 9 兩條路在本機**都能立刻開工**；沒有任何一方需要先安裝大型依賴即可做 PoC。

---

## 4. SRS 版本與需求差異

### 4.1 版本盤點

| 版本 | 來源 | 規模 | 狀態 |
|------|------|------|------|
| v1.0 | `PTT_SRS_v1.0.docx`（回收筒） | FR-001–**023**（FR-023 簽名檔插在 FR-004 之後）、NFR-001–010、AC-01–11、6 張資料表 | 初稿；僅 Phase 1–3 清單 |
| v1.1 | **找不到** | — | 任務書所稱基線，無檔案證據 |
| v1.2 | **找不到** | — | v1.3 檔頭「前版」所指，無檔案證據 |
| v1.3 | `PTT_SRS_v1.3.txt` | FR-001–028、NFR-001–010、AC-01–18 | 「定案候選版」；新增 UNKNOWN 人工處置、Draft 來源欄位、控制碼過濾 |
| **v1.4** | `PTT_SRS_v1.4.txt`（另有 Downloads 副本） | FR-001–**030**、NFR-001–**012**、AC-01–**32**（含 12A/12B）、§14 追溯矩陣 | **「需求基線定案候選版」，§13 仍列 8 項核准條件未滿足** |

v1.0、v1.3、v1.4 檔內日期**全是 2026-10-14**（同日連續修訂）。任務書「FR-001 至 FR-022」是 v1.0 範圍的舊稱（v1.0 實際已含 FR-023）。

### 4.2 版本間重要差異

| 主題 | v1.0 | v1.3 | v1.4 |
|------|------|------|------|
| 簽名檔 | FR-023 P0，要求「變更後須重新確認」 | 同左 | 四級優先順序（草稿→看板→模板→全域）、快照時機、INLINE/SERVER_SLOT 列 PoC、`--` 分隔線豁免、刪除限制 |
| 個人心得 | 無獨立需求（僅 Draft 欄位） | FR-024 | FR-024 + `min_notes_length` NULL/0 語意（AC-10） |
| 看板配額 | 無 | FR-025 P1 | 時區、UNKNOWN 計入、模擬排除 |
| 發文結果驗證 | FR-013：連線中斷標「結果未明」 | FR-013 + UNKNOWN 人工處置閉環（FR-027） | 證據等級 E1/E2/M、write-ahead 階段表、**安全判定線 `safe_stage_boundary`**、CAS 狀態轉移（§8.3 T1–T15） |
| 遠端重複檢查 | 無 | FR-028 **P2** | FR-028 **P0 閘門**（`REMOTE_DUP_CHECK` 階段；後備 CHECKLIST_FALLBACK） |
| 其他新增 | — | 控制碼過濾、單行 `--` 警告 | FR-029 重發保護、FR-030 模擬模式、NFR-011 單一執行個體、NFR-012 資料位置、JobEvent 稽核表、ON DELETE RESTRICT、§7.11 參數表 |
| 可攜式 EXE | §11「待確認」 | §12 待決 | §12 待決；NFR-012 預設 `%APPDATA%`，可攜式「須由使用者明確啟用」 |

### 4.3 互相衝突或已過時之處

1. **標題上限三種數字並存**：SRS v1.4 / GEM = **42 bytes**（且註明含分類框待 PoC）；EXT `checks.js` = **64 bytes**（假設 A6）。**皆未驗證 → 待實測**。
2. **行寬**：SRS 76（換行）/78（檢查）；GEM 換行 76、檢查 78；EXT 78；站台前端有「建議 78 字元」文案 [S]。
3. **編碼**：SRS v1.4 FR-008 要求 Big5-UAO 且「cp950 不等同 UAO，不得預設採用」；GEM 全部用 `cp950` [C]；EXT 用站台自己的 `u2bTable`（外掛專屬）+ 瀏覽器 big5 解碼「估算」[D]。
4. **GEM 是 v1.3 實作**，v1.4 §摘要第二段明說其新增內容來自「v1.3 參考實作審查發現」——即 v1.4 已預期 GEM 有缺陷（見 §5 備註）。
5. **v1.4 §12 待決事項** 12（簽名檔看板/模板優先序）、13（UNKNOWN 阻擋範圍）、14（確認有效期 24h）使用者尚未回覆。
6. **v1.4 與新決策衝突**（最大一組）：見附錄 A。

### 4.4 任務書指定項目是否已納入 SRS

| 項目 | v1.4 是否納入 | 備註 |
|------|---------------|------|
| 簽名檔 | ✅ FR-023、AC-09 | 投遞方式待 PoC |
| 個人心得 | ✅ FR-024、AC-10 | |
| 看板配額 | ✅ FR-025（P1） | 受「本機歷史不完整」限制 |
| 發文結果驗證 | ✅ FR-013／027 | **與新決策衝突，需重寫** |
| 看板「搜尋」 | ⚠️ 僅「輸入名稱或從已保存清單選擇」（FR-005） | 任務書期待的「PTT 看板搜尋」沒有遠端搜尋來源 → 需決策 D-09 |
| Windows UI 自動輸入 / 剪貼簿雙模式 | ❌ 完全沒有 | v1.4 只有「Adapter 登入發文」模型 |
| Portable EXE | ⚠️ 僅列待決與 NFR-012 | |

---

## 5. 功能完成度矩陣

分類：✅ 已完成（有程式碼＋測試佐證）｜🟡 部分完成｜⬜ 尚未實作｜🐞 存在缺陷｜❓ 無法確認｜⛔ 與新架構衝突。
「佐證」皆為 [C]；測試是否通過為 [D]。

### 5.1 任務書 §4 十三項預期功能

| # | 功能 | EXT（外掛） | GEM（Python 參考） | 新架構下判定 |
|---|------|-------------|--------------------|--------------|
| 1 | 文章 URL 輸入與資料擷取 | ✅ `normalizeUrl`（`extract.js:8`）、`importFromUrl`（`url-import.js:47`），5 單元 + 10 整合；但只在 3 個真實網站試跑 [D] | 🐞 `validate_and_canonicalize_url`（:116）：query 不排序、不處理預設 port／userinfo、要求網域含 `.`、`urlparse` 對畸形 IPv6 會拋例外 [推論] | 🟡 邏輯可重用；需依 v1.4 FR-001 重寫並補測試 |
| 2 | 新聞與 PTT 來源解析 | 🟡 DOM 啟發式 + `og:title/site_name`；**無 JSON-LD、無站台規則、無作者／日期、無 robots.txt** | 🐞 三階段（JSON-LD/OG→YAML→trafilatura）設計對；但 UA 偽裝成 Chrome/128（:1212，v1.4 禁止）、cna 規則 `author_selector` 指向正文首段（v1.4 明令禁止）、`fetch_url` 只有逾時（:1207）、無大小/重新導向上限 | 🟡 以 GEM 的三階段架構為藍本、EXT 的 PTT 網頁版與編碼測試案例為資產，重寫 |
| 3 | 標題／來源／來源連結／記者編譯者／內文 | 🟡 只有標題、內文、`sourceUrl`、站名；**沒有記者欄位** | 🟡 Draft 有 `draft_source_site/author/published_at/url`，渲染模板含 6 欄 [C:render_draft_payload] | 🟡 資料模型取 GEM／SRS v1.4 |
| 4 | 個人心得與手動修改 | ⬜ 草稿模型無「心得」欄位 | 🟡 `author_notes` + `min_notes_length`（NULL=未知）[C]；僅 AC-04 一個測試涉及 | 🟡 |
| 5 | PTT 看板搜尋／選擇／板規檢查 | ⬜ 無看板概念 | 🐞 有 `BoardConfig`；**但種子資料預填 Stock／Gossiping 的心得字數、每日上限、冷卻**（:543,548）——違反 v1.4 FR-005「不得預填未經驗證板規」；GUI 下拉為寫死清單（:1566） | ⬜／🐞 需重做；「搜尋」無資料來源（D-09） |
| 6 | 多組簽名檔管理 | ✅ CRUD、全域預設、單篇指定/不使用、快照（`compose.js`，14 單元 + 面板測試）；**缺：看板/模板預設層級** | 🟡 簽名檔 CRUD + 單一預設索引 [C]；`resolve_signature_text` 未逐項審 | ✅／🟡 EXT 的 `compose.js` 邏輯最完整，可移植 |
| 7 | 格式、編碼、長度、必填檢查 | ✅ `checks.js`（20 單元）涵蓋控制字元、不可編碼（估算）、超寬、重複簽名分隔、預覽一致；標題上限 64 為假設 | 🐞 不可編碼字元只是**警告**（:349）；僅移除控制字元、**不移除完整 ANSI 序列**（留下 `[31m` 殘字）；用 cp950 | 🟡 以 v1.4 FR-003/008 規則重寫；EXT 的測試案例是好資產 |
| 8 | 發文前完整預覽＋人工確認 | ✅ 預覽＝複製＝填入（雜湊串接）[D]；**沒有「確認」狀態／確認雜湊** | 🟡 `confirm_draft_and_enqueue`（:821）寫入雜湊，但**不驗證草稿通過檢查**才可確認 | 🟡 |
| 9 | 剪貼簿複製貼上模式 | ✅ 複製整篇／標題／內文，複製內容＝預覽（面板測試）[D] | ⬜ 無（GUI 沒有複製功能；以 `QClipboard` 關鍵字 grep 無結果） | 🟡 概念可沿用；需在桌面端重做（見 IMPLEMENTATION_PLAN §5） |
| 10 | Windows UI 自動輸入模式 | ⛔ 外掛內以 `window.app.send` 填入（EXPERIMENTAL，僅假 BBS 驗證）；**靠頁內介面，換成桌面程式後完全不可用** | ⬜ 無 | ⬜ **全新工作**，且可行性取決於 PoC（§8） |
| 11 | 草稿、文章佇列、歷史紀錄 | 🟡 草稿 ✅；**無佇列、無歷史** | 🟡 `QueueJob/PostRecord` 表與 GUI 佇列分頁存在；無 `JobEvent`、無 CAS | 🟡 佇列語意需重定義（D-08） |
| 12 | 發文結果驗證／重複發文風控／錯誤處理 | ⬜（外掛不判定結果；以「已交給連線」措辭規避） | ⛔🐞 `SafePublisherEngine.execute_job`（:1294）：Python 先讀狀態再 `UPDATE … WHERE job_id`（**無 CAS**，並發可重入）；階段由 Adapter「結束時一次回報」（非 write-ahead）；只有 4 個階段名；`FAILED_SAFE_TO_RETRY` 可直接重跑，**未要求重新確認**；只有模擬 Adapter | ⛔ 整組以「自動送出」為前提，需依新決策重寫（見 IMPLEMENTATION_PLAN §2） |
| 13 | Portable EXE 與本機資料管理 | ⬜ 外掛無 EXE | ⬜ 無打包；DB 路徑相對 cwd；無單一執行個體、無 WAL、無備份 | ⬜ |

### 5.2 SRS v1.4 其他需求盤點（任務書要求「不得只檢查以上清單」）

| 需求 | EXT | GEM | 備註 |
|------|-----|-----|------|
| FR-009 本機重複檢查 | ⬜ | 🟡 `check_local_duplicates`（:649，未逐項審） | |
| FR-010 佇列／並發保護 | ⬜ | 🐞 有部分唯一索引 `idx_active_job_per_draft`（:490）但無全域單一 SUBMITTING、無 CAS | 新架構下大幅簡化 |
| FR-012 確認雜湊與快照 | 🟡 內容雜湊串預覽/填入；無不可變快照 | 🟡 雜湊 JSON 序列化版本 `"v1.3"`；無 `target_payload_text` 快照 | |
| FR-016 日誌遮蔽 | ⬜（外掛不寫日誌） | 🟡 `SensitiveDataFilter` 只遮蔽一組正則（:37-60）；未涵蓋 Authorization/多值 Cookie/堆疊 | |
| FR-017 帳號與連線 | ⛔ | ⛔ 無真實連線 | 新決策：不自動登入 → 本需求整組移出 MVP |
| FR-018/022 備份、匯出 | ⬜ | ⬜ | |
| FR-023 簽名檔 | 見 5.1 #6 | | |
| FR-025 配額 | ⬜ | 🐞 有 `check_quota_and_cooldown`（:866），依寫死的種子數值 | |
| FR-027 UNKNOWN 人工處置 | ⬜ | 🟡 `resolve_unknown_job_manually`（:923）+ 對話框 | 語意需重定義 |
| FR-028 遠端重複檢查 | ⬜ | ⬜（只有 `verify_remote_post` 抽象方法） | ⛔ 需讀看板 → 與新決策衝突 |
| FR-029/030 重發保護、模擬模式 | ⬜ | 🟡（僅 Simulated Adapter，無 UI 標示） | 模擬/假終端機概念**仍適用**（測試必須不造成真實發文） |
| NFR-011 單一執行個體 | ⬜ | ⬜ | |
| NFR-012 資料位置 | ⬜ | 🐞 相對路徑 | |

### 5.3 GEM 缺陷小結（對照 SRS v1.4，皆為靜態閱讀）

編碼用 cp950 而非 UAO；不可編碼字元僅警告；ANSI 序列未整段移除；URL canonicalization 不完整；UA 偽裝；作者選擇器取正文；預填未驗證板規；無 CAS／write-ahead／JobEvent／單一執行個體／WAL；DB 路徑依 cwd；測試僅 4 個卻宣稱涵蓋 AC-01–18。**結論：GEM 適合作為「設計草稿與資料表藍本」，不適合作為可直接擴充的程式基底。**

---

## 6. 現有可重用模組

| 來源 | 模組 | 可重用度 | 說明 |
|------|------|----------|------|
| EXT | `src/lib/compose.js`（簽名檔解析、快照、組合）＋ `tests/unit/compose.test.js`（14） | 高（**移植邏輯與測試案例**，非程式碼） | 規則完整且測試密度高 |
| EXT | `src/lib/checks.js`＋`checks.test.js`（20） | 中高 | 檢查項目清單與邊界案例可直接成為 pytest 案例；數值（64 B）需更新 |
| EXT | `src/lib/text.js`（顯示寬度、控制字元／不可見字元正則） | 中 | 規則可移植；EXT 的 `FORBIDDEN_CONTROL_RE` 涵蓋 C1，比 GEM 完整 |
| EXT | `src/lib/extract.js`、`url-import.js` 與 `import.test.mjs` 夾具 | 中 | 解碼優先順序（標頭>meta>預設）、PTT 網頁版、5 MB/15 s 限制、「僅 GET、不帶 Cookie/Referer」設計值得保留；**HTML 夾具可直接當 pytest 資料** |
| EXT | `tools/lib/mock-bbs.mjs`、`tls.mjs`、`cdp.mjs` | 中（僅測試用途） | 以真實站台 bundle + 假 BBS 驗證的做法，可用於 Mode B 的**安全實測**（不連真實 PTT）；Node 工具與 Python 專案並存的成本需評估 |
| EXT | `tools/check-manifest.mjs`（靜態禁止送出按鍵路徑） | 概念可重用 | 新專案需要同類「靜態安全檢查」（見計畫 §7） |
| EXT | `docs/PHASE0_AUDIT.md` F1–F18／A1–A8／R1–R12 | 高（知識資產） | 已併入本報告 §9 |
| GEM | `SCHEMA_SQL` 資料表與索引（:390–520） | 中（藍本） | 需依 v1.4 補 CHECK、JobEvent、ON DELETE RESTRICT |
| GEM | 三階段擷取器結構、YAML 站台規則格式 | 中（藍本） | 修正 UA、作者選擇器、限制後可用 |
| GEM | PySide6 GUI（`BackgroundTask`/`WorkerSignals` 執行緒模式，:1425–1445） | 中低 | 單檔 600 行 GUI，需拆分；執行緒模式可參考 |
| GEM | `SimulatedPttAdapter` | 概念可重用 | 對應新架構的「假終端機／假 Delivery」 |
| LOGIN | Portable 慣例（單檔 EXE + 同層 `Data\`、`Logs\`）、`FileLogger`、xUnit 結構、`PttWebSocketSession` 的實務註解 | 僅在選 C#／.NET 路線時直接可用 | 否則只作經驗參考；其自動登入功能**不納入** |

---

## 7. 不使用瀏覽器外掛的架構影響

取消外掛後失去的能力（**都是舊外掛能安全填入的根本原因**）：

| 外掛提供 | 桌面程式（無外掛）下的狀況 |
|----------|----------------------------|
| 讀取頁內 `window.app.buf`（`getRowText`、`cur_x/y`、`connectState`）取得**精確畫面文字** [D/S] | **沒有**。畫面預設用 Canvas 繪製，文字不在 DOM，UI Automation 也讀不到 [S]。狀態辨識只能靠截圖＋OCR/模板比對，或要求使用者切成 DOM 渲染模式（待實測） |
| `isEditingScreen` 等站台內建狀態判斷 | 無；需自建 |
| 直接呼叫 `app.send` 並以 `rawSend` 事件**計算實際交給 WebSocket 的位元組** | 無；只能送出鍵盤／貼上事件，**無法確認送達內容** |
| `window.lib.u2bTable`（站台權威的可編碼字元表） | 無；需自備 Big5-UAO 對照表（來源與授權待查，決策 D-10） |
| 前景分頁偵測（`document.hidden`） | 改為視窗前景/最小化偵測（Win32） |
| 不走貼上路徑，避開「78 字元自動換行」外掛改寫 [S] | **若用貼上／輸入就會走該路徑**（外掛預設啟用，待實測是否仍會改寫） |
| `chrome.storage.local` 儲存 | 改 SQLite（§10） |

**結論：**
- 「**內容準備**」（擷取、草稿、簽名檔、檢查、預覽、複製）完全不依賴外掛，可 100% 移到桌面程式。
- 「**終端機填入**」的**安全性大幅下降**：從「能讀畫面、能計算送出位元組」退化為「盲送鍵盤事件＋影像辨識」。因此 Mode B 必須被視為**高風險、待 PoC 驗證**的功能，且不得成為 MVP 的阻塞項（兩模式可獨立啟用，任務書 §2.3 已要求）。
- 外掛時期所有「頁內」測試（`terminal.test.mjs` 20 項、`e2e.test.mjs` 10 項）的**結論不能直接套用**到 Mode B；它們驗證的是「外掛 ↔ 站台前端」，不是「桌面程式 ↔ 視窗」。

---

## 8. 剪貼簿與 Windows UI 自動輸入：可行性與風險

> 共同前提：**程式碼層級不得存在任何「送出／存檔／離開編輯器」的操作**（`Ctrl+X`、`Ctrl+Q`、編輯器外的 `Enter`、存檔確認 `S`/`Y` 等）。UI 自動輸入只代表「把內容填入編輯流程」。

### 8.1 Mode A — 剪貼簿

| 面向 | 評估 |
|------|------|
| 可行性 | **高**。Qt `QClipboard` 即可；不需任何 UI 自動化 |
| 使用者流程 | 程式整理好 → 按「複製標題／複製內文」→ 使用者自行切到 `term.ptt.cc` 貼上 → 自行存檔發文 |
| 提示 | 狀態列提示「已複製（N 字元／M bytes）」，**不彈窗、不搶焦點**（SRS NFR-010）；提供「貼上前請確認在『標題』提示／空白編輯畫面」的步驟說明 |
| 主要風險 | ① **站台貼上路徑會改寫文字**：換行轉 `\r`、「長文自動換行」外掛預設啟用且每行 78 字元（舊稽核 [源碼]；bundle SHA 與舊稽核相同，結論適用本版，**待實測**真實行為）；② **無法編碼字元被靜默替換**為 `¡¼`（同上）→ 複製前**必須**用同一套規則檢查並阻擋；③ 貼上的控制字元可能觸發編輯器快捷鍵 → 與 FR-008 相同的攔截；④ Windows 剪貼簿歷史（Win+V）／雲端剪貼簿同步可能留下文章內容 → 需評估設定「排除於剪貼簿歷史／不上傳雲端」的剪貼簿格式（待實測）；⑤ 使用者在複製後又複製了別的東西 → 貼上前無從得知（可提供「再次複製」與可選的自動清除） |
| 不確定項（待實測，需真實 PTT） | 長文貼上是否掉字（站台以 512 字元分塊、15 ms 間隔 [S 舊稽核]）；編輯器對超寬行的折行（A5）；標題長度上限（A6） |
| 評估 | **MVP 必選**。風險集中在「內容檢查要和實際行為一致」，而非技術難度 |

### 8.2 Mode B — Windows UI 自動輸入

| 面向 | 評估 |
|------|------|
| 可行性 | **條件可行，結論待 PoC。** 「送出鍵盤／貼上」本身技術上可行（`SendInput`、`SetForegroundWindow`）；**難點是「確認目前畫面狀態」與「確認送達」**。 |
| 視窗辨識 | 以 Win32 列舉頂層視窗：行程為 `chrome.exe`/`msedge.exe`/`firefox.exe`，且標題含「批踢踢實業坊」[S: index.html `<title>`]。**注意**：①標題是「作用中分頁」的標題，使用者切分頁標題就變；② 站台收到 bell 時會把標題改為 `🔔 ` 前綴（bundle 內 `document.title=` 邏輯 [S]）→ 比對須容許前綴；③ 多視窗／多 profile／PWA 安裝版視窗皆可能；④ 若使用者以系統管理員身分執行瀏覽器，一般權限程式的 `SendInput` 會被 UIPI 擋下（待實測） |
| 焦點控制 | 每次動作前驗證 `GetForegroundWindow()` 為目標 hwnd 且標題符合；失焦即停。**風險：內容誤打到其他應用程式**（聊天室、郵件…）。Mode B 的首要安全設計是把「打字」次數壓到最少（優先一次貼上）而不是逐字打 |
| 狀態辨識（最難） | 站台預設 Canvas 渲染 [S: `useCanvasEngine:!0`]，文字不在 DOM。可能做法：**(a)** 截圖（Windows Graphics Capture／`PrintWindow`）＋ OCR（Windows.Media.Ocr 需語言套件，或 OpenCV 模板比對——本機已有 opencv-python-headless）辨識最後一列的「編輯文章」狀態列；**(b)** 要求使用者在站台設定關閉「以 HTML5 Canvas 技術繪製畫面」（設定項存在 [S]），改 DOM 渲染後以 UI Automation 讀文字（Chrome 需啟用無障礙樹；待實測）；**(c)** 不辨識，改成「程式提示、使用者確認畫面，再由使用者觸發單次貼上」。三者可靠度皆**待實測**；影像法受字型、縮放、DPI、配色、反鋸齒影響，需校準 |
| 輸入方式比較 | **貼上（Ctrl+V）**：快、一次動作，但走站台貼上路徑（自動換行外掛改寫、剪貼簿被佔用）；**SendInput Unicode 逐字**：慢、受輸入法影響、與站台隱藏 `<input>` 的 `compositionend` 路徑互動未知（待實測）、期間焦點變動風險高；**分行貼上**：折衷，每行之間可重驗狀態。皆待實測 |
| 送達確認 | **無法精確確認**（見 §7）。只能事後截圖比對畫面尾段（輔助證據，不得當作成功證明）。失敗／不明 → 停止並要求使用者目視核實，**不重送** |
| 其他風險 | 延遲與斷線（逾時、`連線中斷`）；使用者在填入中操作滑鼠鍵盤（需偵測使用者輸入或提供全域中止熱鍵）；防毒／EDR 對 `SendInput` 自動化程式的誤判；PyInstaller 未簽章 EXE 的 SmartScreen 警告；螢幕保護／鎖定畫面；DPI 縮放與多螢幕座標 |
| 其他途徑（**需使用者決策，不屬「使用者已開啟的視窗」字面定義**） | **CDP／遠端偵錯**：能讀頁內狀態，但需以 `--remote-debugging-port` 另行啟動瀏覽器（Chrome 新版對預設設定檔限制此參數，待實測），且與「使用者已自行登入的視窗」衝突；**內嵌 WebView2／QtWebEngine 載入 term.ptt.cc**：取得 DOM/JS 存取且不是外掛，但那是程式自己的視窗，使用者需在其中登入（獨立 profile、密碼管理員不共用）。兩者技術上更可靠，是否符合需求由使用者決定（D-02） |
| 評估 | **Mode B 不應進 MVP 主線。** 先以 PoC 驗證「狀態辨識是否可靠」；PoC 未通過 → 降級為「輔助貼上」（程式只把內容放進剪貼簿並顯示逐步指引，等同 Mode A 增強） |

### 8.3 兩模式的共同安全底線（寫入驗收條件）

1. 兩模式共用**同一個**渲染／檢查／雜湊函式；複製與填入的內容 = 預覽內容（位元組一致）。
2. 不存在可送出「存檔／離開／確認」按鍵的函式；以靜態檢查把關。
3. 狀態不明、失焦、逾時、斷線 → 立即停止；不自動重試、不自動重送。
4. 任何「結果不明」→ 草稿標記需人工核實，不能直接再填一次同一篇。
5. 測試一律使用本機假終端機／假視窗，不連真實 PTT、不發文。

---

## 9. PTT 操作可行性（唯讀觀察）

### 9.1 本次唯讀觀察（HTTP GET，無登入、無 WebSocket、無表單）

| 觀察 | 結果 |
|------|------|
| `GET https://term.ptt.cc/`（200，`last-modified 2026-10-03`） | `index.html` SHA-256 `27827442f8750c18…0c092d`，**與舊稽核記錄的 `0f97c9b9…` 不同**；引用 `assets/index-WD38Ce5v.js` 與 `assets/index-CAhZmilb.css` |
| `GET /assets/index-WD38Ce5v.js` | 571,809 bytes，SHA-256 `cf0c9607…6766271`，**與舊稽核完全相同** → 舊稽核對此 bundle 的靜態結論仍適用。入口檔變動原因未知（CSS 檔名雜湊可能不同），列為待釐清 |
| 重驗點 | ① 存在 `isEditingScreen` 判斷；② `useCanvasEngine` 預設 `!0`（true），且有關閉渲染的設定文案；③ `new WebSocket(e,'telnet')`；④ 站台文案含「建議行長 78 字元（送出時自動換行）」「Max N / 78 B」；⑤ `rawSend`、`_sendQueue`、4096 緩衝流量控制、20 ms 等待 |
| 頁面標題 | `<title>批踢踢實業坊</title>`；會有 `🔔 ` 前綴 |

### 9.2 沿用舊稽核的事實（[源碼]，同 bundle；本次未逐條重驗）

F2 Canvas 渲染、F6 編輯畫面狀態列字串、F9 512 字元分塊／15 ms／連線非 OPEN 即清空佇列不重送、F11 **不可編碼字元靜默替換為 `¡¼`（高代理被丟棄）**、F13 貼上轉 `\r` 且「長文自動換行」外掛預設每行 78 字元、F14 輸入攔截外掛。以上對 **Mode A 的貼上路徑**直接相關。

### 9.3 仍屬「待實測」（需真實 PTT；本階段不得做）

登入狀態辨識文字、編輯畫面狀態列實際字串（A1）、標題提示列位置（A2）、長文是否吞字（A3）、實際編碼是否為 Big5-UAO（A4）、編輯器折行行為（A5）、標題長度上限與是否含分類框（A6）、存檔時簽名檔提示（決定 INLINE／SERVER_SLOT）、各階段斷線後伺服器是否保留草稿（決定「安全判定線」）、發文後如何取得 AID／文章識別、看板規則與發文頻率限制。

**這些全部沒有證據，不得寫成已確認。** 建議在 Phase 2 由使用者以測試看板＋非主帳號、手動輔助完成（計畫 §9）。

### 9.4 不使用外掛時各操作方式的限制摘要

| 方式 | 讀畫面 | 精確送達確認 | 符合「用使用者已開啟視窗」 | 自動登入 |
|------|--------|--------------|----------------------------|----------|
| 剪貼簿（A） | 否 | 否（使用者目視） | 是（使用者自貼） | 否 |
| UI 自動輸入（B） | 僅影像／UIA（待實測） | 否 | 是 | 否 |
| CDP | 是 | 部分 | 否（需特殊啟動） | 否 |
| 內嵌 WebView | 是 | 是 | 否（程式自有視窗） | 否 |
| 直連 `wss://ws.ptt.cc/bbs`（LOGIN 的做法） | 是（自建終端機模擬） | 是 | 否 | **是（與新決策衝突）** |

---

## 10. Portable EXE 與資料儲存風險

### 10.1 封裝方式評估（皆未建置）

| 項目 | Python + PySide6 + PyInstaller | C# / .NET 9（self-contained 單檔） |
|------|-------------------------------|-----------------------------------|
| 本機可立即開工 | ✅（PySide6 6.11.2、PyInstaller 6.22.2、pytest 已安裝）[E] | ✅（SDK 9.0.317）[E] |
| 體積 | 約 100–200 MB 量級（待實測；PySide6 本身很大） | LOGIN 實例 113 MB [E] |
| 單檔行為 | `--onefile` 啟動時解壓到 `%TEMP%`，啟動慢、易被防毒誤判；**`__file__` 指向暫存目錄，資料路徑必須改用 `sys.executable` 所在目錄** | 單檔同樣會解壓原生程式庫（視設定）；以 `AppContext.BaseDirectory`/`Environment.ProcessPath` |
| 建議形態 | **one-folder（exe + `_internal` + `data\`），整包壓縮 zip 發行**（「免安裝」成立，啟動較快、誤判較少）；one-file 可作為次選 | 單檔 EXE + 同層 `Data\`（LOGIN 已採用） |
| 與既有技術棧相容（組織規範：優先考量 C#/MSSQL 相容） | 與既有 C# 工具為兩套技術棧 | **與既有 PttAutoLogin 同棧**，且 Windows 自動化（`SendInput`、UI Automation、`Windows.Media.Ocr`、WebView2）為一級公民 |
| 擷取能力 | `beautifulsoup4`、`trafilatura`（未安裝）成熟 | AngleSharp/HtmlAgilityPack 等；正文抽取庫較少（待評估） |

兩者都可行；**這是需要使用者拍板的決策（D-01）**。我的傾向見 IMPLEMENTATION_PLAN §1。

### 10.2 SQLite 是否適合

**適合**：單使用者、資料量小、需交易與唯一索引（SRS 的「同草稿僅一個未結案工作」等）、Python（`sqlite3`）與 .NET（`Microsoft.Data.Sqlite`）皆原生支援。需注意：

- 資料庫放在 USB／網路磁碟時，**WAL 模式不可靠**（需共享記憶體）；偵測非本機磁碟時改用 `journal_mode=DELETE`。
- 隨身碟意外拔除 → 損毀風險；需啟動時 `PRAGMA integrity_check`（可略過大庫）與滾動備份。
- 組織提到 MS SQL Server：本專案為**單機單使用者**，引入 SQL Server 無必要；僅在未來若要多人共用才需評估。

### 10.3 Portable 模式風險清單

| # | 風險 | 對策（計畫 §8） |
|---|------|----------------|
| P1 | 程式放在無寫入權限的位置（Program Files、唯讀光碟） | 啟動寫入測試；失敗則提示並退回 `%LOCALAPPDATA%\<App>\` 並在 UI 顯示實際位置 |
| P2 | SRS NFR-012 預設資料在 `%APPDATA%`、可攜式「須明確啟用」；任務書要求 Portable → **預設值衝突** | 決策 D-03：建議以「exe 同層 `data\` 為預設」並於 SRS v1.5 修訂 |
| P3 | 單一執行個體：同一資料目錄被兩個程序（含不同電腦的隨身碟）開啟 | `QLockFile`／命名 mutex ＋ 資料目錄內鎖檔（含 PID、主機名、時間，偵測殘留鎖） |
| P4 | 升級：新版 exe 覆蓋舊版，schema 變更 | `schema_version` + 遷移腳本；**遷移前自動備份 DB**；拒絕開啟「比自己新」的 schema |
| P5 | 備份／還原／匯出 | 備份＝整個 `data\`（DB 用 SQLite backup API，避免複製半寫入檔）；備份**不含**憑證（本設計根本不存） |
| P6 | 日誌遮蔽與診斷 | 滾動日誌；遮蔽規則取 v1.4 FR-016 清單；提供「匯出診斷包」（去識別化） |
| P7 | 殺毒／SmartScreen | 發行說明、雜湊值公告；有無程式碼簽章憑證待決（D-11） |
| P8 | 資料目錄放在雲端同步資料夾（OneDrive）造成 DB 鎖定／衝突 | 偵測並警告 |
| P9 | 內容外洩：草稿含未發表內容、剪貼簿歷史 | 見 §8.1 ④ |

### 10.4 「發文佇列／重複／結果不明」在新架構下的意義

程式**不會自動送出**，因此：
- 「佇列」＝使用者排好順序、人工逐篇處理的待發清單，不是會自動執行的工作；
- 「結果不明」＝**填入過程被中斷，或使用者回報不確定是否已發**；唯一出口是人工核實（SRS 的途徑 B/C/D 保留精神、移除 `SUBMITTING`／CAS／階段表）；
- 重複內容辨識：本機（URL 正規化、標題、內容指紋）保留；**遠端看板檢查**（FR-028）因需操作終端機而改為「人工核對清單」。

---

## 11. 尚未確認的問題（摘要；完整決策清單見 IMPLEMENTATION_PLAN §10）

| ID | 問題 | 類型 |
|----|------|------|
| D-00 | 回收筒中的原專案與 SRS 是否為有意刪除？是否還原／搬回新目錄？ | **阻塞性** |
| D-01 | 技術棧：Python+PySide6 或 C#/.NET 9？ | 決策 |
| D-02 | Mode B 技術路線：SendInput＋影像／UIA，或 CDP／內嵌 WebView（不符字面定義）？ | 決策 |
| D-03 | Portable 資料位置預設值與無法寫入時的退路 | 決策 |
| D-04 | 是否核准另出 SRS v1.5（依新決策重寫 FR-013/015/017/027/028、8.2/8.3） | 決策 |
| D-05 | v1.1／v1.2 是否存在於其他位置 | 事實釐清 |
| D-06 | 是否同意由使用者在真實 PTT（測試看板、非主帳號）人工協助 PoC（A1–A6、簽名檔、安全判定線） | 授權 |
| D-07 | 標題上限、行寬、編碼的最終數值 | 待實測 |
| D-08 | 「佇列」語意（人工逐篇處理清單？） | 決策 |
| D-09 | 看板「搜尋」的資料來源（本機清單？使用者匯入？） | 決策 |
| D-10 | Big5-UAO 對照表的來源與授權 | 待查 |
| D-11 | 程式碼簽章、防毒誤判的處理 | 決策 |
| — | 站台 `index.html` 雜湊與舊稽核不同的原因 | 待釐清 |
| — | SRS v1.4 §12 的 12、13、14 三項待使用者回覆（簽名檔優先序、UNKNOWN 阻擋範圍、確認有效期） | 待回覆 |

---

## 12. 建議處理優先順序

1. **D-00**：確認回收筒內容是否保留（最便宜、風險最高：回收筒被清空即永久遺失所有規格與舊成果）。
2. **D-01／D-02／D-03**：技術棧、Mode B 路線、Portable 預設——決定後 Phase 1 才能開工。
3. **SRS v1.5 修訂**（D-04）：先釐清需求再寫程式，否則會重蹈「GEM 依舊規格寫出自動發文引擎」的覆轍。
4. **Phase 1 MVP（Mode A + 內容準備 + Portable 封裝）**，不含 Mode B。
5. **Phase 2 PoC：真實 PTT 人工輔助觀察 + Mode B 狀態辨識 PoC**（先對本機假終端機，再由使用者在測試看板確認）。
6. Mode B 依 PoC 結果決定是否納入；否則降級為輔助貼上。

---

## 附錄 A：SRS v1.4 與新架構決策的衝突清單

| SRS v1.4 項目 | 與新決策的衝突 | 建議處置（v1.5） |
|---------------|----------------|------------------|
| FR-013、§8.2 送出階段表（含 `SAVE_COMMAND_SENT`）、`safe_stage_boundary` | 程式不得自動存檔／發文 | 改為「填入階段」記錄（write-ahead 保留以偵測中斷），結果一律由使用者回報 |
| FR-010 SUBMITTING 狀態、NFR-011 CAS、單一 SUBMITTING | 無自動送出 → 無需 | 精簡為單一執行個體鎖 + 草稿層級重複填入保護 |
| FR-017 帳號與連線、Credential Manager、重複登入詢問 | 不自動登入、Mode B 只操作使用者已登入視窗 | 移出 MVP；不儲存任何憑證 |
| FR-028 發文前遠端重複檢查（Adapter 讀看板） | 需操作終端機瀏覽看板 | 預設 `CHECKLIST_FALLBACK`（v1.4 已有）+ 本機檢查 |
| FR-027 途徑 A（遠端自動核對） | 同上 | 移出 |
| FR-030 Adapter 標示／模擬 | 方向相容 | 改為「Delivery 模式標示＋假終端機測試模式」 |
| NFR-012 預設 `%APPDATA%` | Portable 需求 | 預設 exe 同層（D-03） |
| §11 技術架構（Python/PySide6/SQLite、「PTT Adapter」） | 未含雙模式 | 以「Delivery（Clipboard／UiAutomation）」取代「Adapter」 |
| AC-07、08、20、23、28、29、32 | 以自動發文為前提 | 重寫；其餘（AC-01–06、09–12、16–19、24–27、31）大多可沿用 |

## 附錄 B：本次稽核的操作紀錄與唯讀遵守聲明

- 讀取：回收筒內 EXT／SRS／GEM、`D:\Claude\PTTLOGIN\src`（僅原始碼與目錄清單；**未讀取** `credentials.dat` 與日誌內容）、Windows 回收筒 `$I*` 中繼資料。
- 執行的指令皆為唯讀：`ls`/`find`/`grep`/`wc`、`git --no-optional-locks status|log|branch|stash list|rev-parse`（對回收筒內儲存庫，未寫入索引）、`python --version`、`pip list`、`dotnet --list-sdks`、`node --version`。
- 以 Python（`-I` 隔離模式）把 SRS v1.0 docx 解壓為純文字，輸出寫到 `%TEMP%\srs_v10_extract.txt`；對 `term.ptt.cc` 的兩次 HTTP GET（`index.html`、`index-WD38Ce5v.js`）輸出到 `%TEMP%`／`/tmp`。**這些是專案目錄以外的暫存檔，已於報告完成後清除。**
- 在專案目錄**唯一的寫入**：新增 `D:\Claude\PTTAUTOPOST\docs\` 與本報告、`IMPLEMENTATION_PLAN.md`。
- 未執行：任何測試、建置、安裝、PTT 連線、登入、發文、對已開啟視窗的操作。
