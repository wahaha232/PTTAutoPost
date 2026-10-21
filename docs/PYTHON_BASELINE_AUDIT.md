# Python 基線稽核（版本、依賴、既有專案架構）

- 日期：2026-10-15；**唯讀稽核**
- 依據：使用者決策 5：「技術棧維持 Python 基線。請先稽核現有專案的 Python 版本、依賴與架構，沿用既有設計，避免沒有必要的技術棧遷移。」
- 相關：[ARCHITECTURE.md](ARCHITECTURE.md) §2／§4／§12／§15、[SRS.md](SRS.md) §13.3
- **狀態聲明**：本稽核只**讀取**檔案、版本與可匯入性；**沒有打包、沒有執行任何既有專案或本專案的程式、沒有安裝／升級／移除任何套件、沒有修改任何既有專案**。「已觀察」只代表版本與匯入成功，**不代表相容性已驗證**。

---

## 1. 稽核範圍與方法

| 項目 | 做法 |
|------|------|
| 環境 | `python --version`、`pip list`、`pip check`、以 `python -I` 匯入候選模組、以記憶體資料庫查詢 SQLite 編譯選項（不建立任何檔案） |
| 本專案 | 列出 `D:\Claude\PTTAUTOPOST` 內容 |
| 既有專案 | 掃描 `D:\Claude`、`D:\Visual Studio Code\PROJECT` 找出含 Python 程式的專案、`.spec`、`requirements.txt`、`pyproject.toml`；逐一閱讀兩個最相關專案的 `README`／`AGENTS.md`／`requirements.txt`／`.spec`／打包腳本／入口程式／設定、日誌、版本、例外模組與測試結構 |
| 未做 | 不執行既有專案測試（會寫入測試產物）、不打包、不開啟其 Excel／PDF 資料 |

---

## 2. 稽核對象與發現

### 2.1 本專案（`D:\Claude\PTTAUTOPOST`）
只有文件（README、`docs/`）。**沒有原始碼、沒有依賴宣告、沒有虛擬環境、不是 Git 儲存庫**。因此「沿用既有設計」的對象不是本專案舊碼（已由使用者刪除），而是**使用者其他 Python 專案的設計慣例**（§2.3、§2.4）。

### 2.2 執行環境（已觀察）

| 項目 | 觀察 |
|------|------|
| Python | **3.12.10**（MSC v.1943 64-bit），安裝於 `%LOCALAPPDATA%\Programs\Python\Python312`，**全域安裝，無 venv** |
| 作業系統 | Windows 11（10.0.26200） |
| pip | 25.0.1；`pip check`：**No broken requirements found** |
| GUI／打包／測試 | PySide6 **6.11.2**（Essentials／Addons 6.11.2、shiboken6 6.11.2）、PyInstaller **6.22.2**（hooks-contrib 2026.7）、pytest **9.1.1**、hypothesis **6.168.1**、pywin32 **312** |
| 解析相關 | beautifulsoup4 **4.15.0**、lxml **6.1.1**、soupsieve 2.9.2、charset-normalizer **3.4.9**、requests **2.34.2**（urllib3 2.7.0、certifi 2026.7.22、idna 3.18）、PyYAML **6.0.3**、python-dateutil 2.9.0.post0、tzdata 2026.3 |
| 影像（模式 B 候選） | opencv-python-headless **5.0.0.93**、numpy **2.5.2**、pillow 12.3.0 |
| SQLite | 函式庫 **3.49.1**；**FTS5 可建立**、JSON 函式可用、`THREADSAFE=1` |
| **未安裝** | trafilatura、html5lib、chardet、readability、rapidfuzz、regex、httpx、pytest-qt、tldextract、w3lib |
| 與本專案無關但同環境存在 | pandas 3.0.5、onnxruntime 1.20.1、sympy 1.14.0、pymupdf 1.28.2、markitdown 0.1.7、magika 0.6.3、openpyxl 3.1.5、reportlab、pikepdf、oletools… |

### 2.3 既有專案 A：OQCTOOL（`D:\Visual Studio Code\PROJECT\OQCTOOL`）——**與本專案最接近**
Python＋**PySide6**＋openpyxl；已有 PyInstaller 可攜版流程。

