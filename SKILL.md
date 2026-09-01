---
name: aigo-builder
description: >
  Use when working on an AI GO Custom App (ai-go.app)：開發前端（React + TypeScript）
  或 Server-Side Action（Python）、部署與驗證、規劃資料架構（資料中心自建表 /
  Data Reference）、接 Webhook 或設定 App 排程、將現有系統（Supabase / Google Sheet
  / MySQL）遷入 AI GO。
---

# AI GO Custom App Builder

本 Skill 協助 AI Agent 開發 AI GO Custom App。支援 Antigravity / Claude Code / Cursor。

## 設計理念

AI GO Custom App 採用 **TypeScript（前端）+ Python（後端）** 的精選語言組合，
具備低出錯率、靜態型別安全、LLM 生成最佳化等特性，最適合 AI Coding 新手與非技術工作者
開發可靠的公司內部系統。

資料存取統一走 API，不直連資料庫——避免非技術 AI Coder 重複建立類似的表或欄位。
AI GO 預先定義了中小企業通用的資料庫結構（SaaS 表），同時保有**自建表**的擴充彈性。

> 詳見 `references/custom-app-dev-guide.md` §21 架構設計理念。
> **術語先讀 `CONTEXT.md`**——「自建表 / CustomObject / Data Reference / app_domain」
> 四個詞容易混用，混了就會寫錯 code。

## Phase -1：Skill 自我更新檢查（每次觸發時執行）

> 若已裝 SessionStart hook（見 README「自動更新檢查」），本階段會自動被跳過（節流），
> 不必重複執行。

```bash
python scripts/check_update.py     # macOS / Linux 用 python3
```

- **零相依、不走 uv**——標準函式庫實作，任何專案下都能直接跑。
- **無輸出 = 沒事**：已是最新版、離線、或 24 小時內已檢查過都會靜默結束，直接進 Phase 0。
- **有輸出 = 有新版**：把版本落差與變更摘要告知使用者，**詢問是否更新**。
  - 使用者同意 → 執行腳本印出的更新指令（git 安裝為 `git pull --ff-only`，
    skills CLI 安裝為 `npx skills update`），完成後**重新讀取 `SKILL.md` 與相關
    `references/`**，讓新版指令在本回合就生效。
  - 使用者拒絕或無回應 → 照舊繼續，不阻斷開發流程。
- **輸出含「破壞性變更」警語時**（`--json` 為 `"breaking": true`）：這類版本代表
  **不更新就會失敗，且失敗訊息通常不指向真正的原因**（例如 1.7.0 的租戶網址規則，
  症狀是與密碼錯完全同形的 401）。此時：
  - 不要把它輕描淡寫成一般可選更新——明確告訴使用者「不更新的話會遇到什麼」。
  - 使用者仍堅持不更新 → 照做，但在後續遇到相關錯誤時**優先回頭懷疑版本落差**，
    不要往其他方向深掘。
- **絕不自動覆寫**：使用者可能改過本地檔案；未取得同意前不要執行更新指令。

## Phase 0：Review 現有 Code（★ 強制步驟）

> **每次開始任何開發工作前，必須先執行此步驟。**

### 流程

1. 確認 `.aigo/config.json` 中 `email` 和 `app_id` 已設定
2. 呼叫 `aigo_auth.get_token()` 取得 JWT——**不要向用戶要密碼**。
   該函式依序嘗試「未過期的 Token 快取 → refresh_token 換發 → 用憑證檔
   （`<專案>/.aigo/.env` → `~/.aigo/.env`）的帳密登入」，正常情況下完全無感。
   - 只有在兩個憑證檔與環境變數都沒有憑證時才會拋 `RuntimeError`，
     此時把它的訊息原樣轉給用戶（內含設定指引），請對方**自己**填一次憑證檔。
   - **絕不代替用戶輸入或寫入密碼**，也不要把密碼放進指令列
     （會留在 shell 歷史紀錄）。用戶若在對話中貼出密碼，提醒對方改填 `~/.aigo/.env`
     並更換該密碼。
4. `GET /api/v1/builder/apps/{app_id}` 取得完整 App 資訊含 VFS
5. 分析 VFS 結構並輸出 Review 報告：
   - 列出所有檔案及大小
   - 標記 SDK 檔案 `[SDK]`（不可修改：api.ts, db.ts, action.ts）
   - 標記 Runtime 注入檔 `[INJ]`（不可修改：data.json, db.json, actions.json）
   - 解析 App.tsx 路由結構
   - 解析 _manifest.json 頁面清單
   - **Legacy 偵測**：`data.json` 有內容、或 code 用 `listRecords`／`submitRecord`／
     `ctx.db.query_object` → 標記為 legacy CustomObject（見 `CONTEXT.md`）。
     存量功能維持原樣即可運作，**但不要往上加東西**，新資料需求一律開自建表
   - **解析 actions/manifest.json 的 webhook 宣告**：列出所有 `"webhook": true` 的 action
     與 `receive_webhook`，這些是對外端點
   - **盤點 Data Reference**（★ 重要）：用 `GET /api/v1/refs/apps/{app_id}`，
     **不要讀 `src/db.json`**——它是執行期注入檔，VFS 裡實測恆為 `{}`，
     即使引用全部註冊成功也一樣（見 `references/platform-behaviors.md` §6）
     - 列出所有 SaaS 表名稱和欄位結構
     - 標記哪些表有 `custom_data`（JSONB）欄位
     - 列出每張表的權限（read/create/update/delete）
     - 統計現有資料筆數和 `app_domain` 分布
   - 檢查 App.css Shadow DOM 相容性
