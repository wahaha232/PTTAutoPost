# 測試語料與來源支援清單（TEST_CORPUS）

- 版本：**2.0-draft**；日期：2026-10-15；**待使用者審核**
- 用途：M1「真實來源與文章 URL 清單」、本機快照規範、來源支援矩陣。相關：[SRS.md](SRS.md) FR-114～117、[GOLDEN_SPEC.md](GOLDEN_SPEC.md)、[ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) AT-EXT／AT-GLD／AT-SNP／AT-M1、[ARCHITECTURE.md](ARCHITECTURE.md) §15.2。
- 證據檔：[evidence/source_verification_2026-10-15.json](evidence/source_verification_2026-10-15.json)（逐 URL 的驗證原始資料）、[evidence/robots_summary_2026-10-15.json](evidence/robots_summary_2026-10-15.json)。
- **狀態（務必先讀）**：URL **已實際連線驗證**（見 §1）；但**尚未建立任何快照、尚未建立任何黃金檔、尚未執行任何解析比對**。所有「快照」「黃金檔」「比對結果」欄位目前皆為「**未建立／未執行**」，不得解讀為已通過。

---

## 0. 決策紀錄（2026-10-15 使用者決策）

| 決策 | 內容 | 對本文件的影響 |
|------|------|----------------|
| 1 本機快照 | **採用**。僅用於本機測試、不公開散布；保存必要的 **HTML、正文、截圖與來源資訊**；遵守網站使用條款、著作權及存取限制，**不繞過登入或付費牆** | §7 快照規範；§4 合規紀錄；Q-05 已解決 |
| 2 真實來源清單 | **採用**。≥ 12 個不同來源，每來源 ≥ 1 篇實際文章 URL，附來源名稱、文章標題、URL、取得日期、測試用途；**必須實際驗證，不可虛構，不可用首頁或搜尋結果頁代替** | §3（20 個來源、39 篇已驗證）；Q-12／Q-21／Q-27 已解決（清單待使用者最終確認） |
| 3 全文比對與黃金檔 | 採用，**先校準**；規則見 GOLDEN_SPEC | §6；每來源黃金檔狀態欄 |

---

## 1. 驗證方法與限制

- **日期**：2026-10-15。**方式**：對每個 URL 做**單次 GET**（誠實的研究用 User-Agent「PTTAutoPost-planning-research」、不帶 Cookie、不登入、不繞過任何牆、不執行腳本、未用瀏覽器）；請求間隔 ≥ 2 秒；每個網域先讀 `robots.txt` 並以標準解析器判斷該路徑是否允許。
- **「已驗證為實際文章」的判準**（全部成立）：HTTP 200；**未被轉址**到別的頁面（最終 URL 與請求 URL 相同）；路徑為單篇文章樣式（非首頁、搜尋頁、列表頁、分類頁）；`og:title`／`<title>` 為具體文章標題（非站名）；頁面含 `og:type=article`、JSON-LD 文章節點或明確的文章版型（PTT、維基）；段落文字量達一定份量。
- **沒有做的事**：沒有人工閱讀全文；沒有確認內文是否完整；沒有確認是否有付費牆（僅有字樣訊號）；**沒有閱讀各網站的使用條款**（§4 標「待人工確認」）。
- 驗證結果只代表**該時間點**；新聞 URL 與站台版型會變。因此閘門測試一律使用**離線快照**（§7），線上 URL 只用於擷取快照與預警。
- 兩項觀察：`robots.txt` 中 **中央社與 iThome 宣告 `Content-signal: ai-train=no`**（禁止作為 AI 訓練資料）、iThome 宣告 `Crawl-delay: 10`、維基百科 `Crawl-delay: 5`；本專案的快照**僅用於本機解析測試，不用於訓練任何模型**，抓取間隔須取「2 秒」與該站 `Crawl-delay` 的較大值（SRS FR-103／116）。

---

## 2. 驗證結果總覽

| 項目 | 結果 |
|------|------|
| 驗證的來源數 | **20**（Tier A 12、Tier B 8）；決策 2 要求 ≥ 12 ✔ |
| 已驗證文章 URL | **39 篇**（Tier A 24、Tier B 15）＋2 篇備選（PTT）；全部 HTTP 200、無轉址、`robots.txt` 允許（中央社與 PTT 的 robots 狀態見 §4）、判為單篇文章 |
| 驗證時被排除 | 原 Phase 0 清單中的 3 個非典型樣本：報導者電子報與 Podcast、關鍵評論網廣編稿（疑似）→ 已替換 |
| 動態網頁／反爬／登入牆**文章**樣本 | **尚未驗證**（目前只有首頁類探針：Medium、Dcard 回 403；Facebook／LINE TODAY／vocus 為前端渲染外殼）→ 這些**不是文章 URL，不計入 12 個來源**，列於 §3.3 |
| 快照 | **0** 份已建立 |
| 黃金檔 | **0** 份已建立；**0** 份 `VERIFIED` |
| 比對結果 | **未執行** |
| 全文是否完整 | **未確認**（所有來源） |

