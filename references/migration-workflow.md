# 現有系統遷入 AI GO

> 只有「用戶有現存系統要遷入」時才需要這份。純新建 App 完全用不到。
>
> 這是 Phase 1.25 與 Phase 1.5 的**遷移分支**，接在 SKILL.md 的主流程上：
> §1 在任何單一 App 開始 Phase 1.5 之前做；§2 在該 App 的 Phase 1.5 計畫中做。
> **不論單系統或多系統，每個要遷入的系統都必須先做 §2.0 的 stack 盤點、
> 再過 §2.1 的產品線判斷**——判斷結果不可逆（警示與四象限落點見 `product-line-decision.md`），
> 而判斷品質取決於盤點：沒盤過 stack 就分流＝憑感覺押不可逆的注。

---

## 目錄

- 1. 多系統遷入盤點（2 個以上外部系統時）
- 2. 單一系統的遷移評估
- 3. 詳細參考

---

## 1. 多系統遷入盤點（2 個以上外部系統時）

> **觸發條件**：用戶明確表示有 **2 個以上外部系統**（各自帶 Supabase / Google Sheet / MySQL 等 DB）要遷入 AI GO。
> 若僅遷入 1 個系統或純新建 App，跳過此步驟直接進入 Phase 1.5。

### 目的

在任何單一 App 開始 Phase 1.5 之前，先建立**全局視圖**，避免各 App 各自為政導致資料架構混亂。

### 盤點流程

1. **外部系統清單**
   - 列出所有要遷入的系統名稱、用途、技術棧、DB 類型
   - 每個系統的核心資料表 / Sheet 清單與主要欄位

2. **逐系統做 stack 盤點與產品線判斷**（★ 不可省——結果不可逆）
   - 對清單上**每一個**系統先做 §2.0 的 stack 盤點、再跑 §2.1 的決策樹，
     記下 stack 形狀結論、產品線與模式
   - 不要假設「全部都做成 Custom App」——整套要原樣搬的服務屬於 Hosted App，
     硬塞進 Custom App 重構會做白工

3. **跨系統資料表交叉比對**
   - 找出語意相同的表（如都有「客戶」「專案」「訂單」）
   - 判斷是否指向同一群實體（同一批客戶？不同市場的客戶？）
   - 決定合併（進同一張 AI GO 表）或分離（各自獨立表）
   - 詳細的決策框架見 `references/custom-app-dev-guide.md` §22
   - 判定走 Hosted App 的系統**也要參與比對**：它若要與其他 App 共用資料，
     資料就該落在平台側（自建表），由 Hosted App 走 Open Proxy 存取
     （見 `references/hosted-apps.md` §7.1）

4. **AI GO App 規劃**
   - 決定做成幾個 AI GO App（含 Hosted App）
   - 每個 Custom App 的 `app_domain` 初步命名（避免碰撞）
   - 確定遷入順序：主資料（客戶、產品）先於交易資料（訂單、案件），無依賴者先行

5. **產出：遷入全景表**
   - 格式：`| 外部系統 | stack 形狀（§2.0） | 產品線（Custom / Hosted） | 模式（模板 slug / visibility） | 對應 AI GO App | app_domain | 使用者群 → 角色 | 遷入順序 | 語意重疊的表 |`
   - 「使用者群 → 角色」欄跨系統彙整：同一批人（例如經銷商）在多個系統出現時只開一個角色，
     不要每系統各開一個（`member-admin.md` §1）
   - 此表在後續各 App 的 Phase 1.5 中持續參照

---

## 2. 單一系統的遷移評估

> 依序執行 §2.0 → §2.5。§2.1 判走 Hosted App 的系統只需再做 §2.2（解構盤點）
> 與資料側的 §2.4／§2.5（資料落點見 `hosted-apps.md` §7.1），
> 開發與部署改走 `references/hosted-apps.md`，不進本 skill 的 Phase 2–4；
> 驗證閘門用該檔 §3.4（Phase 4.2 的等價物），不是沒有閘門。
> **Hosted 線從盤點到切換、退場的完整順序與每階段的通過條件，照 `hosted-migration-runbook.md`。**

### 2.0 Stack 結構盤點（★ 架構師視角，最先做）

產品線判斷（§2.1）不憑空問用戶——先用架構師視角把系統的 stack 形狀盤出來，
分流結果直接由它推導。這是**快速盤點**（幾分鐘等級，看 repo 結構、依賴清單、
部署設定即可），深度細盤留給 §2.2：

