# 資料中心自建表（Custom Tables）

> 術語定義見根目錄 `CONTEXT.md`。本檔是操作規格。

## 1. 核心語義：租戶級資源

自建表綁 **tenant**，不綁 app。同一租戶下的所有 custom app 與資料中心 UI 看到同一批表、
同一份資料。這與已退場的 CustomObject（綁 app）是最重要的語義差異。

**因此建表前必須先盤點。** 兩個 app 各建一張「客戶」表 = 資料分裂成兩份，事後難以合併。

### 雙軌命名

| | 顯示名（display name） | 實體名（physical name） |
|---|---|---|
| 誰決定 | 你提供 | 系統從顯示名生成 |
| 可否修改 | 可以，隨時 | **建立後永不可變** |
| 字元集 | 任意（中文常見） | 純 ASCII |
| 用途 | UI 呈現 | API 識別、SQL 識別、**刪除確認值** |

**所有 API 在指涉既有表／欄位時一律用實體名。** 改顯示名不影響任何既有引用。

⚠️ **實體名有保留名單（2026-08 擴大）**：除了 ERP 表名與 SQL 保留字，
現在還包含**平台地板表名**（`users`／`tenants`／`audit_logs`／`api_keys`／
`countries` 等共 76 張）。撞名在建表當下就回 **409**（「與平台保留表名衝突」），
**沒有事後補救管道**——顯示名取「使用者」這類會生成保留實體名的名稱前，
先想好實體名會長什麼樣（可加業務前綴避開，如「專案成員」→ `project_members`）。

> ⚠️ **2026-09-01 實測：地板名檢查 prod 尚未生效**（`display_name: "users"` 實際
> 建成了 201，測試表已刪）。**這不是可以撞名的許可，是更強的自律理由**：現在建了
> 保留名的表，等檢查部署後它會被 grandfather（只擋新建不回溯），但你占用了平台
> 語意的名字，日後對照文件、除錯、資料遷移全會混淆。一律當作 409 已生效來規劃。

> **唯一例外**：relation 欄位指向自建表時用的是 `target_table_id`（目標表的 **UUID**，
> 從 `GET /tables` 回應的 `id` 取），不是實體名。填錯會拿到泛用 422。

---

## 2. 權限：結構與資料分開管

| 操作 | 需要權限 |
|------|---------|
| 建表／改表／加欄／改欄（含 ERP 延伸欄位建改，→ §10） | **`datacenter.schema_write`**（2026-08 起；`system.admin` 直通） |
| 刪表／刪欄／刪延伸欄位 | **`system.admin`**（刻意不下放） |
| 讀結構（列表／讀 schema） | `builder.access` 或 `datacenter.schema_write`（任一即可） |
| 記錄 CRUD（查／增／改／刪） | `builder.access` |

這是平台刻意收窄的治理界線：管制的是 schema 的形狀，不是它的使用。
**建改與刪除是兩段權限**：可以建表的角色不一定能刪表。
⚠️ 預設角色**沒有**被回填 `datacenter.schema_write`——要讓非 admin 角色建表，
必須由租戶擁有者到角色 UI 勾選；既有 `system.admin` 呼叫端不受影響（直通）。

### Agent 的建表流程（★ 強制）

```
1. GET /api/v1/data-center/tables        ← 盤點租戶既有自建表（不可跳過）
2. 有語意相同的表？ → 重用，不要新建
3. 需要新表 → 產出「建表規格」給用戶確認（Phase 1.5 計畫閘門）
4. POST /api/v1/data-center/tables
   ├─ 201 → GET 驗收，繼續開發
   └─ 403 → 帳號缺 datacenter.schema_write（也非 system.admin）
          → 不重試、不繞路
          → 輸出可照抄的建表規格，引導用戶到資料中心 UI 自建
          → 用戶回報建好後，GET /tables 驗收再繼續
```

---

## 3. 欄位型別

| 型別 | 說明 | 額外契約 |
|---|---|---|
| `text` | 文字 | |
| `number` | 數值 | |
| `boolean` | 布林 | |
| `date` | 日期 | |
| `datetime` | 日期時間 | |
| `select` | 單選 | 必須提供選項集；值受 CHECK 約束 |
| `relation` | 關聯 | 見下 |
| `json` | 結構化資料 | |
| `image` | 圖片 | 存 storage key，見 §6 |

