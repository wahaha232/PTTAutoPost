# PTT AutoPost 程式碼審查與改進報告（2026-10-27）

- 審查對象：`D:\Claude\PTTAUTOPOST`，分支 `dev/roadmap`，版本 0.8.17（commit `0783672`，領先 main 2 個提交，已推送 origin）
- 範圍：`main.py` 與 `src/` 全部模組（約 10,500 行）、`tests/`（32 個檔案）、打包與更新流程
- 方式：唯讀審查，沒有修改任何程式碼。網路／更新／儲存層由我逐行閱讀；UI 層與解析／終端模組由兩個子代理平行審查，重點項目我再回原始碼抽查
- 嚴重度：P0 致命／P1 高（會造成資料損毀或使用者明顯受害）／P2 中／P3 低

> **修正狀態（2026-10-27）**
> - 0.8.18：已修 P1-1、P1-2、P2-15、P3-20，以及測試視窗洩漏。
> - 0.8.19：已修其餘全部 P1～P3（P2-1 至 P2-16、P3-17 至 P3-39）。
>   - P2-6 改用自建的 Ed25519 更新簽章（不買憑證），私鑰放在儲存庫外。
>   - P2-16 已查證 pttbbs 的 `TTLEN = 64`，錯誤門檻改為 64、提醒門檻為 46。
> - 尚未處理：第五節的架構項目，包括拆分 MainWindow／抽出 TaskRunner、加 CI、整理 docs 索引、清理 dist。

---

## 一、總評

整體品質在個人專案中屬於上乘，安全設計很有意識：

- 帳密只送給 `ws.ptt.cc`（精確比對主機、port、path），密碼送出後立即清掉，log 有自動遮蔽
- 自動輸入不會送出 Enter、Ctrl-X 或存檔；每一段送出前都重新核對畫面，不符就停止，不會重送
- 文章擷取有逐跳 SSRF 檢查與 DNS 綁定，IPv4-mapped 與 NAT64 位址都會擋
- 更新檔必須附 SHA-256，ZIP 路徑有防穿越檢查，主機採白名單
- `SendLock` 讓自動輸入與貼上互斥；SQLite 用 WAL，升級 schema 前會先備份
- 背景工作只透過 signal 把純資料傳回 GUI thread，worker 不會直接碰 widget

主要風險集中在三處：
1. **UI 邊界情況**：PySide slot 參數陷阱、輸入互斥漏了一個入口、非同步結果寫錯草稿
2. **更新套用缺少回滾**：失敗時可能留下新舊混雜的版本
3. **解析不可信網頁時的例外處理不完整**：一個壞欄位就會讓整篇擷取失敗

**沒有發現 P0。**

---

## 二、P1：建議優先修正

| # | 位置 | 問題 | 情境 | 建議修法 |
|---|---|---|---|---|
| 1 | `src/ui/main_window.py:1790`、`:2472` | `btn_sig_del.clicked.connect(self.delete_signature)`：`clicked(bool)` 會把 `False` 傳給 `confirm` 參數 | 按「刪除簽名檔」不會跳確認，直接永久刪除（已抽查原始碼，子代理在 PySide6 實測過） | 改為 `clicked.connect(lambda: self.delete_signature())`，或把 `confirm` 改成只能以關鍵字傳入 |
| 2 | `src/ui/terminal_widget.py:608` `inputMethodEvent` | 只檢查 `locked`，沒有檢查 `pasting`；`client.send()` 本身也不看 `SendLock` | 多行貼上分段送出時，用注音輸入一個字，Big5 bytes 會插進貼上內容中間，破壞文章（已抽查） | 開頭比照 `keyPressEvent` 加上 `if self.pasting:` 檢查；長期做法是讓 `send_user_bytes` 在 lock 被占用時拒絕 |
| 3 | `main_window.py:2007-2050` `_fetch_done`；`open_selected`:2819、`new_draft`:2733 | 擷取標示為「背景執行，可繼續操作」，但完成時直接覆寫所有欄位並把 `draft_id` 設為 None | 擷取期間開啟草稿 #5 並修改，擷取完成後修改被無聲覆蓋 | 擷取中禁止開啟或新增草稿（比照 `clear_all_fields`），或在完成時偵測到變更就再確認一次 |
| 4 | `src/update.py:345-364` 套用腳本 | `Copy-Item` 中途失敗時只寫錯誤 log，沒有用 backup 回復，之後仍啟動 exe | 磁碟滿或防毒鎖住某個 DLL，結果新舊檔案混雜，程式可能無法啟動 | `catch` 區塊把 `$backup` 中已備份的檔案還原，並刪除新加入的檔案；啟動後讓程式讀取 `apply-error.log` 並提示使用者 |

