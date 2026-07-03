# AI GO Custom App 開發者指南（精簡版）

> 完整文件：https://www.ai-go.app/zh-TW/docs/custom-app-dev

## 1. 什麼是 Custom App

- VFS（Virtual File System）：以 JSON `{"路徑": "內容"}` 儲存原始碼
- esbuild 編譯器：React TSX → JS bundle
- Runtime 沙箱：在 Shadow DOM 隔離環境中執行
- 三種模式：Internal（組織內部）/ External（對外客戶）/ Public（匿名檢視）
- 語言選擇：TypeScript（前端）+ Python（後端），為 AI Coding 最佳化的精選組合（詳見 §21）
- 資料架構：統一走 API 存取，不直連資料庫——避免結構混亂（詳見 §21）

## 2. 認證與連線

```http
POST https://ai-go.app/api/v1/auth/login
{"email": "...", "password": "..."}
→ {"access_token": "...", "refresh_token": "...", "expires_in": 3600}
```

所有 Builder API 需帶 `Authorization: Bearer {access_token}`。Token 有效期 1 小時。

## 3. VFS 標準檔案樹

```
package.json
src/main.tsx          ★ 入口點
src/App.tsx           路由 + Layout
src/App.css           全域樣式
src/api.ts            [SDK] Custom Data CRUD
src/db.ts             [SDK] DB Proxy
src/action.ts         [SDK] Server Action
src/data.json         [INJ] Custom Table 定義
src/db.json           [INJ] Data Reference
src/actions.json      [INJ] Action 清單
src/pages/            頁面元件
src/components/       共用元件
actions/manifest.json Action 註冊
actions/*.py          Action 實作
```

## 4. 程式碼注入 API

| 操作 | 方法 | 端點 |
|------|------|------|
| 取得 App | GET | `/api/v1/builder/apps/{slug_or_id}` |
| 局部更新 | PATCH | `/api/v1/builder/apps/{id}/source/files` |
| 刪除檔案 | DELETE | `/api/v1/builder/apps/{id}/source/files` |
| 全量覆寫 | PUT | `/api/v1/builder/apps/{id}/source` |

樂觀鎖：帶入 `expected_version`，版本不匹配回傳 409。

## 5. 編譯 API

```http
POST /api/v1/compile/compile/{slug}?dev=true
→ {"success": true, "html": "...", "bundle_js": "...", "css": "..."}
→ {"success": false, "error": "..."}
```

限制：200 檔案、1MB 單檔、30 秒超時。
External 模組（不需安裝）：react, react-dom, lucide-react, react-router-dom, react-hot-toast

## 6. 內建 SDK

### Custom Data (api.ts)

```typescript
import { listRecords, submitRecord, updateRecord, deleteRecord } from "../api";
```

### DB Proxy (db.ts)

```typescript
import { query, queryAdvanced, insert, update, remove } from "../db";
```

⚠️ `update()` 和 `insert()` 需用 `{"data": {...}}` 包裝（SDK bug）。

### Server Action (action.ts)

```typescript
import { runAction, downloadFile } from "../action";
const { data, file } = await runAction("name", params);
```

## 7. Server-Side Actions

```python
def execute(ctx):
    ctx.params          # 前端參數
    ctx.db.query(t)     # 查詢
    ctx.db.insert(t, d) # 新增
    ctx.http.call(s, e) # 外部 API
    ctx.secrets.get(k)  # 金鑰
    ctx.response.json(d)# 回應
    ctx.csv.export(r)   # CSV
```


## 8. 發布

```http
POST /api/v1/builder/apps/{app_id}/publish
{"published_assets": {}}
```

## 9. Shadow DOM CSS 規範

```css
/* ✅ 正確 */
:host, :root { --primary: #2563eb; }
html, :host { line-height: 1.5; }

/* ❌ 錯誤 */
:root { --primary: #2563eb; }
```

JS API 限制：confirm()→false, alert()→不顯示, prompt()→null。
容器必須：`height: 100vh; overflow-y: auto`。

## 10. VFS 注入規範

- 每次注入必須提供完整的檔案內容（raw string）
- 禁止字串拼接或模板佔位符
- 禁止 `// ... 省略` 之類的佔位

## 11. Custom Table API

```http
POST /api/v1/data/objects/batch
{"app_id": "...", "name": "...", "api_slug": "...", "fields": [...]}
```

欄位類型：text, number, date, relation。
api_slug：`^[a-z0-9]([a-z0-9_]*[a-z0-9])?$`。
限制：20 表/App、50 欄/表。

