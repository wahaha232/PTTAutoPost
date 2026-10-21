# PTT AutoPost 架構設計

- 版本：**1.1-draft**（對應 SRS 2.0-draft r3；已納入使用者 2026-10-15 五項決策）；**待使用者審核**
- 日期：2026-10-15
- 性質：設計文件。**未撰寫任何應用程式原始碼、未安裝依賴、未建置**；文中所列程式庫、數值皆為候選或暫定，凡未驗證者標【待驗證】V-xx／【待確認】Q-xx（定義見 [SRS.md](SRS.md) §10–11）。**目前沒有任何功能已實作或已驗證。**
- 相關：[SRS.md](SRS.md)、[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)、[ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md)、[TEST_CORPUS.md](TEST_CORPUS.md)、[GOLDEN_SPEC.md](GOLDEN_SPEC.md)、[PYTHON_BASELINE_AUDIT.md](PYTHON_BASELINE_AUDIT.md)
- **r1.1 變更**：①技術棧決議為 **Python 基線**，並依 PYTHON_BASELINE_AUDIT **沿用使用者既有專案設計**（§2、§4、§12、§15）；②M1 簽名檔改為單一全域文字欄位（§5、§10）；③快照與黃金檔規範（§15.2）。

---

## 1. 設計目標與約束

| 目標 | 說明 |
|------|------|
| **M1 先行** | 先把「URL 解析 → 人工修正 → PTT 組稿 → 預覽／檢查 → 草稿 → 複製」做穩，且解析器必須可擴充（SRS FR-109） |
| **結構性安全** | 程式碼層級沒有送出／存檔路徑；遞送介面本身無法表達「送出」（SP-02） |
| **不信任解析結果** | 逐欄位狀態、來源策略、完整性判定、人工修正；標題成功 ≠ 全文成功（FR-110、113） |
| **可重複測試** | 解析與內容處理為純函式式；離線快照＋黃金檔；不連網、不連 PTT（FR-115、SP-08） |
| **Portable** | 解壓即用，資料在同層 `data\`；不寫登錄檔、不需系統管理員（FR-804） |
| **兩種遞送模式互不依賴** | 剪貼簿（A）與 UI 自動輸入（B）各自獨立、可單獨停用 |
| **誠實標示** | 沒有證據的技術假設一律列入驗證計畫，不寫成既定事實 |

硬性約束：不用瀏覽器外掛；不自動登入；不自動發文；不直接連線 PTT；解析不執行網頁腳本；不儲存憑證。

---

## 2. 技術棧評估與基線

### 2.1 決議：**維持 Python 基線**（使用者決策 5，2026-10-15）

依據 [PYTHON_BASELINE_AUDIT.md](PYTHON_BASELINE_AUDIT.md)：本機 Python 3.12.10、PySide6 6.11.2、PyInstaller 6.22.2、pytest 9.1.1、hypothesis、lxml／bs4／requests／PyYAML／charset-normalizer、SQLite 3.49.1（含 FTS5）皆已就緒且 `pip check` 乾淨；使用者另有兩個同棧專案（OQCTOOL：PySide6＋PyInstaller 可攜版；電容規格書工具：requests＋bs4 網路擷取、`ToolError` 例外階層、live 測試分流）。**沒有技術棧遷移的必要**，且不再把 C#／.NET 當作預設方向。

| 項目 | 基線 | 驗證狀態 |
|------|------|----------|
| 語言／執行環境 | Python 3.12.10（專用 venv，Q-28） | 已觀察版本；venv 可重現性 V-23 |
| UI | PySide6 6.11.2（鎖定） | 授權遵循（LGPL，onefile 散布）須於 Phase 1 確認，**非法律建議**（K-12） |
| 打包 | PyInstaller 6.22.2；**沿用既有 onefile＋windowed＋`tools/make_portable.py`（build／組裝／verify）流程**；`EXCLUDES` 清單；**不沿用 UPX**（Q-29） | 【待驗證】V-24、V-25；**one-folder 為 V-24／V-25 失敗時的退路** |
| 儲存 | SQLite（標準庫 `sqlite3`；明確 ISO 8601 UTC 字串，不使用已棄用的預設 adapter） | FTS5／JSON 已觀察；可攜式行為 V-02 |
| 測試 | pytest＋`pytest.ini`；hypothesis；UI 腳本風格 `*_check.py` 或 pytest-qt（V-26） | — |
| 解析程式庫 | 已安裝：lxml 6.1.1、beautifulsoup4 4.15.0、charset-normalizer 3.4.9、requests 2.34.2、PyYAML 6.0.3；**未安裝：trafilatura、html5lib**；一律於 Phase 1 評選後才進依賴清單 | 【待驗證】V-26 |
| Windows 自動化（模式 B） | Win32（`ctypes`／`pywin32` 312，已安裝） | 【待驗證】V-07～V-13（M3） |

### 2.2 沿用的既有設計（摘要；完整表見 PYTHON_BASELINE_AUDIT §4）

根目錄入口＋`src/` 平面套件（`models`、`parsers`、`validation`、`services`、`ui`、`utils`、`errors.py`、`logging_setup.py`、`version.py`）；`ToolError` 例外階層；`config/settings.json`（EXE 同層、原子寫入）＋`logs/`（每日輪替保留 30 份）；`src/version.py`＋`bump_version`＋版本檢查測試；`make_portable.py` 的 `--verify`；`.bat` 僅 ASCII 與 `-X utf8`；`pytest.ini`；live 測試以環境變數啟用；真實（版權）樣本不進版控；網路擷取原則（來源可追溯、絕不偽造、錯誤分層、保守解析、不修改來源、不繞過保護）。

**不沿用**：UPX、`>=` 未鎖版本、全域環境直接打包、OQCTOOL 的「禁止 QThread」規則（本專案抓取／解析／備份必須背景執行，採 `QThreadPool`）。

### 2.3 退出準則（仍保留，但不再是預設路徑）

| 情況 | 處置 |
|------|------|
| Phase 1 spike 顯示 onefile 啟動時間或防毒誤判不可接受 | 先切 one-folder；仍不可接受再與使用者討論，**不自動遷移技術棧** |
| 模式 B PoC 顯示 Python 綁定不足（WinRT／UIA 等） | 考慮「Python 主程式＋小型輔助程序（僅模式 B、白名單 IPC）」；是否引入其他語言須使用者決策 |
| MS SQL Server | 單機單使用者，**無必要** |

**結論**：Python 基線；架構以「分層＋介面」隔離遞送、解析器、儲存，使任何日後替換的成本落在邊界而非領域邏輯。決策閘門 G-P1（Phase 1 結束）確認 V-23～V-26 與 V-01／V-02 結果。

---

## 3. 系統脈絡與分層

```
                           使用者
        ┌────────────────────┼─────────────────────────┐
        │ 貼 URL／編輯／確認   │ 自行貼上、存檔、發文       │
        ▼                     ▼                         │