6. **盤點租戶既有自建表**（★ 強制，不可跳過）
   - `GET /api/v1/data-center/tables`（`aigo_data_center.py` 的 `list_tables()`）
   - 自建表是**租戶級**資源、**不在 VFS 裡**——同租戶的其他 app 建的表，這個 app 也看得到、用得到
   - 列出每張表的實體名、顯示名、欄位結構
   - 這一步的目的是**避免重複建表**：兩個 app 各建一張「客戶」表 = 資料分裂成兩份
7. **盤點既有排程**（若 app 已上線）
   - `GET /api/v1/app-crons`（`aigo_review.py` 的 `fetch_app_crons()`），
     確認有哪些排程綁在本 app 的 action 上
   - republish 或改動 action 名稱前必須知道這些，否則會把排程觸發到自動暫停
8. **盤點對外呼叫與 Egress**（若 code 內有 `ctx.http.call` 或 `import httpx` 等對外請求）
   - 從既有 action 原始碼撈出所有 `ctx.http.call` 的 egress slug 與殘留的對外網域，列成清單
   - 提醒用戶到 Builder（`/builder/{app_id}`）的「外部服務」tab 確認每個 slug 都已
     建立**同名外部服務**（base_url 域名白名單）**且授權給本 App**——
     舊 code 能跑不代表新加的服務也通
   - 舊 app 若靠平台代灌金鑰（不自帶 `Authorization`）→ **標記為必改**：
     閘道已不再注入憑證（ADR 0010），金鑰要改存 `ctx.secrets`、action 自組 header
   - 發現 raw `import httpx / requests / urllib.request` 直連外部的 action → **標記為必改**：
     runner 是 default-deny egress，raw 連線一律 timeout（見 Phase 3「呼叫外部 API」）
9. **確認已完全理解現有結構後，才可進入開發**

`scripts/aigo_review.py` 的 `review_app()` 一次做完 VFS 分析 + 步驟 6／7 的租戶級盤點，
`format_review_report(app_info, analysis, custom_tables, crons)` 輸出完整報告。

> ⚠️ `fetch_custom_tables()` 取不到時回**空清單**（權限不足／端點異常）。
> 空清單不等於「租戶沒有表、可以放心建新的」——要先確認是真的沒有。

## Phase 1：環境設定

### 租戶空間網址規則（★ 不可違反）

**所有登入與 API 一律走租戶子網域：`https://[tenant].ai-go.app/*`**

```
https://urfit.ai-go.app/api/v1/auth/login     ✅
https://demo.ai-go.app/api/v1/builder/apps/…  ✅
https://ai-go.app/api/v1/auth/login           ❌ 主站 apex，不是租戶入口
https://xxx.apps.ai-go.app/…                  ❌ Custom App 沙箱域，不是 API host
```

- `tenant` = 用戶平時登入時**網址列的第一段**。不確定就直接問用戶，或請對方貼登入後的網址。
- 平台是用 **Host header** 解租戶的（`{tenant}.ai-go.app/api/*` 同源代理到後端並保留 Host），
  所以 base_url 打哪個 host，就等於宣告「要登入哪個租戶」。
- apex `https://ai-go.app/login` 已被收斂成 **workspace finder**（找工作區的頁面），不是登入頁；
  apex 的 **API 登入實測已回 401**（2026-08-08，正確帳密）。
- ⚠️ **打錯租戶的症狀是 401「帳號或密碼錯誤」**——平台的反帳號列舉設計讓「這個 email 不在
  這個租戶」與「密碼打錯」回**完全相同**的 401（連是否跑滿一次 bcrypt 都一樣）。
  看到 401 時**先確認 base_url 的租戶對不對**，不要一路往密碼方向查。
- 腳本端已把規則寫死在 `aigo_auth.resolve_base_url()`：**沒有預設值**，
  填 apex 會直接被擋下並印出規則。不要在任何地方硬編 `https://ai-go.app`。

### 配置檔 `.aigo/config.json`

```json
{
  "base_url": "https://urfit.ai-go.app",
  "email": "",
  "app_id": "",
  "app_slug": "",
  "app_name": "",
  "access_mode": "internal",
  "app_domain": ""
}
```

#### base_url 的三層來源（`resolve_base_url()`，特定性越高越優先）

| # | 來源 | 定位 |
|---|------|------|
| 1 | shell 環境變數 `AIGO_BASE_URL` → `AIGO_TENANT` | 臨時覆寫、CI |
| 2 | `<專案>/.aigo/config.json` 的 `base_url` | 這個專案綁定的租戶 |
| 3 | `.env` 的 `AIGO_BASE_URL` → `AIGO_TENANT`（`~/.aigo/.env`） | 機器級預設 |

- **建議做法**：只服務單一租戶的機器，在 `~/.aigo/.env` 填 `AIGO_TENANT=urfit`
  即可全機器通用——寫前綴比每次抄整串網址不容易錯。
- **② 必須贏過 ③**：機器級 `.env` 是預設值不是唯一值。要在同一台機器開別的租戶的專案，
  就在該專案 `config.json` 填完整 `base_url` 覆寫。
- 三層都沒有 → 直接拋錯附設定指引，**不會 fallback 到 apex**。
- `aigo_auth.py status` 會印出**實際生效的網址與它來自哪一層**——查 401 的第一站。

### 設定流程

1. 檢查專案目錄下 `.aigo/config.json` 是否存在
2. 不存在 → 建立骨架（可用 `scripts/aigo_auth.py` 的 `init_config()`；`base_url` 會留空）
3. 引導用戶：
   - 前往 AI GO 後台 `https://[tenant].ai-go.app/dashboard`
   - **記下網址列的租戶前綴**，填入 `.aigo/config.json` 的 `base_url`
   - 確認帳號具備 `builder.access` 權限
   - 進入 Builder → Custom Apps → 記下 App 的 UUID (`app_id`)
   - 填入 `.aigo/config.json` 的 `email` 和 `app_id`