系統欄位 `id` / `created_at` / `updated_at` 自動帶，不可刪、不可改型別、不計入欄位配額。

### relation 的兩種目標（恰擇其一）

- **→ 自建表**：參數 `target_table_id`＝目標表的 **UUID**（從 `GET /tables` 的 `id` 取，
  **不是實體名**）。建**真正的資料庫外鍵**，刪除仍被引用的列會被 DB 擋下
  （409，`detail.dependents` 列出依賴者）。
- **→ ERP 表**：參數 `target_erp_key`＝ERP 表 key。軟關聯，**不建外鍵**（跨 schema 邊界），
  目標值在寫入時驗證存在性。

兩者**恰擇其一**——都給或都不給皆為錯誤。建立後不可變（PATCH 改欄不收這兩個參數）。

---

## 4. 配額

| | 免費檔 | 付費檔 |
|---|---|---|
| 每租戶表數 | **20** | **200** |
| 每表非系統欄位數 | **50** | **100** |

- 付費判定 = 有 active 訂閱 ∪ 平台租戶；取不到狀態時 **fail-closed 落免費檔**。
- 平台 ops 可對個別租戶覆寫配額（`tenants.settings.data_center_quota`）——
  **不是租戶自助**，撞限且有正當需求時引導用戶聯絡平台，不要嘗試繞。
- 超限錯誤是 **409**，body `{"error": code, "message": ...}`：
  `table_quota_exceeded`「已達自建表數上限（N 張，目前 M 張）」／
  `field_quota_exceeded`「已達欄位數上限（N 欄，目前 M 欄）」。
- ⚠️ **單次 `POST /tables` 最多帶 50 個欄位**（schema 層上限），這與每表欄位配額是兩回事：
  付費租戶想一次建 60 欄會拿到 **422 而不是 409**，必須先建表再逐次 `POST /tables/{key}/fields`。
- ERP 延伸欄位（EAV）沿用同一組欄數配額。
- 超限回 **409**（不是靜默截斷）。

---

## 5. 刪除是兩段式的

刪表與刪欄**不可逆**，伺服器端強制兩段：

1. **影響預覽**：`GET /tables/{key}/impact` 或 `GET /tables/{key}/fields/{field_key}/impact`
   → 回傳記錄數、各欄位非空值統計、是否有其他表以關聯依賴它
2. **確認執行**：確認值走 **query 參數 `confirm`**，必須等於**實體名**
   （不可用顯示名——顯示名可改，拿它當確認值等於沒確認）

```http
DELETE /api/v1/data-center/tables/{key}?confirm={表實體名}
DELETE /api/v1/data-center/tables/{key}/fields/{field_key}?confirm={欄位實體名}
```

---

## 6. 圖片欄位

`image` 欄位存的是 **storage key，不是 URL**。URL 只有一小時有效期，存進欄位會過期。

```
data-center/{租戶 UUID}/{表實體名}/{隨機 UUID}.{png|jpg|gif|webp}
```

| 動作 | 端點 | 契約 |
|---|---|---|
| 上傳 | `POST /api/v1/data-center/tables/{key}/images` | 回傳 storage key 與一張可直接顯示的 URL；**把 key 存進欄位** |
| 取 URL | `GET /api/v1/data-center/images/url` | 帶 key，回傳短效期簽章 URL；每次顯示時重取 |

- 允許 PNG／JPEG／GIF／WebP，單檔上限 **10 MB**。**SVG 被刻意排除**（可內嵌 script）。
- 圖片會出現在**檔案總管**的「資料中心圖片」資料夾，使用者可自行刪除。
  刪掉後欄位顯示「圖片已移除」——這是已知取捨，不是 bug。
- 刪記錄／刪欄／刪表**不會**連帶刪 storage 物件（孤兒檔由平台前綴掃描對帳）。

---

## 7. API 速查

### REST（登入使用者身分）

