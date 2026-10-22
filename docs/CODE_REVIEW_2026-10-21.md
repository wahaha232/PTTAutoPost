# PTT AutoPost 程式碼檢視報告

- **檢視日期**：2026-10-21
- **檢視範圍**：`main.py`、`src/` 全部模組、`tests/`、`tools/`、`PTTAutoPost.spec`、`make_portable.bat`、`README.md`
- **檢視方式**：逐檔閱讀、執行測試、靜態檢查、針對可疑流程做唯讀重現
- **本次性質**：只檢視與提出建議，**未修改任何程式碼**
- **測試結果**：`python -m pytest -q` → **122 passed**
- **靜態檢查**：`python -m pyflakes src main.py tools` 與 `python -m pyflakes tests` 有少數未使用變數/import
- **版本**：`src/version.py` 為 `0.5.3`（BUILD_DATE `2026/10/16`）

---

## 一、整體結論

這個專案的安全設計與測試品質明顯高於一般桌面小工具，特別是：

- 「只輸入文字、絕不按 Enter／Ctrl-X／存檔」的硬性保證，並用假 BBS 逐 byte 驗證。
- 登入密碼只送一次、不儲存、不寫 log；連線中斷不自動重連、不重送。
- 遇到 robots、登入牆、付費牆、前端渲染頁面時只回報原因，不繞過。
- `Screen`、Big5、ANSI、IAC 的邊界案例測得很細。
- 錯誤訊息、狀態標示、註解與 docstring 都相當清楚。

但目前有 **3 個會直接造成錯誤內容、崩潰或資料遺失的高優先問題**，以及數個資料一致性、併發與錯誤處理問題。建議先修 P1，再處理 P2。

| 等級 | 代表問題 | 建議時程 |
|---|---|---|
| **P1 高** | 檢查器崩潰、複製／輸入到過期預覽、未儲存內容被無提示覆蓋 | 立即 |
| **P2 中** | 解析器全域狀態污染、草稿／輸入狀態錯亂、設定檔損壞崩潰、手動輸入與自動輸入交錯、簽名檔未快照、錯誤處理與效能 | 近期 |
| **P3 低** | 文件過時、原始碼含不可見控制字元、UI 小瑕疵、打包與測試衛生 | 有空再做 |

---

## 二、P1：高優先問題

### P1-1 `compose.check()` 會拋出 `ValueError`，連帶讓「檢查／複製／輸入」失敗

**位置**：`src/compose.py:183`

```python
if line.strip() == "--" and not (used_signature and i == body.rstrip().split("\n").index("--") + 1):
```

**問題**：`line.strip() == "--"` 會把 `" -- "`、`"\t--"` 這類行也視為分隔線；但後面用 `.index("--")` 只找**完全等於** `"--"` 的行。若預覽被手動修改成有 `" -- "`、但沒有精確的 `"--"` 行，且 `used_signature=True`，就會拋出：

```text
ValueError: '--' is not in list
```

**重現**（已實測）：

```python
from src.compose import check
check("t", "內容\n -- \n", "sig", True)
# ValueError: '--' is not in list
```

**影響**：`run_checks()` 沒有 catch，會往上冒到 `copy()`、`type_into_ptt()` 等 Qt slot。使用者按下「檢查」、「複製」或「輸入內文」時可能直接看到例外，該次操作失敗。預覽可手動編輯，所以這不是理論路徑。

**建議**：

- 先算一次精確分隔線索引，例如 `sep = next((n for n, l in enumerate(lines, 1) if l == "--"), None)`。
- 用 `sep` 判斷，不要在迴圈內重複 `.index()`。
- 若要支援 `" -- "`，就統一用 `line.strip()` 判斷並同步用 `strip()` 找索引，或直接把「是否為系統簽名分隔線」由 `render()` 回傳位置，不要用字串搜尋猜。
- 補 regression test：`check()` 遇到 `" -- "` 不得崩潰。

---

### P1-2 「複製／輸入」可能使用 350ms 前的過期預覽

**位置**：`src/ui/main_window.py:604-612`、`632-635`、`649-660`、`919-951`

**問題**：欄位變更只會啟動 350ms 的 debounce timer：

```python
def _schedule_preview(self):
    if not self._loading:
        self._refresh_timer.start()      # 350 ms
```

但 `current_texts()` 直接讀 `self.preview.toPlainText()`：

