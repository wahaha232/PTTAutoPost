PTT AutoPost {version}（Windows 可攜資料夾版）
建置日期：{build_date}

【啟動】
1. 將整個資料夾解壓縮到您想要的位置（路徑可以包含中文與空白）。
2. 雙擊 PTTAutoPost.exe。
3. 第一次啟動會在程式旁邊建立 config\、logs\、data\；不會寫入登錄檔，也不需安裝。

【系統需求】
Windows 10／11（64 位元）。不需要另外安裝 Python 或 Qt。

【安全設計】
- 程式只會把文字輸入到 PTT，不會代按 Enter、Ctrl-X、存檔或送出。
- 自動輸入前會先記錄狀態；斷線、取消或畫面不符就停止，不會自動重送。
- 帳號密碼只送出一次，不儲存、不寫入日誌。輔助登入只對 PTT 官方端點送出帳密。
- 貼上只接受 Big5（cp950）可編碼文字；控制字元會移除，換行會轉成 Enter。
  多行或超過 200 字會先顯示預覽，超過 5000 字直接拒絕；長文字分批送出，
  中途斷線或被鎖定會停止並回報已送出多少。

【常用操作】
- F11：全螢幕；F12：顯示／收合文章面板。
- 終端機：滑鼠拖曳選取、雙擊選詞、三擊整列、Alt＋拖曳矩形選取。
- Ctrl+Shift+C：複製選取；Ctrl+Shift+V：貼上；右鍵選單也有相同功能。
- Esc、方向鍵、PgUp／PgDn、Home／End 會照常送進 PTT。
- 連線端點預設 wss://ws.ptt.cc/bbs；連線中斷只提示，不會自動重連。

【Windows SmartScreen】
本程式沒有數位簽章，Windows 可能顯示「不明的發行者」警告。若您信任檔案來源，
可選「更多資訊」→「仍要執行」。請只從您信任的來源取得本程式。

【資料與隱私】
- config\、logs\、data\ 都在程式資料夾內；移除資料夾即移除本機資料。
- config\ 內可能有瀏覽器路徑等設定；data\ 內是草稿與簽名檔資料庫。
- 帳號密碼不會被保存。程式只連線 PTT 與您指定要擷取或開啟的網址。

【授權】
本程式為專有授權，請見 LICENSE。第三方元件（Qt／PySide6 為 LGPL-3.0 等）
與授權全文請見 THIRD_PARTY_NOTICES.md 與 licenses\ 資料夾。Qt 函式庫是資料夾內
可替換的 DLL，您可以用介面相容的版本替換。

【指令列（進階）】
PTTAutoPost.exe --selftest   無視窗自我檢測
PTTAutoPost.exe --probe      唯讀檢查 wss://ws.ptt.cc/bbs（不送出任何資料）

本程式與 PTT 官方無關。使用 PTT 時請遵守站規與相關法令。