| 操作 | 方法 | 端點 | 權限 |
|---|---|---|---|
| 列表 | GET | `/api/v1/data-center/tables` | `builder.access` |
| 讀單表 | GET | `/api/v1/data-center/tables/{key}` | `builder.access` |
| 建表 | POST | `/api/v1/data-center/tables` | `system.admin` |
| 改表（顯示名等） | PATCH | `/api/v1/data-center/tables/{key}` | `system.admin` |
| 刪表影響 | GET | `/api/v1/data-center/tables/{key}/impact` | `builder.access` |
| 刪表 | DELETE | `/api/v1/data-center/tables/{key}` | `system.admin` |
| 加欄 | POST | `/api/v1/data-center/tables/{key}/fields` | `system.admin` |
| 改欄 | PATCH | `/api/v1/data-center/tables/{key}/fields/{field_key}` | `system.admin` |
| 刪欄影響 | GET | `/api/v1/data-center/tables/{key}/fields/{field_key}/impact` | `builder.access` |
| 刪欄 | DELETE | `/api/v1/data-center/tables/{key}/fields/{field_key}` | `system.admin` |
| 查記錄 | GET | `/api/v1/data-center/tables/{key}/records` | `builder.access` |
| 新增記錄 | POST | `/api/v1/data-center/tables/{key}/records` | `builder.access` |
| 更新記錄 | PATCH | `/api/v1/data-center/tables/{key}/records/{record_id}` | `builder.access` |
| 刪記錄 | DELETE | `/api/v1/data-center/tables/{key}/records/{record_id}` | `builder.access` |

External app 的執行期走 `/api/v1/ext/data-center/...`——含 `GET /tables`（列出整租戶自建表
及其欄位定義）與記錄 CRUD，但**沒有結構操作**。前端 SDK 依 `window.__IS_EXTERNAL__` 自動分流。

### 前端 SDK（`src/api.ts`，Custom App 內）

```typescript
import { listTables, queryTable, insertRow, updateRow, deleteRow } from "../api";

const tables = await listTables();

// 分頁信封 {items, total, page, page_size}
const page = await queryTable("orders", {
  filters: [{ field: "status", op: "eq", value: "open" }],  // op ∈ eq/contains/gte/lte
  sort: "-created_at",     // <實體名> 升冪，-<實體名> 降冪，單欄
  page: 1,
  page_size: 25,
});

await insertRow("orders", { customer_name: "王大明", amount: 1200 });
await updateRow("orders", rowId, { status: "closed" });
await deleteRow("orders", rowId);
```

SDK 依 `window.__IS_EXTERNAL__` 自動分流 `/data-center` 或 `/ext/data-center`，不需自己判斷。

### Server Action（`ctx.db`，Python）

```python
def execute(ctx):
    tables = ctx.db.list_tables()
    # [{"key": "orders", "display_name": "訂單", "fields": [...]}, ...]

    page = ctx.db.query_table("orders", {
        "filters": [{"field": "status", "op": "eq", "value": "open"}],
        "sort": "-created_at", "page": 1, "page_size": 25,
    })

    row = ctx.db.insert_row("orders", {"customer_name": "王大明"})
    ctx.db.update_row("orders", row["id"], {"status": "closed"})
    ctx.db.delete_row("orders", row["id"])
```

**SDK 不提供結構操作**——app 執行期無法建表或改欄，這是刻意的能力邊界。

---

## 8. 舊 CustomObject：只讀不加

存量 app 可能還在用。辨識方式：

| 訊號 | 說明 |
|---|---|
| `src/data.json` 有內容 | legacy CustomObject 表定義 |
| `listRecords` / `submitRecord` / `updateRecord` / `deleteRecord` | api.ts 的 legacy 方法（雙軌並存，不會壞） |
| `ctx.db.query_object` / `insert_object` / `list_custom_objects` | ctx 的 legacy 方法 |

**處置原則：不要往上加東西。** 存量功能維持原樣即可運作；任何新資料需求一律開自建表。

已退場的部分：builder 的 CustomObject 工具（派發層直接拒絕舊工具名）、後台「資料」tab、
新租戶的示範表自動建立。存量資料遷移尚未排程。

---

## 9. 租戶使用者目錄：自建表要「關聯使用者」怎麼做（2026-09 起）

> ⚠️ **2026-09-01 實測 prod 回 404——已 merge 尚未部署**。用之前先打一次確認；
> 404 時退回「text 欄存 UUID、顯示名暫用其他管道」的做法。

新端點 **`GET /api/v1/users`**（已登入即可，無需額外權限）回傳租戶使用者目錄：

- 參數只有 `page`（預設 1）與 `page_size`（1–500，預設 200）；回傳分頁信封
  `{items, total, page, page_size}`