| 盤點項 | 要判讀的事 |
|---|---|
| 前端 | 框架（React / Vue / 靜態頁…）、是否 SPA、是否直連 BaaS（Supabase / Firebase）；**面向**：應用介面（登入後使用的工具）vs **公開 web 資產**（官網、電商 storefront——訊號：自有網域、SEO／社群分享卡、內容行銷頁、匿名是主要動線） |
| 後端 | **有沒有自有伺服器行程**；有的話看形狀：無狀態 request/response API（可改寫）vs 常駐進程 / WebSocket / 自選框架深度綁定（改不動） |
| 資料 | DB 種類與表數量級、storage（S3 / Supabase Storage…）——只盤不分流，落點統一由 §2.4 與規則 32 決定 |
| 附屬 | 背景排程、對外 webhook、第三方整合、環境變數／金鑰 |
| **原雲端拓撲**（2026-09-21 補） | 現在跑在哪家雲、幾個服務（web／API／DB／cache／queue／worker）、誰連誰、網域與憑證在哪、部署怎麼觸發（手動腳本／CI／平台 CLI）。畫得出一張圖才算盤完——遷入後每個節點都要有落點或退場 |
| **本機／外部跑的微服務與排程**（2026-09-21 補） | repo 裡看不到、但系統實際依賴的東西：跑在**誰的機器**（同事的筆電、公司內網 VM、另一個雲端專案）、觸發方式（本機排程器／手動／被 webhook 打）、依賴的內網資源（ERP 資料庫、內網 API、本機憑證檔）、對外副作用（寄信、推播、寫第三方）。每一支的落點三選一：**搬平台排程**（能改成打 app 的 action 就搬）／**留原機、改指向**（碰內網資源的搬不動，只把它打的網址改成 AI GO 上的 app）／**退役**（遷入後平台功能已涵蓋）。落點之外還要寫**切換順序與回滾**：這支先停還是後停、停了誰會發現、怎麼切回去 |
| **狀態層** | 原系統**算好的中間結果**：預先算好的報表／快照、排程重烤的產物、session 或暫存檔、寫在原 DB 但不屬於業務資料表的東西。**每一項都要有落點**——沒有落點的會在遷入後默默退化成程序內記憶體，容器縮到零就清空，症狀是「打開是舊數字」，會被誤判成資料源壞掉。落點三選一：要能被平台其他地方讀到 → 自建表；只有這支 app 自己用但不能消失 → `/data` 持久碟（`hosted-apps.md` §7，`persistent_disk=true`）；重算很便宜 → 不搬、每次重算。**寫成 runner／容器本機的 `.json`／sqlite 不是落點**（不擋、但隨 pod 消失，`custom-app-dev-guide.md` §19「禁止項」） |

> 典型形狀：web repo 在某個 PaaS 上，但另有幾支只在同事本機跑的東西——人員同步（讀**內網** ERP 資料庫，
> 搬不動 → 留原機、改成打 AI GO 上的 API）、通知重試（可搬平台排程或退役）、靠本機工具或訂閱制服務的分析
> 排程（搬不動 → 留原機）、部署腳本（遷入後由平台部署取代 → 退役）。
> 沒盤到這些，遷入後第一個排程日名單就不會更新，而且沒有任何錯誤訊息。

產出「**stack 形狀結論**」四選一，帶進 §2.1 問題二：

1. **純前端**——無自有後端行程，且資料層只是存取（直連 BaaS 但只當資料庫用的 SPA 算這類，走 §2.4 映射）
2. **有後端、可改寫**——無狀態 API，業務邏輯可搬進 `execute(ctx)` 形狀
3. **有後端、整搬**——常駐進程、WebSocket、自選框架深度綁定，或形狀上可改寫但工作量／風險不可行
4. **BaaS 為後端、瀏覽器直連**（2026-09-22 補）——沒有自有伺服器行程，但「後端」不只是資料層：
   認證（BaaS 發的 JWT）、授權（RLS policy）、業務邏輯（SQL function／trigger）、
   排程與外呼（DB 內的 cron／HTTP 擴充）**全在資料庫裡**，前端只是薄殼。
   **辨識訊號**（任一成立就不是第 1 類）：前端程式裡大量 BaaS client 直接查表的呼叫、
   DB 有數十到數百條 RLS policy、有數十支以上承載業務規則的 SQL function／trigger、
   登入用 BaaS 自己的 Auth（session／JWT 由它發、RLS 靠那顆 JWT 解身分）