## 12. Storage API

- POST `/api/v1/ext/storage/upload`（multipart/form-data）
- GET `/api/v1/ext/storage/url?path={path}`
- GET `/api/v1/ext/storage/list?folder={folder}`
- DELETE `/api/v1/ext/storage/file?path={path}`

需 Custom App Token (`window.__APP_TOKEN__`)。單檔 100MB 上限。

## 13. Runtime 全域變數

| 變數 | 說明 |
|------|------|
| `window.__APP_TOKEN__` | JWT Token |
| `window.__APP_SLUG__` | App slug |
| `window.__APP_ID__` | App UUID |
| `window.__API_BASE__` | API 基底 URL |
| `window.__IS_AUTHENTICATED__` | 是否已認證 |
| `window.__IS_EXTERNAL__` | 是否為 External 模式 |

## 14. External Auth API

端點前綴：`/api/v1/custom-app-auth/{slug}/`

- POST `.../register` → 註冊
- POST `.../login` → 登入
- GET `.../me` → 當前用戶
- POST `.../refresh` → 刷新 Token
- POST `.../logout` → 登出

Auth SDK：`window.__auth__.login()`, `.register()`, `.logout()`, `.getToken()`

## 15. Public 匿名 API

啟用條件：`allow_anonymous_access=true` + `is_public_readable=true`

- GET `/api/v1/pub/data/{slug}/objects`
- GET `/api/v1/pub/data/{slug}/objects/{table}/records`
- POST `/api/v1/pub/proxy/{slug}/{table}/query`

Rate Limit：120 次/分鐘 per IP。

## 16. 套件管理

Runtime 內建：react ^18.x, react-dom ^18.x, react-router-dom ^6.x, lucide-react latest, react-hot-toast latest
不支援：CSS Modules, Tailwind, styled-components, @mui/material, 動態 import, Node.js 原生模組

## 17. 常見問題速查

| 問題 | 解法 |
|------|------|
| 白屏 | 檢查 main.tsx 掛載和 App.css import |
| 路由不動 | HashRouter，非 BrowserRouter |
| 無法捲動 | Layout height:100vh + overflow-y:auto |
| CSS 變數無效 | :host, :root 雙選擇器 |
| db.update 400 | {"data": {...}} 包裝 |
| 401 | Token 過期，重新登入 |
| 409 | VFS 版本衝突，重新 GET |
| 423 | 有待審核發布，等待/取消 |

## 18. 核心策略：app_domain 標籤

### 概念

每個 Custom App 在寫入 SaaS 表（Data Reference）時，必須在 `custom_data` JSONB 中標記 `app_domain`，
用於標識該筆資料由哪個 App 建立，實現多 App 共用同一張表但資料隔離。

### 格式

- snake_case，如 `patent_os`、`crm_leads`、`inventory_mgr`
- 記錄在 `.aigo/config.json` 的 `app_domain` 欄位

### 寫入規範

所有 `db.insert()` 和 `db.update()` 呼叫，payload 的 `custom_data` 中必須包含：

```json
{
  "custom_data": {
    "app_domain": "<config 中的值>",
    "...其他欄位": "..."
  }
}
```

### 讀取規範

讀取 SaaS 表資料時，應用 `app_domain` 過濾，僅處理本 App 建立的資料：

```typescript
const myRecords = allRecords.filter(
  r => r.custom_data?.app_domain === APP_DOMAIN
);
```

### 實例

```json
{
  "name": "AI溢流防護裝置",
  "custom_data": {
    "app_domain": "patent_os",
    "case_no": "IP-E2E-FULL-001",
    "status": "待檢索",
    "country": "TW",
    "patent_type": "發明",
    "inventor": "王大明、李小華"
  }
}
```

## 19. Data Reference vs Custom Table 選擇指引

### 決策流程

1. 用 Refs API 查詢所有可用 SaaS 表（見 §20），確認是否有結構相似的表
2. 用 Refs API 查詢該表欄位，確認是否有 `custom_data`（JSONB）欄位可擴充
3. 確認權限（read/create/update/delete）是否滿足需求
4. 在 AI GO Builder 後台將選定的表加入 Data Reference，使其出現在 `db.json`

### 選擇矩陣