┌──────────────────────────────────────┐   ┌────────────▼───────────────┐
│ PTT AutoPost（桌面程式，單一行程）     │   │ 使用者的瀏覽器：term.ptt.cc │
│                                      │   │（使用者自行登入、自行操作） │
│ UI 層（PySide6）                      │   └────────────▲───────────────┘
│   ├ 解析結果／草稿／預覽／檢查／複製   │ 剪貼簿／（模式 B：視窗輸入）│
│ 應用服務層                            │────────────────┘
│   ├ ArticleImportService ──┐          │
│   ├ DraftService           │          │        ┌───────────────┐
│   ├ CompositionService     │          │ HTTP   │ 使用者指定的   │
│   └ DeliveryService        │          │ GET ──►│ 文章網站       │
│ 領域核心（純邏輯）           │          │        └───────────────┘
│   ├ Parsing（解析器架構 §7）│◄─┘          │
│   ├ Content（正規化/編碼/寬度/渲染/檢查）│
│   └ Models（草稿/簽名檔/看板…）          │
│ 基礎設施                              │
│   ├ Storage（SQLite）／Config／Paths   │
│   ├ Logging（遮蔽）／SingleInstance     │
│   └ Delivery 實作：Clipboard／UIA／Fake │
└──────────────────────────────────────┘
```

依賴方向：UI → 應用服務 → 領域核心 ← 基礎設施實作（以介面反轉）。**領域核心不依賴 Qt、不依賴網路、不依賴檔案系統**，因此可在無桌面環境下測試。

---

## 4. 套件結構（設計；尚未建立）

```
PTTAUTOPOST\
  main.py                      入口（沿用既有專案慣例：根目錄入口＋ src.* 匯入）
  README.md  AGENTS.md  requirements.txt  pytest.ini  .gitignore
  docs\                        SRS / ARCHITECTURE / IMPLEMENTATION_PLAN / ACCEPTANCE_TESTS / TEST_CORPUS / GOLDEN_SPEC / PYTHON_BASELINE_AUDIT / PHASE0_*
  src\                         （平面套件；沿用 OQCTOOL／電容專案的 src 慣例）
    errors.py                  ToolError 階層：InputError / ParseError / ValidationError / NetworkError / ConfigurationError /
                               UnexpectedError ＋ 新增 StorageError / DeliveryError / SnapshotError
    logging_setup.py           每日輪替（保留 30 份）、共用 handler、敏感資料遮蔽 filter
    version.py                 單一版本來源（版號／建置日期／CHANGELOG）
    models\                    Article, Draft, Board, BoardRule, Template, SignatureProfile(M2), QueueItem, DeliveryAttempt …
    validation\                normalize, encoding, width, wrap, checks（對完整 payload）, hashing
    parsers\                   ★解析器架構（§7；沿用既有 parsers 命名）
      pipeline.py  registry.py  result.py  completeness.py  dynamic_detect.py  dedupe.py
      strategies\              站台規則、結構化資料（JSON-LD/OG/內嵌 JSON）、署名推定、通用抽取
      profiles\ 或 ..\rules\   宣告式站台規則（見下方 rules\）
      fetch\                   受限抓取（http_fetcher, robots, rate_limit, decoder）— 唯一對外連線處
    services\                  import_service, draft_service, composition_service(render/template), delivery_service, backup_service
    storage\                   db, migrations\, repositories\, backup（SQLite）
    delivery\                  base（無「送出」成員）, clipboard\, uia\（模式 B, M3）, fake\
    ui\                        main_window, views\, widgets\, notifications, theme
    utils\                     路徑解析 runtime_base_dir(), settings_manager（原子寫入）, single_instance
  rules\                       內建站台規則（宣告式 YAML；隨程式發行；唯讀）
  config\                      settings.json（EXE 同層；原子寫入）
  logs\                        app_YYYYMMDD.log（EXE 同層）
  data\                        app.db、backups\（執行時產生；Portable）
  tests\
    test_*.py                  pytest（單元／整合／夾具）；*_check.py 為 UI／E2E 獨立腳本
    poc\                       模式 B 假終端機（M3）
    corpus\                    manifest.yaml；snapshots\、golden\（含版權內容，不進版控；見 TEST_CORPUS §7）
  tools\                       make_portable.py（--build／組裝／--verify）、bump_version.py、靜態安全檢查、語料工具