> **第 4 類最容易被誤判成第 1 類**（某遷入案 2026-09-22 實踩）：它的前端確實「沒有後端行程」，
> 照第 1 類會判成 Custom App 重寫——但要重寫的其實是整個後端。擋得下來的只有 §2.3 的
> 可移植性核對逐項攤開（Tailwind、檔案路由、數十顆 npm 依賴、>500 檔，實務上不會過）。
> **預設走向是 Hosted App 整搬**（§2.1 問題二已列）。
>
> **資料層是待決事項，計畫裡不要先承諾任何一條路**：這一型的資料層需要 BaaS 的 RLS（以 Auth 發的 JWT 判斷權限）、
> SQL function 與 DB 內排程，而 **`dev-rules.md` 規則 32 的例外明文只限「關聯式 PostgreSQL」，
> 不含 Auth／Storage／Realtime／Edge Functions／pg_cron** ⇒ 現行例外**不涵蓋**這一型；
> 例外的「一租戶一顆、服務以 schema 分」粒度在這一型也不成立（BaaS 的 Auth 是 per-project、
> Data API 必須開、既有 migration 寫死 `public`）。builder 的動作是**把這個落差連同證據
> 當成平台／PO 的決議事項提出來**，不是自己選一條、也不是改規則 32。
> 待決的是**資料層**（RLS、SQL function、DB 內排程、瀏覽器直連）。**登入本身**維持原本的 BaaS Auth 是正當選項
> （§2.4.5、`member-admin.md` §7.1），不必等這個決議。
>
> **前置步驟：先取正式庫的 schema-only dump**（是前置，不是建議）。「拿 repo 裡的 migration
> 重建一份 schema」在這一型會失敗：某遷入案（2026-09-22 實踩）211 支手動貼上去的 migration 裡，
> 7 支是綁正式資料列的 backfill（空庫直接失敗），另有 1 個被 5 支 migration 引用的欄位
> **repo 裡沒有任何檔案建過**（正式庫已漂移）。**repo 不是 schema 的正本，正式庫才是。**
>
> **保留 BaaS 自己的 Auth／session 又改用 AI GO 登入時，要加做「即時撤權」**：BaaS 發的 token 瀏覽器直接拿去打資料，
> 被平台移除的人在 token 到期前照用——做法與撤權延遲交代見 `dev-rules.md` 規則 34。

另判**前端面向**二選一（帶進 §2.1 問題二的純前端行）：
**應用介面**（登入後使用的工具）／**公開 web 資產**（官網、電商 storefront）。

### 2.1 產品線與模式判斷（★ 承接 §2.0，結果不可逆）

> **兩問四象限的本體（問題一落點、四象限表、混合方案分工、不可逆與硬前提）是兩條路共用的，
> SSOT 在 `references/product-line-decision.md`**——本節只補遷入特有的輸入：
> 問題一改問「**原系統現在是誰在登入**」，問題二用 **§2.0 的 stack 形狀×面向**
> 取代新建線的需求形狀。先問使用者是誰，再看 stack 形狀——模式選錯要砍掉重建，
> 技術形狀選錯頂多多花工。

**問題零：原系統進正式環境了嗎？**（判準見 `product-line-decision.md` §0）
→ **已進正式環境、有既有程式要搬**（有真實使用者在用，或有不能丟的正式資料）= 預設 **Hosted App 整搬**，
主流程照 `hosted-migration-runbook.md`；問題二的表只用來確認形狀與資料層待決事項，不用它改判 Custom。
用戶明確要重寫成 Custom App 才改判，改判前先把 §2.3 可移植性核對與重寫工作量攤開確認。
→ **還沒進正式環境**（只有 repo／原型／demo，資料可丟）= 先看 **Custom App** 做不做得到：
照問題二的表判，§2.3 可移植性核對過得了就走 Custom App，既有程式當素材重寫。
→ **已進正式環境、但沒有程式要搬**（只有試算表／SaaS／人工流程與正式資料）= 產品線照新建線判（先看 Custom App），
正式資料照 §2.4／§2.5 搬進平台。
拿不準就直接問「現在有沒有人每天在用、裡面的資料能不能丟」，不從 repo 的部署設定猜。

**問題一：原系統有哪些登入者？有沒有不登入就能看的部分？**
→ 有登入者（員工、外部經銷商、客戶都算）= **internal**，人一律成為租戶成員、用角色分流
（誰能開、掛什麼角色留給計畫第 1.7 項，`member-admin.md` §1、§7）；
只有匿名訪客 = **Hosted public**；兩者都有（登入後系統 + 匿名可看的頁）= **拆**：匿名部分 Hosted public、
登入部分 internal。原系統有「客戶帳號」不是 external 的理由——那些客戶邀進租戶掛外部角色。
拿不準就直接問「這系統現在有哪些人登入、有沒有不登入就要看的頁」，不可用預設值帶過。