| 條件 | 選擇 | 說明 |
|------|------|------|
| SaaS 表有適合的主表結構 + JSONB 欄位 | **Data Reference** | 用 `custom_data` 存放 App 特有資料 |
| SaaS 表結構部分適用 | **Data Reference + Custom Table** | 主資料用 SaaS 表，輔助資料用 Custom Table |
| 需要完全自訂的獨立資料結構 | **Custom Table** | 最後手段 |
| 需要與其他 SaaS 功能整合 | **Data Reference**（優先） | 與看板、專案等功能共用資料 |

### SaaS 表常見結構

SaaS 表通常包含以下標準欄位：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | UUID | 主鍵 |
| `name` | VARCHAR | 名稱 |
| `active` | BOOLEAN | 啟用狀態 |
| `description` | TEXT | 描述 |
| `custom_data` | JSONB | **App 擴充資料**（app_domain + 自訂欄位） |
| `user_id` | UUID | 負責人 |
| `customer_id` | UUID | 客戶 |
| `stage_id` | UUID | 階段 |
| `created_at` | TIMESTAMP | 建立時間 |
| `updated_at` | TIMESTAMP | 更新時間 |

## 20. Data Reference 探索 API

用於在開發規劃階段（Phase 1.5）探索所有可用的 SaaS 表，決定哪些表適合作為 Data Reference。

### 20.1 查詢可用資料表清單

```http
GET /api/v1/refs/available-tables
Authorization: Bearer {access_token}
```

功能：列出資料庫中所有目前可以被 Custom App 引用的資料表名稱與備註。自動排除系統敏感黑名單表。

權限限制：帳號必須擁有 `builder.access` 權限。

回應範例：

```json
[
  {"name": "customers", "comment": "客戶/夥伴"},
  {"name": "sale_orders", "comment": "銷售訂單"},
  {"name": "project_projects", "comment": "專案"},
  {"name": "project_tasks", "comment": "專案任務"},
  {"name": "account_invoices", "comment": "發票"},
  {"name": "product_templates", "comment": "產品模板"}
]
```

### 20.2 查詢特定資料表欄位

```http
GET /api/v1/refs/tables/{table_name}/columns
Authorization: Bearer {access_token}
```

功能：列出指定資料表下可用的欄位資訊（含欄位名稱、資料型別、是否可為 Null、是否為系統欄位）。

權限限制：帳號必須擁有 `builder.access` 權限。

回應範例：

```json
[
  {"name": "id", "type": "UUID", "nullable": false, "is_system": true},
  {"name": "tenant_id", "type": "UUID", "nullable": false, "is_system": true},
  {"name": "name", "type": "VARCHAR(255)", "nullable": false, "is_system": false},
  {"name": "email", "type": "VARCHAR(255)", "nullable": true, "is_system": false},
  {"name": "phone", "type": "VARCHAR(50)", "nullable": true, "is_system": false},
  {"name": "custom_data", "type": "JSONB", "nullable": true, "is_system": false},
  {"name": "created_at", "type": "TIMESTAMP", "nullable": false, "is_system": true},
  {"name": "updated_at", "type": "TIMESTAMP", "nullable": false, "is_system": true}
]
```

欄位說明：

| 欄位 | 說明 |
|------|------|
| `name` | 欄位名稱 |
| `type` | 資料型別（UUID, VARCHAR, TEXT, INTEGER, BOOLEAN, NUMERIC, JSONB, DATE, TIMESTAMP 等） |
| `nullable` | 是否可為 NULL |
| `is_system` | 是否為系統欄位（id, tenant_id, created_at, updated_at 等，不可手動寫入） |

### 20.3 典型使用流程

```
Phase 1.5 實作計畫時：

1. GET /api/v1/refs/available-tables
   → 取得所有可用 SaaS 表清單

2. 對每個候選表 GET /api/v1/refs/tables/{name}/columns
   → 確認欄位結構、是否有 custom_data (JSONB)

3. 決定資料架構：哪些需求用 SaaS 表、哪些用 Custom Table

4. 在 AI GO Builder 後台將選定的 SaaS 表加入 Data Reference
   → 表即出現在 VFS 的 db.json 中

5. 重新 Phase 0 Review 確認 db.json 已包含所需的表
```

> **重要**：`available-tables` 僅列出可用表名，實際將表加入 App 的 Data Reference 需在 AI GO Builder 後台操作。
> 加入後，該表的完整 schema 和資料會自動注入到 `src/db.json`。

## 21. 架構設計理念

### 為什麼是 TypeScript + Python

TypeScript（前端）和 Python（後端 Server Action）是 AI GO 精選的開發語言組合，基於以下特性選定：