```python
return title, self.preview.toPlainText().rstrip("\n")
```

若使用者在欄位修改後 **350ms 內**按下「複製」或「輸入內文」，`preview` 還是舊內容。`run_checks()` 也會檢查舊內容。

**重現**（已實測）：修改媒體來源後立刻 `copy("body")`，剪貼簿仍是舊的「媒體來源」。

```text
NEW in clipboard: False
OLD in clipboard: True
```

**影響**：這是核心正確性問題。使用者可能以為已複製／輸入最新內容，實際上送到 PTT 的是舊版文章；且因為「檢查」也看舊預覽，可能檢查通過但實際內容不同。

**建議**：

- `current_texts()` 在 `not self._preview_manual` 時先同步 flush：停止 timer 並呼叫 `render_preview()`，再讀取。
- 或在 `copy()`、`type_into_ptt()`、`run_checks()` 開頭強制刷新一次。
- 更根本的作法：不要讓「正確性路徑」依賴 debounce；debounce 只用於畫面更新，複製／輸入前一律重建。
- 補測試：修改欄位後**不 pump event loop**，直接 copy/type，內容必須是最新的。

---

### P1-3 未儲存內容可能被無提示覆蓋或丟棄

**位置**：

- `src/ui/main_window.py:521-572`（`start_fetch` / `_fetch_done`）
- `src/ui/main_window.py:614-622`（`render_preview(force=True)`）
- `src/ui/main_window.py:816-837`（`new_draft`）
- `src/ui/main_window.py:857-897`（`open_selected`）

**問題**：

- 使用者手動填好標題／內文／心得後，貼上 URL 按「擷取」，`_fetch_done` 會直接覆蓋所有欄位，沒有確認。
- 手動修改過的預覽，會被 `preview_manual_reset()` + `render_preview(force=True)` 直接丟棄。
- 按「新增草稿」或從草稿清單開啟另一篇，會直接清空／取代目前編輯內容，沒有「是否儲存」提示。

**影響**：正常操作就可能造成資料遺失，這是桌面編輯器應避免的行為。

**建議**：

- 增加 `_dirty` 狀態（任何欄位／預覽／心得變更設為 True）。
- 在 `new_draft()`、`open_selected()`、`start_fetch()`、`closeEvent()` 前檢查 `_dirty`，詢問「儲存／放棄／取消」。
- 抓取結果要覆蓋目前內容時，至少顯示確認；或把抓取結果先放到「預覽／候選」狀態，由使用者按「套用」。
- 預覽手動修改被強制重建前也要提示。

---

## 三、P2：中優先問題

### P2-1 解析器使用模組級可變狀態，會把上一篇文章的「截斷」狀態帶到下一篇

**位置**：`src/parsers/extract.py:19`、`356`、`430`、`471-472`、`572`；`478-481`

```python
_paragraphs_of.raw_tail = ...          # function attribute
_extract_body.trunc = bool(...)         # function attribute
TIME_NOTES: list[str] = []              # module global
```

**問題**：`_extract_body.trunc` 只在 `_extract_body()` 成功選出候選時設定；若下一次 `parse()` 走 PTT 網頁早期返回（line 478-481，不會呼叫 `_extract_body`），`_finish()` 仍會讀到**上一篇文章留下的 `trunc=True`**，把新文章誤判為 `suspect_partial`。

**重現**（已實測）：

```text
first:  suspect_partial
second: suspect_partial   # 第二次是完整 PTT 文章，仍被標成疑似不完整
```

**影響**：內文完整度判斷錯誤，使用者會被誤導去手動補內容；也讓 `parse()` 不具可重入性，未來若同時抓多篇會互相污染。

**建議**：

- 讓 `_extract_body()` 回傳 `truncated` 布林值，不要用 function attribute。
- `_paragraphs_of()` 的 `raw_tail` 也改成回傳值或 local context。
- `TIME_NOTES` 改成 `parse()` 內的 local list，或傳入 `ParseContext`。
- 每次 `parse()` 都應從乾淨狀態開始；補「先解析截斷文章，再解析完整文章」的測試。

---

### P2-2 `type_into_ptt()` 在草稿不存在時會 `TypeError`

**位置**：`src/ui/main_window.py:927-932`