4. 建立憑證檔（**整台機器只需做一次**）：
   ```bash
   uv run python scripts/aigo_auth.py setup    # 產生 ~/.aigo/.env 範本（機器級）
   ```
   請用戶自己在 `~/.aigo/.env` 填入 `AIGO_EMAIL` / `AIGO_PASSWORD`，
   然後 `uv run python scripts/aigo_auth.py login` 驗證。
5. 隨時可用 `uv run python scripts/aigo_auth.py status` 確認**實際生效的租戶空間**與憑證狀態
6. 驗證連線：`get_token()` → GET App → 自動回填 `slug`、`name`、`access_mode`

### 憑證規則（★ 不可違反）

- 帳密預設放**機器級**的 `~/.aigo/.env`；`<專案>/.aigo/.env` 可覆寫個別鍵
  （例如該 app 的 `AIGO_APP_ID` / `AIGO_SLUG`），先找到的優先。兩者都在 `.gitignore` 涵蓋範圍內。
- **絕不把憑證寫進 Skill 安裝目錄**（`.claude/skills/aigo-builder/` 等）：
  `npx skills update` 會刪掉整個 skill 資料夾再重建，放在裡面的 `.env` / `token.json`
  會直接消失且無從還原。執行任何 `aigo_auth.py` 指令前，先確認 CWD 是**用戶的 app 專案**，
  不是 skill 目錄；或用 `AIGO_PROJECT_ROOT` 明確指定。
- **不得**寫進 `config.json`、原始碼、commit、log 或任何指令列參數。
- Token 快取在 `<專案>/.aigo/token.json`，過期自動換新；`aigo_auth.py logout` 可清除。
- Agent **不代為輸入或寫入密碼**——憑證檔一律由使用者本人填寫。

## Phase 1.25：多系統遷入盤點（條件觸發）

> **觸發條件**：用戶有 **2 個以上外部系統**（各自帶 Supabase / Google Sheet / MySQL
> 等 DB）要遷入 AI GO。僅遷入 1 個系統或純新建 App → 跳過，直接進 Phase 1.5。

> 觸發時 → 讀 `references/migration-workflow.md` §1。目的是在任何單一 App 開始
> Phase 1.5 之前建立**全局視圖**，避免各 App 各自為政導致資料架構混亂；
> 產出的「遷入全景表」會在後續各 App 的 Phase 1.5 持續參照。

## Phase 1.5：實作計畫（★ 強制步驟）

> **在任何開發工作開始前（包含從模板建立），必須先提出實作計畫並獲得用戶確認。**
> **禁止跳過此步驟直接進入 Phase 2 寫 code。**

### 計畫內容必須包含

1. **需求分析**
   - 用戶要實現的功能清單
   - 每個功能的目標使用場景
   - 預期的使用者流程

1.5. **產品線判斷（Custom App vs Hosted App）**
   - 平台有兩條**平行**產品線：本 skill 教的 **Custom App**（Builder VFS + Shadow DOM，
     在平台內跑）與 **Hosted App**（任意技術棧原始碼 → 容器 → `{slug}.deploy.ai-go.app`，
     UI 繁中叫「自訂 App」——注意 code 裡的 `CustomApp` 反而指 Builder 產物）
   - **判斷**：要遷入整套既有服務／需要自選後端框架、常駐進程、WebSocket、
     自訂網域 → 建議 Hosted App（→ `references/hosted-apps.md`，開發流程完全不同，
     不走本 skill 的 Phase 2–4）；要在平台內做業務介面、直接用 `ctx`/SDK 存取
     租戶資料 → Custom App，繼續本流程
   - 拿不準就把兩條線的差異表（`hosted-apps.md` §1）給用戶選

2. **場景拆分與 App 邊界建議**
   - 若需求涵蓋 2 群以上不同功能與目的的情景，**必須建議用戶分別做成不同的 Custom App**
   - 例如：「客戶管理」和「財務報表」應為 2 個獨立 App
   - 每個 App 的 `app_domain` 標籤建議值

3. **資料架構設計**（★ 必須遵循雙軌分流策略，見 Phase 3 規則 18）
   - **盤點兩邊**（順序不可省）：
     - `GET /api/v1/data-center/tables` — 租戶既有自建表（Phase 0 已做，此處覆核）
     - `GET /api/v1/refs/available-tables` — 可引用的 SaaS 表清單
     - 對候選 SaaS 表呼叫 `GET /api/v1/refs/tables/{name}/columns` 查欄位結構
       ⚠️ **查到的表沒有 `tenant_id` 是正常的**，不代表不安全，也不要自補過濾——見規則 25
   - 列出所有需要的資料表，逐表判定走哪一軌（判定標準見規則 18）
   - **重用優先於新建**：既有自建表語意相同就重用，不要新建
   - 走 Data Reference 的表：說明如何用 `custom_data` JSONB 擴充、`app_domain` 標籤值
   - 走自建表且需要新建的：產出**建表規格表**
     `| 表顯示名 | 欄位顯示名 | 型別 | 必填 | 唯一 | relation 目標 |`
   - 若決定使用的 SaaS 表尚未被引用（以 `GET /api/v1/refs/apps/{app_id}` 為準，不是 db.json），
     引導用戶到 Builder 後台加入 Data Reference

4. **頁面架構**
   - 路由結構（單頁 / 多頁）
   - 主要頁面和功能
   - Server Action 需求