```

此為設計草圖，實際目錄於 Phase 1 建立；變更需同步更新本節。與先前版本（`src\pttpost\…`）不同處已依「沿用既有設計」修訂。

---

## 5. 資料設計（SQLite）

通則：時間戳為 UTC ISO 8601；列舉欄位有 CHECK；外鍵啟用；歷史類表 `ON DELETE RESTRICT`；`SchemaMeta(version)` 驅動遷移。

| 表 | 主要欄位 | 備註 |
|----|----------|------|
| **Article** | id, source_url, final_url, canonical_url, fetched_at, http_status, content_type, charset_used, fetch_status(SUCCESS/PARTIAL/FAILED), page_class, body_status, parser_profile_id, parser_profile_version, result_json（完整 ParseResult，見 §7.5）, raw_snapshot_ref（可空；是否保存原始 HTML 見保留策略）, content_hash, created_at | 唯讀紀錄；重新擷取＝新增一筆 |
| **Draft** | id, article_id(可空), cloned_from_draft_id, board_name, template_id, category_tag, title, source_site, author, published_at, source_url_display, body, notes（個人心得）, signature_mode, signature_id, signature_snapshot, field_states_json（逐欄位狀態：已取得／未取得／使用者修改）, content_fingerprint, draft_version, review_status, confirmed_*（雜湊、版本、時間、序列化版本、payload 快照）, posting_status（M2）, archived_at, created_at, updated_at | CHECK：CONFIRMED 必有雜湊與版本；M1 僅用到部分欄位 |
| **SignatureProfile** | id, name, text, is_default, created_at, updated_at | 部分唯一索引：至多一個 is_default |
| **Board** | name（NOCASE 唯一）, display_name, allowed_categories_json, default_template_id, default_signature_id, notes | 種子僅 `Test`，無規則 |
| **BoardRule** | id, board_name, rule_type, value_json, source_note, status(UNVERIFIED/VERIFIED), verified_at | `rules_verified_at` 只在使用者明確核對時寫入 |
| **Template** | id, name, is_builtin, version, field_layout_json, default_category, default_signature_id | 內建唯讀 |
| **QueueItem**（M2） | id, draft_id, position, status(WAITING/ACTIVE/DONE/REMOVED), added_at, removed_reason | 至多一個 ACTIVE |
| **DeliveryAttempt**（M2） | id, draft_id, draft_version, payload_hash, mode, started_at, ended_at, outcome, abort_reason, checklist_json | write-ahead：先寫 started |
| **PostingReport**（M2） | id, draft_id, reported_at, result(POSTED/ABANDONED/UNKNOWN/NOT_POSTED_CONFIRMED), remote_id, posted_at, note | 使用者回報 |
| **AuditEvent** | id, time, type, actor(USER/SYSTEM/RECOVERY), draft_id, attempt_id, detail_json | 僅追加 |
| **Setting** | key, value_json, updated_at | 不含憑證 |
| **SchemaMeta** | version, migrated_at | |

**M1 的最小 schema**：Article、Draft、Template（含內建）、Setting、AuditEvent、SchemaMeta（簽名檔以**單一全域文字設定**代替，FR-304：`Setting` 鍵 `signature.global_text`、`signature.apply_by_default`；`Draft` 欄位 `use_signature`（布林）與 `signature_snapshot`（當時的簽名檔文字））。遷移機制自 M1 就建立，之後只加表／欄；**M2 遷移**：把 `signature.global_text` 轉為一筆名為「預設」的 `SignatureProfile` 並設為全域預設，既有草稿快照不變（SIG-M1-010）。

**原始 HTML 保留**：預設只保存解析結果 JSON 與必要的內文；是否保存完整原始回應（利於日後重新解析）以大小上限與保留天數控制【待確認】；**語料測試用的快照另存於 `tests/corpus`，不進使用者資料庫**。

---

## 6. 狀態機

### 6.1 草稿確認狀態（review_status）
| 轉移 | 觸發 | 條件／副作用 |
|------|------|--------------|
| DRAFT → CONFIRMED | 使用者按「確認」 | 無阻擋級錯誤；使用者已檢視差異報告；保存 payload 快照與雜湊 |
| CONFIRMED → INVALIDATED | 影響渲染的實際編輯／逾期／遞送前雜湊不符 | M2：連動移出佇列 |
| INVALIDATED → CONFIRMED | 重新確認 | 同上 |

### 6.2 發文狀態（posting_status；M2；使用者回報，程式不判定）
`NOT_POSTED` → `DELIVERED`（已複製／已填入）→ `POSTED` | `ABANDONED` | `UNKNOWN`；`UNKNOWN` → `POSTED` | `NOT_POSTED`（須原因＋二次確認）| `ABANDONED`；遞送嘗試於輸入開始後被中止 → `UNKNOWN`。`UNKNOWN`／`POSTED` 的草稿拒絕再遞送。

### 6.3 遞送嘗試（M2；M1 僅日誌）
`STARTED` → `COPIED`（模式 A）；`STARTED` → `FILLED`／`ABORTED`／`FAILED`／`INTERRUPTED`（模式 B）。重啟時殘留 `STARTED` → `INTERRUPTED`＋草稿 `UNKNOWN`。

### 6.4 解析工作（非持久；於記憶體）
`QUEUED → FETCHING → PARSING → DONE | FAILED | CANCELLED`；任何階段可取消；FAILED 仍保存一筆 Article（FR-106）。

---

## 7. 解析器架構（M1 核心）

### 7.1 目標與原則

1. **通用與特定分離**：通用策略不含任何網站常數；網站專屬知識只在宣告式站台規則或獨立的專屬解析器外掛（FR-109）。
2. **逐欄位合併**，而非「整篇採用某一策略」：標題可能來自 JSON-LD、內文來自站台規則、作者來自內文署名推定。
3. **純函式式**：`(文件, 規則集, 設定) → ParseResult`，不連網、不執行腳本、無隱藏狀態；利於離線回歸。
4. **永不把「沒有」當「有」**：每欄位有狀態；缺失即 MISSING；推定即標 INFERRED。
5. **失敗可解釋**：每個失敗／降級都有分類與原因（§7.8）。

### 7.2 流程

```
URL ─► [UrlNormalizer] ─► [Fetcher：受限 GET（FR-103）] ─► RawResponse(bytes, headers, final_url)
         │                                                          │
         │                                           [Decoder：標頭>meta>BOM>偵測；記錄 charset_used]
         │                                                          ▼
         │                                           [DocumentLoader：建 DOM（純文字處理，不執行腳本）]
         │                                                          ▼
         │                                   [PageClassifier：ARTICLE / LISTING / CSR_SHELL / LOGIN_WALL /
         │                                                    PAYWALL / BLOCKED / NON_HTML / UNKNOWN]
         │                                                          ▼
         │                         [ParserRegistry.select(url, doc) → 有序的 SourceParser 清單]
         │                                                          ▼
         │        ┌───────────────── 策略鏈（各自產出 PartialResult；逐欄位合併）─────────────────┐
         │        │ S1 站台規則（SiteProfile，宣告式）                                              │
         │        │ S2 專屬解析器外掛（僅當 S1 不足；內建、獨立檔案）                                 │
         │        │ S3 結構化資料：JSON-LD(@graph/@type)、OpenGraph、meta、內嵌狀態 JSON            │
         │        │ S4 內文署名推定（Byline）：由內文首尾行辨識「記者／編譯」等                        │
         │        │ S5 通用正文抽取（Readability 類啟發式／候選庫）                                   │
         │        └────────────────────────────────────────────────────────────────────────────────┘
         │                                                          ▼
         │                                   [FieldMerger：依欄位優先序＋信心合併，保留 provenance]
         │                                                          ▼
         │                                   [Cleaner：去雜訊、純文字化、保留換行、FR-401 正規化預覽]
         │                                                          ▼
         │                                   [CompletenessAnalyzer → body_status（FR-110）]
         │                                                          ▼
         └──────────────────────────────► ParseResult（§7.5）──► 草稿建立／UI 呈現（FR-113）
                                                                   ＋ 重複比對（Canonical／內容指紋，FR-604）