```python
did = self.draft_id or self.save_draft()
if did is None:
    return
self.save_draft()                       # 回傳值被忽略
d = self.db.get_draft(did)
if target is Target.BODY and d["input_state"] != "none" ...
```

**問題**：

- `self.draft_id` 可能已被另一個視窗／程式刪除；`save_draft()` 更新失敗會回傳 `None`，但第二次呼叫的結果被忽略。
- `get_draft(did)` 回傳 `None`，下一行 `d["input_state"]` 直接 `TypeError`。

**影響**：核心「輸入到 PTT」流程可能直接例外；而且 `save_draft()` 被呼叫兩次，屬於多餘寫入。

**建議**：

- 只呼叫一次 `did = self.save_draft()`，檢查 `None`。
- `d = self.db.get_draft(did)` 後檢查 `if d is None: notice(...); return`。
- 把「目前草稿 id」在輸入開始時快照到 `PostTyper` 或區域變數，不要在完成時讀可變的 `self.draft_id`。

---

### P2-3 輸入過程中切換草稿，完成狀態會寫到錯誤的草稿

**位置**：`src/ui/main_window.py:953-962`、`816-837`、`857-897`

**問題**：`_typing_finished()` 使用當下的 `self.draft_id`：

```python
if self._typing_target is Target.BODY and self.draft_id:
    self.db.set_input_state(self.draft_id, "done" if ok else "aborted")
```

輸入期間使用者仍可從草稿分頁開啟另一篇、按「新增草稿」。完成後狀態會寫到**新草稿**，原草稿可能停留在 `started`，下次啟動被 recovery 改成 `aborted`。這會讓「避免重複輸入」的判斷失準。

**建議**：

- 在 `type_into_ptt()` 開始時把 `draft_id` 存到 `self._typing_draft_id`，完成時用它。
- 輸入期間停用「新增草稿／開啟草稿／刪除草稿」等會改變目前草稿的操作，或切換前先取消輸入。
- 補測試：輸入中切換草稿，原草稿狀態仍正確。

---

### P2-4 設定 JSON 損壞時，`signatures()`／`favorite_boards()` 會拋 `TypeError`，可能讓程式無法啟動

**位置**：`src/storage/db.py:128-138`、`177-181`

**問題**：`json.loads("null")` 合法回傳 `None`，後續 `for i in items` 直接 `TypeError: 'NoneType' object is not iterable`。`signatures()` 只 catch `ValueError, AttributeError`，`favorite_boards()` 只 catch `ValueError`。

**重現**（已實測）：

```text
signatures      TypeError 'NoneType' object is not iterable
favorite_boards TypeError 'NoneType' object is not iterable
```

**影響**：`MainWindow.__init__()` 會呼叫 `active_signature_index` → `signatures()`，以及 `_reload_boards` → `favorite_boards()`；設定值若因舊版格式、手動編輯或寫入中斷而變成 `null`，程式可能在啟動時直接崩潰。

**建議**：

- 讀取後做型別驗證：`if not isinstance(items, list): return []`；每個元素也驗證是 `dict`。
- 失敗時寫一筆 warning（不要靜默吞掉），並提供「重置設定」選項。
- `favorite_boards` 過濾非字串、去重、限制長度。
- 補 corrupt JSON 測試（`null`、物件、字串、混合陣列）。

---

### P2-5 自動輸入／自動登入期間，使用者仍可在終端機手動輸入，造成位元組交錯

**位置**：`src/net/poster.py:146-168`、`src/ui/terminal_widget.py:218-227`、`src/net/session.py:163-206`

**問題**：`PostTyper` 逐段送資料時，`TerminalWidget` 仍接受鍵盤輸入；`PttSession` 登入流程進行中，終端機也沒有鎖住。若使用者在此期間按鍵（特別是 Enter 或 Ctrl-X），就可能：

- 把殘餘的標題 chunk 打進編輯器；
- 提前離開標題提示，讓後續內容進入錯誤畫面；
- 與自動登入的帳號／密碼輸入交錯。

`PostTyper._screen_ok()` 對 TITLE 的後續 chunk 直接回傳 `True`（line 143），所以標題輸入中途畫面被 Enter 帶走時不會停止。

**建議**：