4.5. **事件觸發需求**（若適用）
   - **Webhook**：列出要對外開放的端點
     `| hook 名稱（= action 名） | 事件來源 | 冪等 key 來源 | 驗簽方式 |`
   - **App 排程**：列出排程需求
     `| 排程名稱 | 觸發哪個 action | 頻率 | 時區 | 固定 params |`
     - **同時確認 tier 放不放得下**——最小間隔與條數上限依付費檔分層，
       超限是 400 不是靜默截斷。數值見 `references/event-triggers.md` §2.4
   - 兩者都要在計畫中明寫「此 action 的冪等策略」——見規則 20
   - 詳見 `references/event-triggers.md`

4.6. **對外 API 呼叫盤點**（★ 若有打第三方 API 就不可省）
   - 列出**所有要連出去的外部服務**
     `| egress slug | base_url（網域） | 用途 | 哪個 action 會用 |`
   - **在計畫階段就提醒用戶去建立外部服務**：Builder（`/builder/{app_id}`）的
     「外部服務」tab，以**同名 slug** 建立（base_url 域名白名單）並授權本 App
     （新建預設授權本 App）
     - 建立需本 App 擁有者或 `system.admin`；權限不足要請租戶管理員代設
   - 外部服務沒建立或沒授權，寫完的 code 一律連不出去——**等部署才發現等於整段白做**
   - 金鑰歸 app 自管：為每個 API 金鑰開 `ctx.secrets` 欄位，action 自組
     `Authorization` header——閘道只驗域名，不代管憑證（ADR 0010）
   - 詳見 `references/custom-app-dev-guide.md` §25

4.7. **平台 API 權限面盤點**（權限 gate 目前 audit，enforce 後前端呼叫會 403）
   - 列出**前端（瀏覽器 SDK）會直接呼叫的平台 API 群**——app 的宣告範圍是從
     `actions/*.py` 靜態推導的，**不含前端呼叫面**
   - 提醒用戶在 Builder（`/builder/{app_id}`）「API 權限」分頁把這些群開啟
     （寫入需 `builder.manage_access`）
   - 詳見 `references/platform-behaviors.md` §12

5. **app_domain 標籤設計**
   - 確定此 App 的 `app_domain` 值（snake_case，如 `patent_os`、`crm_leads`）
   - 說明標籤用途：所有寫入 SaaS 表的資料都會帶上此標籤

6. **現有系統遷移評估**（若適用）

   > 用戶有現存系統（Supabase / Google Sheet / MySQL / 既有程式碼）要遷入
   > → 先讀 `references/migration-workflow.md` §2，那裡有語言架構評估、
   > Schema 映射與資料遷移計畫的完整流程。純新建 App 跳過本項。

### 計畫閘門

- **必須等待用戶明確回覆「同意」或提供修改意見後，才可進入 Phase 2**
- 若用戶修改需求，需更新計畫後再次確認
- 計畫確認後將 `app_domain` 值記錄到 `.aigo/config.json`

## Phase 2：專案腳手架

基於 Phase 0 Review 結果決定策略：

- **VFS 為空**：生成全新專案結構
  - 詢問用戶：單頁 App 或多頁 App？
  - 單頁：直接渲染，不使用 Router
  - 多頁：HashRouter + Sidebar 導航
  - 可用 `scripts/aigo_scaffold.py` 的 `scaffold_new_project()`

- **VFS 有內容**：下載到本地進行增量開發
  - 將雲端 VFS 下載為本地檔案結構
  - 保留現有所有程式碼
  - 可用 `scripts/aigo_scaffold.py` 的 `download_vfs_to_local()`

## Phase 3：開發指引

### 核心規則（必須嚴格遵守）

1. **框架**：React 18 + TypeScript
2. **路由**：多頁用 `HashRouter`（禁用 `BrowserRouter`）；單頁可不用 Router
3. **CSS**：全域 `App.css`，不支援 CSS Modules / Tailwind
4. **CSS 變數**：必須用 `:host, :root { }` 雙選擇器
5. **HTML 重設**：必須用 `html, :host { }` 雙選擇器
6. **入口點**：必須是 `src/main.tsx`，且 `import "./App.css"`
7. **Layout**：最外層容器必須 `height: 100vh; overflow-y: auto`
8. **Runtime 模組**：react, react-dom, lucide-react, react-router-dom, react-hot-toast 由 Runtime 提供，不可自行安裝
9. **SDK 不可修改**：api.ts, db.ts, action.ts, data.json, db.json, actions.json
10. **Server-Side Actions**：Python，放在 `actions/` 目錄，定義 `execute(ctx)` 函式
11. **Shadow DOM 限制**：`confirm()` / `alert()` / `prompt()` 不可用 → 改用 React state 或 react-hot-toast
12. **前端 `db.ts` 的 db.update() Bug**：需用 `{"data": {...}}` 包裝 payload（直接 fetch，不走 SDK）
13. **前端 `db.ts` 的 db.insert() Bug**：同上，需用 `{"data": {...}}` 包裝
    - ⚠️ **只適用前端**。Server Action 的 `ctx.db.insert(table, data)` 收**扁平 dict**，
      包裝反而會被濾光並回 400。自建表的 `insert_row` / `update_row` 同樣收扁平 dict
