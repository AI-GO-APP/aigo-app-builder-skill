# 現有系統遷入 AI GO

> 只有「用戶有現存系統要遷入」時才需要這份。純新建 App 完全用不到。
>
> 這是 Phase 1.25 與 Phase 1.5 的**遷移分支**，接在 SKILL.md 的主流程上：
> §1 在任何單一 App 開始 Phase 1.5 之前做；§2 在該 App 的 Phase 1.5 計畫中做。
> **不論單系統或多系統，每個要遷入的系統都必須先做 §2.0 的 stack 盤點、
> 再過 §2.1 的產品線判斷**——判斷結果不可逆（見 §2.1 的警示），
> 而判斷品質取決於盤點：沒盤過 stack 就分流＝憑感覺押不可逆的注。

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
   - 格式：`| 外部系統 | stack 形狀（§2.0） | 產品線（Custom / Hosted） | 模式（internal / external / visibility） | 對應 AI GO App | app_domain | 遷入順序 | 語意重疊的表 |`
   - 此表在後續各 App 的 Phase 1.5 中持續參照

---

## 2. 單一系統的遷移評估

> 依序執行 §2.0 → §2.5。§2.1 判走 Hosted App 的系統只需再做 §2.2（解構盤點）
> 與資料側的 §2.4／§2.5（資料落點見 `hosted-apps.md` §7.1），
> 開發與部署改走 `references/hosted-apps.md`，不進本 skill 的 Phase 2–4。

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

產出「**stack 形狀結論**」三選一，帶進 §2.1 問題二：

1. **純前端**——無自有後端行程（直連 BaaS 的 SPA 算這類：它的「後端」是資料層，走 §2.4 映射）
2. **有後端、可改寫**——無狀態 API，業務邏輯可搬進 `execute(ctx)` 形狀
3. **有後端、整搬**——常駐進程、WebSocket、自選框架深度綁定，或形狀上可改寫但工作量／風險不可行

另判**前端面向**二選一（帶進 §2.1 問題二的純前端行）：
**應用介面**（登入後使用的工具）／**公開 web 資產**（官網、電商 storefront）。

### 2.1 產品線與模式判斷（★ 承接 §2.0，結果不可逆）

用兩個問題把系統定位到四象限。**先問使用者是誰，再看 stack 形狀**——
「使用者是誰」決定的模式選錯了要砍掉重建，技術形狀選錯頂多多花工。

**問題一：原系統的登入使用者是誰？**

| 答案 | 走向 |
|------|------|
| 公司／租戶內部成員（員工工具、內部後台） | **internal** 線 |
| 外部客戶、會員、公眾（對外網站、客戶入口） | **external** 線 |
| 兩者都有（員工後台 + 客戶前台） | **拆成兩個 App**，各走各的線——一個 App 只能有一種模式 |

**問題二：§2.0 的 stack 形狀結論＋前端面向是哪一種？**

| stack 形狀 × 面向 | 預設走向 |
|------|------|
| 純前端 × 應用介面 | **1..n 個 Custom App**（前端重寫進 Builder；直連 BaaS 的資料層走 §2.4 映射進平台） |
| 純前端 × 公開 web 資產（官網、電商 storefront） | **Hosted App**（zbpack 任意棧含靜態站、`hosted-apps.md` §9 綁自訂網域）——Custom App 的 `/runtime` 網址＋HashRouter 做不了 SEO 與自有網域，`/pub` 只適合少數公開頁，不承載整個公開站 |
| 有後端、可改寫 | **Custom App**（後端邏輯改寫成 Server Action）；用戶明確不願重構 → 改判 Hosted App |
| 有後端、整搬 | **1..n 個 Hosted App**（整套原始碼進容器） |

- stack 形狀給的是**預設值**，最終仍要向用戶確認——特別是「可改寫」與
  「整搬」的邊界：改寫工作量（§2.3 可移植性核對）攤開後用戶不買單，就改判整搬。
- **自有網域／SEO 需求凌駕形狀判斷**：不論後端可不可改寫，需要自有網域的
  公開站一律偏 Hosted——公開 web 資產的判定看產品面向，不看技術棧。
- **混合情景（官網＋登入後系統）→ 拆開各走各的**：官網 → Hosted App、
  系統 → Custom App；兩邊共用的資料落平台側（自建表；Hosted 走 Open Proxy，
  `hosted-apps.md` §7.1），不因共用而硬併成一個 app。