---

## 3. 真實來源與文章清單

欄位：**驗證**＝HTTP 200／無轉址／robots 允許／為單篇文章（結構訊號摘要）；「用途」為本專案測試用途。標題為取得當日頁面的 `og:title`（可能含站名後綴）。取得日期皆為 **2026-10-15**。

### 3.1 Tier A（12 個來源、24 篇）

| ID | 來源名稱 | 文章標題 | URL | 測試用途 |
|----|----------|----------|-----|----------|
| S-cna-01 | 中央社 | 2026九合一選舉　22縣市長登記參選名單一次看 \| 政治 \| 中央社 CNA | https://www.cna.com.tw/news/aipl/202609045002.aspx | 通訊社標準版型；清單型長文；meta author 為機構名→記者需內文推定 |
| S-cna-02 | 中央社 | 彰化縣長選戰11月電視辯論會　無交互詰問 \| 地方 \| 中央社 CNA | https://www.cna.com.tw/news/aloc/202610150202.aspx | 地方新聞；內文署名行格式 |
| S-ltn-01 | 自由時報 | 透早臭又吵！集集支線列車怠速惹怨 台鐵3方案改善 - 生活 - 自由時報電子報 | https://news.ltn.com.tw/news/life/breakingnews/5607412 | 大型入口標準版型；頁面含「展開」「下一頁」字樣→是否有分頁待確認 |
| S-ltn-02 | 自由時報 | 接見加拿大國會議員團 韓國瑜拋「築巢引鳳」：盼擴大來台投資AI、無人機 - 政治 - 自由時報電子報 | https://news.ltn.com.tw/news/politics/breakingnews/5607344 | 同上；標題含引號與全形標點 |
| S-udn-01 | 聯合新聞網 | 影／川普宣布台灣投資阿拉斯加LNG 同場又批「台偷走美國晶片產業」 \| 聯合新聞網 | https://udn.com/news/story/6811/9816746 | 長文（約 1 萬字）；「影／」前綴標題；重複偵測：加 `?from=redpush` 變體（首頁連結上觀察到） |
| S-udn-02 | 聯合新聞網 | 高金素梅出庭前再限制出境8個月 法院裁定曝：入監執行的機率不低 \| 聯合新聞網 | https://udn.com/news/story/7315/9816953 | 長文；頁面含「會員」「登入」字樣→付費牆風險待確認 |
| S-ettoday-01 | ETtoday新聞雲 | 淡江教授心寒「全班只1人來上課」　校方：將和學生溝通補課 \| ETtoday生活新聞 \| ETtoday新聞雲 | https://www.ettoday.net/news/20261015/3255218.htm | 作者在 meta（疑為記者姓名）；先前取樣觀察到 JSON-LD 解析失敗→壞資料隔離案例（待快照確認） |
| S-ettoday-02 | ETtoday新聞雲 | 烏克蘭恢復攻擊！無人機大規模出動　俄煉油廠起火 \| ETtoday國際新聞 \| ETtoday新聞雲 | https://www.ettoday.net/news/20261015/3255237.htm | 國際新聞；短文（約 900 字） |
| S-chinatimes-01 | 中時新聞網 | 魏哲家霸氣宣告：不會把食物留給別人！2度上修全年營收成長達44％ - 財經 | https://www.chinatimes.com/realtimenews/20261015002904-260410 | **短快訊**（約 640 字）：短文章規則與完整性判定；`?ctrack=` 追蹤參數變體 |
| S-chinatimes-02 | 中時新聞網 | 史上第六慘！台股收盤慘跌1655點 後市看他表現 - 財經 | https://www.chinatimes.com/realtimenews/20261015002697-260410 | 短快訊；JSON-LD 型別為 `Article`（非 NewsArticle） |
| S-tvbs-01 | TVBS新聞網 | 年前真能領到錢？藍盼三讀發2萬　政院喊話立院：拉同一把弓 | https://news.tvbs.com.tw/politics/4036502 | 回應標頭**無 charset**→編碼優先序走 meta；發布時間為 UTC；無作者 meta；36 段落含雜訊 |
| S-tvbs-02 | TVBS新聞網 | 馬祖工安事故釀3死！2工人船艙內失去意識　同事救援也喪命 | https://news.tvbs.com.tw/local/4036526 | 同上；社會新聞 |
| S-setn-01 | 三立新聞網 | 老師遭濫訴不用怕！教育部挺基層出手了：每人最高給「這金額」法律諮詢 \| 生活 \| 三立新聞網  SETN.COM | https://www.setn.com/news/1923085 | 發布時間不在 meta（可能在 JSON-LD）；無 `og:site_name`；標題後綴含雙空白 |
| S-setn-02 | 三立新聞網 | 畏寒發燒以為感冒！17歲高中生急診一查⋯肝臟藏「8公分大膿瘍」急住院 | https://www.setn.com/news/1923099 | 標題含省略號「⋯」（編碼檢查案例） |
| S-pts-01 | 公視新聞網 | 批美制裁國際刑事法院 新科和平獎得主稱「川普需上國際法課」 ｜ 公視新聞網 PNN | https://news.pts.org.tw/article/831468 | JSON-LD 含多種型別（FAQPage 等）→非文章節點干擾；作者疑為記者姓名 |
| S-pts-02 | 公視新聞網 | 美國8州聯合起訴OpenAI 控容許ChatGPT誘導兒少自傷 ｜ 公視新聞網 PNN | https://news.pts.org.tw/article/831467 | 同上 |
| S-storm-01 | 風傳媒 | 台積電法說會也救不了台股？外資賣超金額、期貨空單創新高，台指期夜盤繼續殺 \| 林彥呈 \| 財經 | https://www.storm.mg/article/11172736 | 超大頁面（約 1.0 MB）效能；作者姓名在標題後綴 |
| S-storm-02 | 風傳媒 | 華爾街日報》面對高築的貿易壁壘，中國難以承受失去歐洲之痛 \| 華爾街日報 \| 新聞 | https://www.storm.mg/article/11172645 | 約 1.2 MB；轉載／授權文章（作者欄位為機構）→「機構非記者」案例 |
| S-nownews-01 | NOWnews今日新聞 | 吳思瑤出席辯論協商！羅智強要求為「疑心病」向TVBS、三立道歉 \| 政治快訊 \| 要聞 \| NOWnews今日新聞 | https://www.nownews.com/news/6883719 | meta author 為機構名；標題多段後綴 |
| S-nownews-02 | NOWnews今日新聞 | Uber包車正式上線！2小時2000元起 最多跑10景點、取消恐噴3千元 \| 3C車市 \| 生活 \| NOWnews今日新聞 | https://www.nownews.com/news/6883713 | 含價格／數字／符號（全形半形混用） |
| S-bbc-01 | BBC News 中文 | 尼泊爾洪災：為何這喜馬拉雅山脈國家希望中印開展合作？ - BBC News 中文 | https://www.bbc.com/zhongwen/articles/c674pq1e0dxqo/trad | 含內嵌狀態 JSON（`__NEXT_DATA__`）；author 為社群網址須排除；繁體版路徑 |
| S-bbc-02 | BBC News 中文 | 東南亞霧霾：是甚麼讓新加坡、馬來西亞和印尼窒息？ - BBC News 中文 | https://www.bbc.com/zhongwen/articles/cjkge2k03kgpo/trad | 同上；長文（約 50 段落） |
| S-ptt-01 | PTT 網頁版（Tech_Job 板） | [新聞] 中華電信工會今起罷工投票 全總批資方恐 | https://www.ptt.cc/bbs/Tech_Job/M.1791958449.A.EF6.html | **PTT 新聞轉貼文**（與本產品用途最相關）；純文字 `div`、無 `<p>`；metaline；推文須排除 |
| S-ptt-02 | PTT 網頁版（Tech_Job 板） | [討論] 黃仁勳和張忠謀首次通電話 | https://www.ptt.cc/bbs/Tech_Job/M.1792040286.A.AE5.html | 討論文；推文數量多 |