| 面向 | 既有做法（已閱讀） |
|------|--------------------|
| 結構 | 根目錄 `main.py`；`src/` 內 `models/`、`services/`、`ui/`（含 `widgets/`）、`utils/`、`version.py`；`tests/`、`tools/`、`config/`、`logs/`、`docs/` |
| 依賴 | `requirements.txt`：`PySide6>=6.6`、`openpyxl>=3.1`、`pyinstaller>=6.0`（**未鎖定版本**） |
| 打包 | PyInstaller **onefile**、windowed（無主控台）、**`upx=True`**；`make_portable.bat`（純 ASCII）呼叫 `tools/make_portable.py` 三步：`--build`、組裝可攜資料夾（EXE＋`config\`＋`logs\`）、`--verify`（驗證 EXE 內含最新修正與版本一致） |
| 為何 `.bat` 只留 ASCII | 內含說明：UTF-8 中文路徑在 cp950 的 cmd 下會變亂碼，導致 `mkdir ""` 失敗卻「顯示成功」、**舊版 EXE 殘留**；因此中文路徑操作全部移到 Python |
| 設定 | `config/settings.json`，位於 EXE 同層（打包時取 `sys.executable` 所在資料夾；開發時取專案根）；有 `SettingsManager`、**原子寫入** |
| 日誌 | `logs/app_YYYYMMDD.log`，`TimedRotatingFileHandler`（午夜輪替、保留 30 份）、單一共用 handler、INFO 只留重要事件 |
| 版本 | `src/version.py` 為**單一真實來源**（版號、建置日期、CHANGELOG）；`tools/bump_version.py`；`tests/version_check.py` 強制檢查「進版」與一致性 |
| 測試 | `pytest`（`tests/test_*.py`）＋獨立 `*_check.py` 腳本（UI／E2E，需個別執行）；中文 emoji 輸出需 `PYTHONUTF8=1` |
| 協作規範 | `AGENTS.md`：繁中回覆；最小修改；不自行擴大範圍；**不自動 commit／push／打包**；階段結束固定六段報告並停止；受保護模組清單；效能最佳化凍結 |
| Git | 有 `.git`，工作樹有**未提交的修改**（與本稽核無關，**未碰**） |

### 2.4 既有專案 B：電容規格書數據擷取與檢驗工具（`D:\Visual Studio Code\PROJECT\電容規格書數據擷取與檢驗工具VS版`）——**有網路擷取與解析的設計**
Python＋**tkinter**（非 PySide6）；PyInstaller onefile。

| 面向 | 既有做法（已閱讀） |
|------|--------------------|
| 結構 | 根目錄 `launcher.py`／`run_gui.py`；`src/` 內 `engines/`、`parsers/`（含 `online_spec.py`、`spec_pdf.py`）、`validation/`、`exporters/`、`models/`、`ui/`、`errors.py`、`logging_setup.py`、`pipeline.py`、`cli.py` |
| 依賴 | `requirements.txt` **鎖定版本**（`==`）並註明環境（Python 3.12.10／Windows）；含 `requests`、`beautifulsoup4`、`pytest==9.1.1`、`hypothesis==6.168.1` |
| 例外階層 | `errors.py`：`ToolError`（基底）→ `InputError`／`ParseError`／`ValidationError`／`ExportError`／`NetworkError`／`ConfigurationError`／`UnexpectedError`；UI 只攔截基底；禁止 silent failure |
| 網路擷取原則（`online_spec.py` 文件） | 來源可追溯（記錄 URL 與站名）；**絕不偽造**（抓不到就回報失敗並附原因）；錯誤分層；保守解析；**不修改來源**（只下載副本）；遇反爬頁面丟 `NetworkError` 並說明、改引導手動；**「以一般使用者可見內容為限」、不繞過任何保護機制** |
| 測試 | `pytest.ini`（`testpaths = tests`）；以 mock session 測邏輯（無網路）＋**實測檔 `test_online_spec_live.py` 預設略過，需環境變數 `CAPTOOL_LIVE_ONLINE=1` 才執行**（契約回歸測試） |
| 版權樣本 | `.gitignore` 排除 `tests/fixtures/real_pdfs/`（註明「含原廠版權內容，不可納入版控」） |
| 打包 | `build.spec`＋`build_exe.ps1`；onefile／windowed；`EXCLUDES` 明列排除 pandas、numpy、scipy、IPython、其他 Qt 綁定、pytest、hypothesis 等以縮小體積；`datas` 帶入 `assets/`；有 onedir 切換說明 |
| Git | 該資料夾**不是** Git 儲存庫 |

---

## 3. 結論：基線與沿用

1. **Python 基線成立**：Python 3.12.10、PySide6 6.11.2、PyInstaller 6.22.2、pytest 9.1.1、hypothesis、lxml／bs4／requests／PyYAML／charset-normalizer、SQLite 3.49.1（FTS5）**皆已就緒且 `pip check` 乾淨**；使用者已有兩個同棧專案，因此**沒有技術棧遷移的必要**。
2. **沿用使用者既有設計**（§4）；本專案不重新發明目錄結構、打包流程、版本管理、例外階層、日誌與設定慣例。
3. **差異只有三處**（皆非技術棧遷移）：虛擬環境（Q-28）、打包形態的取捨（V-24／V-25）、背景執行緒（既有 OQCTOOL 的「禁止 QThread」是其專案凍結規則，不適用於本專案的抓取／解析）。

---

## 4. 沿用決策表

| # | 項目 | 既有做法 | 本專案採用 | 備註 |
|---|------|----------|------------|------|
| 1 | 語言／UI | Python 3.12＋PySide6（OQCTOOL） | **採用** | 不採 tkinter |
| 2 | 專案結構 | 根目錄入口＋`src/` 平面套件（`models`、`services`、`ui`、`utils`／`parsers`、`validation`、`errors.py`、`logging_setup.py`、`version.py`）；`tests/`、`tools/`、`config/`、`logs/`、`docs/` | **採用**；新增 `storage/`、`delivery/`；解析器架構放 `src/parsers/`（沿用既有 `parsers` 命名） | ARCHITECTURE §4 已改寫 |
| 3 | 例外 | `ToolError` 階層 | **採用並擴充**（`DeliveryError`、`StorageError`、`SnapshotError`…）；以 `source`／`detail` 欄位對應 `E-EXT-*` 等錯誤碼家族 | UI 只攔截基底 |
| 4 | 日誌 | `logs/` 同層；每日輪替、保留 30 份；單一共用 handler | **採用**；另加**遮蔽 filter**（SRS FR-801） | |
| 5 | 設定 | `config/settings.json` 同層、原子寫入、`runtime_base_dir()` | **採用**；資料庫與備份放 `data/` | 不用 `__file__` 推算打包後路徑 |
| 6 | 版本 | `src/version.py`＋`bump_version`＋版本檢查測試 | **採用** | |
| 7 | 打包 | onefile、windowed；`tools/make_portable.py`（`--build`／組裝／`--verify`）；`.bat` 僅 ASCII；`-X utf8`；`EXCLUDES` 清單 | **採用為基線**（取代先前文件的「one-folder 優先」）；one-folder 作為 V-24／V-25 失敗時的退路 | **本階段不打包** |
| 8 | UPX | `upx=True`（OQCTOOL） | **不沿用**（Q-29） | 防毒誤判風險 |
| 9 | 測試 | `pytest.ini`（`testpaths`）；`tests/test_*.py`；UI 另有 `*_check.py` 腳本；hypothesis 做屬性測試 | **採用** | `pytest-qt` 未安裝，UI 測試風格待評估（V-26） |
| 10 | 線上測試 | 預設略過，需環境變數才執行；mock 與 live 分檔 | **採用**（環境變數名稱：`PTTPOST_LIVE`，Phase 1 定案） | 對應 FR-115 線上抽查 |
| 11 | 版權樣本 | `.gitignore` 排除真實樣本 | **採用**（FR-116、TEST_CORPUS §7.3） | |
| 12 | 依賴宣告 | `requirements.txt`；電容專案以 `==` 鎖定並註明環境 | **採用「鎖定」版本**；搭配專用 venv（Q-28） | OQCTOOL 的 `>=` 不採用 |
| 13 | 網路擷取原則 | 來源可追溯、絕不偽造、錯誤分層、保守解析、不修改來源、**不繞過保護機制** | **採用為解析器設計原則**（SRS FR-103、111） | 與使用者決策 1 一致 |
| 14 | AI 協作規範 | `AGENTS.md`（繁中、最小修改、不自動 commit／打包、六段階段報告） | **建議採用**（Phase 1 建立；Q-37） | |
| 15 | 背景執行緒 | OQCTOOL 凍結「禁止 QThread」 | **不沿用** | 抓取、解析、備份必須背景執行（SRS NFR-02）；採 `QThreadPool`／`QRunnable`，並以測試證明 UI 不凍結 |

---

## 5. 相容性問題與風險清單

「已觀察」＝本次實際看到；「未驗證」＝尚無證據。**沒有任何一項已在本專案中實測通過打包。**

| ID | 問題 | 證據 | 嚴重度 | 狀態／處置 |
|----|------|------|--------|------------|
| K-1 | **全域 Python 環境、無 venv**，含大量無關套件（pandas、numpy、onnxruntime、sympy、pymupdf、markitdown…）；PyInstaller 在此環境打包易拖入多餘模組、造成體積暴增與不可重現 | `pip list`；既有兩專案皆依賴全域環境，電容專案以 `EXCLUDES` 補救 | 高 | Q-28：建立專用 venv＋鎖定依賴；`EXCLUDES` 清單沿用；V-23 |
| K-2 | OQCTOOL 依賴宣告為 `PySide6>=6.6`，本機為 **6.11.2**；PySide6 次版本差異可能影響打包與行為 | requirements／pip list | 中 | 鎖定 `PySide6==6.11.2`（或經 spike 選定版本）；V-24 |
| K-3 | **PyInstaller 6.22.2＋Python 3.12.10＋PySide6 6.11.2＋onefile** 未實測（啟動時間、體積、Qt 外掛、隱藏匯入） | 僅觀察到版本 | 高 | V-24（Phase 1 spike） |
| K-4 | OQCTOOL spec 使用 **UPX**；UPX 常提高防毒／SmartScreen 誤判 | `.spec` | 中 | 本專案預設不用（Q-29）；V-25 |
| K-5 | **Windows 主控台 cp950**：中文／emoji 輸出會 `UnicodeEncodeError`；`.bat` 讀 UTF-8 中文路徑會亂碼並造成「顯示成功但舊檔殘留」（既有專案已發生事故） | OQCTOOL `AGENTS.md`、`make_portable.py` 說明 | 中 | 沿用：`-X utf8`、`.bat` 僅 ASCII、路徑操作寫在 Python；AT-PRT 納入含中文與空白路徑的案例 |
| K-6 | 專案路徑慣例含**中文與空白**（`D:\Visual Studio Code\PROJECT\…`）；本專案位於 `D:\Claude\PTTAUTOPOST` | 目錄觀察 | 低 | 測試時包含含中文／空白的安裝路徑 |
| K-7 | **`pytest-qt` 未安裝**；既有 UI 測試用獨立 `*_check.py` | pip list／tests 目錄 | 低 | 評估採用既有腳本風格或新增 `pytest-qt`（V-26） |
| K-8 | **正文抽取程式庫未定**：`trafilatura`、`html5lib` 未安裝；已有 lxml 6.1.1、bs4 4.15.0、charset-normalizer 3.4.9 | 匯入探針 | 中 | V-26：以 TEST_CORPUS 評選；**不得未評選就加入依賴** |
| K-9 | `opencv-python-headless 5.0.0.93`、`numpy 2.5.2`、`pywin32 312` 為模式 B 候選；若誤入 M1 的打包會增加體積 | pip list | 低 | M1 的 spec 明確排除；模式 B 屬 M3 |
| K-10 | SQLite **3.49.1** 含 FTS5／JSON 已觀察；**WAL 在可攜式／隨身碟／雲端同步資料夾**行為未驗證 | 記憶體資料庫查詢 | 中 | V-02 |
| K-11 | **Python 3.12 已棄用 `sqlite3` 預設 datetime adapter**（會產生 DeprecationWarning）；本專案以 UTC ISO 8601 字串存時間 | 官方行為（3.12）；本次執行 `sqlite3.version` 亦出現棄用警告 | 低 | 設計上不使用預設 adapter，明確轉換字串 |
| K-12 | **PySide6（LGPL）以 onefile 散布**的授權遵循要求 | 授權性質 | 中 | Phase 1 確認（**非法律建議**，須諮詢專業人士） |
| K-13 | 既有專案的 requirements 未鎖版本（OQCTOOL）與鎖版本（電容）不一致 | requirements | 低 | 本專案採鎖定 |
| K-14 | 既有 OQCTOOL 工作樹有未提交修改 | `git status`（唯讀） | — | **與本稽核無關，未碰**；僅提醒 |

---

## 6. 驗證狀態彙整

| 類別 | 項目 |
|------|------|
| **已觀察（版本／匯入）** | Python 3.12.10；PySide6 6.11.2（Core／Widgets／Gui 可匯入）；PyInstaller 6.22.2；pytest 9.1.1；hypothesis 6.168.1；lxml、bs4、requests、PyYAML、charset-normalizer、pywin32（`win32api`／`win32gui`／`win32clipboard`）、cv2、numpy、PIL 可匯入；`pip check` 乾淨；SQLite 3.49.1＋FTS5＋JSON |
| **未驗證** | 任何打包（K-3、K-4）；venv 可重現性（K-1）；候選解析程式庫表現（K-8）；SQLite 於可攜式環境（K-10）；PySide6 散布授權（K-12）；UI 測試風格（K-7）；既有專案測試是否目前全綠（**未執行**，亦非本專案範圍） |

---

## 7. 對規格與架構的影響（已同步修訂）

- ARCHITECTURE §2：技術棧決策改為「**維持 Python 基線（已決議）**」；打包基線改為既有的 onefile＋`make_portable` 流程；退出準則保留。
- ARCHITECTURE §4：目錄改採既有 `src/` 平面套件慣例。
- ARCHITECTURE §12：目錄配置改為 `config\`、`logs\`、`data\`。
- SRS：FR-702／804 對齊既有 `config\settings.json`；新增 Q-28、Q-29、Q-37 與 V-23～V-26。
- IMPLEMENTATION_PLAN Phase 1：新增 venv／requirements 鎖定、`version.py`、`make_portable` 移植、`AGENTS.md`、`pytest.ini`。