- `PostTyper.running` 或 `Login.LOGGING_IN` 時停用終端機輸入（至少停用 Enter/Ctrl 組合鍵），或把使用者輸入視為「取消自動輸入」。
- 若要保留手動輸入，應在每次 chunk 前重新確認畫面；標題至少確認目前仍在 title prompt（可接受 echo 造成的差異）。
- UI 明確顯示「自動輸入中，鍵盤已暫停」。

---

### P2-6 草稿只記 `use_signature`，沒有快照簽名檔內容／版本

**位置**：`src/storage/db.py:17-18`、`src/ui/main_window.py:598-602`、`857-897`

**問題**：草稿存了 `use_signature`，但簽名文字來自目前全域的 `sig_edit`。開啟舊草稿時，只還原勾選狀態，預覽會用**目前選取的簽名檔**重建。若使用者之後換了簽名檔或刪除舊簽名，舊草稿的內容會悄悄改變，甚至變成沒有簽名。

**影響**：同一篇草稿在不同時間開啟／輸入到 PTT，可能產生不同內容；這與「預覽、複製、輸入共用同一份輸出」的設計目標衝突。

**建議**：

- 草稿額外儲存 `signature_name` / `signature_text`（或 `signature_id` + 內容 hash）。
- 開啟草稿時使用快照；若目前簽名檔與快照不同，顯示提示讓使用者選擇「沿用快照／改用目前簽名」。
- 若簽名檔被刪除，草稿仍能保留當時文字。

---

### P2-7 「允許輸入到非空白編輯區」勾選狀態會跨草稿保留

**位置**：`src/ui/main_window.py:475`、`816-837`、`857-897`

**問題**：`chk_nonempty` 只在建立時設定一次；`new_draft()` 與 `open_selected()` 沒有重設。使用者曾為某一篇勾選「進階」後，下一篇文章會自動沿用，等於在沒有重新確認的情況下允許插入到既有內容。

**建議**：

- `new_draft()`、`open_selected()`、`_typing_finished()` 都重設 `chk_nonempty=False`。
- 或每次輸入前重新要求勾選，不要讓它成為持續性的危險開關。

---

### P2-8 HTTP 串流讀取期間的例外沒有被包成 `FetchError`

**位置**：`src/parsers/fetch.py:145-155`

**問題**：只有 `sess.get()` 被 `try/except requests.RequestException` 包住；`r.iter_content()` 讀取期間若發生 `ChunkedEncodingError`、`ConnectionError`、`ContentDecodingError`，會直接往上拋。`FetchTask.run()` 雖然有 generic `except Exception`，但使用者只會看到「擷取時發生未預期的錯誤」，而不是可理解的「連線中斷／內容解碼失敗」。

**建議**：

- 將 `iter_content` 包在 `try/except requests.RequestException`，轉成 `FetchError("讀取網頁內容時連線中斷。", str(e))`。
- `_fetch_failed()` 目前也忽略 `detail`（`main_window.py:538-544`），建議把 detail 寫入 log，或視情況顯示在警告區。

---

### P2-9 啟動時資料庫／初始化失敗沒有友善處理

**位置**：`main.py:108-109`

```python
win = MainWindow(Database(), PttSession())
```

**問題**：`Database()` 可能因權限、磁碟滿、DB 損壞、版本較新而拋 `StorageError`；`MainWindow` 建構也可能失敗。這是 windowed EXE，沒有 console，使用者可能只看到程式閃退或 PyInstaller 的原始 traceback。

**建議**：

- 在 `main()` 包住 `Database()` 與 `MainWindow()`，`except ToolError` 時用 `QMessageBox.critical` 顯示原因，並寫入 log。
- 安裝 `sys.excepthook` 記錄未處理例外。
- 對 DB 損壞提供「備份後重建」的明確指引，不要自動刪除。

---

### P2-10 發佈版含開發機絕對路徑

**位置**：`src/ui/main_window.py:998`

```python
DEFAULT_PTTLOGIN = "D:/Claude/PTTLOGIN/release/PttAutoLogin.exe"
```

**問題**：這是開發機路徑，會出現在每一位使用者的設定欄位；在別台電腦一定找不到，也暴露內部目錄結構。

**建議**：預設留空，只顯示 placeholder 與「瀏覽…」；不要把任何 `D:/...` 寫進原始碼。

---

### P2-11 缺少依賴清單，README 的安裝資訊不足

**位置**：專案根目錄、`README.md:8`