*備選（已驗證，未列入主清單）*：S-ptt-03 `[請益] 前鎮緯創廠` https://www.ptt.cc/bbs/Tech_Job/M.1791964052.A.7D0.html；S-ptt-04 `[徵才] 聯發科 IT SW Infra工程師` https://www.ptt.cc/bbs/Tech_Job/M.1792031149.A.5EB.html。PTT 文章含使用者帳號識別，僅本機測試用、不散布。

### 3.2 Tier B（8 個來源、15 篇）

| ID | 來源名稱 | 文章標題 | URL | 測試用途 |
|----|----------|----------|-----|----------|
| S-twreporter-01 | 報導者 | 生成式AI如何影響選舉？國外案例借鏡與公民因應之道 - 報導者 The Reporter | https://www.twreporter.org/a/2026-local-elections-ai-generated-contents-negatively-affect-elections | 深度長文（約 77 段落）；無 JSON-LD 文章節點；無 author／`og:site_name` meta |
| S-twreporter-02 | 報導者 | 小黨生存空間最新實驗：四合一的「台灣前進」能前進到什麼地方？ - 報導者 The Reporter | https://www.twreporter.org/a/2026-local-elections-taiwan-go-go | 同上 |
| S-newslens-01 | 關鍵評論網 | AI引爆華爾街新震盪！繼「軟體末日」後，銀行業能守住存款護城河嗎？ - TNL The News Lens 關鍵評論網 | https://www.thenewslens.com/article/270582 | `og:type=website`（非 article）仍為文章→不可單靠 og:type 判斷 |
| S-newslens-02 | 關鍵評論網 | 「砍預算」失言又涉選舉違法！日本農相上任不到一個月請辭，成高市內閣首位因醜聞下台閣員 - TNL The News Lens 關鍵評論網 | https://www.thenewslens.com/article/270583 | 同上；長標題 |
| S-ithome-01 | iThome | 美司法部與FBI查封中國永信至誠科技兩款駭客工具，揭臺灣兩所大學曾遭Microscan掃描，後續被部署SoftEther VPN | https://www.ithome.com.tw/news/179572 | 無 JSON-LD；無 meta 時間／作者；頁面小；robots 宣告 `Crawl-delay: 10` |
| S-ithome-02 | iThome | 中國駭客Flax Typhoon利用8個已知漏洞發動攻擊，美CISA要求聯邦機構緊急修補其中5個弱點 | https://www.ithome.com.tw/news/179574 | 同上；英文專有名詞與數字混排 |
| S-technews-01 | 科技新報 | 台積電將於 2030 年開始採用 High-NA EUV，客戶 A14 參與度高於 N2 | https://technews.tw/2026/10/15/tsmc-will-begin-adopting-high-na-euv-in-2030/ | 無 JSON-LD；author 為社群網址須排除；中英數字混排 |
| S-technews-02 | 科技新報 | AI 晶片需求有多強？魏哲家：所有 AI 業者都與台積電合作 | https://technews.tw/2026/10/15/tsmc-ai-demand-is-booming/ | 同上 |
| S-bnext-01 | 數位時代 | 台積電法說會4大焦點！明年營收再成長40%？德州設廠、晶圓漲價與CoWoS擴產進度一次看 | https://www.bnext.com.tw/article/92628/tsmc-q3-2026-earnings-preview | 超長內文（段落文字量極大）；頁面含「付費」字樣→付費牆待確認；`og:type=website` |
| S-bnext-02 | 數位時代 | 台達電首秀SST固態變壓器，破解AI資料中心供電瓶頸！SOFC年底試量產搶能源商機 | https://www.bnext.com.tw/article/92631/2026-delta-sst-energy-taiwan | 同上 |
| S-cw-01 | 天下雜誌 | 98歲的他，至今仍每天看診！醫師周神榮：長壽秘訣其實很簡單｜天下雜誌 | https://www.cw.com.tw/article/5143032 | **付費牆風險**（「訂閱」「會員」字樣）→內文不完整判定測試（是否為付費內容待確認）；`?rec=` 追蹤參數變體 |
| S-cw-02 | 天下雜誌 | 花1100萬入住澳洲養生村，6年後竟拿回千萬？台灣能學嗎？｜天下雜誌 | https://www.cw.com.tw/article/5143233 | 同上 |
| S-yahoo-01 | Yahoo奇摩新聞 | 2026九合一選舉 22縣市長候選人完整名單一次看 | https://tw.news.yahoo.com/2026%E4%B9%9D%E5%90%88%E4%B8%80%E9%81%B8%E8%88%89-22%E7%B8%A3%E5%B8%82%E9%95%B7%E5%80%99%E9%81%B8%E4%BA%BA%E5%AE%8C%E6%95%B4%E5%90%8D%E5%96%AE%E4%B8%80%E6%AC%A1%E7%9C%8B-060431831.html | 轉載型；中文 slug（percent-encoding）；頁面大（約 760 KB）；**與 S-cna-01 疑似同題材→轉載重複偵測候選**（待確認內容是否相同） |
| S-yahoo-02 | Yahoo奇摩新聞 | 2026金鐘獎入圍名單／周渝民《與惡2》隔14年再爭影帝 | https://tw.news.yahoo.com/2026%E9%87%91%E9%90%98%E7%8D%8E%E5%85%A5%E5%9C%8D%E5%90%8D%E5%96%AE%EF%BC%88%E4%B8%8D%E6%96%B7%E6%9B%B4%E6%96%B0%EF%BC%89-000000384.html | 「持續更新」型文章（內容會變，快照時間點重要）；URL 含全形括號 |
| S-wiki-01 | 維基百科 | 臺北市 - 维基百科，自由的百科全书 | https://zh.wikipedia.org/wiki/%E8%87%BA%E5%8C%97%E5%B8%82 | 長文（約 1 MB）、表格、參考資料、infobox；無記者；robots 宣告 `Crawl-delay: 5` |

