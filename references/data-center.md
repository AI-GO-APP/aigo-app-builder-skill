# 資料中心自建表（Custom Tables）

> 術語定義見根目錄 `CONTEXT.md`。本檔是操作規格。

## 1. 核心語義：租戶級資源

自建表綁 **tenant**，不綁 app。同一租戶下的所有 custom app 與資料中心 UI 看到同一批表、
同一份資料。這與已退場的 CustomObject（綁 app）是最重要的語義差異。

**因此建表前必須先盤點。** 兩個 app 各建一張「客戶」表 = 資料分裂成兩份，事後難以合併。

### 雙軌命名

| | 顯示名（display name） | 實體名（physical name） |
|---|---|---|
| 誰決定 | 你提供 | **系統從顯示名生成，API 不收** |
| 可否修改 | 可以，隨時（`PATCH`） | **建立後永不可變，平台沒有改名 API** |
| 字元集 | 任意（中文常見） | 純 ASCII，`[a-z_][a-z0-9_]*`，基底 ≤48 字元 |
| 用途 | UI 呈現 | API 識別、SQL 識別、`filters`／`sort` 的欄名、**刪除確認值** |

**所有 API 在指涉既有表／欄位時一律用實體名。** 改顯示名不影響任何既有引用。

建表 payload 只收 `display_name`；改表／改欄 payload 帶 `physical_name` 直接 422
（`extra="forbid"`）。⇒ **實體名是你唯一控制不到、又永遠改不掉的東西，只能靠顯示名間接決定。**

### ★ 中文顯示名會生出 `tbl` / `col_2`（命名硬閘的由來）

生成規則是 NFKD 折疊 → 丟掉非 ASCII → 非 `[a-z0-9]` 收斂成底線 → 去頭尾底線。
**純中文折疊後是空字串**，於是落到「前綴保底 ＋ 同名流水號」：

| 填的顯示名 | 生成的實體名 |
|---|---|
| 「客戶」（該租戶第一張純中文表） | `tbl` |
| 「訂單」（第二張） | `tbl_2` |
| 欄位「姓名」「電話」「地址」 | `col`、`col_2`、`col_3` |
| 預設表延伸欄位「業務備註」 | `ext`、`ext_2` |
| 「2024報表」（數字開頭） | `tbl_2024` |
| 「客戶Customer」（中英混） | `customer`（ASCII 部分留下） |
| 「Customer List」 | `customer_list` |

後果是永久的——往後所有程式碼長成
`queryTable('tbl_3', { filters: [{ field: 'col_7', op: 'eq', value: x }] })`，
且**沒有改名管道**（要換名只能重建，見 §11）。
⚠️ 資料中心 UI 建表框的 placeholder 就寫「例如：客訴紀錄」，**用戶自己在 UI 建的表幾乎都是這個下場**；
接手既有租戶時先照 §11.1 掃一遍。

### ★ 命名規範（強制）

**1. 表：實體名一律 `biz_<英文實體複數>`**，snake_case。
`biz_` 是自建表的固定前綴，三個作用：

- 讀 code 一眼分得出自建表與預設表——預設表用功能區前綴（`crm_`／`sale_`／`hr_`／`account_`…，
  見 `default-table-lookup.md` §1），自建表一律 `biz_`
- **完全避開保留名 409**：保留母體 = SQL 保留字 ∪ 預設表名 ∪ 平台地板表名
  （`users`／`tenants`／`audit_logs`／`api_keys`／`countries`…共 76 張），沒有任何一個以 `biz_` 開頭
- 不佔用 `dc_`／`app_`——那是平台自己的表在用（`dc_tables`、`app_api_grants`…）

**2. 欄位：實體名一律英文 snake_case**，不加前綴（表已經有前綴）。
關聯欄位用 `<單數實體>_id`（`biz_orders.customer_id`）。延伸欄位同規範。

**3. 兩步命名法（★ 唯一能同時要到「英文實體名」與「中文 UI」的做法）**