**問題二：§2.0 的 stack 形狀結論＋前端面向是哪一種？**

下表與表下各點的預設走向適用於**還沒進正式環境**的系統；已進正式環境、有既有程式要搬的，寫 Custom App 的地方一律改為 Hosted App（問題零）。

| stack 形狀 × 面向 | 預設走向 |
|------|------|
| 純前端 × 應用介面 | **1..n 個 Custom App**（前端重寫進 Builder；直連 BaaS 的資料層走 §2.4 映射進平台） |
| 純前端 × 公開 web 資產（官網、電商 storefront） | **Hosted App**（zbpack 任意棧含靜態站、`hosted-apps.md` §9 綁自訂網域）——Custom App 的 `/runtime` 網址＋HashRouter 做不了 SEO 與自有網域，`/pub` 只適合少數公開頁，不承載整個公開站 |
| 有後端、可改寫 | **Custom App**（後端邏輯改寫成 Server Action）；用戶明確不願重構 → 改判 Hosted App |
| 有後端、整搬 | **1..n 個 Hosted App**（整套原始碼進容器） |
| BaaS 為後端、瀏覽器直連 | **Hosted App 整搬**（Custom 重寫要 §2.3 可移植性核對**全部**過，實務上不會過）；**資料層：待平台決議**——規則 32 的例外不涵蓋 Auth／RLS／SQL function／DB 內排程（§2.0 第 4 類）；登入維持原本的 BaaS Auth 不受此限（§2.4.5） |

- stack 形狀給的是**預設值**，最終仍要向用戶確認——特別是「可改寫」與
  「整搬」的邊界：改寫工作量（§2.3 可移植性核對）攤開後用戶不買單，就改判整搬。
- **自有網域／SEO 需求凌駕形狀判斷**：不論後端可不可改寫，需要自有網域的
  公開站一律偏 Hosted——公開 web 資產的判定看產品面向，不看技術棧。
- **混合情景（官網＋登入後系統）→ 拆開各走各的**：官網 → Hosted App、
  系統 → Custom App（已進正式環境、有既有程式要搬的 → Hosted App，問題零）；兩邊共用的資料落平台側（自建表；Hosted 走 Open Proxy，
  `hosted-apps.md` §7.1），不因共用而硬併成一個 app。
- ⚠️ **資料層不參與這個判斷**：不論分到哪條線，DB 與 storage 都**不允許**
  自立 Hosted App 承載（`dev-rules.md` 規則 32）——table schema 一律落平台
  預設表／自建表、檔案一律 Storage API（Hosted 線就是 `/open/storage/*`，
  `hosted-apps.md` §5.2）；Hosted App 的資料層一律改寫 Open Proxy、檔案層改寫
  `/open/storage`（`hosted-apps.md` §7.1）。「把 Postgres／包了 REST 的 DB
  搬成一個 Hosted App 給其他 App 打」不是選項。
  唯一例外見 **dev-rules.md 規則 32**（平台工程師核准並建立的租戶級外接 PostgreSQL；核准紀錄存在才生效）：
  §2.4 映射做完、逐項確認交易／FK／唯一約束／列鎖／RLS 在平台**做不到也改不掉設計**時才提申請，
  申請前不得先開庫、不得先切。

**判斷結果**：填入 **app 分配表**（`product-line-decision.md` §7；每個 app 一列：alias、產品線、
模式、負責的功能群、拆分理由），多系統時同步記入 §1 的全景表。四象限落點與不可逆警示
（`access_mode` 建立後不可改、`internal` 不能開匿名、DB 不得立成 Hosted App）
見 `product-line-decision.md` §4／§6，不在此重複。

### 2.2 專案解構盤點（前端 + 後端 + DB 完整專案時）

要遷入的不只是「一個 DB」而是**整個專案**時，資料表映射（§2.4）只涵蓋一半——
另一半是程式與服務元件的落點。逐項盤點原專案的：

- 頁面／路由、後端 API endpoints、背景排程、對外 webhook 接收
- 檔案儲存、第三方 API 呼叫、環境變數與金鑰
  - ★ **環境變數要逐顆盤，不是寫一句「env 要設」**：從程式碼、`.env.example`、**原託管平台的
    env 設定頁**、本機排程四個來源盤出全部 key，做成對帳表，遷入後逐顆核對 AI GO 上有沒有設；
    沒設的列給用戶、提醒負責人設定——做法與常見漏項見 `hosted-apps.md` §4「遷入既有系統時要重新
    提供的 env 清單」（Custom App 線同樣要盤，後端密鑰落在 Builder「服務」tab／`ctx.secrets`，前端設定另列落點——見該節「Custom App 線」段）。缺的 env 通常不會讓主流程壞，
    而是讓某個功能或排程每天默默失敗