- 每筆**只有三欄**：`id`（UUID）、`name`、`status`（`pending`/`active`/`disabled`）。
  **刻意沒有 email、roles、member_id**——沒有名字的帳號回固定字串「（未命名帳號）」，
  **不要自己拿 email 或 id 去補顯示名**（平台明文禁止的呈現方式）
- 資料中心也多了一張唯讀表 `users`（「使用者帳號」，readonly-shared，
  無側欄入口、可直開 `/dashboard/data/users`）

⚠️ **自建表目前不能把 relation 欄位指向 `users`**——它不在可解析的關聯目標內
（選了會 422，前端建欄選單也已排除身分表）。要在自建表記「哪個使用者」：

1. 開一般 `text` 欄存 user UUID（寫入時 action 用 `ctx.user_id` 覆蓋，見核心規則 23）
2. 顯示時用 `GET /api/v1/users` 的結果解 UUID → name（建個 id→name 的 Map 快取）

> 平台方向是未來讓 UUID 欄升級成關聯選單，此端點是前置建設；
> 落地前不要嘗試 `target_erp_key='users'` 之類的寫法。

---

## 10. ERP 延伸欄位（EAV）：幫 SaaS／ERP 預設表加正式欄位（2026-08 起）

> 端點與行為核對自平台原始碼（`backend/app/api/data_center_ext.py`、
> `services/data_center/ext_fields.py`），prod 未逐項實測——
> 拿到 404 或缺欄位先懷疑部署落差，不是文件錯。

### 定位：Data Reference 軌的第三種擴充機制

SaaS／ERP 表**本體 schema 不可改**（平台定義，沒有任何 API 能對它 ALTER TABLE）。
要讓預設表「更符合使用者的資料結構需求」，有三個選項，**不是只有 custom_data**：

| 需求 | 選 | 理由 |
|------|-----|------|
| 原生欄位語意能對上 | **原生欄位** | 永遠優先 |
| 租戶級的正式欄位：要有型別、要在資料中心 UI 對全租戶可見可管理 | **延伸欄位**（本節） | 有型別驗證、有欄位定義、跨 app 一致 |
| app 私有標記（`app_domain` 必在此）、鬆散或暫時性的擴充 | `custom_data` JSONB | 免定義成本，但無型別、僅該 app 自己認得 |

讀寫頻繁且 app 是該資料的主要使用者時，回頭重新考慮：這個實體也許該整個走自建表。

### 是 overlay，不是實體欄位（★ 讀寫契約，最容易踩）

延伸欄位的定義與值存在**獨立的 EAV 表**，ERP 表本體零改動。後果：

- **`ctx.db.query`／`db.ts` 的查詢結果不會包含延伸欄位值**——讀 = 主列查詢
  ＋另打 `:batch-get` 自己合成；寫 = 原生欄位走既有路徑、延伸欄位另打 PATCH
- 「缺值不回填」：batch-get 只回傳實際存在的值，**不代入 `default_value`**
- relation 型別一律**軟關聯無 FK**；required／unique 由應用層保證，DB 不擋
- Custom App SDK（`api.ts`／`ctx.db`）**沒有封裝**——app 執行期要用得自己打 REST；
  需要在 app 內大量讀寫延伸欄位時，優先重新評估改走自建表

### 端點速查（前綴 `/api/v1/data-center`）

| 動作 | 方法與路徑 | 權限 |
|------|-----------|------|
| 列出定義 | GET `/ext-fields/{erpKey}` | `builder.access` 或 `datacenter.schema_write` |
| 建欄 | POST `/ext-fields/{erpKey}` | `datacenter.schema_write`（`system.admin` 直通） |
| 改欄 | PATCH `/ext-fields/{erpKey}/{fieldKey}` | `datacenter.schema_write` |
| 刪欄（兩段式：impact → confirm） | GET `.../{fieldKey}/impact` → DELETE | **`system.admin`**（帶走該欄所有值，刻意不下放） |
| 批取值 | POST `/ext-values/{erpKey}:batch-get`（body `row_ids` ≤ **200**） | `builder.access` |
| 寫值 | PATCH `/ext-values/{erpKey}/{rowId}` | `builder.access` |

- `{erpKey}` 是 ERP meta registry 的表 key；`{fieldKey}` 是延伸欄位實體名
- 型別與自建表**同一套 9 型別**（§3），select 選項集驗證也同一套
- 配額沿用每表欄數配額（§4）
- 管結構的人不自動獲得看資料的權——定義面與值面的權限是分開的