- **低出錯率與高可靠性**：TypeScript 的靜態型別系統和 Python 的清晰語法，大幅降低常見程式錯誤的發生率
- **依賴樹扁平、注入漏洞少**：靜態型別減少了動態語言常見的型別注入與未預期行為，提供更安全的執行環境
- **LLM 生成與閱讀最佳化**：這兩種語言在 LLM 訓練資料中覆蓋度最高，AI Agent 生成的程式碼品質與正確性顯著優於其他語言

因此，TypeScript + Python 最適合 **AI Coding 的新手或非技術工作者**，用來開發需要可靠性的公司內部系統。

### 為什麼資料存取走 API，不直連資料庫

- **避免結構混亂**：直接連線資料庫且 schema 可疊加時，非技術的 AI Coder 容易重複建立類似的表或欄位，造成資料結構混亂
- **通用結構先行**：AI GO 預先定義了中小企業通用的資料庫結構（SaaS 表），涵蓋專案、客戶、銷售、會計等常見業務場景
- **擴充彈性**：同時保有 Custom Table 的自訂擴充能力，以及 SaaS 表的 `custom_data`（JSONB）欄位
- **安全與一致性**：中間統一走 API 與反向代理，確保多租戶隔離、權限控制、資料驗證等安全機制

### 現有系統遷移

若用戶的情景屬於「現有系統匯入 AI GO 部署」，且現有系統不是 TypeScript + Python：

1. **解釋語言選擇理由**：說明上述 TypeScript + Python 的精選特性
2. **建議建立新專案重構**：在 AI GO 上建立全新 Custom App 專案，以 AI GO 架構重新設計
3. **原專案不更動**：用戶的本地原始專案保持不變，AI GO 專案獨立開發
4. **業務邏輯遷移**：引導用戶將現有系統的業務邏輯和資料結構，對應到 AI GO 的 SaaS 表 + Custom Table 架構

## 22. 外部 Schema 映射指引

當用戶要將外部系統（Supabase / Google Sheet / MySQL 等）遷入 AI GO 時，需要將外部 DB 的表結構映射到 AI GO 的資料架構。

### 22.1 映射流程

```
1. 列出外部系統的所有資料表與欄位
2. 用 Refs API 查詢 AI GO 可用 SaaS 表（見 §20）
3. 逐表比對：
   外部欄位 → SaaS 表原生欄位？ → 直接對應
   外部欄位 → 無原生對應？       → custom_data JSONB 擴充
   整張表都不適用 SaaS 表？      → Custom Table
4. 處理外鍵 / 關聯
5. 產出映射表（模板見 resources/migration_mapping_template.md）
```

### 22.2 語意重疊表的合併 / 分離決策

當多個外部系統有語意相同的表（如都有「客戶表」）時：

| 判斷條件 | 結果 | 說明 |
|---------|------|------|
| 指向同一群實體 + 未來需統一檢視 | **合併** | 進同一張 SaaS 表，各 App 用 `app_domain` 標籤區分來源 |
| 指向同一群實體 + 各自獨立運作 | **合併** | 但各 App 只過濾自己 `app_domain` 的資料 |
| 指向不同群實體（如不同市場的客戶） | **分離** | 各自建 Custom Table 或用不同 `app_domain` 隔離 |
| 欄位結構差異過大（>50% 不同） | **分離** | 硬塞進同一張表會造成 custom_data 過於複雜 |

決策樹：

```
多個外部系統都有語意相同的表
  ├─ 是同一群實體？
  │   ├─ 是 → 合併進同一張 SaaS / Custom Table
  │   │       ├─ 欄位聯集 → 共有欄位用原生欄位，各自特有欄位放 custom_data
  │   │       └─ 去重策略 → 以 email / 名稱為 key，衝突時由用戶決定保留哪邊
  │   └─ 否 → 分離
  │           ├─ 各自對應不同 AI GO App
  │           └─ 各自做 Schema 映射
  └─ 不確定 → 問用戶確認
```

### 22.3 外鍵 / 關聯處理

AI GO 的 SaaS 表和 Custom Table 沒有原生外鍵約束。外部 DB 的 FK 關係需要轉換：

| 外部 FK 類型 | AI GO 處理方式 |
|-------------|---------------|
| `tasks.project_id → projects.id` | Custom Table 中建立 `project_id`（relation 型別）欄位；或 SaaS 表中存入 `custom_data.project_id` |
| `orders.customer_id → customers.id` | 若兩表都用 SaaS 表，可直接用 SaaS 表的 `customer_id` 欄位 |
| 多對多（junction table） | 轉為 Custom Table 存放關聯，或在 `custom_data` 中存 ID 陣列 |