### 3.3 Tier C 探針（**非文章 URL，未驗證為文章，不計入 12 個來源**）

| ID | 目標 | 觀察（2026-10-15，單次 GET） | 預期 | 狀態 |
|----|------|------------------------------|------|------|
| P-medium | https://medium.com/ | HTTP 403（挑戰頁） | `BLOCKED`；不繞過 | **文章 URL 待蒐集**（須使用者提供） |
| P-dcard | https://www.dcard.tw/f/trending | HTTP 403 | `BLOCKED` | **文章 URL 待蒐集** |
| P-fb | https://www.facebook.com/ | 無腳本時可見文字約 270 字元；登入牆／前端渲染 | `NEEDS_JS`／`LOGIN_REQUIRED` | **貼文 URL 待蒐集** |
| P-line | https://today.line.me/tw/v3/tab | 前端渲染外殼（可見文字約 725 字元） | `NEEDS_JS` | **文章 URL 待蒐集** |
| P-vocus | https://vocus.cc/ | 前端渲染外殼＋內嵌狀態 JSON（可見文字約 1,270 字元） | 嘗試靜態內嵌 JSON；否則 `NEEDS_JS` | **文章 URL 待蒐集** |

---

## 4. 來源合規紀錄

> 決策 1 要求「遵守網站使用條款、著作權及存取限制」。`robots.txt` 已機器判定；**使用條款尚未逐站人工閱讀**，在使用者（或指定者）確認前，該來源**不建立快照**。