```
1. POST /tables   display_name = "biz_customers"          → physical_name = biz_customers
                  欄位 display_name = "customer_name"      → physical_name = customer_name
2. PATCH /tables/biz_customers                       {"display_name": "客戶"}
   PATCH /tables/biz_customers/fields/customer_name  {"display_name": "客戶名稱"}
```

顯示名可改、實體名不可改 ⇒ **先用英文建、再把顯示名改成中文**。中文 UI 一點沒少，實體名乾淨。

⚠️ **兩步要在同一次交付內做完**。只做第一步就收工，用戶會在資料中心看到一排英文表名，
然後自己去改——那時實體名已經定了，改的只是顯示名，沒事；但沒改成中文的觀感問題會回頭變成你的 bug 單。

⚠️ 用戶要求「表名就是要中文」時，說明的是**顯示名確實是中文**，實體名是資料庫識別字、
不對一般使用者露出（只有開發者在 code 與 API 看得到）。不要因此退回中文顯示名建表。

> **保留名 409**：撞名在建表當下就回 409（「與系統內建（ERP）表名衝突」／「為 SQL 保留字」／
> 「與平台保留表名衝突」），**沒有事後補救管道**。照 `biz_` 前綴走就不會撞。
> ⚠️ 2026-09-01 實測**地板名檢查 prod 尚未生效**（`display_name: "users"` 實際建成 201，測試表已刪）——
> 這不是可以撞名的許可：檢查部署後既有表會被 grandfather（只擋新建不回溯），
> 但你占用了平台語意的名字，日後對照文件、除錯、資料遷移全會混淆。一律當作 409 已生效來規劃。

> **唯一例外**：relation 欄位指向自建表時用的是 `target_table_id`（目標表的 **UUID**，
> 從 `GET /tables` 回應的 `id` 取），不是實體名。填錯會拿到泛用 422。
---

## 2. 權限：結構與資料分開管

| 操作 | 需要權限 |
|------|---------|
| 建表／改表／加欄／改欄（含預設表延伸欄位建改，→ §10） | **`datacenter.schema_write`**（2026-08 起；`system.admin` 直通） |
| 刪表／刪欄／刪延伸欄位 | **`system.admin`**（刻意不下放） |
| 讀結構（列表／讀 schema） | `builder.access` 或 `datacenter.schema_write`（任一即可） |
| 記錄 CRUD（查／增／改／刪） | `builder.access` |

這是平台刻意收窄的治理界線：管制的是 schema 的形狀，不是它的使用。
**建改與刪除是兩段權限**：可以建表的角色不一定能刪表。
⚠️ 預設角色**沒有**被回填 `datacenter.schema_write`——要讓非 admin 角色建表，
必須由租戶擁有者到角色 UI 勾選；既有 `system.admin` 呼叫端不受影響（直通）。

> ⚠️ **這張權限表就是執行期的權限表，不只是後台的。** internal app 的前端 SDK
> 以**登入者身分**打同一組端點，所以「記錄 CRUD 需 `builder.access`」意味著：
> **沒有開發權限的一般員工，在 app 畫面上做任何自建表讀寫都會 403**。
> 這是 internal app 最容易踩、且開發階段測不出來的破口——完整機制與修復流程見 §7.5。

### Agent 的建表流程（★ 強制）

```
1. GET /api/v1/data-center/tables        ← 盤點租戶既有自建表（不可跳過）
2. 有語意相同的自建表？ → 重用，不要新建
2.5 平台有同語意的預設表？（default-table-lookup.md §2 ＋ Meta API；同樣不可跳過）
    → 有 → 走 Data Reference，不建表
    → 沒有 → 資料承載表寫下「已對照 X／不採用理由」再往下
3. 需要新表 → 產出「建表規格」給用戶確認（Phase 1.5 計畫閘門）
   └─ 規格表每一列都要寫出【實體名】：表 biz_<英文複數>、欄 英文 snake_case（§1 命名規範）
4. POST /api/v1/data-center/tables（display_name 先填【英文實體名】）
   ├─ 201 → GET 驗收 physical_name；不如預期就停下來（拿到 tbl / col_N = 填錯了，刪掉重建）
   │        → 5. PATCH 表與各欄 display_name → 中文（兩步命名法，同一次交付內做完）
   └─ 403 → 帳號缺 datacenter.schema_write（也非 system.admin）
          → 不重試、不繞路
          → 輸出可照抄的建表規格（含實體名欄與兩步命名法說明），引導用戶到資料中心 UI 自建
          → 用戶回報建好後，GET /tables 驗收（連 physical_name 一起看）再繼續
```