```

### 7.3 擴充點與介面（契約，非實作）

| 介面 | 職責 | 契約要點 |
|------|------|----------|
| `SourceParser`（策略） | `matches(url, doc) → 分數/否`；`extract(ctx) → PartialResult` | 無副作用；不得連網；不得改動 DOM（須在副本上操作）；例外由管線隔離 |
| `SiteProfile`（宣告式資料） | 網域／路徑比對、欄位選擇器、移除選擇器、日期格式、署名正則、已知限制 | 由安全載入器解析（不執行程式碼）；載入時**逐項驗證**，單項錯誤只停用該項並報告檔名與原因（AC-17） |
| `FieldMerger` 的優先序表 | 每欄位的策略優先順序（資料驅動） | 站台規則可覆寫預設表；變更需有測試 |
| `CompletenessSignal` | 單一完整性訊號（長度、截斷標記、交叉比對、分頁…） | 可插拔；每個訊號有單元測試與參數 |
| `PageClassifierRule` | 辨識外殼／登入牆／反爬頁 | 可擴充；有負向測試（正常文章不得被誤判） |

**新增一個來源的標準作業**：① 蒐集快照；② 寫站台規則；③ 產生並人工核對黃金檔；④ 執行回歸測試；⑤ 更新來源支援矩陣。若宣告式規則無法表達才新增專屬解析器外掛（每來源一個獨立檔案，附測試）。**核心流程檔案不因新增來源而修改**（以測試與 code review 守住）。

### 7.4 站台規則（SiteProfile）概念格式（示意，非最終）

> 僅示意欄位語意；實際 schema 於 Phase 3 定案，並以 schema 驗證。

```yaml
# 示意：不代表任何特定網站的真實選擇器
id: example-news
version: 1
verified_on: 2026-10-15            # 最後驗證日期（FR-104 要求）
match:
  hosts: [example.com]             # 完全相等或子網域
  paths: ["^/news/\\d+"]
fields:
  title:      { prefer: [jsonld, selector], selector: "h1.headline" }
  site_name:  { value_from: og:site_name, fallback: "範例新聞" }
  author:     { selector: ".byline .name", byline_regex: ["記者(.+?)／", "（.+?記者(.+?)[^）]*報導）"] }
  published:  { selector: "time[datetime]", attr: datetime, formats: ["ISO8601"] }
  body:
    container: ["article .content", "div#story"]
    keep: ["p", "h2", "blockquote"]
    remove: [".related", ".ad", ".share", "figure figcaption"]
    drop_paragraph_regex: ["^延伸閱讀", "^責任編輯"]