| 來源 | robots.txt | 對本專案文章路徑 | Content-signal／Crawl-delay | 使用條款（人工確認） |
|------|------------|------------------|-----------------------------|----------------------|
| 中央社 | 200 | 允許（手動確認；程式解析器對該檔判讀失敗，原因待查） | `ai-train=no`（本專案不訓練模型） | **待確認** |
| 自由時報 | 200 | 允許 | — | **待確認** |
| 聯合新聞網 | 200 | 允許 | — | **待確認** |
| ETtoday | 200 | 允許 | — | **待確認** |
| 中時新聞網 | 200 | 允許 | — | **待確認** |
| TVBS | 200 | 允許 | — | **待確認** |
| 三立新聞網 | 200 | 允許 | — | **待確認** |
| 公視新聞網 | 200 | 允許 | — | **待確認** |
| 風傳媒 | 200 | 允許 | — | **待確認** |
| NOWnews | 200 | 允許 | — | **待確認** |
| BBC 中文 | 200 | 允許 | — | **待確認** |
| PTT 網頁版 | **404（無 robots.txt）** | 無宣告限制 | — | **待確認**（個人貼文內容與帳號識別，僅本機測試） |
| 報導者 | 200 | 允許 | — | **待確認** |
| 關鍵評論網 | 200 | 允許 | — | **待確認** |
| iThome | 200 | 允許 | `ai-train=no`；**Crawl-delay 10** | **待確認** |
| 科技新報 | 200 | 允許 | — | **待確認** |
| 數位時代 | 200 | 允許 | — | **待確認** |
| 天下雜誌 | 200 | 允許 | — | **待確認** |
| Yahoo奇摩新聞 | 200 | 允許 | — | **待確認** |
| 維基百科 | 200 | 允許 | **Crawl-delay 5** | **待確認**（內容為 CC 授權，仍須確認引用條件） |

注意：著作權與轉載相關問題**不構成法律建議**，須諮詢專業人士（SRS Q-13）。

---

## 5. 跨站規律（對解析器設計的意義；單篇取樣）

| 編號 | 觀察 | 設計意義 |
|------|------|----------|
| C-01 | 取樣的 19 個站（Phase 0 取樣）與本次 20 個來源的文章皆為 HTTP 200；多數 UTF-8、伺服器端渲染且含 OpenGraph；**TVBS 與 Yahoo 的回應標頭未帶 charset** | 編碼判定優先序（標頭 > meta > BOM > 偵測）必須有「標頭缺漏」案例 |
| C-02 | JSON-LD 文章型節點：多數站有；報導者、iThome、科技新報、PTT 無；ETtoday 先前取樣為壞 JSON；中時為 `Article` 型別；公視含多種非文章型別 | 隔離壞資料；`@type` 選取；不可只靠 JSON-LD |
| C-03 | **meta `author` 常是機構名而非記者**（中央社、自由時報、聯合新聞網、中時、NOWnews、三立）；BBC、科技新報為社群網址；ETtoday、公視、風傳媒、數位時代看似記者姓名；TVBS、天下、iThome、報導者、Yahoo、PTT 無 | 記者需內文署名推定＋INFERRED＋人工確認 |
| C-04 | 發布時間 meta 缺失：三立、Yahoo、iThome、科技新報、數位時代、天下、PTT、維基；TVBS 為 UTC | 多路徑與時區處理 |
| C-05 | 部分站台首頁連結帶疑似追蹤參數：聯合新聞網 `?from=`、中時 `?ctrack=`、天下 `?rec=`（**用途為推測，待快照／站台說明確認**） | 追蹤參數由站台規則宣告 |
| C-06 | `og:type` 不可靠：關鍵評論網、數位時代、維基的文章頁為 `website` | 「是否為文章」不能只看 `og:type` |
| C-07 | 頁面體積差異大：PTT 約 8–12 KB、iThome 約 51 KB、風傳媒約 1.0–1.2 MB、維基與 Yahoo 約 0.8–1.0 MB | 抓取上限（暫定 5 MB）夠用；效能案例 |
| C-08 | 「持續更新」型文章（Yahoo 金鐘獎）與清單型長文（中央社、Yahoo 候選人名單） | 快照時間點重要；完整性判定須能處理清單型內容 |
| C-09 | 所有來源的頁面都含大量站內元素（導覽、推薦、留言、廣告、延伸閱讀） | 雜訊率必須量測（GOLDEN_SPEC §5） |
| C-10 | 轉載授權文章（風傳媒的華爾街日報）作者欄為機構 | 「機構非記者」案例 |

---

## 6. 來源支援矩陣（M1 閘門基準；**全部尚未驗證**）