---

## 三、P2：中度

### 更新與連線

5. **`update.py:228`、`234`、`334`、`336`：manifest 的 `version` 沒驗證就拿來組路徑**
   - `staging-{version}` 會被 `rmtree` 刪除，`version` 又直接拼進 backup 路徑與 `.ps1` 檔名。
   - 若 `version` 含 `../`，`rmtree` 會刪到 updates 資料夾以外。這需要 Release 本身被惡意置換才會發生，屬於縱深防禦。
   - 建議：要求 `parse_version(version)` 成功，並且等於 Release 的 tag 版本。
6. **`update.py`：SHA-256 只能保證「完整性」，無法保證「來源」**
   - digest 與檔案都來自同一個 GitHub Release。只要 GitHub 帳號或 token 外洩，攻擊者就能發布帶有正確 digest 的惡意更新。
   - 建議：日後公開發佈前，加上 Authenticode 程式碼簽章，或用內嵌公鑰的 minisign／ed25519 驗證 manifest。
7. **`main_window.py:1250-1277`：`stage_delta`／`stage_full_zip` 在 GUI thread 執行**
   - 解壓數十 MB 的 ZIP 加上 `rmtree`，視窗會「沒有回應」數秒。
   - 建議：移到 `UpdateDownloadTask` 或另一個 QRunnable。
8. **`main_window.py:1273-1283`：自動更新可能在輸入或貼上進行中關閉程式**
   - `_confirm_unsaved` 只看 `_dirty`，而輸入前已存過草稿，所以會直接放行。賺 P 幣模式逐字輸入時（可能好幾分鐘），文章會停在一半。
   - 建議：檢查 `typer.running`／`term.pasting`，若在進行中就延後套用。
9. **`src/net/client.py:26` 的 `ORIGIN` 寫死為 `https://term.ptt.cc`**
   - 預設站台「PTT2」(`ws.ptt2.cc`) 需要 `Origin: https://term.ptt2.cc`（10-22 probe 已證實），目前必定 403。`sites.py:19` 的備註也寫著握手 403。
   - 建議：在站台資料加入 `origin` 欄位，連線時帶入。
   - 另外 `sites.py:3` 的 docstring 仍寫「Only WSS is supported」，但 0.8.x 已支援 Telnet，需要更新。

### 草稿與 UI

10. **`main_window.py:2889`：刪除「目前開啟且有未存修改」的草稿後，`draft_id` 仍指向已刪除的那筆**
    - 之後每次儲存都會因 `rowcount==0` 失敗，只能選「放棄」。
    - 建議：刪除目前草稿時，把 `draft_id` 設為 None。
11. **`main_window.py:2355`、`:1941`：縮網址與上傳圖片的非同步結果會寫進「當下」的草稿**
    - 中途切換草稿，結果就會寫到別篇。回覆模式下網址插進 `body`，但實際輸入的是 `notes`，所以網址根本不會被打上去。
    - 建議：發起時記錄 `draft_id`，回來時比對不一致就只顯示結果、不寫入；回覆模式改插入 `notes`。

### 解析不可信網頁（子代理已用本機 Python 實際驗證）

12. **`src/parsers/extract.py:225-238`、`558`：JSON-LD 欄位沒檢查型別**
    - `"headline":["a","b"]` 會造成 `AttributeError`，整篇擷取失敗。
    - 建議：只接受 `str`，list 取第一個字串元素。
13. **`extract.py:742` 等 6 處：`urljoin()` 遇到 `http://[bad/` 會拋 `ValueError`，沒有捕捉**
    - 一個壞連結就讓整篇擷取失敗。
    - 建議：包一個 `_safe_join()`，失敗時回傳空字串。
14. **`extract.py:559-562`：canonical／og:url 沒驗證 scheme，網域只比對最後兩段**
    - `attacker.com.tw` 的頁面可以把「完整新聞連結」換成 `cna.com.tw` 的網址。`javascript://` 也會被採用，之後可能被寫進公開貼文（已抽查原始碼）。
    - 建議：先通過 `validate_http_url`，主機比對改用 public-suffix 規則。