known_limits: ["分頁文章僅取第 1 頁", "會員專屬內容僅有摘要"]
```

要點：作者／記者在多數媒體不在獨立欄位而在內文首段（O-06 觀察到多站缺作者欄位）——因此「署名推定（S4）」是一級策略，結果標 `INFERRED` 並降低信心，使用者可一鍵確認或修改。

### 7.5 解析結果資料結構（ParseResult）

| 區塊 | 內容 |
|------|------|
| `request` | 原始 URL、Canonical URL、最終 URL、重新導向鏈、HTTP 狀態、content-type、`charset_used`、`fetched_at` |
| `page_class` | ARTICLE／LISTING／CSR_SHELL／LOGIN_WALL／PAYWALL／BLOCKED／NON_HTML／UNKNOWN |
| `fields.*` | 對 `title`、`site_name`、`source_url`、`author`、`published_at`、`body`、`images`：`value`、`status`（FOUND／MISSING／INFERRED／SUSPECT）、`provenance`（策略 ID＋規則版本）、`confidence`（0–1）、`notes` |
| `body_status` | COMPLETE_LIKELY／SUSPECT_PARTIAL／INSUFFICIENT／UNKNOWN＋`signals`（逐訊號結果）＋`reasons` |
| `fetch_status` | SUCCESS／PARTIAL／FAILED；**SUCCESS 的定義包含 body_status ∈ {COMPLETE_LIKELY}**；標題與連結齊全但內文不足者為 PARTIAL |
| `parser` | 使用的 profile／策略清單、耗時、版本 |
| `warnings`／`errors` | 結構化（代碼＋訊息＋建議動作） |

### 7.6 欄位預設優先序（可被站台規則覆寫）【待驗證 V-15】

| 欄位 | 優先序（高→低） | 備註 |
|------|-----------------|------|
| 標題 | 站台規則 → JSON-LD 文章節點 `headline` → `og:title` → `<h1>` → `<title>`（去站名後綴，僅在與站名吻合時去除） | JSON-LD 只取文章型節點 |
| 媒體來源 | 站台規則 → `og:site_name` → JSON-LD `publisher.name` → 網域對照表 | |
| 原文 URL | `<link rel=canonical>`／`og:url`（需與請求同站台才採用）→ 最終 URL | 原始輸入 URL 另保留 |
| 作者／記者 | 站台規則 → JSON-LD `author`（Person）→ meta author（**僅當不是機構名或網址**）→ **內文署名推定（INFERRED）** | 語料觀察（TEST_CORPUS C-03）：多家媒體的 meta author 是機構名（如通訊社／報社名）或社群網址，而非記者；機構名歸入「媒體來源」，不當作記者 |
| 發布時間 | 站台規則 → JSON-LD `datePublished` → `article:published_time` → `<time>` → 內文推定 | 統一為帶時區 ISO；無時區者標註並假設來源時區【待確認】 |
| 內文 | 站台規則 → 專屬外掛 → 內嵌狀態 JSON → 通用抽取 | 通用抽取結果用於與其他策略**交叉比對完整性** |

### 7.7 內文完整性分析（FR-110；門檻【待驗證】V-20）

| 訊號 | 判定要點 |
|------|----------|
| 長度／段落 | 與同站台快照的分佈比較；過短→INSUFFICIENT／SUSPECT |
| 交叉比對 | 站台規則內文 vs 通用抽取內文 vs JSON-LD `articleBody`（若有）：長度比、段落重疊率差異過大 → SUSPECT_PARTIAL |
| 截斷標記 | 「展開全文」「繼續閱讀」「閱讀更多」「請登入／訂閱後閱讀」等出現在內文區附近 |
| 分頁 | `rel=next`、「第 N/M 頁」「下一頁」連結 → SUSPECT_PARTIAL＋頁數 |
| 結尾 | 末段無結束標點且被截斷樣式 |
| 內容比 | 內文文字量／整頁可見文字量過低 → 可能抓到導覽或推薦清單 |
| 外殼 | CSR_SHELL／LOGIN_WALL／PAYWALL → INSUFFICIENT＋原因 |

輸出為「判定＋原因清單」，**不輸出「確定完整」**。測試以標註的「完整／不完整」快照量測誤判率（AT-M1）。

### 7.8 失敗與降級分類（錯誤碼家族 `E-EXT-*`）

| 類別 | 例 | 處置 |
|------|----|------|
| 輸入 | URL 無效、協定不支援、畸形（IPv6） | 驗證失敗，說明原因 |
| 抓取 | 逾時、超過大小、重新導向過多、非 HTML、HTTP 4xx/5xx、**403／挑戰頁**（BLOCKED） | FAILED＋原因；**不繞過**；引導手動輸入 |
| 外殼／牆 | CSR_SHELL（NEEDS_JS）、LOGIN_REQUIRED、PAYWALL、年齡確認 | FAILED／PARTIAL＋原因；引導手動輸入 |
| 解析 | 無站台規則、規則損壞、JSON-LD 壞 JSON、候選區塊不明 | 降級到下一策略；記錄隔離事件 |
| 完整性 | SUSPECT_PARTIAL／INSUFFICIENT | PARTIAL＋警告；不得顯示為成功 |
| 編碼 | 宣告編碼與內容不符、解碼出現大量替代字元 | 警告；顯示 `charset_used`；允許使用者改編碼重解碼 |

### 7.9 動態網頁與登入牆（FR-111；V-19）

偵測特徵（皆待以語料驗證）：可見文字極少（觀察到 Facebook 首頁、LINE TODAY 頁、vocus 首頁在無腳本下可見文字僅數百字元級，O-06 附表）、存在前端框架根節點／內嵌狀態資料、`<noscript>` 要求啟用 JS、標題為通用站名。處置：先嘗試**靜態**內嵌狀態 JSON（不執行腳本）；失敗則 `NEEDS_JS`，並引導手動輸入。**M1 不引入瀏覽器引擎**（Q-22）。

### 7.10 重複偵測（FR-604 的 M1 範圍）

- Canonical URL 比對：已移除追蹤參數（`utm_*`、`fbclid`、`gclid`；語料另在特定站台首頁連結上觀察到 `from`、`ctrack`、`rec` 參數，**疑為追蹤用途，待確認**——**以站台規則宣告該站的追蹤參數**而非全域刪除，避免誤刪文章識別參數）。
- 內容指紋：未斷行、空白正規化後文字的雜湊；另用 shingle／SimHash 類相似度找「轉載相同新聞」（演算法【待驗證】，門檻 Q-14）。
- 結果以警告呈現（依據、既有草稿／Article），使用者決定；不自動合併或刪除。

### 7.11 抓取層（Fetcher）

遵循 FR-103：逾時、大小、重新導向上限、同網域間隔、誠實 User-Agent、robots.txt 警告、不帶 Cookie／Referer、只 GET、僅 HTML。速率限制以每網域令牌機制；取消即中止連線。**抓取層是唯一會連外的元件**（靜態檢查白名單，SA-02）。

### 7.12 解析器的測試介面

- 輸入為**快照**（原始位元組＋標頭），輸出 ParseResult；與黃金檔逐欄位比對（內文以段落召回率／雜訊率）。
- 測試執行器輸出「每來源×每快照×每欄位」報告，並更新來源支援矩陣（FR-114）。
- 線上抽查模式：對清單 URL 重新抓取並與最近快照比對差異，**僅預警**。

---

## 8. 內容處理管線（Domain / content）

`Article/使用者輸入 → Normalize（FR-401）→ [差異報告] → 使用者確認 → Compose（模板＋簽名檔）→ Render（單一渲染）→ Validate（FR-404）→ Hash（FR-406）→ Preview（FR-405）→ Delivery`

| 元件 | 要點 |
|------|------|
| Normalize | CRLF／CR、Tab、**完整 ANSI 序列**、控制字元、Unicode 不可見字元；回傳（新文字，差異報告） |
| Encoding | 介面 `Encoder(name) → can_encode(ch)／byte_len(text)`；基線為「保守字集」實作，待 V-03 替換為 UAO 對照；**位元組長度、可編碼性、雜湊同一個編碼** |
| Width／Wrap | 顯示欄寬（含 Ambiguous 參數）；URL／英文單字保護；避頭尾 |
| Template | 欄位順序／顯示由模板資料定義；內建「新聞轉貼」模板；渲染為純文字 |
| Render | **唯一**渲染入口；輸出（完整標題、完整內文、各欄位範圍對照）；預覽／複製／填入／雜湊都取此輸出 |
| Validate | 對完整 payload 一次檢查；阻擋／警告分級；每項檢查附規則來源（看板規則附狀態與核對時間） |
| Hash | SHA-256；固定、版本化序列化；僅偵測變更 |

---

## 9. 遞送子系統

### 9.1 介面（結構性安全）

```
Delivery（概念）
  ├ prepare(payload_part)          準備標題或內文（不改變外部世界）
  ├ deliver(payload_part, ctx)     模式 A：寫入剪貼簿；模式 B：輸入到使用者的終端機視窗
  └ cancel()