欄位目標：T 標題、S 媒體來源、U 原文 URL、A 作者／記者、D 發布時間、B 內文（全文）。「✔」＝要求取得；「△」＝允許未取得但須明確標示；「推」＝允許由內文署名推定（INFERRED）。
**黃金檔／比對結果欄全部為「未建立／未執行」**；「規則版本」「最後驗證」待 Phase 3 填入。

### 6.1 Tier A（M1 閘門：每來源 ≥ 1 份 `VERIFIED` 保留快照黃金檔通過；另有 ≥ 1 份開發快照）

| 來源 | T | S | U | A | D | B | 已知／預期特性 | 黃金檔 | 比對結果 |
|------|---|---|---|---|---|---|----------------|--------|----------|
| 中央社 | ✔ | ✔ | ✔ | 推 | ✔ | ✔ | meta author 為機構；記者在內文 | 未建立 | 未執行 |
| 自由時報 | ✔ | ✔ | ✔ | 推 | ✔ | ✔ | 可能有分頁（待確認） | 未建立 | 未執行 |
| 聯合新聞網 | ✔ | ✔ | ✔ | 推 | ✔ | ✔ | 追蹤參數；會員字樣；長文 | 未建立 | 未執行 |
| ETtoday | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | 壞 JSON-LD 需隔離（待快照確認） | 未建立 | 未執行 |
| 中時 | ✔ | ✔ | ✔ | 推 | ✔ | ✔ | 短快訊：短文章規則 | 未建立 | 未執行 |
| TVBS | ✔ | ✔ | ✔ | △ | ✔ | ✔ | 標頭無 charset；UTC 時間 | 未建立 | 未執行 |
| 三立 | ✔ | ✔ | ✔ | 推 | ✔ | ✔ | 時間不在 meta | 未建立 | 未執行 |
| 公視 PNN | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | LD 多型別干擾 | 未建立 | 未執行 |
| 風傳媒 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | 超大頁面；轉載文章 | 未建立 | 未執行 |
| NOWnews | ✔ | ✔ | ✔ | 推 | ✔ | ✔ | meta author 為機構 | 未建立 | 未執行 |
| BBC 中文 | ✔ | ✔ | ✔ | △ | ✔ | ✔ | 內嵌狀態 JSON；author 為 URL | 未建立 | 未執行 |
| PTT 網頁版 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | 無 `<p>`；metaline；推文排除 | 未建立 | 未執行 |

### 6.2 Tier B（部分支援；≥ 1 篇快照；欄位狀態與警告必須正確）

| 來源 | 期望 | 已知／預期特性 | 黃金檔 | 比對結果 |
|------|------|----------------|--------|----------|
| 報導者 | T／U／B；A、D 視站台 | 長文；無 LD | 未建立 | 未執行 |
| 關鍵評論網 | T／U／B | `og:type=website` | 未建立 | 未執行 |
| iThome | T／U／B | 無 LD、無 meta 時間 | 未建立 | 未執行 |
| 科技新報 | T／U／B | author 為 URL 須排除 | 未建立 | 未執行 |
| 數位時代 | T／U／B／A | 可能有付費內容→完整性警告 | 未建立 | 未執行 |
| 天下雜誌 | T／U；B 可能部分 | 付費牆風險→必須警告「疑似不完整」 | 未建立 | 未執行 |
| Yahoo 新聞 | T／U；B 視轉載型態 | 中文 slug；持續更新；轉載重複 | 未建立 | 未執行 |
| 維基百科 | T／U／B | 長文、表格、參考資料雜訊 | 未建立 | 未執行 |

### 6.3 Tier C（優雅失敗）
Medium、Dcard、Facebook／Threads／Instagram、LINE TODAY、vocus：目前僅首頁探針（§3.3）；**文章 URL 待蒐集**後才能驗證。預期：說明原因、不繞過、引導手動輸入。

---

## 7. 快照規範（決策 1）

### 7.1 保存內容（每篇一份）
| 項目 | 內容 | 檔案 |
|------|------|------|
| **HTML** | 原始回應位元組（不經轉碼）＋回應標頭＋最終 URL | `response.html`（或 `.bin`）、`headers.json` |
| **正文** | 擷取出的正文純文字（黃金檔草稿來源；經人工核對前為 `DRAFT`） | `body.txt` |
| **截圖** | **全頁畫面截圖**，作為人工核對的佐證 | `screenshot.png`（可多張） |
| **來源資訊** | 來源名稱、文章標題、請求 URL、最終 URL、取得日期時間、HTTP 狀態、使用的 User-Agent、robots 判定、Crawl-delay、取得方式、測試用途、使用條款確認狀態、各檔案 SHA-256 | `meta.json` |

**截圖取得方式【待確認】Q-31**：建議由**人工核對者以自己的瀏覽器**擷取（核對黃金檔本來就要開原網頁，且不增加自動化請求）；自動化無頭瀏覽器截圖會執行站台腳本、載入廣告與追蹤碼，列為選用且須單次、遵守 robots 與間隔。