15. **`src/compose.py:215-216`：子字串判斷與 `lines.index()` 整行比對不一致**
    - 網址與標籤打在同一行時，`check()` 拋出 `ValueError`，「檢查」與「複製」都會靜默失敗（已抽查原始碼）。
    - 建議：改成 `next((i for i, l in enumerate(lines) if l.startswith(prefix)), None)`。
16. **`compose.py:19-20`（疑似）：標題錯誤門檻是 78 bytes**
    - pttbbs 的 `TTLEN` 可能是 64，而且還要扣掉「[分類] 」前綴。尚未對照 pttbbs 原始碼確認。
    - 建議：查證後調整門檻。

---

## 四、P3：低

| # | 位置 | 問題與建議 |
|---|---|---|
| 17 | `update.py:263` | delta 的 `delete` 清單沒有排除 `config/data/logs/updates`，`stage_full_zip` 則有排除。兩者應一致 |
| 18 | `update.py:254` | `if ...:` 與 `raise` 寫在同一行（中間只有空白），可讀性差，疑似合併時誤刪換行 |
| 19 | `update.py` | 私人儲存庫的 `browser_download_url` 帶 Bearer token 會 404。要支援私庫更新，應改走 API asset URL，並帶 `Accept: application/octet-stream` |
| 20 | `net/paster.py:324-326` | `acquire(PASTE)` 之後才呼叫 `build_chunks`。若傳入無法用 cp950 編碼的文字，會拋例外並讓 lock 永久卡住。目前 UI 有先檢查，但 `PasteSender.start` 應自行驗證，或用 try/finally 釋放 lock |
| 21 | `net/client.py:206` | 忽略 `sendBinaryMessage` 的回傳值；送出 0 bytes 時仍會回報成功 |
| 22 | `storage/db.py` events 表 | 沒有清理機制，會無限成長。建議只保留 N 天或 N 筆 |
| 23 | `db.py:640` | 刪除任何簽名檔後，作用中的簽名檔一律重設為第 1 則，可能悄悄換掉使用者原本選的那則 |
| 24 | `parsers/fetch.py:178` | 沒擋 CGNAT `100.64.0.0/10`。建議改用 `not addr.is_global` 判斷 |
| 25 | `fetch.py:326` | 壞 port（`:99999`）會拋 `ValueError`，畫面只顯示「未預期的錯誤」 |
| 26 | `fetch.py:286-299` | 宣告 big5 時用嚴格 big5 解碼，遇到碁、銹、恒等 cp950 才有的字會失敗；也抓不到帶引號的 `charset="utf-8"` |
| 27 | `fetch.py:49`（疑似） | requests 預設讀取 `HTTPS_PROXY` 環境變數，會繞過 DNS 綁定。建議設定 `trust_env=False` |
| 28 | `net/image.py:64` | Referer 設在 session 層級，跨主機重新導向時會把原文網址洩漏給第三方 |
| 29 | `net/image_meta.py` | 動態 WebP／APNG 只會存第一格，每格 duration 會遺失；上千格的 GIF 會耗用大量記憶體 |
| 30 | `upload.py`、`shortener.py` | 回應沒有用 stream，整個讀進記憶體後才截斷 |
| 31 | `terminal/screen.py:234-260` | `ESC[P/@/X/K` 遇到被切開的全形字時，會留下孤立的後半格，使連結與選取錯位 |
| 32 | `sites.py:52` | IPv6 主機組網址時沒有加方括號；`int(port)` 遇到非數字會拋例外 |
| 33 | `links.py:17` | 結尾一律去掉 `)`，`Foo_(bar)` 這類網址會被截斷 |
| 34 | `main_window.py:2819` | 開啟草稿時沒有清掉上一篇的圖片清單，「打包下載圖片」會下載到前一篇的圖 |
| 35 | `main_window.py:2834` | `_loading=True` 沒有 try/finally；中途出錯後就再也不會標記修改 |
| 36 | `main_window.py:3171` | `_build_tray` 在 `show()` 之前呼叫，所以即使系統匣選項都關閉，圖示仍會出現 |
| 37 | `main_window.py:3074`、`3088` | 登入小幫手會以 CWD 相對路徑和上兩層目錄搜尋 exe，有執行到同名惡意檔的風險。建議只接受明確指定的絕對路徑 |
| 38 | `main_window.py:2655`、`tasks.py:130` | 「測試連線」：舊結果可能覆蓋新結果；非 OSError 的例外沒有回報，畫面會卡在「測試中」 |
| 39 | `main_window.py:2719` | 草稿搜尋每打一個字就全表 LIKE 查詢一次。建議加 250 ms debounce |