⚠️ **第 0 步是「盤點回來的既有表合不合命名規範」**（§11.1）。
重用一張 `tbl_3` 會把這個名字再寫進一支新 app，偵錄越累越多。

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
- **→ 預設表**：參數 `target_erp_key`＝預設表 key（API 參數沿用 erp 命名）。軟關聯，**不建外鍵**（跨 schema 邊界），
  目標值在寫入時驗證存在性。
  ⚠️ **只有部分預設表能當目標，且無法事先查詢**（核自原始碼：目標是靠命名慣例解析的，
  2026-08-31 主線 86 張只有 38 張可解析；2026-09-02 prod 實測 8 張常用表**只有 `sale_orders` 過**，
  `customers`／`product_templates`／`sale_order_lines`／`crm_leads`／`hr_employees`／
  `account_payments`／`product_products` 皆 422「無法解析 target_erp_key…本版尚不支援此表作為關聯目標」）。
  `GET /refs/available-tables` 與 `/refs/tables/{t}/columns` 都看不出可否當目標。
  **規劃時一律先假設不支援**：指向預設表的欄位建成 `text` 存平台 UUID（軟參照本來就不建 FK，
  只損失寫入時的存在性驗證），只在建表規格裡標「可升級為 relation」。遷入案第三張表才撞到會很痛——
  前兩張已建好

兩者**恰擇其一**——都給或都不給皆為錯誤。建立後不可變（PATCH 改欄不收這兩個參數）。

### relation／select／unique 的三個實測契約（2026-09-02）

- **relation → 自建表沒有 cascade**：真 FK 只會擋刪除（409 `dependents`），沒有 `ON DELETE CASCADE`
  的對應物。原系統靠 cascade 的鏈（課程→學期→班級→場次）要**由葉到根手刪**；
  降級成 `text` 的軟參照更沒有 FK，也要手動清
- **`select` 的 `options` 是純字串陣列**（schema `list[str]`）：傳 `{label, value}` 物件會 422
  `Input should be a valid string`
- **單欄 `is_unique` 重複寫入回 409 `unique_violation`**「欄位「x」的值重複，需唯一。」——
  這是平台上**唯一可用的伺服器端 compare-and-set**；預設表**沒有**這個原語（`customers.ref`
  實測無唯一約束，連 INSERT 兩次建出兩列）。需要冪等或併發防線的寫入，一律先在自建表
  用 unique 欄搶錨點——模式見 `custom-app-dev-guide.md` §23.9

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
- 延伸欄位（EAV）沿用同一組欄數配額。
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
**Hosted App 容器內**（`AIGO_API_TOKEN`）走 `/api/v1/open/data-center/...`——照上表路徑打會 401
（`hosted-apps.md` §5）。

records 平面的三個契約（自己寫 client 時最常踩；2026-09-02 實測＋原始碼核對）：

- **POST records 的 body 必須包 `{"data": {...}}`**。裸物件不報格式錯，而是整包被忽略後回
  422 `not_null_violation`「欄位「x」為必填」——訊息指向第一個必填欄位，容易誤以為欄位名對不上。
  `PATCH .../records/{id}` 兩種形狀都收。`scripts/aigo_data_center.py` 的 `insert_record` 已包好