**問題**：README 只說「Python 3.12 + PySide6」，但實際還需要 `requests`、`beautifulsoup4`、`lxml`，`charset-normalizer` 則是選用但打包時列為 hidden import。沒有 `requirements.txt`、`pyproject.toml` 或 lock file，版本無法重現，新環境很容易啟動失敗。

**建議**：

- 新增 `requirements.txt` 或 `pyproject.toml`，至少固定 `PySide6`、`requests`、`beautifulsoup4`、`lxml` 的主要版本。
- README 補 `pip install -r requirements.txt`、Python 版本、PyInstaller 版本。
- 若要長期維護，考慮 `uv`/`pip-tools` 產生 lock。

---

### P2-12 解析與終端機繪製的效能風險

**位置**：

- `src/parsers/extract.py:473`、`477`：同一份 HTML 被 `BeautifulSoup` 解析兩次。
- `src/parsers/extract.py:350-363`：每個候選容器都用 `str(el)` 重新 parse 一次，最多 18 個候選。
- `src/ui/terminal_widget.py:263-302`：每次畫面更新都逐格 `drawText` / `fillRect`，80×24 = 1920 格。
- `src/ui/terminal_widget.py:176-200`：每次 resize 從 6px 迴圈到 96px 量字型。

**影響**：5MB 上限的頁面可能在 worker thread 花費數秒到數十秒；終端機在快速輸出或高 DPI 大視窗下可能掉格。目前 UI 不會凍結（解析在背景），但使用者會覺得「擷取很久」或終端機卡頓。

**建議**：

- `visible` 直接從已解析的 `doc.get_text()` 取得，不要第二次 parse。
- 候選容器只 parse 一次，或直接在原 DOM 上做 `_paragraph_texts`（用 `copy.copy`／局部走訪），避免 `str(el)` + lxml 重建。
- 終端機可考慮 QPixmap cache、只重繪 dirty rows，或把整頁畫到 cache image 後 blit；先 profile 再優化。
- `_fit()` 可先依公式估算字型大小，再做少量二分搜尋，而不是線性掃 90 次。

---

### P2-13 登入輸入只檢查 ASCII，允許控制字元；MD5 作為畫面去重

**位置**：`src/net/session.py:101`、`167`

**問題**：

- `account.isascii()` 對 `\x00`、`\x1b`、`\t` 等控制字元也回傳 True，只擋了 `\r`／`\n`。若使用者貼上含 ESC 的字串，可能送出終端機控制序列。
- `hashlib.md5` 僅用於畫面去重，但在 FIPS 環境可能被禁用；且沒有安全需求，用 MD5 容易引起誤解。

**建議**：

- 改用 `str.isprintable()`，並限制帳號／密碼長度（例如 1–128）。
- 去重 key 改用 `hashlib.sha256`，或直接使用 `screen.text()` 的 bytes／字串比較。

---

### P2-14 robots 與重新導向的合規細節

**位置**：`src/parsers/fetch.py:106-119`、`135-137`

**問題**：

- 即使使用者勾選 `ignore_robots=True`，程式仍會先抓 `robots.txt`（浪費請求，且與「忽略」語意不一致）。
- 只檢查原始 URL 的 robots；若 HTTP 重新導向到另一個 host，沒有對最終 URL 重新檢查 robots。
- `robots.txt` 的下載沒有大小上限。

**建議**：

- `ignore_robots=True` 時跳過 robots 請求。
- 重新導向後對 `final_url` 重新檢查 robots（或至少記錄警告）。
- robots 回應加上大小上限與 content-type 檢查。

---

## 四、P3：低優先／品質問題

### 文件與版本

- `README.md:9`：`src\x0bersion.py` 含一個 **垂直 Tab（0x0B）**，實際應是 `src\version.py`；同行的「目前 0.2.0」也與 `src/version.py` 的 0.5.3 不符。
- `README.md:20`：仍寫「單一全域簽名檔」，但程式已支援最多 10 個簽名檔。
- `README.md:28`：寫「終端機不支援捲動」，但 0.5.2 已加入滑鼠滾輪捲動。
- `main.py:3-4` docstring 只列 `--selftest`，漏了 `--probe`。
- `docs/` 內容是規劃文件，README 已標示僅供參考；但 README 本身應視為使用文件同步維護。

### 原始碼中的不可見控制字元