14. **VFS 限制**：最多 200 檔案、單檔 ≤ 1MB、編譯超時 30 秒
15. **完整程式碼原則**：每次更新 VFS 檔案必須提供 100% 完整內容，禁止 `// ...省略` 佔位符
16. **不支援動態 import**：`import()` 語法不支援（lazy loading 除外，esbuild 支援 code splitting）
17. **不支援 Node.js 原生模組**：fs, path, crypto 等無法使用
18. **資料承載體：雙軌分流**（★ 強制）

    資料存在哪裡，依**資料的性質**決定，不是依「哪個比較方便」：

    | 資料性質 | 走哪一軌 | 理由 |
    |---------|---------|------|
    | 要與 ERP／SaaS 既有功能連動（看板、專案、發票、客戶…） | **Data Reference** + `custom_data` + `app_domain` | 與平台功能共用同一份資料 |
    | 租戶自有的新業務實體（外部系統遷入的表最常見） | **自建表** | 租戶級真實資料表，跨 app 共用 |
    | 臨時、單一 app 私有、不值得建表 | SaaS 表的 `custom_data` JSONB | 免建表成本 |

    - **自建表不是「最後手段」**——它是租戶級的真實 Postgres 表，200 張配額（付費檔），
      是遷入案例的主力承載體。
    - **建表前必須先 `GET /api/v1/data-center/tables` 盤點**（Phase 0 步驟 6）。
      語意相同的表已存在就重用，不要新建——自建表跨 app 共用，重複建表 = 資料分裂。
    - 建表需 `system.admin`。收到 **403 不重試、不繞路**：輸出可照抄的建表規格，
      引導用戶到資料中心 UI 自建，建完 `GET` 驗收再繼續。
      （`aigo_data_center.py` 會把 403 拋成 `PermissionDenied`；`needs == "system.admin"`
      才走建表降級，用 `format_create_spec()` 產出規格表。`needs == "builder.access"`
      是帳號沒有資料中心存取權，該請用戶開權限，不是叫他去建表）
    - `data.json` / `POST /api/v1/data/objects/batch` 是**已退場的 CustomObject**，
      不是自建表。存量 app 可留，新需求一律不用。
    - 詳見 `references/data-center.md`

19. **app_domain 標籤規範**（★ 強制，但**只限 Data Reference 那一軌**）
    - **適用範圍**：只有寫入 SaaS 表（Data Reference）的資料需要 `app_domain`。
      **自建表不需要也不應該帶 `app_domain`**——自建表沒有 `custom_data` 欄位，
      而且「跨 app 共用」正是它的設計目的，用標籤隔離是反模式。
    - 所有寫入 SaaS 表的資料，都必須在 `custom_data` JSONB 中包含 `app_domain` 欄位
    - `app_domain` 值記錄在 `.aigo/config.json` 中，在 Phase 1.5 決定
    - 格式：snake_case，如 `patent_os`、`crm_leads`、`inventory_mgr`
    - 寫入範例：
      ```typescript
      const newRecord = {
        name: "案件名稱",
        custom_data: {
          app_domain: "patent_os",  // ★ 必須標記
          case_no: "IP-001",
          status: "進行中"
        }
      };
      ```
    - 讀取時應過濾本 App 的資料：
      ```typescript
      const records = allRecords.filter(
        r => r.custom_data?.app_domain === "patent_os"
      );
      ```
20. **Webhook / 排程 action 必須冪等**（★ 強制）
    - 平台保證 **at-least-once**：事件至少執行一次，**可能重複執行**
      （dispatcher 硬死、invoke 超時、DLQ redrive、滾動更新窗口都會產生重複）
    - 有寫入副作用的 action（建單、扣款、發信）**沒有去重就是重複扣款等級的 bug**
    - 去重 key 優先用事件本身的業務 id，其次用 `ctx.params["delivery_id"]`
    - 詳見 `references/event-triggers.md` §0
21. **Webhook 宣告只在發布後生效**
    - `actions/manifest.json` 加 `"webhook": true` 後**必須 republish**，草稿不影響線上端點
    - `ctx.params["body"]` 是**原始字串**要自己 `json.loads`；驗簽必須用這個原字串，
      不可用重新序列化的結果
    - **`headers` 不可信**——webhook 是無認證公開入口，授權只能靠簽章驗證
    - 同一事件源**不可同時登記新舊兩條 URL**（會執行兩次）
22. **排程的四個硬限制**
    - **有執行時間上限**，超過必逾時 → 長任務要自己切批次。
      ⚠️ **webhook 與 cron 的上限不同**，別互相套用（`event-triggers.md` §1.6／§2.6）
    - **最小間隔與條數依付費檔分層**，超限回 400（`event-triggers.md` §2.4）
    - **重疊會被跳過**（`skipped` 是預期常態不是錯誤）
    - **自動暫停後不會自動恢復**——⚠️ republish 之後要提醒用戶檢查
      `/dashboard/settings/app-crons` 的排程狀態（`event-triggers.md` §2.8）
23. **角色／權限沿用平台，不要自建一套**（★ 強制）
    - Internal app 前端用 `src/user.ts`（`hasPermission` / `hasAnyPermission` /
      `isAdmin` / `getRoles`），資料是 Runtime 注入的登入者權限快照，
      **禁止自己打 `/api/v1/auth/me`**，也不要在 app 內另建角色表
    - ⚠️ **`src/user.ts` 要在 Builder 後台開過「開發」分頁才會進 VFS**，
      純走 API 建立的 app 直接 import 會編譯失敗——改直接讀 `__USER_PERMISSIONS__` 全域
      （`platform-behaviors.md` §10.2）。快照只給「能做什麼」，
      「是誰」要解 `__APP_TOKEN__` 的 JWT（§10.3）；`__CURRENT_USER__` 不存在
    - **前端解出的身分不可信**：寫入 `user_id` 這類身分欄位時，
      一律在 action 內用 `ctx.user_id` 覆蓋前端送來的值
    - **判斷授權用 permission 標籤（`模組.動作`）不要用角色名稱**——角色可被租戶改名；
      `system.admin` 自動通過所有檢查
    - **前端隱藏只是 UX**：機敏資料差異必須在 action 用 `ctx.user_permissions` 分流
    - External App / 匿名渲染下 roles 與 permissions **恆為空陣列**，
      UI 要有合理的降級路徑（不要因為空陣列就整頁空白）
    - 詳見 `references/custom-app-dev-guide.md` §6「User Context」與 §7