- **`filters` 的運算子依欄位型別限縮**：`text` 只有 `eq`／`contains`；`number`／`date`／`datetime`
  才有 `gte`／`lte`（對 text 用 → 422「欄位「x」（型別 text）不支援運算子 'gte'」）。
  **沒有 `in`、`ne`、`is_null`，沒有 OR**——錯了會回 422 並列出合法集合。
  需要範圍查詢的日期欄要建成 `date`／`datetime`（§23.7 降級表本就如此），別存 text
- 與預設表 proxy 平面的完整對照（鍵名、運算子、錯誤反應都不同）→ `platform-behaviors.md` §1.5

### 前端 SDK（`src/api.ts`，Custom App 內）

> ⚠️ **先確認適用範圍再用（§7.5）**：前端 SDK 只適用受眾全員持有 `builder.access` 的開發工具型 app
> （以及判進 external 的例外 app，SDK 自動分流 `/ext/data-center`）。
> **internal app 的自建表存取一律包成 Server Action（`ctx.db.*`）**，
> 前端走 `runAction`——直呼下面這些方法，一般員工執行期必 403。

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

## 7.5 internal app 的執行期權限破口（★ 必讀）

### 機制：前端 SDK 是「登入者身分」，不是「app 身分」

三條資料中心通道的身分與權限完全不同：

| 通道 | 身分 | `builder.access` 閘 |
|---|---|---|
| 前端 SDK（internal，`/data-center/*`） | **登入使用者** | **有**——記錄 CRUD 全掛（router 層，源碼核對 2026-08-31） |
| 前端 SDK（external，`/ext/data-center/*`） | app 憑證脈絡 | 無 |
| Server Action（`ctx.db.*`，`/internal/ctx/invoke`） | app 憑證（invocation token） | 無——走 allowlist + scope gate，不驗使用者權限 |

後果：internal app 的受眾大多是**沒有** `builder.access` 的一般員工，
前端直呼 `queryTable`／`insertRow` 等方法時，他們拿到的是 403——
症狀是「畫面資料載不出來／按鈕按了沒反應」，network 面板可見 `/data-center/...` 403。

**為什麼開發時測不出來**：開發與驗證用的帳號必有 `builder.access`
（不然連 Builder 都進不去），所以 FDE 自己怎麼點都是通的。
2026-08-31 prod 盤點：**44 支 internal app 現行中招、另有 18 支未爆彈**——
這不是邊角案例，是照直覺寫就會踩的預設路徑。

### 正確寫法（新開發）

- internal app：自建表讀寫**一律**包 Server Action，前端 `runAction`。
- 前端 SDK 僅限受眾全員持有 `builder.access` 的開發工具型 app 直呼
  （判進 external 的例外 app 由 SDK 自動分流 `/ext/data-center`，不在此閘）。
- 受眾在 Phase 1.5 計畫階段就要確認（SKILL.md 核心規則 31）。

### 存量 app 修復流程

1. **盤點**：找出前端（`.ts`/`.tsx`，排除 `src/api.ts` 本體）所有
   `listTables`／`queryTable`／`listRows`／`getRow`／`insertRow`／`updateRow`／`deleteRow`
   呼叫與 `../api` import——`aigo_review.py` 的 Review 報告會自動標記（Phase 0）。
2. **逐組包 action**：前端與 `ctx.db` 的查詢契約相同
   （同樣的 `filters`/`sort`/`page` 與分頁信封；insert/update 同收扁平 dict），
   搬移本身是低風險的機械工作。
3. **★ 授權語意會改變，必須補閘**：前端直呼時「至少要有 `builder.access`」雖是錯的閘，
   但也是一道閘；包進 action 後變成「**看得到 app 的人都打得到這個 action**」。
   凡有權限差異的操作，action 內必須用 `ctx.user_permissions` 分流（核心規則 23）；
   身分欄位一律以 `ctx.user_id` 覆蓋前端送來的值。
   **跳過這一步，等於把「403 太多」修成「資料開太大」——後者更糟。**