```

**不存在** `submit` / `save` / `post` / `send_key(key)`。模式 B 的輸入驅動只接受型別受限的「文字內容」與「貼上」兩種操作值；組合鍵由列舉白名單定義，其他無法建構。靜態檢查（§15.3）再次把關。

### 9.2 模式 A：剪貼簿

流程：Render → Validate（阻擋級→拒絕）→（M2：核對清單）→ 寫入剪貼簿（含「排除歷史／雲端」格式嘗試，V-14）→ 讀回比對雜湊 → 非模態提示（含位元組／字元數與下一步）→ 記錄。重點風險：貼上路徑可能被站台改寫（O-05；V-04）→ 以同規則的複製前檢查降低；實際行為待真實 PTT 人工驗證。

### 9.3 模式 B：Windows UI 自動輸入（M3；**全部待驗證**）

#### 9.3.1 必須先承認的限制

- `term.ptt.cc` 預設以 Canvas 繪製（O-01）：**不得假設**畫面文字可由 UI Automation 或一般 Windows 控制項讀取；Canvas 內容預期不在可存取樹中，須實測 V-11。
- 程式無法讀取頁內 JS 狀態（無外掛、無偵錯連接）；也無法精確得知輸入是否到達伺服器。
- 因此模式 B 的可靠度取決於**影像／視窗層級的狀態辨識**，此為最大不確定性（V-09、V-10）。

#### 9.3.2 元件

| 元件 | 職責 | 待驗證 |
|------|------|--------|
| `WindowLocator` | 列舉頂層視窗；行程名稱允許清單；**視窗標題列**含「批踢踢實業坊」（容許 🔔 前綴，O-02）；多候選由使用者選；輸出唯一的 hwnd 或「無法唯一」 | V-07 |
| `FocusGuard` | 動作前驗證：前景視窗＝hwnd、標題、未最小化、非 UIPI 落差；動作後再驗；任一失敗→中止 | V-08 |
| `ScreenCapture` | 擷取目標視窗客戶區影像（`PrintWindow`／Windows Graphics Capture 擇一或組合） | V-09（GPU 合成視窗可能擷取為空白） |
| `StateClassifier` | 由影像／（DOM 模式下的）可存取文字辨識 PTT 畫面狀態：`TITLE_PROMPT`、`EDITOR_EMPTY`、`EDITOR_NONEMPTY`、`OTHER`、`UNKNOWN`。對應使用者所稱的「PTT 標題欄」與「內文區」 | V-10、V-11 |
| `InputDriver` | 白名單操作：①寫入剪貼簿＋單次貼上快捷鍵；②逐字輸入已檢查字元（備選）。**無法表達**送出類按鍵 | V-12 |
| `AbortController` | 全域中止熱鍵、偵測使用者實體輸入、逾時；統一中止旗標，每步前檢查 | V-13 |
| `FillSession` | 編排：前置條件 → write-ahead 記錄 → [驗證→輸入→驗證]* → 結束記錄；任何異常→停止，不重試 | — |

#### 9.3.3 狀態辨識選項（以 PoC 擇一或組合）

| 選項 | 作法 | 優點 | 限制／風險（待驗證） |
|------|------|------|----------------------|
| (a) 影像辨識 | 擷取視窗→定位終端機畫布→切 80×24 格→對底部狀態列與游標列做模板比對或 OCR | 不需改動站台設定 | 對字型、縮放、DPI、配色、反鋸齒敏感；需校準；OCR 引擎與語言套件為額外依賴 |
| (b) DOM 模式＋UIA | 請使用者在站台設定關閉 Canvas 渲染（設定項存在，O-01），以 UIA 讀取文字 | 文字可得性高 | 是否真的可讀、讀取效能、需使用者變更站台設定；瀏覽器可存取性需啟用（V-11） |
| (c) 不辨識 | 僅輔助貼上（備好剪貼簿＋逐步指引） | 最安全 | 無自動輸入 |

**放行邏輯**：只有「連續 N 次取樣皆 = 預期狀態且信心 ≥ 門檻」才輸入；`OTHER`／`UNKNOWN`／取樣不一致 → 停止並提示改用剪貼簿。PoC 通過標準：誤判為「可輸入」= 0（見 ACCEPTANCE_TESTS AT-UIA）。

#### 9.3.4 結果與不明處理

輸入後只做**輔助**比對（再次擷取畫面尾段與預期文字相似度），結果寫成事實描述，**不宣稱成功**；任何不確定／中止（輸入已開始）→ INTERRUPTED＋草稿 UNKNOWN，須人工回報；**絕不自動重送**。

#### 9.3.5 其他可能路線（不採用於基線；列為使用者決策項）

CDP／遠端偵錯、內嵌 WebView 載入 `term.ptt.cc`：技術上更可靠，但前者需以特殊參數啟動瀏覽器、後者是程式自有視窗並需在其中登入，皆偏離「操作使用者已開啟視窗」；除非使用者另行決定，否則**不納入**。

---

## 10. UI 設計（M1 為主）

### 10.1 主要視圖

| 視圖 | 內容 |
|------|------|
| 匯入 | URL 輸入列、解析進度（可取消）、結果摘要（頁面分類、`fetch_status`、`body_status`） |
| 解析結果／欄位表 | 七個欄位的值、狀態徽章（已取得／未取得／推定／使用者修改）、來源策略、警告；欄位可就地編輯；**「未取得」以醒目樣式顯示**；內文完整性警告置頂 |
| 組稿編輯 | 個人心得、分類框、看板、模板選擇；M1：**單一全域簽名檔文字欄位**（編輯、儲存；草稿勾選「套用簽名檔」；FR-304）；無多組簽名檔 UI |
| 預覽 | 終端機風格等寬文字（純文字元件）；標題與內文位元組／寬度；超寬行標示；80×24 分頁模擬（可選） |
| 檢查 | 阻擋／警告清單，點擊跳到位置；正規化差異報告 |
| 草稿 | 列表、搜尋、開啟、刪除（M1 基本；封存 M2） |
| 重複提示 | 匯入時顯示疑似重複的既有 Article／草稿 |
| 操作列 | 複製標題、複製內文、複製整篇、儲存草稿、確認 |
| 狀態列／通知 | 非模態；進度、已複製、錯誤摘要＋下一步 |

### 10.2 互動原則

- 任何耗時動作在背景；UI 不凍結；不彈出非必要視窗、不搶焦點、不置頂（SP-07）。
- 複製按鈕在有阻擋級錯誤時停用並說明原因；複製成功用狀態列提示。
- 解析失敗時，主畫面直接提供「改用手動輸入」，流程不中斷（FR-112）。
- 所有解析來源標示清楚；使用者永遠可覆寫。

---

## 11. 執行緒與併發

| 工作 | 執行位置 | 備註 |
|------|----------|------|
| UI | 主執行緒 | 不做 I/O 與 CPU 密集 |
| 抓取＋解析 | 背景工作（`QThreadPool` 或等價）；解析為 CPU 密集，必要時獨立行程以隔離解析庫崩潰【待評估】 | 可取消；進度回報 |
| 資料庫 | 每執行緒各自連線，或單一寫入執行緒＋佇列（Phase 1 spike 擇一）；交易短；`busy_timeout` | WAL 僅在本機磁碟（V-02） |
| 模式 B | 獨立工作執行緒＋`AbortController` | UI 持續可操作（含中止） |
| 備份 | 背景；使用 SQLite 線上備份機制 | |

---

## 12. Portable、設定與備份

### 12.1 目錄與路徑

```
<可攜資料夾>\                    （沿用既有 OQCTOOL 可攜版：EXE＋config＋logs 同層）
  PttAutoPost.exe
  config\settings.json          小型啟動設定（資料目錄覆寫、日誌等級、UI 偏好）；原子寫入
  logs\app_YYYYMMDD.log         每日輪替、保留 30 份
  data\                         app.db、backups\、rules\（使用者站台規則覆寫）、.lock（本產品新增）