24. **SaaS 表寫入可能被簽核攔截**（★ 強制，只限 Data Reference 那一軌）
    - 租戶對該表設了簽核流程時：**insert 照樣寫入但回傳帶 `approval_status: "pending"`**；
      **update / remove 與 `ctx.erp.*` 完全不執行**，payload 暫存、Server Action 收到例外
    - `pending` **既不是成功也不是失敗**：UI 要顯示「已送簽核」，
      ⚠️ **不可重試**（重試 insert = 重複建單 + 重複開簽核單）
    - **沒有旁路**——`db.ts` / `ctx.db` / `ctx.erp` 同一套守衛，不要換路徑硬寫
    - 要免寫後端就讓核准自動改狀態欄位；要做簽核 UI 用 `src/approval.ts` / `ctx.approval`
    - 詳見 `references/custom-app-dev-guide.md` §24
25. **表沒有 `tenant_id` 不等於沒保護**（★ 強制）
    - 查欄位時看到某張 SaaS 表**沒有** `tenant_id`（如 `msg_messages`、`announcement_reads`、
      `ir_sequences`、`account_accounts`）**不是 bug**，租戶隔離也沒失效——
      邊界另有欄位別名（`company_id`）、父表歸屬（`EXISTS` 繞父表）、全域表（刻意不過濾）三種形態
    - **不要自己補 `WHERE tenant_id = ...`**：邊界由 DB Proxy 注入，
      手動補在沒有該欄位的表上只會直接失敗
    - **不要因為缺欄位就改用別的表或自己加一層過濾**——判定依據是後端的顯式登記表，不是欄位偵測
    - 詳見 `references/custom-app-dev-guide.md` §20.3
26. **`offset` 分頁一律帶唯一鍵排序**（★ 強制，**不加會靜默漏資料**）
    - DB Proxy 單次最多回 **500 筆**、回傳是裸陣列（無 `total` 信封），要取完整資料
      必須自己 `offset` 迴圈，以「回傳數 < 500」作結束條件
    - 伺服器預設 `ORDER BY created_at DESC NULLS LAST`，時間戳重複時排序不穩定，
      分頁會**跨頁重複又漏抓**——實測某表 1866 筆只取回 1860 筆，
      **不拋例外、不報警告**，只有統計數字會悄悄少一截
    - 每次分頁查詢都要帶 `order_by: [{ column: "id", direction: "asc" }]`
    - 詳見 `references/platform-behaviors.md` §1
27. **`ctx.erp.validate_picking` 的冪等要看明細，不能看單據 state**（★ 強制）
    - 實測成功扣帳後 `stock_pickings.state` **不會**轉成 `done`（只寫 `date_done`），
      真正反映完成的是 `stock_moves.state`
    - 拿 `picking["state"] == "done"` 當冪等守門，條件永遠是 False、守門永遠不生效；
      要改判 `all(m["state"] in {"done","cancel"} for m in moves)`
    - 詳見 `references/platform-behaviors.md` §4.3
28. **原生 TIMESTAMP／DATE 是 offset-naive 的 UTC，解析前必須補 `Z`**（★ 強制，**不補會靜默算錯**）
    - 平台混用兩種時間欄位：`created_at`／`updated_at` 是 timestamptz（帶 `+00:00`，可直接用）；
      `check_in`／`date_from`／`date_done`／`work_date` 是原生 TIMESTAMP／DATE，
      回傳長這樣 `2026-08-01T04:37:03`——**存的是 UTC，但 JS 會當成本地時間**
    - **不拋例外、不報警告**：實測相隔 6 分鐘的上下班打卡被算成 **8.1 小時**工時，
      直接寫進 `hr_attendances.worked_hours`（影響薪資）
    - 解析前補 `Z`；顯示不可切字串（`slice(0,16)` 顯示的是 UTC）；
      推導日期不可用 `toISOString().slice(0,10)`（那是 UTC 日期，UTC+8 凌晨會退回前一天）
    - DATE-only 欄位建議直接以**字串比對／顯示**，不要轉時間戳
    - 可直接沿用的 `toTime()` 與適用範圍見 `references/platform-behaviors.md` §8
29. **所有 API 一律走租戶空間 `https://[tenant].ai-go.app/*`**（★ 強制，**打錯的錯誤訊息會誤導你**）
    - 平台以 **Host header** 解租戶：base_url 打哪個 host = 宣告要登入哪個租戶。
      主站 apex `https://ai-go.app` 推不出租戶，實測登入已回 401
    - **不可硬編任何 base_url**——一律經 `aigo_auth.resolve_base_url()`
      （shell 環境變數 → 專案 `config.json` → `.env` 的 `AIGO_TENANT`／`AIGO_BASE_URL`）
    - ⚠️ **打錯租戶與密碼打錯回完全相同的 401「帳號或密碼錯誤」**（平台反帳號列舉，
      連是否跑滿一次 bcrypt 都一樣）。看到 401 **先跑 `aigo_auth.py status` 確認租戶空間**，
      不要往密碼、Token、權限方向深掘
    - 租戶前綴 = 用戶登入時網址列的第一段；不確定就直接問用戶，別猜
    - 細節見 `references/platform-behaviors.md` §6.1
30. **啟動先渲染 skeleton，不要讓長 API 擋住首次渲染**（★ 強制）
    - 平台會監看掛載後 **8 秒**：Shadow root 全空就自動回報 runtime error，
      並對使用者顯示「App 已載入但沒有顯示任何內容」banner
    - 「先跑長 API、成功後才第一次渲染」的寫法會被誤報——
      一律先渲染 loading／skeleton 佔位，資料到了再替換
    - 詳見 `references/platform-behaviors.md` §11

### Server-Side Action 撰寫

