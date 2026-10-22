# PTT AutoPost 專案重啟｜Phase 0 唯讀稽核

- 日期：2026-10-22
- 基準：`main` @ `369b787`（0.6.2），GitHub 私有庫，Release v0.6.2 為 Latest
- 性質：**唯讀**。未修改任何程式碼、未提交、未連線 PTT；只執行測試（`-p no:cacheprovider`、不寫 .pyc）與讀檔。
- 依據文件：`docs/ROADMAP_2026-10-22.md`、`docs/ESTIMATE_2026-10-22.md`、專案記憶

---

## 一、結論

1. **基準健康，可以開始階段 1**：工作樹乾淨、與 origin 同步、5 個版本標籤齊全，**168 項測試全部通過**（Python 3.12.10、PySide6 6.11.2，QT offscreen）。
2. **有 4 個檔案或資料夾未納入版控**，建議第一次提交時先處理（見第三節）。
3. 程式碼現況和路線圖的前提**一致**：單一連線、只有 WSS、Big5 寫死、Origin 寫死、終端機不能選取或複製。下面列出每個階段要改的確切位置。
4. **probe 腳本沒有留下**：ptt2 WSS 與 ssh.exe 的 probe 結果只記在文件和記憶裡，`tools/` 裡只有 `probe_wss.py`（PTT 用）。階段 4 前建議補一支可重跑的 probe 腳本。

---

## 二、基準狀態

| 項目 | 結果 |
|---|---|
| 分支／同步 | `main`，與 `origin/main` 一致，無未提交修改 |
| 標籤 | v0.5.3 至 v0.6.2，遠端有 5 個（本機原缺 v0.6.2，已 fetch 補齊） |
| 版本 | `src/version.py` 0.6.2／2026/10/16（CHANGELOG 首筆一致） |
| 測試 | 168 passed |
| 程式碼量 | 追蹤檔約 7,050 行（含測試）；`main_window.py` 1,255 行最大，其次 `extract.py` 611 行 |
| 程式碼全文檔 | `PTTAutoPost_全部程式碼.txt` 已提交，內容為 0.6.2，與目前原始碼版本一致 |
| 建置產物 | `dist/` 有 0.6.1、0.6.2 portable 與 0.6.2 ZIP（已被 .gitignore 排除） |
| 依賴 | `requirements.txt` 只設下限（`>=`），沒有鎖定版本 |

---

## 三、未納入版控

| 路徑 | 內容 | 建議 |
|---|---|---|
| `docs/CODE_REVIEW_2026-10-21.md` | 10-21 程式碼檢視（P1 共 3 項、P2 共 14 項） | 提交；P1、P2-1 至 P2-11、P2-13、P2-14 都可在 0.5.4 至 0.6.2 的 CHANGELOG 找到對應的修正。**P2-12（解析與繪製效能）在 CHANGELOG 找不到對應**，要確認是刻意延後還是遺漏 |
| `docs/ROADMAP_2026-10-22.md` | 13 項功能規劃 | 提交，但第一節第 6 點與第九節第 2 點仍寫「帳密維持不儲存」，**和 10-22 的放寬決定衝突**，提交前要更正 |
| `docs/ESTIMATE_2026-10-22.md` | 整合評估（11 組需求） | 提交（目前以這份為準） |
| `新增資料夾/` | 站台清單 txt＋4 張 PTT Star 設定截圖 | 改名為 `docs/reference/` 之類的名稱再提交；站台清單會成為內建 13 站的資料來源。截圖是否入庫由你決定 |

另外，`docs/` 下 10-15 的舊文件（SRS、ARCHITECTURE、PHASE0_AUDIT 等）是實作前的設計，內容已落後於 0.6.2，建議加註「歷史文件」或移到 `docs/archive/`，避免新的工作階段誤用。

---

## 四、路線圖各階段對應的程式碼位置

| 階段／組 | 現況（確切位置） | 影響 |
|---|---|---|
| B 底部精簡 | `main_window.py:199` `msg_log`（main_window 中 6 處引用、測試中 10 處）、`:204` 提示文字 | 移除後，狀態訊息要有新的出口（狀態列），測試要跟著改 |
| C 複製貼上 | `terminal_widget.py` 沒有任何 mouse press/move 或 clipboard 處理 | 從零開始做；選取座標要處理中文雙格寬 |
| D 多分頁 | `MainWindow.__init__` 只持有一個 `self.session = PttSession(self)`（`main_window.py:73`），連線按鈕直接綁定它（`:208`） | 確認是最大的重構；session、terminal、輸入器、托盤狀態都要改成每分頁一組 |
| E／F 每站 Origin | `client.py:24` `ORIGIN` 是模組常數，`:94` `QWebSocket(ORIGIN)` | 改成每站台設定（ptt2 需要 `term.ptt2.cc`） |
| F 編碼 | cp950 寫死在 `screen.py:69`（解碼）、`terminal_widget.py:39,261`（鍵入）、`poster.py:32-77`（發文）、`compose.py:67,173`（長度計算） | 每站台編碼只需要動「終端機解碼與鍵入」；**發文與長度計算要維持 cp950（PTT 專用）**，不要一起改 |
| F Telnet | `net/telnet.py` 目前只**剝除** IAC、不回應 | 直連 Telnet 23 的站台多半需要回應協商（NAWS、TTYPE 等），屬於新工作，不能直接沿用 |
| F 連線抽象 | `PttClient` 是 QWebSocket 專用；`endpoint_problem()` 只允許 wss:// | 要抽出共同的傳輸介面；端點規則要改成依協定檢查 |
| G 帳密與 ptt2 | `client.py:26` `TRUSTED_LOGIN_HOSTS = ("ws.ptt.cc",)` | ptt2 登入輔助要加入名單；DPAPI 儲存要另寫模組與測試 |
| J 發佈 | `PTTAutoPost.spec` 為單檔版；`make_portable.py` 只產單檔 | 改資料夾版、剔除 Qt 元件時要一起改 |

---

## 五、風險與建議（開始階段 1 之前）

1. **先做一次「整理提交」**（只動文件）：更正 ROADMAP 的帳密描述 → 提交三份文件與站台資料 → 標註舊文件。這樣新的工作階段讀到的才是正確的前提。
2. **確認 P2-12 效能項目**是否延後；多分頁會讓繪製負擔放大，建議在階段 2 之前處理或明確延後。
3. **依賴鎖定**：PySide6 6.11 與 `>=6.6` 的下限差距很大；發佈前建議產生鎖定檔（例如 `requirements.lock`），讓建置可以重現。
4. **probe 可重跑**：把 ptt2 WSS 與 ssh.exe 的 probe 寫成 `tools/` 腳本（只收畫面、不送資料），之後的驗證才有依據。
5. 真實 PTT 登入後的行為至今**從未驗證**，這點不變；階段 5（防閒置）前要安排你本人登入配合。

---

## 六、尚待你決定（沿用 ESTIMATE 第六節，未變動）

贊助連結、第 13 項「其他」清單、公開發佈範圍、階段 6 要不要做、帳密儲存的預設值。