```
- 路徑一律由 `runtime_base_dir()` 計算：打包後取 **`sys.executable` 所在資料夾**，開發時取專案根（沿用既有慣例）；**不使用 `__file__` 或工作目錄**（AT-PRT、ENV-005）。
- 啟動寫入測試；失敗→退回 `%LOCALAPPDATA%` 專屬資料夾並持續顯示實際位置。
- 偵測雲端同步資料夾／網路／可移除磁碟→警告並關閉 WAL（V-02）。

### 12.2 封裝（Phase 1 spike；M2 正式）

**基線沿用既有流程**：PyInstaller onefile＋windowed；`tools/make_portable.py`（`--build` → 組裝可攜資料夾 → `--verify` 驗證 EXE 內容與版本一致，防止舊檔殘留）；`.bat` 僅 ASCII、路徑操作寫在 Python；`EXCLUDES` 排除無關大型套件（pandas、numpy、onnxruntime、sympy、pymupdf…；模式 B 的 opencv／numpy 於 M3 才納入）。**不使用 UPX**（Q-29）。onefile 的缺點（啟動時需解壓、防毒誤判）以 V-24／V-25 量測；不可接受時退回 one-folder（同一流程，改 `COLLECT`）。內建站台規則隨程式發行於唯讀位置，使用者覆寫放 `data\rules`。`--verify` 另須確認**不含 `tests/corpus` 內容**（SNP-009）。**不建置 EXE，直到 Phase 1 spike 授權**。

### 12.3 備份、還原、升級

- 備份＝線上備份快照＋設定＋規則覆寫，檔名含 schema 版本與時間；**不含憑證**（不存在）。
- 還原：驗證格式與版本→先備份現況→還原→失敗回滾。
- 升級：替換程式檔、保留 `data\`；啟動時 `schema_version` 比對，較舊則先自動備份再遷移，較新則拒絕開啟。
- 單一執行個體：鎖檔含 PID／主機名／時間；殘留鎖可偵測接管。

---

## 13. 日誌與錯誤處理

- 滾動日誌；每筆含時間、等級、錯誤碼、草稿／嘗試 ID、摘要；遮蔽規則見 FR-801（含堆疊與 URL userinfo／敏感 query）。
- 錯誤碼家族：`E-EXT-*`（解析，§7.8）、`E-CHK-*`（檢查）、`E-DLV-*`（遞送）、`E-DB-*`、`E-CFG-*`、`E-SYS-*`。
- 使用者訊息 = 原因＋影響＋可行處理；技術細節只進日誌／診斷包。
- 原則：只有「確定尚未輸入任何內容」的失敗才算 FAILED；已開始輸入後的異常一律 INTERRUPTED/UNKNOWN；**永不自動重試遞送**。

---

## 14. 安全與隱私架構

| 面向 | 設計 |
|------|------|
| 無自動送出 | 遞送介面無送出成員；輸入驅動白名單；靜態檢查＋變異測試 |
| 無 PTT 連線 | 專案內無 `ptt.cc` 連線程式；網路出口只有抓取層；靜態檢查白名單 |
| 無憑證 | 不儲存／不處理帳密；日誌遮蔽為縱深防禦 |
| 內容隱私 | 資料僅本機；剪貼簿排除格式與可選自動清除；診斷包預設不含全文 |
| 解析安全 | 解析不執行腳本、不載入圖片／iframe；內容一律純文字顯示；站台規則僅宣告式、安全載入；專屬外掛僅限內建 |
| 供應鏈 | 依賴白名單；Phase 1 評選時記錄授權與維護狀態 |
| 誠實抓取 | 誠實 UA、robots 警告、頻率限制、不繞過任何牆 |

---

## 15. 測試架構

### 15.1 分層
單元（領域核心、解析策略、正規化、編碼、渲染、雜湊）→ 夾具／語料（離線快照＋黃金檔）→ 儲存（暫存 DB、遷移、約束）→ UI（互動式 Windows 工作階段；M1 的複製流程）→ 假終端機（模式 B PoC）→ 封裝煙霧測試 → 人工（真實 PTT，使用者執行）。

### 15.2 語料與解析回歸（M1 關鍵）

- `tests/corpus/manifest.yaml`：來源、Tier、URL、取得日期、測試用途、使用條款確認狀態、角色（dev／holdout）、快照路徑、黃金檔路徑與**狀態**、情境標籤、各檔 SHA-256（結構見 TEST_CORPUS §10）。
- 離線測試完全不連網；快照＝**HTML 原始位元組＋標頭＋最終 URL＋正文＋截圖＋來源資訊**（FR-116）；黃金檔＝人工核對的欄位與內文（GOLDEN_SPEC）。
- **比對**：依 GOLDEN_SPEC——正規化 `N_v0`、指標 `S`／`R`／`D`／`E`、結構性防護 G1～G6、欄位比較器、衝突規則 C1～C11；測試框架**只接受 `VERIFIED` 黃金檔作為閘門基準**，其餘標「暫行」；門檻先校準（AT-CAL）後凍結。
- 報告：每來源×快照×欄位（含黃金檔狀態）；彙整成來源支援矩陣；**任何 Tier A 來源缺 `VERIFIED` 保留快照黃金檔或比對未過→M1 閘門不過**。
- 合成夾具（Big5／GBK 編碼、壞 JSON-LD、截斷、分頁、外殼、登入牆、重複、劣化集 X-41）補足真實網站難取得的情境（TEST_CORPUS §8）。
- 線上抽查：預警用，不入閘門；預設關閉，需環境變數（沿用既有 live 測試做法，名稱 `PTTPOST_LIVE`，Phase 1 定案）。
- **版權與散布**：`snapshots/`、黃金檔正文、截圖不進版控（沿用既有專案排除真實樣本的作法），發行版不得包含（SNP-008／009）。

### 15.3 靜態安全檢查（自 Phase 1 起於建置流程）
1. 遞送元件不得出現送出類按鍵常數／字面量／成員名稱；
2. 網路客戶端只能在抓取層，且目的地不得為 `ptt.cc` 網域；
3. 依賴白名單；
4. 變異測試：故意加入禁用按鍵或違規連線，檢查必須失敗。

### 15.4 假終端機（模式 B PoC）
本機假終端機頁（自製 Canvas 畫面，必要時另依 Q-36 使用站台前端副本）＋假 BBS 伺服器（**伺服器端記錄實際收到的位元組＝真值**）＋誘餌視窗集合（相近標題的其他視窗、不同 DPI／縮放、前景切換）。全程不連真實 PTT（SP-08）。

---

## 16. 主要風險與對應

| # | 風險 | 嚴重度 | 對應 |
|---|------|--------|------|
| R1 | 解析覆蓋不足：媒體版型異質、改版漂移（O-06） | 高 | 解析器架構、站台規則外部化、語料回歸、線上抽查預警（V-15、V-21） |
| R2 | **把標題成功當全文成功** | 高 | FR-110；M1 驗收以黃金全文比對（V-20） |
| R3 | 作者／記者多藏在內文首段，推定可能錯 | 中 | INFERRED 標示＋人工確認；站台規則署名正則 |
| R4 | 動態網頁／反爬／登入牆 | 中 | 偵測＋誠實失敗＋手動備援（V-19） |
| R5 | 編碼：Big5-UAO 對照不明；不可編碼字元被站台靜默替換 | 高 | 保守字集＋阻擋；V-03；非 UTF-8 解碼語料（V-22） |
| R6 | 貼上路徑被站台改寫、標題上限／行寬未知 | 高 | 參數化＋保守預設＋Phase 7b 人工驗證（V-04、V-05） |
| R7 | **模式 B 狀態誤判**導致內容誤入錯誤畫面或其他應用程式 | 最高 | PoC 閘門（誤判=0）；FocusGuard；單次貼上；全域中止；未過則降級（SP-05） |
| R8 | Portable 封裝體積／防毒誤判（PyInstaller onefile）；全域環境污染（K-1） | 中 | Phase 1 spike（V-24、V-25）；專用 venv（Q-28）＋`EXCLUDES`；不用 UPX；退路 one-folder（§2.3） |
| R9 | SQLite 在可攜式環境的損毀／鎖 | 中 | V-02；滾動備份；鎖檔；警告 |
| R10 | 剪貼簿歷史／雲端同步外洩 | 中 | V-14；排除格式；可選自動清除 |
| R11 | 第三方內容快照的使用範圍／著作權／使用條款 | 中 | 決策 1（採用，僅本機測試、不散布）；使用條款逐站人工確認（Q-32）；robots／Crawl-delay；不繞過（FR-116）；Q-13（非法律建議） |
| R13 | **黃金檔錯誤或門檻不當導致誤判**（把錯的答案當基準、95%／3% 過鬆或過嚴） | 高 | 只有 `VERIFIED` 為基準；先校準後凍結（AT-CAL）；結構性防護 G1～G6；保留快照；衝突規則 C3（不得以輸出回寫黃金檔） |
| R12 | 範圍膨脹：M1 要求多來源＋全文驗證，工作量高 | 中 | 分 Tier；Tier A 先行；規則以宣告式批次量產；以計畫中的 Phase 3 專注 |

---

## 17. 需求追溯（摘要）

| 架構章節 | 對應 SRS |
|----------|----------|
| §7 解析器架構 | FR-101～115、AC AT-EXT、AT-M1 |
| §8 內容處理 | FR-401～406 |
| §9 遞送 | FR-501～507 |
| §5–6 資料與狀態 | FR-201～207、601～603、701 |
| §12 Portable | FR-702～704、803、804 |
| §13–14 日誌／安全 | FR-801、802、NFR-04 |
| §15 測試 | FR-115、SP-08 |