4. **前端改 `runAction`**，並記得 action 要 **republish 才上線**（核心規則 21 精神）。
5. **驗證**：重跑 `aigo_review.py` 確認前端零殘留直呼；有條件時再用
   **無 `builder.access` 的測試帳號**實測關鍵路徑——用 FDE 帳號點過不算數（見上）。

### 假修法排除清單（都不要做）

- **把 app 改成 external**：`access_mode` 建立後不可改，且 external 語意完全不同
  （匿名／自助註冊、權限快照恆空）——不是修復路徑。
- **發 `builder.access` 給全員**：等於把開發權限發給全公司，反模式。
- **前端捕捉 403 後改打別的端點**：沒有旁路；正路只有 action 化。

> legacy CustomObject 的前端方法（`listRecords` 等）走 `/data/objects/*`，
> **同樣掛 `builder.access` 閘**——存量 legacy app 有一般員工受眾時是同一個病，
> 修法相同（包 action；legacy 原則見 §8：不要往上加東西）。

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

## 10. 延伸欄位（EAV）：幫預設表加正式欄位（2026-08 起）

> 端點與行為核對自平台原始碼（`backend/app/api/data_center_ext.py`、
> `services/data_center/ext_fields.py`）。**2026-09-01 prod 唯讀實測**：
> `GET /ext-fields/{erpKey}` 回 200 `[]`、`POST /ext-values/{erpKey}:batch-get`
> 對不存在的 row 回 200 `{}`（「缺值不回填」同步證實）——**功能已上線**。
> **2026-09-02 寫值端點形狀探測**：`PATCH /ext-values/...` 對未定義欄位回
> 422 `invalid_field`——寫入端點已上線且做欄位定義驗證。
> 建欄／改欄／刪欄與完整寫值流程仍未實測；拿到非預期回應先懷疑部署落差。

### 定位：Data Reference 軌的第三種擴充機制

預設表**本體 schema 不可改**（平台定義，沒有任何 API 能對它 ALTER TABLE）。
要讓預設表「更符合使用者的資料結構需求」，有三個選項，**不是只有 custom_data**：

| 需求 | 選 | 理由 |
|------|-----|------|
| 原生欄位語意能對上 | **原生欄位** | 永遠優先 |
| 租戶級的正式欄位：要有型別、要在資料中心 UI 對全租戶可見可管理 | **延伸欄位**（本節） | 有型別驗證、有欄位定義、跨 app 一致 |
| app 私有標記（`app_domain` 必在此）、鬆散或暫時性的擴充 | `custom_data` JSONB | 免定義成本，但無型別、僅該 app 自己認得 |

讀寫頻繁且 app 是該資料的主要使用者時，回頭重新考慮：這個實體也許該整個走自建表。

### 是 overlay，不是實體欄位（★ 讀寫契約，最容易踩）

延伸欄位的定義與值存在**獨立的 EAV 表**，預設表本體零改動。後果：

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

- `{erpKey}` 是預設表的表 key（平台內部命名帶 erp 字樣，見 CONTEXT.md 稱謂對照）；`{fieldKey}` 是延伸欄位實體名
- 遷入情景要把外部資料批次寫進延伸欄位 → 匯入機制與量的紅線見
  `custom-app-dev-guide.md` §23.8（逐列 PATCH、無批次寫入端點）
- 型別與自建表**同一套 9 型別**（§3），select 選項集驗證也同一套
- 配額沿用每表欄數配額（§4）
- 管結構的人不自動獲得看資料的權——定義面與值面的權限是分開的

---

## 11. 既有自建表不合命名規範：重建式改名（★ 有資料時這是遷移，不是改名）

接手既有租戶、或用戶自己在資料中心 UI 建過表時，Phase 0 步驟 6 盤點完**要逐表看 `physical_name`**。
`GET /api/v1/data-center/tables` 的回應每列都有 `physical_name` 與 `display_name`，看的是前者。

### 11.1 掃描：哪些表不合規（分級，不要一律重建）