### 7.2 取得規則（合規）
1. **只對「來源合規紀錄」（§4）已確認可用的來源擷取**；使用條款未確認者不擷取。
2. 誠實 UA；遵守 `robots.txt`（Disallow 則略過並記錄）與 `Crawl-delay`；同網域間隔取 `max(2 秒, Crawl-delay)`；每 URL 單次 GET。
3. **不登入、不帶 Cookie、不繞過付費牆／登入牆／反爬**；遇 403／挑戰頁／登入牆即停止並記錄（該情境本身就是 Tier C 測試資料）。
4. 抓取由使用者啟動的語料工具執行（FR-116），不是產品執行階段功能。
5. 快照**僅供本機測試，不公開散布，不用於訓練模型**。

### 7.3 存放與版本控管
- 位置：`tests/corpus/snapshots/<來源>/<ID>/`、黃金檔 `tests/corpus/golden/<來源>/<ID>/`、索引 `tests/corpus/manifest.yaml`。
- **版控規則**（沿用使用者既有專案的做法：含原廠版權內容的真實樣本以 `.gitignore` 排除）：`snapshots/`、`golden/**/body.txt`、截圖**不進版控**；`manifest.yaml`、`meta.json`、`golden.json`（不含正文）可進版控；`manifest` 記錄各檔 SHA-256 供完整性檢查。
- **發行版排除**：打包流程（`tools/make_portable.py`）須驗證 EXE 與發行資料夾**不含**任何 `tests/corpus` 內容。
- 語料缺失時，閘門測試**明確失敗並說明**（不得靜默略過）。

---

## 8. 合成夾具（補足真實網站難以取得或不穩定的情境；不含第三方內容）

ID 規則：`X-<序號>`。標籤：LAYOUT 版型、DYN 動態、FAIL 失敗、MISS 缺欄位、ENC 中文編碼、DUP 重複、PART 內文不完整、SAFE 安全／雜訊、PERF 效能。

| ID | 標籤 | 內容 | 預期 |
|----|------|------|------|
| X-01 | ENC | Big5 編碼頁面（標頭宣告 big5） | 正確解碼；`charset_used=big5` |
| X-02 | ENC | GBK／簡體頁面 | 正確解碼；提示為簡體 |
| X-03 | ENC | UTF-8 含 BOM；無標頭宣告、僅 BOM | 以 BOM 判定 |
| X-04 | ENC | 標頭宣告 UTF-8，meta 宣告 big5（互相矛盾） | 依標頭；不被偵測覆蓋 |
| X-05 | ENC | 未宣告編碼的 Big5 頁面 | 自動偵測＋警告 |
| X-06 | ENC | 內文含 emoji、罕用字、全形標點 | 解析保留；組稿檢查階段標示不可編碼 |
| X-07 | LAYOUT | 標準新聞（JSON-LD＋OG＋`<article>`） | 全欄位 FOUND |
| X-08 | LAYOUT | JSON-LD `@graph`，Organization 先於 NewsArticle | 取自 NewsArticle |
| X-09 | MISS | 壞 JSON-LD | 隔離；降級；警告 |
| X-10 | MISS | 作者只在內文首段「記者○○／台北報導」 | A＝INFERRED |
| X-11 | MISS | meta author 為機構名 | 不當記者 |
| X-12 | MISS | meta author 為社群網址 | 排除 |
| X-13 | MISS | 無發布時間 | D＝未取得 |
| X-14 | MISS | 無標題 | T＝未取得；PARTIAL |
| X-15 | LAYOUT | 純 `div` 文字、無 `<p>` | 保留換行 |
| X-16 | LAYOUT | 巢狀 `div` 含 `p` | 無重複段落 |
| X-17 | SAFE | 夾雜延伸閱讀／相關新聞／責任編輯／廣告 | 移除或標記 |
| X-18 | SAFE | 內文含 ESC 序列、控制字元、零寬字元 | 解析保留；正規化產生差異報告 |
| X-19 | DYN | 前端渲染外殼＋`noscript` | `CSR_SHELL`／`NEEDS_JS` |
| X-20 | DYN | 外殼但內嵌狀態 JSON 含完整文章 | 靜態取得 |
| X-21 | FAIL | HTTP 403 挑戰頁 | `BLOCKED` |
| X-22 | FAIL | 登入牆／年齡確認 | `LOGIN_REQUIRED` |
| X-23 | FAIL | 404／500／逾時／拒絕連線 | 對應錯誤碼 |
| X-24 | FAIL | 非 HTML（PDF／圖片） | 拒絕 |
| X-25 | FAIL | 重新導向過多／循環／非 HTTP(S) | 達上限即停 |
| X-26 | FAIL | 超過大小上限 | 中止 |
| X-27 | FAIL | 畸形 URL 清單 | 驗證失敗，不拋例外 |
| X-28 | PART | 結尾「展開全文／繼續閱讀」 | `SUSPECT_PARTIAL` |
| X-29 | PART | 付費牆：前 2 段＋訂閱提示 | `SUSPECT_PARTIAL`／`INSUFFICIENT` |
| X-30 | PART | 分頁文章 | `SUSPECT_PARTIAL`＋頁數 |
| X-31 | PART | 標題齊全、內文為空／過短 | `INSUFFICIENT`；不計成功 |
| X-32 | PART | 候選區塊為推薦清單 | 不採用 |
| X-33 | DUP | 同文加／不加追蹤參數、大小寫、query 順序 | Canonical 相同；警告重複 |
| X-34 | DUP | 同內容跨網域轉載 | 內容指紋／相似度警告 |
| X-35 | DUP | 僅標題相同、內容不同 | **不得**判重複 |
| X-36 | DUP | 同 Article 建第二份草稿／其他看板 | 額外警告 |
| X-37 | LAYOUT | 規則網域匹配（`example.com`／`www.example.com`／`notexample.com`） | 前兩者匹配 |
| X-38 | MISS | 規則檔損壞 | 只停用該規則 |
| X-39 | LAYOUT | 規則存在但版型已變 | 回退＋警告 |
| X-40 | PERF | 約 1 MB 長文、深層巢狀 | 預算內完成 |
| X-41 | PART | **黃金檔劣化樣本集**（由 VERIFIED 黃金檔自動產生：只有標題、截斷 10/20/50%、缺單一長段、加雜訊 3/5/10%、段落重複、順序錯置、標點替換、簡繁混入、空白差異、亂碼） | 供校準（GOLDEN_SPEC §8）與 AT-CAL |