- `src/ui/main_window.py:177` 的按鍵列使用**實際 ESC byte**（`b"\x1b[D"` 等，共 9 個），而非 `b"\x1b[D"` 的 escape 寫法；`src/ui/terminal_widget.py:235` 也有 2 個。
- `src/compose.py:15-17` 的 `INVISIBLE` regex 直接內嵌 U+200B／U+2028 等不可見字元。
- 這些雖然目前可執行，但很容易在編輯器、diff、複製貼上或程式碼審查中被破壞，建議全部改成 `\x1b`、`\u200b` 等可見 escape。

### UI 小瑕疵

- `src/ui/main_window.py:243`：`self.chk_keybar.setChecked(self.keybar.isVisible())` 在視窗尚未 show 時永遠是 False，導致筆電上按鍵列已啟用、設定頁卻顯示未勾選。應改用 `not self.keybar.isHidden()` 或 `isVisibleTo(self)`。
- `src/ui/main_window.py:111-113`：`reload_drafts()` 先執行，`recover_interrupted_inputs()` 後執行，草稿清單會先顯示 `started`，直到下次 reload 才變 `aborted`。應先 recovery 再 reload。
- `src/ui/main_window.py:643`：`n, ctrl = compose.normalize(body)` 的結果完全沒使用，是多餘的計算；直接刪除。
- `src/ui/main_window.py:641-642`：開啟舊草稿後 `_last_result=None`，原本的 `body_status` 警告會消失；`parse_status` 仍顯示舊狀態，資訊不一致。
- `src/ui/main_window.py:538-544`：`_fetch_failed` 忽略 `detail`，使用者只看得到概括訊息；建議至少寫入 log。
- `src/ui/main_window.py:558`：無論標題是否已含 `[新聞]` 都再加一次，PTT 網頁版標題可能變成 `[新聞] [新聞] ...`。
- `src/ui/main_window.py:1079`：啟動時視窗尚未 show，`not self.isVisible()` 為 True，系統匣圖示會預設顯示，即使兩個 tray 選項都關閉。若這不是刻意設計，應在 `showEvent` 重新計算。

### 網路／終端機邊界

- `src/net/client.py:97-106`：只在第一個 WebSocket message 開頭剝除 `HTTP/1.1 200 OK\r\n\r\n`；若 proxy header 被拆成兩個 frame，就不會剝除。建議緩衝到前綴完整或確定不是前綴為止。
- `src/net/client.py:66`：`textMessageReceived` 以 UTF-8 重新編碼，但 PTT 是 Big5；若伺服器送 text frame，內容會錯。建議明確只接受 binary frame，或依實際協議處理。
- `src/net/client.py:74-81`：`close()` 在 `CONNECTING` 時只改 state，沒有 abort socket；可能留下進行中的 handshake。建議在 close 時 abort 並清掉 `_ws`。
- `src/terminal/screen.py:145-153`：scroll 新產生的空白列使用目前 `self.bg`，不是 `DEFAULT_BG`；在有色背景後捲動可能留下殘色。
- `src/terminal/screen.py:266-295`：SGR 未處理 `38`／`48` 的 extended color；`38;5;n` 會被拆成 `38`（忽略）、`5`（BLINK）、`n`（忽略），可能誤開閃爍。PTT 目前多用 16 色，但建議明確跳過 38/48 的參數。
- `src/ui/terminal_widget.py:300`：游標顏色依 `hasFocus()` 決定，但沒有在 focus in/out 時重繪；焦點改變後游標顏色可能停在舊狀態。
- `src/ui/terminal_widget.py:239-248`：IME commit 後沒有檢查 `send_user_bytes()` 回傳值；斷線時輸入會靜默消失。

### 資料庫／併發

- `src/storage/db.py:88-96`：搜尋直接將使用者輸入放進 `LIKE`，`%` 與 `_` 會被當萬用字元；若使用者搜尋 `50%` 會得到非預期結果。可用 `ESCAPE` 轉義。
- 沒有 `PRAGMA busy_timeout`、WAL 或單一實例鎖；同時開兩個程式可能遇到 `database is locked`，且兩個實例會共用同一份 `input_state`。
- `Database.close()` 沒有 context manager；若初始化後段失敗，連線可能未關閉。
- `db.event()` 的 `detail[:500]` 會截斷，但不影響功能。

### 打包與 repo 衛生