| 級別 | 症狀 | 判準（對 `physical_name`） | 處置 |
|---|---|---|---|
| **P0 必改** | 生成保底名 | 表 `^tbl(_\d+)?$`；欄 `^col(_\d+)?$`；延伸欄位 `^ext(_\d+)?$` | 重建式改名（§11.3） |
| **P1 建議改** | 撞平台語意 | 等於平台地板表名或預設表名（`users`／`customers`／`orders`…） | 重建式改名；資料量大時可與用戶議定延後 |
| **P2 記錄即可** | 只是少了 `biz_` 前綴，名字本身可讀 | `inventory`、`customers_v2`、`project_logs` | **預設不動**，記進計畫的「已知偏差」；新表一律照規範 |
| **P3 免費修** | 只有**顯示名**不對（實體名合規、顯示名是英文或空泛） | — | 直接 `PATCH` 改顯示名，零風險、不需重建 |

⚠️ **不要為了前綴一致就重建一張可讀又有資料的表**——重建的每一步都不可逆，
收益（命名一致）與風險（資料遺失、圖片失效、app 停擺）不成比例。
P2 一律先列出來讓用戶自己決定，agent 不主動建議重建。

⚠️ 欄位名同樣要掃。**一張表只有部分欄位是 `col_N`**時，處置比整表重建輕得多：
加一個新欄（正確名）→ 逐列把值搬過去 → 改引用 → 刪舊欄（`system.admin`＋
`?confirm=<欄位實體名>`）。表不用動，relation 與圖片都不受影響。**能只改欄就不要重建表。**

### 11.2 為什麼是「重建」而不是「改名」

- `PATCH /tables/{key}` 只收 `display_name`／`section_path`／`position`／`title_field_key`／
  `is_public_readable`；改欄 payload 是 `extra="forbid"`，帶 `physical_name` 直接 422。
- 平台側**有**一支 ops 改名腳本（撞 ERP 表名專用），但那不是租戶自助管道，不要引導用戶去要。
- ⇒ 「改名」實際上是：**建新表 → 搬資料 → 改引用 → 驗收 → 刪舊表**，五步都要人盯。

### 11.3 計畫書：五塊，缺一塊不送用戶

**(1) 改名對照表**
`| 舊實體名 | 舊顯示名 | 新實體名 | 新顯示名 | 資料筆數 | 級別 | 被誰引用 |`
筆數與依賴從 `GET /tables/{key}/impact` 取（它同時回各欄非空值統計與 relation 依賴者）。

**(2) 引用掃描結果**（§11.4 的產出，逐 app 逐檔逐行）

**(3) 連鎖清單**：**新表 = 新 UUID**，其他表指向舊表的 `relation` 欄位**也必須重建**
（`target_table_id` 建立後不可變，PATCH 不收）。有依賴鏈時排出**由葉到根**的順序。
指向預設表的欄位不受影響（那是 `target_erp_key` 軟關聯）。

**(4) 配額檢查**：重建期間新舊表並存 → 表數暫時翻倍。免費檔 20 張／付費 200 張（§4），
先算會不會撞 409 `table_quota_exceeded`；會撞就**一次一張**走完整流程再做下一張。

**(5) 停機與回滾**：搬資料期間 app 不能寫——平台沒有交易、沒有雙寫機制，
中途寫進舊表的資料會遺失。講清楚要停用該 app 或約非上班時段；
**舊表在用戶驗收通過前不刪**，那就是唯一的回滾點。

> 已封裝：`aigo_data_center.py` 的 `audit_table_naming(tables)` 回不合規清單與分級，
> `format_naming_audit()` 直接接進 Phase 0 盤點報告。兩支都**只盤點、不動任何東西**。

### 11.4 引用掃描：實體名會出現在哪裡

自建表實體名散在 code 各處，**同租戶的每一個 app 都要掃**（自建表跨 app 共用，
只掃手上這一個必漏）。用 `aigo_auth.py app list` 看登錄表，沒登錄的 app 要主動問用戶還有沒有；
`aigo_sync.py` 拉下 VFS 後在本地 grep。