> **重要**：參照完整性需由前端 / Server Action 程式碼維護，AI GO 不會自動做 cascading delete 等操作。

### 22.4 多系統遷入時的 custom_data 命名空間

當多個 App 共用同一張 SaaS 表時，建議在 `custom_data` 中使用 `app_domain` 作為命名空間前綴：

```json
{
  "app_domain": "crm_leads",
  "crm_leads__level": "VIP",
  "crm_leads__source": "官網"
}
```

或使用巢狀結構：

```json
{
  "app_domain": "crm_leads",
  "ext": {
    "level": "VIP",
    "source": "官網"
  }
}
```

選擇哪種取決於查詢複雜度，但**必須在 Phase 1.25 全景表中統一決定**，所有 App 遵循同一規範。

## 23. 資料遷移方法

當用戶決定要將外部系統的歷史資料遷入 AI GO 時，使用以下指引。

### 23.1 遷移策略矩陣

| 資料量 | 關聯複雜度 | 建議方式 |
|--------|-----------|---------|
| 少（< 200 筆） | 簡單（無 FK） | API 逐筆寫入，可手動或簡單 script |
| 少（< 200 筆） | 複雜（有 FK） | Server Action 批次匯入，先匯主表再匯子表 |
| 中（200~2000 筆） | 任意 | Server Action 批次匯入 |
| 多（> 2000 筆） | 任意 | Server Action 分批匯入（每批 100 筆），加入錯誤處理與斷點續傳 |

### 23.2 Server Action 批次匯入範例

```python
def execute(ctx):
    """批次匯入外部資料到 SaaS 表或 Custom Table"""
    records = ctx.params.get("records", [])
    table = ctx.params.get("table", "")
    app_domain = ctx.params.get("app_domain", "")
    
    results = {"success": 0, "failed": 0, "errors": [], "id_mapping": {}}
    
    for record in records:
        try:
            # 注入 app_domain 標籤（SaaS 表適用）
            if app_domain:
                record.setdefault("custom_data", {})
                record["custom_data"]["app_domain"] = app_domain
            
            # 記住外部 ID 用於後續關聯映射
            old_id = record.pop("_external_id", None)
            
            result = ctx.db.insert(table, {"data": record})
            results["success"] += 1
            
            if old_id and result.get("id"):
                results["id_mapping"][str(old_id)] = result["id"]
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"record": record, "error": str(e)})
    
    ctx.response.json(results)
```

### 23.3 ID 體系轉換

外部系統通常使用自增整數 ID 或 Google Sheet 行號，AI GO 使用 UUID。遷移時需要：

1. **匯入主表**，記錄 `{外部 old_id → AI GO new_uuid}` 映射
2. **匯入子表**時，用映射表替換 FK 欄位的值
3. 映射表可存在 Server Action 的回傳結果中，或暫存為 Custom Table

```
遷移順序（有 FK 時）：
1. 匯入 customers → 取得 old_id → new_uuid 映射
2. 匯入 orders → 用映射表替換 orders.customer_id
3. 匯入 order_items → 用映射表替換 order_items.order_id
```

### 23.4 Google Sheet 遷移特殊考量

| 問題 | 處理方式 |
|------|---------|
| 無明確型別（全部是字串） | 遷入時在 Server Action 中做型別轉換（數字、日期） |
| 無外鍵 | 需人工識別哪些欄位是關聯欄位（如「客戶名稱」→ 對應到 customers 表） |
| 欄位名稱為中文 | 映射時建立「中文欄位名 → AI GO 英文欄位名」對照表 |
| 空行 / 重複行 | 遷入前先清洗：去除空行、依關鍵欄位去重 |
| 格式不一致（日期混用） | 在 Server Action 中統一格式化 |

### 23.5 遷移後驗證 Checklist

```
✓ 總筆數比對：外部系統 N 筆 → AI GO N 筆
✓ 關鍵欄位抽驗：隨機抽 5~10 筆，比對名稱/金額/日期等關鍵欄位
✓ 關聯完整性：子表的 FK 欄位都能對應到主表的有效記錄
✓ app_domain 標籤：所有 SaaS 表記錄都帶有正確的 app_domain
✓ custom_data 結構：JSONB 欄位的 key 符合映射表定義
✓ 無殘留測試資料：遷移過程中的測試記錄已清除
```