- ⚠️ **資料層不參與這個判斷**：不論分到哪條線，DB 與 storage 都**不允許**
  自立 Hosted App 承載（SKILL.md 規則 32）——table schema 一律落平台
  預設表／自建表、檔案一律 Storage API；Hosted App 的資料層一律改寫
  Open Proxy（`hosted-apps.md` §7.1）。「把 Postgres／包了 REST 的 DB
  搬成一個 Hosted App 給其他 App 打」不是選項。

**四象限落點：**

| | 內部成員用 | 外部使用者用 |
|---|---|---|
| **Custom App** | `starter-internal` 模板（access_mode=`internal`，沿用平台角色權限） | `starter-external` 模板（access_mode=`external`，custom-app-auth 自助註冊；可開匿名 `/pub`） |
| **Hosted App** | `visibility=internal`（平台 proxy 代處理登入，僅租戶成員） | `visibility=public`（預設；app 自理或不設認證） |

**⚠️ 不可逆與硬前提（判斷前必讀）：**

- **Custom App 的 `access_mode` 由模板決定、建立後不可改**——選錯要砍掉重建
  （`custom-app-dev-guide.md` §26.1）
- **`internal` 不能開匿名存取**（回 400）——「內部工具但想給訪客看一頁」
  這種需求要在此刻攤開講清楚（`CONTEXT.md`）
- 拿不準 Custom vs Hosted → 把 `hosted-apps.md` §1 的差異表給用戶選；
  拿不準 internal vs external → 直接問「這系統現在是誰在登入」

判斷結果記入 §1 的全景表（多系統）或本 App 的 Phase 1.5 計畫（單系統）。

### 2.2 專案解構盤點（前端 + 後端 + DB 完整專案時）

要遷入的不只是「一個 DB」而是**整個專案**時，資料表映射（§2.4）只涵蓋一半——
另一半是程式與服務元件的落點。逐項盤點原專案的：

- 頁面／路由、後端 API endpoints、背景排程、對外 webhook 接收
- 檔案儲存、第三方 API 呼叫、環境變數與金鑰
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
  | 規模 | VFS 上限 200 檔、單檔 ≤1MB、編譯 30 秒 |
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
- **使用者／認證表先剔除**——它們走 §2.2 解構清單的認證映射，不進本流程
- 逐表對照（先跑 Phase 1.5 第 3 點的雙邊盤點）：
  - 與平台既有功能連動的資料 → 預設表原生欄位；無原生對應的欄位 →
    租戶級正式欄位用**延伸欄位**（EAV，`data-center.md` §10）、
    app 私有標記與鬆散擴充用 `custom_data` JSONB
  - 租戶自有的新業務實體（**遷入案例的主力**）→ 自建表
  - 租戶已有語意相同的自建表 → 直接重用；**欄位不足 → 加實體欄位**
    （`data-center.md` §7 加欄），不要因缺欄就新建表或把結構化欄位塞進 json
- 欄位型別對不上時，查降級對照表（`custom-app-dev-guide.md` §23.7）
- 處理外部表之間的外鍵 / 關聯（AI GO 需用 ID 欄位 + 程式邏輯維護參照完整性）
- 產出「外部 Schema ↔ AI GO 映射表」（模板見 `resources/migration_mapping_template.md`）
- 若有 §1 的全景表，映射須與全景表的合併 / 分離決策一致
- 詳見 `references/custom-app-dev-guide.md` §22

### 2.5 資料遷移計畫（★ 若需遷入歷史資料）

> **閘門：§2.4 的映射表未產出、或未經用戶確認前，不可執行任何匯入。**
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

---

## 3. 詳細參考

- Custom vs Hosted 差異表 → `hosted-apps.md` §1；起手式模板（internal/external）→ `custom-app-dev-guide.md` §26.1
- 專案解構清單模板（元件落點、使用者表處理）→ `resources/project_deconstruction_template.md`
- Schema 映射決策框架、語意重疊表的合併／分離、外鍵處理 → `custom-app-dev-guide.md` §22
- 遷移策略矩陣、批次匯入範例、ID 體系轉換、驗證 checklist → `custom-app-dev-guide.md` §23
- 資料抽取路徑、型別降級對照 → `custom-app-dev-guide.md` §23.6／§23.7
- 映射表模板 → `resources/migration_mapping_template.md`
- Hosted App 遷入時原 DB 的去向 → `hosted-apps.md` §7.1