- `git count-objects -vH` 顯示 `.git` 約 **111 MiB**；commit `f4a4134` 曾加入兩個 56MB 的 EXE，後續 `f21e609` 雖然停止追蹤，但 blob 仍在歷史中。若這個 repo 會分享／推到 remote，建議用 `git filter-repo` 或 BFG 清歷史（需團隊協調）。
- `docs/docs.zip` 與 `docs/` 內容重複，約 111KB，可移除。
- `PTTAutoPost.spec` 沒有 Windows 版本資源（FileVersion/ProductVersion）；EXE 內容詳細資料會是空白。
- 沒有 code signing；Windows SmartScreen 會警告。個人工具可接受，但若要發佈需考慮。
- `EXCLUDES` 相當廣（包含 `setuptools`、`unittest` 等），目前 selftest 過，但建議在乾淨機器上實測打包版，避免某個延遲 import 在特定流程才失敗。
- `config/` 目錄會被建立但程式實際把設定存在 SQLite；若沒有用途，可移除或文件說明。

### 測試與 lint

- `python -m pyflakes src main.py tools` 有 5 個問題：
  - `main.py:59` `_app` 未使用
  - `tools/make_icon.py:18` `_app` 未使用
  - `tools/probe_wss.py:15` `QObject` 未使用
  - `tools/probe_wss.py:22`、`61` `app` 未使用
- `python -m pyflakes tests`：
  - `tests/test_extract_fetch.py:37` f-string 沒有 placeholder
  - `tests/test_ui.py:14` `QSize` 未使用
- `tests/test_ui.py:16` 直接 `from test_extract_fetch import H`，測試模組互相依賴；建議把測試 server 搬到 `conftest.py` 或獨立 helper。
- 測試大量使用固定 `pump(ms)` 與 timeout，慢機器上可能 flaky；建議盡量用條件等待，必要時標記 `slow`。
- 沒有 coverage 設定；建議加入 `pytest-cov`，至少追蹤 `src/net`、`src/compose`、`src/terminal`。
- `pytest.ini` 定義了 `live` marker，但目前沒有測試使用；要嘛補 live 測試，要嘛移除。

---

## 五、建議落地順序

### 第一階段（先修正確性，約半天）

1. `compose.check()` 分隔線索引（P1-1）+ regression test。
2. `current_texts()` 強制刷新預覽（P1-2）+ 測試「編輯後立即複製」。
3. `new_draft`／`open_selected`／`start_fetch` 的未儲存提示（P1-3）。
4. `type_into_ptt()` 只儲存一次、檢查 `get_draft()` 為 None（P2-2）。
5. `_typing_draft_id` 快照（P2-3）。
6. `chk_nonempty` 重設（P2-7）。

### 第二階段（穩定性與資料一致性，約 1–2 天）

1. `extract.py` 移除 function attribute/global，改回傳 `truncated` 與 local context（P2-1）。
2. 設定 JSON 型別驗證（P2-4）。
3. 自動輸入／登入期間鎖定終端機輸入（P2-5）。
4. 草稿快照簽名檔（P2-6）。
5. `fetch` 串流例外與 detail（P2-8）。
6. 啟動錯誤對話框 + `sys.excepthook`（P2-9）。
7. 移除 `DEFAULT_PTTLOGIN` 絕對路徑（P2-10）。
8. 新增 `requirements.txt` / `pyproject.toml`（P2-11）。

### 第三階段（重構、效能、文件）

1. 解析器效能：移除 double parse、避免候選容器重複 parse（P2-12）。
2. 終端機繪製 cache/dirty row（P2-12）。
3. `main_window.py` 拆分 controller/view（目前 1126 行，混合 UI、DB、網路、tray、外部程式）。
4. README 全面同步（版本、安裝、簽名檔、捲動、路徑）。
5. 清理 repo 歷史與 `docs.zip`、補版本資源／簽章。
6. 補 CI（pytest + pyflakes + PyInstaller selftest）與 coverage。

---

## 六、建議新增的回歸測試

優先補這幾個，因為它們各自對應一個已確認或高風險的缺陷：