- 被外部呼叫的端點與寫死的正式資源：切換前照 §2.6 盤出「誰會從外面打進來」與 fallback 回正式的寫死值
- **使用者／認證表**（★ 特殊處理，不進 §2.4 的表映射流程）
- DB 層邏輯（trigger / view / RLS / stored procedure / edge functions / realtime）

每一項在 AI GO 的對應落點、以及「使用者表為什麼不能照一般表遷」的完整說明，
用 `resources/project_deconstruction_template.md` 逐項填寫。

### 2.3 語言與架構評估（Custom App 線）

> 判走 Hosted App 的系統跳過本節——Hosted App 支援任意技術棧，
> 應用形狀限制見 `hosted-apps.md` §2。

- 若現有系統不是 TypeScript + Python：
  - **務必解釋**為什麼 AI GO 選擇 TypeScript + Python（見設計理念 / §21）
  - **建議用戶建立新的 AI GO 專案來重構**，而非嘗試直接移植原始碼
  - **原自身本地專案不更動**，AI GO 專案獨立開發
- 若已是 TypeScript + Python，**也不代表能直接搬**——先跑下面的可移植性核對，
  再評估哪些檔案能重用：

  **前端可移植性核對清單**（任一項不符都需要改寫，向用戶如實預告工作量）：

  | 核對項 | Custom App 的限制 |
  |---|---|
  | CSS 方案 | 只支援全域 `App.css`；Tailwind / CSS Modules / styled-components / MUI **全部不可用** |
  | Router | 只能 `HashRouter`；`BrowserRouter` / Next.js 檔案路由不可用 |
  | 依賴 | Runtime 只提供 react、react-dom、react-router-dom、lucide-react、react-hot-toast 五個；**其他 npm 套件裝不了** |
  | 瀏覽器 API | Shadow DOM 內 `confirm()` / `alert()` / `prompt()` 不可用 |
  | 規模 | 查目標 App 的 `GET /api/v1/builder/apps/{app_id}/limits`，以 `vfs` 數值為準 |
  | 動態載入 | `import()` 動態 import 不支援 |

  實務結論：**即使原前端是 React + TS，CSS 與依賴幾乎必然要重寫**；
  能直接搬的通常只有純邏輯（型別定義、資料轉換、hooks 內的業務規則）。
  後端同理：Python 程式的**邏輯**可搬，但形狀要改成 `execute(ctx)`、
  依賴要過 `actions/requirements.txt` 的白名單規則（§16.2）、
  對外呼叫要改 `ctx.http.call`。

### 2.4 外部 Schema → AI GO 架構映射（★ 必要）

> 分流判定與直接開發**同一棵決策樹**（表級 → 欄位級），SSOT 在
> `custom-app-dev-guide.md` §19——遷入不因「資料是搬進來的」放寬任何判定。
> 本節列的是把外部 schema 餵進那棵樹的操作步驟。

- 列出外部系統所有資料表 / Sheet 與其欄位結構
- **自建表的實體名先定英文**（表 `biz_<英文複數>`、欄位 snake_case），中文只放顯示名——遷入是一口氣建一批表的場景，
  中文顯示名建出來的是永不可改的 `tbl_3`／`col_2`；規範與兩步命名法見 `resources/migration_mapping_template.md`
  自建表區塊與 `data-center.md` 雙軌命名
- **使用者／認證表先剔除**——它們走 §2.2 解構清單的認證映射，不進本流程
- 逐表對照（先跑 Phase 1.5 第 3 點的雙邊盤點；**每張外部表都先用業務語言查 `default-table-lookup.md` §2**——
  外部表名不是語意：`tenders` 是商機、`agencies` 是客戶、`deliverables` 是里程碑）：
  - 平台有同語意的實體 → 預設表原生欄位；無原生對應的欄位 →
    **app 執行期要讀寫的一律 `custom_data` JSONB 或自建表**；
    延伸欄位（EAV，`data-center.md` §10）只給「app 不讀、管理者在資料中心 UI 維護」的欄位
    ——app 的前端與 action 都取不到 EAV 值（§10 的通道表、issue #71）
  - 查過查表與 Meta API 仍沒有同語意實體 → 自建表，映射表寫下「已對照 <預設表>／不採用理由」
    （語意落在 CRM、專案、銷售採購、HR、會計的表**預設引用預設表**，只有平台真的沒有對應實體才自建；
    常見誤判見查表 §5）
  - ★ **欄位級的「平台有沒有這個欄位」只認引用面 `GET /refs/tables/{t}/columns`**——
    Meta 面的 `fields` 是策展白名單會少欄（`hr_employees` 20 vs 42，缺地址欄），
    依 Meta 判會把整批欄位誤推去自建／EAV（查表 §0、issue #70）
  - 租戶已有語意相同的自建表 → 直接重用；**欄位不足 → 加實體欄位**
    （`data-center.md` §7 加欄），不要因缺欄就新建表或把結構化欄位塞進 json