---

## 五、架構與工程面

1. **`main_window.py` 有 3,270 行、約 250 個方法**，同時管終端機、文章、草稿、站台、設定、更新、系統匣。大量 `hasattr`／`getattr` 防禦代表初始化順序互相耦合。建議依分頁拆成子 widget 或 controller。0.9 要做的「多分頁」會直接受這點影響，**建議先拆再做**。
2. **背景工作的接線樣板重複 6 次以上**（busy 旗標、停用按鈕、接 signal、start、完成／失敗後還原），`_cancel_background_tasks` 還要手動列出每個 task。建議抽成共用的 `TaskRunner`；P2-8、P2-11、P3-38 這類「結果回來時情境已經變了」的問題，也可以一次在這裡解決（task 帶 generation id 或 draft_id）。
3. **沒有 CI**（沒有 `.github/workflows`）。建議加一個 GitHub Actions（windows-latest，`QT_QPA_PLATFORM=offscreen`），執行 pytest 加 ruff；目前 `pytest.ini` 已經把 live 測試分開，直接可用。
4. **相依套件**：`requirements.txt` 只有下限。已有 `constraints-build.txt`，建議在 README 註明打包一律使用它，避免 PySide6 小版本升級造成行為差異。
5. **本機磁碟**：`dist/` 累積 666 MB 的舊版打包（已被 gitignore），可以定期清理。
6. **文件**：docs 裡有多份 AUDIT／PLAN／REVIEW，新舊並存。建議在 `docs/README.md` 列出哪些是現行文件、哪些是歷史文件。

---

## 六、測試缺口

- **UI**：簽名檔刪除確認、IME 在貼上中的行為、擷取中切換草稿、刪除目前草稿後儲存，目前都沒有測試
- **更新**：套用失敗後的回滾，以及 manifest `version` 不合法的情況
- **extract**：非字串的 JSON-LD、壞的 href／srcset／canonical、跨網域與非 http 的 canonical、極端時區
- **compose**：網址與標籤同一行；標題 bytes 邊界值（64／65／78）
- **fetch**：非法 port、`100.64.0.0/10`、帶引號的 charset、含 cp950 專有字的 big5 頁面
- **screen／selection**：全形字邊界上的刪除與插入，以及 col 0 是孤立後半格的情況
- **image_meta**：動態 WebP／APNG、每格 duration

---

## 七、建議修正順序

1. **立即（30 分鐘內可修完，風險低）**：P1-1 簽名檔確認、P1-2 IME 貼上鎖、P2-15 compose 例外、P3-20 paster lock 釋放，以及修正測試 fixture 的視窗洩漏（第八節），讓 `pytest` 能一次跑完
2. **0.8.18**：P1-3 擷取覆寫、P1-4 更新回滾、P2-5 version 驗證、P2-8 更新避開輸入中、P2-10、P2-11、P2-12～14 解析強化，並補上對應測試
3. **0.9 前**：P2-9 每站台 Origin（PTT2 才能使用）、P2-7 解壓移出 GUI thread、拆分 MainWindow 與 TaskRunner、加 CI
4. **公開發佈前**：P2-6 程式碼簽章或 manifest 簽章、查證 TTLEN（P2-16）

---

## 八、測試執行

- 直接執行 `python -m pytest`：跑到 `tests/test_ui.py::test_theme_combo_applies_and_persists` 後就停住，超過 15 分鐘沒有結束
- **原因（已傾印堆疊確認）**：
  - `win` fixture 只做 `db.close()`，沒有 `close()`／`deleteLater()` 建立的 `MainWindow`
  - 跑到第 60 幾個 UI 測試時，記憶體中已累積數十個主視窗
  - `apply_theme()` 呼叫 `app.setStyleSheet()` 時會重新 polish 所有視窗，非常慢，看起來就像卡死
  - 這個測試單獨執行只要 4.7 秒就通過，所以是測試資源洩漏，不是程式本身的死結
- 排除這一項後：**482 passed、1 deselected、1 warning，耗時 400 秒**
- **建議（P2）**：fixture 結束時加上 `w.close(); w.deleteLater(); pump(0)`，`test_theme_restores_and_corrupt_falls_back` 也一樣處理；並安裝 `pytest-timeout`（例如 `timeout = 120`），讓卡住的測試直接失敗，不會無限等待