### 8.1 真實樣本的缺口（誠實清單）
1. **非 UTF-8（Big5）的真實網站頁面**（V-22）：只有合成夾具；
2. **已確認的真實付費牆／截斷／分頁文章**：天下、數位時代、聯合新聞網、自由時報為「疑似」，**未確認**；
3. **真實動態網頁的文章頁**（Tier C 文章 URL 待蒐集）；
4. **已確認的真實轉載重複案例**（Yahoo 與中央社同題材為候選，未確認內容是否相同）；
5. 圖輯／影音／直播型文章頁；
6. 使用者實際會轉貼的其他來源（Q-27 的延伸）。

---

## 9. 尚未驗證清單（彙整）

| 類別 | 項目 | 狀態 |
|------|------|------|
| 來源 | 20 個來源的**使用條款**未人工確認（§4） | 未驗證 |
| 來源 | 39 篇文章的內文是否完整、是否有付費牆／分頁（僅有字樣訊號） | 未驗證 |
| 來源 | Tier C 文章 URL（Medium、Dcard、Facebook、LINE TODAY、vocus） | 未蒐集 |
| 來源 | 已確認的 Big5／付費牆／分頁／轉載重複真實樣本 | 未蒐集 |
| 快照 | 快照、截圖、`meta.json` | 0 份 |
| 黃金檔 | 黃金檔、`VERIFIED` | 0 份 |
| 比對 | 任何解析器對黃金檔的比對結果 | 未執行（解析器尚未存在） |
| 指標 | `metrics_v0` 的校準、門檻凍結 | 未做（GOLDEN_SPEC §8） |
| 觀察 | 先前取樣中的推論（ETtoday 壞 JSON-LD、追蹤參數用途、各站記者署名位置） | 待快照確認 |
| 工具 | 中央社 `robots.txt` 以標準解析器判讀失敗的原因 | 待查 |
| 截圖 | 截圖取得方式（Q-31） | 待確認 |

---

## 10. 維護流程與 manifest 結構

1. **建立快照**：使用者在 §4 確認某來源後，執行語料工具（Phase 1.6）對其文章清單各 GET 一次，寫入 §7.1 檔案。
2. **黃金檔**：依 GOLDEN_SPEC §3、§9 建立與人工核對；每來源 ≥ 1 份由使用者核對；保留快照於規則凍結後擷取。
3. **回歸**：離線、不連網；輸出每來源×快照×欄位結果；更新 §6 矩陣（FR-114）。
4. **線上抽查**（預警，非閘門；需環境變數啟用，沿用使用者既有專案的做法）：對清單 URL 重新 GET，與最近快照比對結構訊號。
5. **新增來源**：IMPLEMENTATION_PLAN §4.2 SOP。

```yaml
# tests/corpus/manifest.yaml（示意；實際 schema 於 Phase 1.6 定案）
- id: S-ettoday-01
  source: ettoday
  tier: A
  article_title: "（取得當日標題）"
  url: https://www.ettoday.net/news/20261015/3255218.htm
  retrieved_on: 2026-10-15
  purpose: "壞 JSON-LD 隔離；作者在 meta"
  role: dev            # dev＝規則開發用；holdout＝驗收用（規則凍結後擷取）
  terms_check: pending # pending / ok / blocked
  snapshot: snapshots/ettoday/S-ettoday-01/
  golden:
    path: golden/ettoday/S-ettoday-01/
    status: none       # none / DRAFT / DEV_CHECKED / VERIFIED / REJECTED / DISPUTED / SUPERSEDED
  tags: [LAYOUT, MISS]
  sha256: {}           # 各檔 SHA-256，擷取時填入
```