- 欄位型別對不上時，查降級對照表（`custom-app-dev-guide.md` §23.7）
- 處理外部表之間的外鍵 / 關聯（AI GO 需用 ID 欄位 + 程式邏輯維護參照完整性）：
  - 指向**預設表**的外鍵（遷入案的 `user_id` → `customers` 等）**一律映射成 `text` 存 UUID**——
    `relation → 預設表` 只有部分表可解析、無法事先查，在第三張表才撞到 422 會回頭重建
    （`data-center.md` §3）
  - 複合主鍵／`ON CONFLICT`／partial unique／advisory lock／`UPDATE … WHERE` 全部在映射表
    改寫成 `legacy_id`(unique) + 409 的模式，JOIN 改成兩平面的過濾組合——
    做法表見 `custom-app-dev-guide.md` §23.9，**在映射階段就決定**，不留到改寫程式時才發現
  - 預設表的 CHECK 值域從 columns 端點看不到——映射表的「AI GO 欄位」欄先照
    `custom-app-dev-guide.md` §20.2.1 的值域表對齊，不要對正式租戶試寫
- 產出「外部 Schema ↔ AI GO 映射表」（模板見 `resources/migration_mapping_template.md`）
- 若有 §1 的全景表，映射須與全景表的合併 / 分離決策一致
- 詳見 `references/custom-app-dev-guide.md` §22

### 2.4.5 使用者與登入的落點

登入方式二選一，遷入計畫要寫明選哪一種（**不預設引導**；正本 `member-admin.md` §7.1）：

- **維持原系統自己的登入**：app 照舊自己認人，使用者不必有 AI GO 帳號。
- **選用 AI GO 登入**：原系統的 `users` 表不搬進 AI GO，先過「租戶成員＋app 角色」這道門，app 自己的名單是第二道，
  兩道門怎麼走依產品線不同。遷入計畫要多一張「app 可登入名單 vs 租戶成員」對照表，邀請由客戶做；
  UAT 只補測試者：`uat-environment.md` §3.5。
**若選用 AI GO 登入、又保留自家認證後端（自己發 session／token），另須做即時撤權**（`dev-rules.md` 規則 34）；撤權延遲要寫進交接。

### 2.5 資料遷移計畫（★ 若需遷入歷史資料）

> **閘門：§2.4 的映射表未產出、或未經用戶確認前，不可執行任何匯入。**
> 映射表裡任何一張自建表缺「已對照的預設表／不採用理由」，視同映射表未產出。
> 「先倒進來再整理」不接受——匯錯落點的資料要清要搬，成本遠高於先把逐欄對應做完。
> Custom App 線與 Hosted App 線都受此閘門約束。

- 遷移範圍：全量 / 部分 / 僅結構不帶資料
- **簽核流程檢查**（★ Data Reference 軌必查）：目標預設表掛簽核流程時，
  批次匯入會逐筆開簽核單——匯入前依 `custom-app-dev-guide.md` §23.1 的
  「匯入前必查」處置（首選：請管理員暫停流程 → 匯入 → 恢復）
- **延伸欄位寫入計畫**（若映射有欄位分到 EAV 軌）：逐列 PATCH、無批次端點，
  量大先重新評估分流——機制見 `custom-app-dev-guide.md` §23.8
- **抽取路徑**：資料怎麼從來源離開（★ 先確認，MySQL/Postgres 直連只能在本地做）
  → `custom-app-dev-guide.md` §23.6
- 遷移方式：本地腳本打平台 API / Server Action 批次匯入 / API 逐筆寫入
- ID 體系轉換：外部自增 ID / Sheet 行號 → AI GO UUID 的對應方案
- 遷移後驗證：筆數比對、關鍵欄位抽驗
- 詳見 `references/custom-app-dev-guide.md` §23
- Hosted App 線的資料落點與匯入方式（無 `ctx.db` 可用）→ `hosted-apps.md` §7.1

### 2.6 切換準備：從外面打進來的登記項、寫死的正式資源（★ 切換前必做）

