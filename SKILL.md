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

## Phase 0：Review 現有 Code（★ 強制步驟）

> **每次開始任何開發工作前，必須先執行此步驟。**

### 流程

1. 確認 `.aigo/config.json` 中 `email` 和 `app_id` 已設定
2. 請用戶臨時提供密碼（不儲存）
3. 呼叫 Login API 取得 JWT
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
   - **解析 db.json Data Reference 定義**（★ 重要）：
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
8. **確認已完全理解現有結構後，才可進入開發**

`scripts/aigo_review.py` 的 `review_app()` 一次做完 VFS 分析 + 步驟 6／7 的租戶級盤點，
`format_review_report(app_info, analysis, custom_tables, crons)` 輸出完整報告。

> ⚠️ `fetch_custom_tables()` 取不到時回**空清單**（權限不足／端點異常）。
> 空清單不等於「租戶沒有表、可以放心建新的」——要先確認是真的沒有。

## Phase 1：環境設定

### 配置檔 `.aigo/config.json`

```json
{
  "base_url": "https://ai-go.app",
  "email": "",
  "app_id": "",
  "app_slug": "",
  "app_name": "",
  "access_mode": "internal",
  "app_domain": ""
}
```

### 設定流程

1. 檢查專案目錄下 `.aigo/config.json` 是否存在
2. 不存在 → 建立骨架（可用 `scripts/aigo_auth.py` 的 `init_config()`）
3. 引導用戶：
   - 前往 AI GO 後台 (https://ai-go.app/dashboard)
   - 確認帳號具備 `builder.access` 權限
   - 進入 Builder → Custom Apps → 記下 App 的 UUID (`app_id`)
   - 填入 `.aigo/config.json` 的 `email` 和 `app_id`
4. 驗證連線：用戶臨時輸入密碼 → Login API → GET App → 自動回填 `slug`、`name`、`access_mode`
5. **密碼不儲存到任何檔案中**

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

2. **場景拆分與 App 邊界建議**
   - 若需求涵蓋 2 群以上不同功能與目的的情景，**必須建議用戶分別做成不同的 Custom App**
   - 例如：「客戶管理」和「財務報表」應為 2 個獨立 App
   - 每個 App 的 `app_domain` 標籤建議值

3. **資料架構設計**（★ 必須遵循雙軌分流策略，見 Phase 3 規則 18）
   - **盤點兩邊**（順序不可省）：
     - `GET /api/v1/data-center/tables` — 租戶既有自建表（Phase 0 已做，此處覆核）
     - `GET /api/v1/refs/available-tables` — 可引用的 SaaS 表清單
     - 對候選 SaaS 表呼叫 `GET /api/v1/refs/tables/{name}/columns` 查欄位結構
   - 列出所有需要的資料表，逐表判定走哪一軌（判定標準見規則 18）
   - **重用優先於新建**：既有自建表語意相同就重用，不要新建
   - 走 Data Reference 的表：說明如何用 `custom_data` JSONB 擴充、`app_domain` 標籤值
   - 走自建表且需要新建的：產出**建表規格表**
     `| 表顯示名 | 欄位顯示名 | 型別 | 必填 | 唯一 | relation 目標 |`
   - 若決定使用的 SaaS 表尚未在 db.json 中，引導用戶到 Builder 後台加入 Data Reference

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
      `isAdmin` / `getRoles`），資料是 Runtime 注入的登入者快照，
      **禁止自己打 `/api/v1/auth/me`**，也不要在 app 內另建角色表
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
    # ctx.http.call(service, endpoint) — 外部 API
    # ctx.secrets.get(key) — 金鑰
    # ctx.response.json(data) — 回應
    # ctx.csv.export(rows) — CSV 匯出
    data = ctx.params.get("key", "default")
    ctx.response.json({"result": data})
```

> `ctx.db` **不提供結構操作**——action 執行期無法建表或改欄，這是刻意的能力邊界。


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