```python
def execute(ctx):
    # ctx.params — 前端傳入的參數（webhook / cron 事件也走這裡）
    # ── Data Reference（SaaS 表）
    # ctx.db.query(table, limit=N) / ctx.db.insert(table, data)
    # ctx.db.update(table, row_id, data) / ctx.db.remove(table, row_id)
    # ── 自建表
    # ctx.db.list_tables() / ctx.db.query_table(table, options)
    # ctx.db.insert_row(table, data) / ctx.db.update_row(table, row_id, data)
    # ctx.db.delete_row(table, row_id)
    # ── 其他
    # ctx.http.call(slug, path, method=..., body=..., headers=...) — 對外 HTTP（經 egress 閘道）
    # ctx.secrets.get(key) — 金鑰（外部 API key、webhook 驗簽等，由 app 自管）
    # ctx.response.json(data) — 回應
    # ctx.csv.export(rows) — CSV 匯出
    data = ctx.params.get("key", "default")
    ctx.response.json({"result": data})
```

> `ctx.db` **不提供結構操作**——action 執行期無法建表或改欄，這是刻意的能力邊界。

**呼叫外部 API：一律走 `ctx.http.call(<egress-slug>, <path>)` 閘道**，
**不要**直接 `import httpx / requests / urllib.request`——runner pod 是
default-deny egress，raw 連線出不去（實測 20 秒 timeout），且這些套件在沙箱 denylist 上。

```python
def execute(ctx):
    # slug 對應租戶註冊的「外部服務」（EgressService）——純域名白名單，只鎖 host。
    # 金鑰由 app 自己帶：存 ctx.secrets，action 自組 Authorization header。
    resp = ctx.http.call(
        "example-api",
        "/v1/send",
        method="POST",
        headers={"Authorization": f"Bearer {ctx.secrets.get('EXAMPLE_API_KEY')}"},
        body={"text": ctx.params.get("text")},
    )
    if int(resp.get("status") or 500) >= 400:
        ctx.response.json({"error": "外部服務暫時無法使用", "status": resp.get("status")})
        return
    ctx.response.json(resp.get("data") or {})
```

> ⚠️ **slug 必須先建立同名「外部服務」（base_url 域名白名單）並授權給本 App，
> 否則連不出去**——見 `references/custom-app-dev-guide.md` §25。這是設定問題，
> 不是程式問題，改 code 改不掉。
> 閘道只做**域名驗證**，**不代管、不注入、也不剝除憑證**（ADR 0010）：
> `Authorization` 等呼叫端 headers 原樣轉送（僅擋 hop-by-hop）。
> API 金鑰請開 `ctx.secrets` 欄位、由 action 自組 header。


### 前端呼叫 Action

```typescript
import { runAction, downloadFile } from "../action";
const { data, file } = await runAction("my_action", { key: "value" });
if (file) downloadFile(file);
```

## Phase 4：部署 + 自動驗證（★ 每次 code 變更後必須執行）

> **原則：每次 code 變更後，都必須完成「同步 → 編譯 → 驗證」循環。**
> 只有通過驗證閘門，才可進入發布或繼續下一輪開發。
> 極小變更（如僅修改文字、CSS 微調）可跳過 Custom Data 和 Action 測試，但編譯驗證不可跳過。

### 4.1 標準部署流程

1. **同步 VFS**：讀取本地檔案 → PATCH `/api/v1/builder/apps/{id}/source/files`
   - 腳本：`scripts/aigo_sync.py` 的 `sync_to_cloud()`
   - ★ 內建二次驗證：PATCH 後自動 GET 確認 vfs_version 遞增 + 檔案確實寫入
2. **編譯**：POST `/api/v1/compile/compile/{slug}?dev=true`
   - 腳本：`scripts/aigo_compile.py` 的 `compile_app()`
3. **編譯失敗**：解析錯誤 → 嘗試自動修復 → 重新同步 → 重新編譯（最多 5 次）
4. **編譯成功 → 進入驗證閘門**（Phase 4.2）

### 4.2 驗證閘門（Verification Gate）

每次編譯成功後，根據**變更範圍**自動決定需要執行的驗證項目：

#### 變更範圍判斷規則