遷入後最容易「主流程正常、切換那天才一次全壞」的是兩類東西：**登記在外面、會打進來的設定**，以及
**程式裡寫死的正式資源**。repo 裡搜不到完整清單，env 對帳（`hosted-apps.md` §4）也蓋不到，只能主動盤。

**A. 外部登記項：誰會從外面打進來**

第三方後台、別人的機器上登記著原系統的網址或金鑰。AI GO 上 env 全對，它們還是打舊站。
訊息平台的 webhook、聊天 App 這類一個 channel／bot 只能設一個網址，UAT 必須另開一組測試登記；
可以設多個的（OAuth redirect URI、金流 webhook、Pub/Sub 訂閱）也建議 UAT 分開，避免互相污染。

盤法：先從程式盤出所有**被外部呼叫的端點**（webhook 接收、OAuth 回呼、推送訂閱端點、排程或內部呼叫端點、
裝置或代理程式回報端點、MCP／OAuth well-known），找法是路由清單＋驗簽、驗金鑰的程式碼；再對每一個問
「誰登記了它、登記在哪個後台、誰有權改」。常見類別：

| 類別 | 登記在哪 | 切換時要改 | 沒改的症狀 |
|---|---|---|---|
| 訊息平台 webhook（LINE、Slack、Telegram…） | 該平台的開發者後台 | webhook 網址；驗簽 secret 若加密存在 DB，解密金鑰要沿用原值 | 收不到訊息，或全部 401 |
| OAuth 回呼與來源（Google、GitHub、LINE Login…） | 雲端主控台的 OAuth client | 加新網域的 redirect URI 與 JS origin；UAT 另加，並把測試帳號加進測試使用者 | 登入或連結時 `redirect_uri_mismatch` |
| 推送訂閱（Pub/Sub push、行事曆／雲端硬碟 watch、金流 webhook…） | 雲端專案、金流後台 | 推送端點網址與驗證金鑰 | 事件靜默不來 |
| 腳本與自動化（Apps Script、Zapier、n8n、表單） | 各自的腳本或流程 | 寫死的網址與簽章金鑰 | 進件或同步靜默停止 |
| 留在原機的排程與微服務（§2.0） | 同事電腦、內網 VM | base URL 與金鑰 | 打舊站：兩邊重複跑，或新站的佇列沒人領 |
| 終端裝置與代理程式（員工電腦的回報設定、安裝腳本、MCP 設定） | 每一台機器 | 重跑安裝或改設定 | 資料只進舊站 |
| 聊天 App（Google Chat、Teams 這類，一個 App 只能設一個端點） | 雲端主控台 | 端點網址 | UAT 與正式互搶 |
| 第三方的 IP 白名單 | 對方系統或後台 | 新站的出站 IP（Hosted 有沒有固定出站 IP **未核實**，先問平台；退路是請對方改用 token 或簽章驗證，或這支整合留在原機） | 對方 API 直接拒絕連線 |
| SSO／SAML、進件信箱、監控探針 | IdP 後台、郵件轉寄規則、監控服務 | ACS 網址、轉寄目的地、探測網址 | 登入失敗、進件停止、監控誤報或不報 |
| 自訂網域、DNS（Hosted App） | 網域商 | `hosted-apps.md` §9 回傳的 DNS 記錄；切換前先建好網域、過了憑證驗證（`pending_cert`）再改指向 | 舊網域仍指向舊站 |

產出一張**切換清單**：每一項寫「登記在哪、誰有權改、改成什麼、何時改、怎麼驗證、怎麼改回去」。
第三方後台在 AI GO 之外，由有權限的負責人改；AI 列規格與驗證方式，不代設。
UAT 用**另一組測試登記**（測試官方帳號、測試 OAuth client 或測試使用者、測試主題），不要指向正式那一份。

切換順序：新站先補齊要沿用原值的密鑰（`hosted-apps.md` §4 對帳表處置為「照搬值」的列；特別是兼當加密金鑰、
換了會讓資料庫裡已加密的資料解不開的）→ 部署與 UAT 測過的同一版 →
逐項改指並當場驗證 → 停掉舊站的排程，再開新站的（不可兩邊同時開）→ 每項保留改回去的方法，直到觀察期結束。

**B. 寫死的正式資源：fallback 讓新環境靜默打回正式**

原系統只有一個環境時，程式常把正式的網址、雲端資源 ID 寫成預設值或 fallback。搬到新站或開 UAT 之後，
env 沒設的那一刻就靜默退回正式值——沒有錯誤訊息。典型三種：