| 位置 | 樣態 |
|---|---|
| 前端 `src/api.ts` 呼叫端 | `queryTable('<表>'`／`insertRow('<表>'`／`updateRow`／`deleteRow`／`listTables()` 的結果過濾 |
| 前端查詢選項 | `filters: [{ field: '<欄>'`、`sort: '<欄>'`／`'-<欄>'` |
| Server Action | `ctx.db.query_table("<表>"`／`insert_row`／`update_row`／`delete_row` |
| TS 型別與解構 | `interface Row { <欄>: string }`、`const { <欄> } = row`、`row['<欄>']` |
| 圖片欄位 | storage key 內嵌**舊表實體名**——見 §11.5 第 4 步的紅字 |
| 排程／Webhook action | 參數預設值或 action 內寫死的表名 |
| 本機測試腳本／匯入腳本 | `aigo_data_center.py` 呼叫端的 `key=` 參數 |

> 已封裝：`aigo_review.py` 的 `scan_table_references(vfs_state, names)`（全字比對＋另收動態表名）
> 與 `format_table_reference_scan()`。VFS 用 `aigo_sync.get_remote_vfs()` 拉。
> **逐 app 跑一次**，把每支的結果都放進計畫書。

⚠️ **`grep` 要對整個 VFS 跑，不只 `src/`**。
⚠️ **`tbl_2` 這種名字不可用鬆散 pattern**（會誤中 `tbl_20`、也會漏掉字串拼接）——
用 `\btbl_2\b`，並人工看過每一個命中點；欄位名 `col_7` 同理。
⚠️ 掃到**動態組出來的表名**（`queryTable(tableName)`、`f"{prefix}_orders"`）就停下來標紅：
grep 保證漏，這些點要人工逐一確認。

### 11.5 執行順序（每張表，用戶同意後才動）

```
0. 用戶書面同意計畫（含停機時段）→ 請用戶停用該 app 或確認無人使用
1. 建新表：POST /tables，display_name = 新實體名（英文）
   → GET 驗收 physical_name 確實是預期的 biz_xxx，不是又拿到 tbl_N
2. PATCH 新表與各欄 display_name → 中文（兩步命名法）
3. 搬資料：舊表 query_records 全撈（★ `page_size` 預設只有 25，依回傳的 `total` 分頁撈完）→ 新表 insert_record 逐列
   ├─ id 會換新（DB 生 UUID）→ 保留 {舊 id → 新 id} 映射表
   ├─ 有 relation 指向本表的子表 → 等本表搬完，用映射改寫子表 FK
   └─ unique 欄位重複會 409 → 停下來給用戶看，不要吞掉繼續
4. 圖片欄位（image）★ 不可直接複製 key
   → key 內嵌舊表實體名，取 URL 端點會驗「key 裡的表是本租戶現存的表」；
     舊表一刪，所有沿用舊 key 的圖片立刻取不到（404/403）
   → 正解：舊表還在時逐張 GET /images/url 下載 → POST /tables/{新表}/images 重傳
     → 把回傳的新 key 寫進新表。這一步做不完就不要進第 7 步
5. 改引用：照 §11.4 的清單改 code → aigo_typecheck → compile → 部署
6. 驗收：新表筆數 = 舊表筆數；抽 5~10 列比對關鍵欄位；圖片抽驗能顯示；
   app 主要流程實際走一遍（讀＋寫）
7. 用戶確認驗收通過 → 刪舊表：GET /tables/{舊}/impact → DELETE ?confirm=<舊實體名>
   （需 system.admin；403 就停下來請用戶到 UI 刪，不要繞路）
```

⚠️ **第 7 步不可提前**。刪表不可逆，`impact` 顯示 0 依賴**不代表 app code 已經改乾淨**——
`impact` 只看得到 DB 層的 relation 依賴，看不到任何一行 `queryTable('tbl_3')`。

⚠️ **舊表刪掉之後才發現漏改**，唯一的路是照本節再建一次並重新輸入資料——
所以第 6 步的驗收要由**用戶**確認，不是 agent 自己說通過。