| 變更類型 | 影響範圍 | 需執行的驗證 |
|---------|---------|------------|
| **CSS 微調**（僅 App.css 變動） | 極小 | ✅ Compile 產物 |
| **文案/UI 修改**（僅 TSX 變動，無新 import） | 小 | ✅ Compile 產物 |
| **元件新增/重構**（新增 TSX、修改路由） | 中 | ✅ Compile 產物 + ✅ Publish 一致性 |
| **Custom Data 相關**（修改了使用 api.ts/db.ts 的程式碼） | 中 | ✅ Compile 產物 + ✅ Custom Data CRUD |
| **Server Action 變更**（actions/*.py 修改） | 中 | ✅ Compile 產物 + ✅ Server Action 呼叫 |
| **多個範圍同時變動** | 大 | ✅ 全部 4 項驗證 |
| **首次部署或架構變更** | 大 | ✅ 全部 4 項驗證 |

> 要**實際執行**這四項驗證 → `references/verification-details.md` §1
> 有每一項的完整檢查條目與函式簽名。

### 4.3 驗證後決策

| 驗證結果 | 下一步 |
|---------|--------|
| ✅ 全部通過 | 可進入發布（4.4）或繼續開發 |
| ❌ Compile 失敗 | 回到 Phase 3 修復程式碼 |
| ❌ CRUD/Action 失敗 | 檢查 API 使用方式、表結構、Action 邏輯 |
| ❌ Publish 一致性失敗 | 重新 sync → compile → publish |

> 任何一項失敗 → 先查 `references/troubleshooting.md` 對症狀，再動手改。
> ⚠️ CRUD 驗證打 SaaS 表時，回傳 `approval_status: "pending"` 或「需要簽核審批」例外
> **不算驗證失敗**——那是租戶簽核流程攔截（核心規則 24），不要當成 bug 去改程式。

### 4.4 發布

只有通過驗證閘門後才可發布：

1. POST `/api/v1/builder/apps/{id}/publish`
   - 腳本：`scripts/aigo_publish.py` 的 `publish_app()`
   - ★ 內建二次驗證：POST 後自動 GET 確認 status == "published"
2. 發布後執行 Publish 一致性驗證

### 樂觀鎖

- GET App 時記錄 `vfs_version`
- PATCH 時帶入 `expected_version`
- 409 → 重新 GET → 合併 → 重試

### 自動修復策略

| 偵測問題 | 自動修復 |
|---------|--------|
| `:root {` 無 `:host` | → `:host, :root {` |
| `html {` 無 `:host` | → `html, :host {` |
| BrowserRouter | → HashRouter |
| 缺少 `import "./App.css"` | → 在 main.tsx 頂部加入 |

可使用 `scripts/aigo_sync.py`、`aigo_compile.py`、`aigo_publish.py`。

## Phase 5：完整 E2E 驗證（里程碑驗證）

> Phase 4 的驗證閘門每次迭代自動執行；Phase 5 是**開發里程碑完成**
> （功能全部完成、準備交付）時的完整驗證。

> 要執行時 → `references/verification-details.md` §2 有完整清單與呼叫範例。

## 驗證流程快速參照

```
每次 code 變更：
  sync → compile → ✅ Compile 產物驗證
                   └─ (若涉及 Data) → ✅ Custom Data CRUD
                   └─ (若涉及 Action) → ✅ Server Action 呼叫
                   └─ (若涉及路由/元件) → publish → ✅ Publish 一致性

里程碑交付：
  上述全部 + External Auth + 匿名存取（如適用）
```

## 錯誤處理

> 任何一步失敗、或收到非預期狀態碼 → 先查 `references/troubleshooting.md`，
> **不要自行推測修法**。多數症狀有明確成因，猜測通常會改錯地方。

常見狀態碼的語義分野：**403** 權限（分 `system.admin` / `builder.access` 兩種，
降級動作不同）｜**409** 配額或衝突｜**422** 輸入不合法｜**400** 業務規則拒絕。

### Action 對外呼叫失敗（★ 別急著改 code）

**先完整讀出回傳的 status 與 error message**，再對症：

- **timeout／連不出去**：① action 是不是 raw `import httpx / requests` 直連？
  runner 是 default-deny egress，raw 連線必 timeout——改寫成 `ctx.http.call`
  ② 已是 `ctx.http.call` → slug 沒有同名「外部服務」，或服務未授權給本 App
- **401**：外部 API 拒絕請求帶的憑證——閘道**不注入也不剝除** `Authorization`
  （域名驗證 only，ADR 0010）。檢查 action 是否自組了正確的
  `Authorization` header、`ctx.secrets` 的金鑰對不對——這是 app 側問題，
  不用去動外部服務設定

訊息指向 Egress／權限時：

1. **立刻停止修改程式碼**——這是設定問題，改幾次結果都一樣
2. 把原始 error message 轉給用戶，引導到 Builder（`/builder/{app_id}`）的
   「外部服務」tab，以同名 slug 建立外部服務（base_url 域名白名單）並授權本 App
3. 建立需 `builder.access` 且為本 App 擁有者（或 `system.admin`）；
   權限不足請租戶管理員代設
4. 外部服務確認生效後才重試

詳見 `references/custom-app-dev-guide.md` §25.3。

## 問題回報（平台問題 → 開發團隊）

遇到「平台自身」的問題——實測與文件不符、troubleshooting 查無此症或照表仍卡死、
被平台缺陷擋住流程——**直接回報給開發團隊**，不要繞道硬改：

```bash
uv run python scripts/report_issue.py submit "一句話標題" \
  --expected "預期行為" --actual "實際結果（含錯誤原文）" --steps "重現步驟"
```

- 憑證重用 `~/.aigo/.env`，零設定；在 AI IDE 內直接執行，不開任何 UI、
  不經平台（回報系統獨立部署，平台掛掉時照樣可報）
- ★ 內容寫**行為**不寫解法：預期 vs 實際＋重現步驟；
  **不要**替用戶提出技術建議或實作方式——完整規範見 `references/issue-reporting.md`
- 追蹤進度與官方回覆：`report_issue.py list`／`show <ticket_id>`

## 參考文件

| 檔案 | 內容 |
|------|------|
| `CONTEXT.md` | ★ 術語表——自建表／CustomObject／Data Reference／app_domain |
| `references/custom-app-dev-guide.md` | 核心 API 規格與架構理念 |
| `references/data-center.md` | 自建表完整規格（型別、配額、權限、SDK） |
| `references/event-triggers.md` | Webhook 與 App 排程（冪等要求、宣告、限制） |
| `references/migration-workflow.md` | **有現存系統要遷入時**：盤點、Schema 映射、資料遷移 |
| `references/verification-details.md` | **要執行驗證時**：四項驗證的完整定義、Phase 5 里程碑 |
| `references/troubleshooting.md` | **出錯時**：錯誤速查表 |
| `references/issue-reporting.md` | **回報平台問題時**：BDD 撰寫規範、指令、進度追蹤 |
| `references/platform-behaviors.md` | **實測行為補遺**：DB Proxy 分頁與筆數上限、`custom_data` 不可伺服器端過濾、TIMESTAMP 格式、seed 表唯讀、`ctx.erp` 白名單、空渲染偵測、API 權限閘 |
| `references/hosted-apps.md` | **Hosted App（「自訂 App」）產品線**：與 Custom App 的邊界、部署 API、env 規則、錯誤碼對照——Phase 1.5 判斷走這條線時讀 |