- env 沒設就退回寫死的正式雲端硬碟 ID → UAT 上傳的檔案寫進正式硬碟
- 寫死正式的訊息主題或訂閱 → UAT 在正式主題上建訂閱、續訂正式在用的訂閱
- 寫死舊平台網址 → 信件、通知、安裝說明裡的連結指回舊站

找法（★ 只輸出命中片段與位置，**不印整行**——同一行可能帶著密碼或金鑰）：

- 一律用只印命中片段的搜尋：`rg -no '<pattern>'` 或 `grep -rnoE '<pattern>'`，並排除 `.env*`、憑證 JSON、`node_modules`、建置產物
- 舊平台網域：`\.zeabur\.app`、`\.vercel\.app`、`\.onrender\.com`、`\.herokuapp\.com`、`\.fly\.dev`、`\.railway\.app`、
  `\.netlify\.app`、`\.pages\.dev`、`\.web\.app`、`\.firebaseapp\.com`、`\.appspot\.com`、`\.run\.app`、`\.azurewebsites\.net`、
  `\.supabase\.co`，以及原系統的正式網域
- 讀 env 後帶預設值的寫法，只印「檔案:行號＋key 名」：JS 用 `process\.env\.[A-Z0-9_]+\s*(\|\||\?\?)`、
  `import\.meta\.env\.[A-Z0-9_]+\s*(\|\||\?\?)`；Python 用 `os\.(getenv|environ\.get)\(\s*["'][A-Z0-9_]+["']\s*,`；
  再加上專案自己的設定讀取函式（`getenv(`、`config.get(` 一類，同 `hosted-apps.md` §4 步驟 1）。
  預設值是不是正式資源，**逐處人工開檔判讀**，判讀結果只寫 key 名與「是／否正式資源」，不把值抄進對話或文件
- 雲端資源識別：`projects/[^/]+/topics/`、`projects/[^/]+/subscriptions/`、寫死的雲端硬碟／試算表 ID、正式 bucket 名稱

修法：

- 一律改讀 env；**非正式環境 env 沒設就直接報錯**（fail closed），不准退回正式值
- 是不是正式環境由 app 自己的一顆明確 env 判斷（例如在 runtime-settings 明設 `APP_ENV=production`），
  **沒設＝視為非正式**，不要從網址推測。平台注入的 `AIGO_ENV` 的語意未定義，正式與 UAT 是同平台上的兩支 Hosted App，
  值很可能相同，未實測前不要拿它判斷
- 加一條測試或 CI 檢查，禁止舊平台網域字樣再進到程式裡
- 開 UAT 前先做完這一步（`uat-environment.md` §3）；驗證時在 UAT 觸發每一個會用到這些資源的功能，確認正式資源沒有新東西

**C. 檢查工具**（只讀，不印任何設定值）

- `scripts/aigo_env_diff.py`：比對兩個 Hosted App 的 runtime-settings（例如正式與 UAT），列出只在一邊的 key、空值、
  **兩邊值相同的密鑰**（正式與 UAT 共用同一把密鑰本身就是問題）；或拿 §4 的對帳表檢查一支 app 缺哪些 key——
  清單只放「目標位置＝Hosted runtime-settings、處置不是不搬／退役」的列，不放平台注入的 `AIGO_*`、`PORT`；
  正式與 UAT 的清單不同（UAT 會刻意清空第三方金鑰）
- `scripts/aigo_cron_health.py`：列出平台排程的狀態、最近結果、是否被暫停，並可斷言某支 action 有沒有排程
  （抓「切換後的新正式 app 沒補排程」：排程是後台資料，不跟 VFS 走）。UAT 預設**不建**排程（`uat-environment.md` §3 步驟 9），
  對 UAT 跑時預期是零條。平台的 success 只代表 action 有回應，工作本身的結果要看 app 自己的執行結果表

---

## 3. 詳細參考

- Custom vs Hosted 差異表 → `hosted-apps.md` §1；起手式模板 → `custom-app-dev-guide.md` §26.1
- 專案解構清單模板（元件落點、使用者表處理）→ `resources/project_deconstruction_template.md`
- 使用者搬遷（人一律成為租戶成員、角色對映、批次邀請）與授權架構表 → `member-admin.md` §1、§4、§7
- Schema 映射決策框架、語意重疊表的合併／分離、外鍵處理 → `custom-app-dev-guide.md` §22
- 遷移策略矩陣、批次匯入範例、ID 體系轉換、驗證 checklist → `custom-app-dev-guide.md` §23
- 資料抽取路徑、型別降級對照 → `custom-app-dev-guide.md` §23.6／§23.7
- 映射表模板 → `resources/migration_mapping_template.md`
- Hosted App 遷入時原 DB 的去向 → `hosted-apps.md` §7.1