```text
test_check_with_spaced_separator_and_signature_does_not_crash
test_copy_immediately_after_field_edit_uses_fresh_preview
test_type_into_ptt_with_missing_draft_shows_error_and_sends_nothing
test_switch_draft_during_typing_marks_original_draft
test_parse_after_truncated_article_is_not_suspect
test_corrupt_signature_and_board_settings_return_empty
test_nonempty_allowance_resets_on_new_draft_and_open
test_fetch_read_error_is_reported_as_fetch_error
test_manual_keys_are_blocked_while_post_typer_runs
test_session_login_rejects_control_characters
test_ptt_web_title_does_not_get_double_news_prefix
```

另外建議把 `test_ui.py` 的 `H` server 移到 `tests/conftest.py` 或 `tests/helpers.py`，避免測試模組互相 import。

---

## 七、做得好的地方（建議保留）

- **安全邊界清楚**：`PostTyper` 只送可列印、cp950 可編碼文字，不送 Enter/Ctrl-X；`preflight` 在每次輸入前正面辨識畫面；斷線／逾時／取消都不重送。
- **測試是行為導向**：`fake_bbs.py` 記錄每個 byte，直接驗證「實際送了什麼」，比只測函式回傳值可靠。
- **登入隱私處理**：密碼只送一次、密碼欄位立即清空、log 有 redaction filter，並有測試驗證。
- **錯誤不造假**：擷取失敗、登入牆、付費牆、CSRF shell 都只回報原因，不補造欄位。
- **UI 狀態標示完整**：已取得／未取得／推定／已修改，以及內文完整度警告，對使用者很友善。
- **可移植性**：`paths.py` 的 EXE 同層 `data/logs/config` 與 `LOCALAPPDATA` fallback 設計良好。
- **打包流程**：版本化輸出、`--selftest`、`--verify`、honest UA、robots 預設遵守。

---

## 八、剩餘風險

- 依 README 所述，**尚未用真實帳號登入並完成一次真實發文**；登入後的提示處理、「標題：」／編輯文章畫面辨識、標題長度上限、編輯器吃字行為都尚未實測。這是目前最大的產品風險，程式目前以「辨識不到就停止」降低風險，但仍需一次受控的真實流程驗證。
- 擷取規則以通用 heuristics 為主，部分網站可能殘留版面雜訊；已用警告提示，仍需人工對照原網頁。
- PTT 專用（UAO）字元會顯示成「？」；終端機不支援複製貼上（依設計）。

---

**總結**：這個專案的「防止誤發文」設計是強項，測試也足以支撐。最需要優先處理的是 **P1-1 檢查器崩潰、P1-2 過期預覽、P1-3 未儲存內容覆蓋**；接著是解析器全域狀態、草稿／輸入狀態一致性與設定容錯。完成 P1/P2 後，這個工具在正確性與可維護性上會明顯提升。

---

## 附錄：`PTTAutoPost_全部程式碼.txt` 比對

- 檔案包含 **39 個程式碼區段**、約 **5,969 行**（UTF-8）。
- 以區段標題逐檔比對 repo：匯出當下 39 個檔案全部存在，內容一致；唯一差異是 6 個空白的 `src/**/__init__.py` 在匯出檔中多了一個空白行。
- 因此本報告的 `file:line` 可直接對應 repo（以匯出當下的版本為準）；在 consolidated 檔中的主要位置如下：
  - `compose.check` 分隔線：第 390 行
  - 預覽 debounce／`current_texts`／`copy`／`type_into_ptt`：第 3224、3252、3269、3539 行
  - `_fetch_done`／`new_draft`／`open_selected`：第 3166、3436、3477 行
  - 解析器 trunc 寫入／讀取：第 1555、1697 行
  - `signatures`／`favorite_boards`：第 2071、2120 行
  - `_typing_finished`：第 3579 行
  - `DEFAULT_PTTLOGIN`：第 3618 行
- 這次匯出沒有新增或缺少任何程式碼，故不改變前述（匯出檔版本的）結論。

> **工作樹狀態註記（2026-10-21 17:57）**：匯出後 repo 的 `src/compose.py` 與 `src/ui/main_window.py` 出現未提交修改，內容看起來是在套用本報告的 P1-1、P1-2、P1-3、P2-2、P2-3、P2-7 修正。這些修改**不包含在** `PTTAutoPost_全部程式碼.txt` 中，因此本附錄的「內容一致」只代表匯出當下；上述 P1/P2 條目仍精確描述匯出檔。若要確認修正是否完整，應另審 `git diff`；本次未將那些變更視為已驗證。
