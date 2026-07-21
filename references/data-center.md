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

> **唯一例外**：relation 欄位指向自建表時用的是 `target_table_id`（目標表的 **UUID**，
> 從 `GET /tables` 回應的 `id` 取），不是實體名。填錯會拿到泛用 422。

---

## 2. 權限：結構與資料分開管

| 操作 | 需要權限 |
|------|---------|
| 建表／改表／刪表／加欄／改欄／刪欄 | **`system.admin`** |
| 讀結構（列表／讀 schema） | `builder.access` |
| 記錄 CRUD（查／增／改／刪） | `builder.access` |

這是平台刻意收窄的治理界線：管制的是 schema 的形狀，不是它的使用。

### Agent 的建表流程（★ 強制）

```
1. GET /api/v1/data-center/tables        ← 盤點租戶既有自建表（不可跳過）
2. 有語意相同的表？ → 重用，不要新建
3. 需要新表 → 產出「建表規格」給用戶確認（Phase 1.5 計畫閘門）
4. POST /api/v1/data-center/tables
   ├─ 201 → GET 驗收，繼續開發
   └─ 403 → 用戶不是租戶管理員
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
