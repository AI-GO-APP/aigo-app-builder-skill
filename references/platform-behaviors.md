# 平台實測行為補遺

> 本檔記錄**實際打過 API 才知道**的行為，用來補上規格文件沒寫、但一踩就卡住的地方。
> 每一條都標了驗證環境與日期；平台行為可能隨版本變動，發現不符請更新本檔。
>
> 驗證環境：`ai-go.app` 正式站、單一租戶、`ctx.env == "online"`、時區 **UTC+8**
> ｜日期 2026-07-31 ～ 08-01
>
> §10 的全域變數注入條件與 SDK 檔案來源另經平台原始碼交叉核對（2026-08-01）。

---

## 1. DB Proxy 查詢（★ 影響每一支 App）

### 1.1 單次查詢硬上限 500 筆，回傳是裸陣列

`POST /api/v1/proxy/{app_id}/{table}/query` 無論 `limit` 給多大，單次最多回 **500 筆**，
且**回傳沒有分頁信封**（沒有 `total`／`page`），就是一個 JSON 陣列。

要取完整資料必須自己用 `offset` 迴圈，並以「回傳數 < 500」作為結束條件。

### 1.2 offset 分頁必須指定唯一鍵排序，否則會重複又漏抓（★ 最容易靜默出錯）

伺服器預設 `ORDER BY created_at DESC NULLS LAST`。當多列的 `created_at` 相同時，
排序不穩定，`offset` 分頁會**跨頁重複某些列、同時漏掉另一些**。

實測：某表實際 1866 筆，不指定排序時只取回 **1860 筆**（重複 6、漏 6）。
加上 `order_by: [{ column: "id", direction: "asc" }]` 後精確取回 1866 筆。

```typescript
// 正確：一律帶唯一鍵排序
await queryAdvanced(table, {
  select, limit: 500, offset: page * 500,
  order_by: [{ column: "id", direction: "asc" }],
});
```

這個錯誤不會拋例外、不會有任何警告，只會讓統計數字悄悄少一截。

### 1.3 `custom_data`（JSONB）無法在伺服器端過濾

所有 JSONB path 語法都會被拒：

| filter 的 `column` 值 | 結果 |
|---|---|
| `custom_data->>'app_domain'` | 400 `不合法的欄位名稱` |
| `custom_data->>app_domain` | 400 `不合法的欄位名稱` |
| `custom_data.app_domain` | 400 `不合法的欄位名稱` |
| `custom_data`（op=eq） | 500 `invalid input syntax` |
| `custom_data`（op=is_not_null） | 200（整欄操作可用） |

**推論出的設計規則**：任何需要被**篩選、排序、分頁**的維度，一律放預設表**原生欄位**；
`custom_data` 只適合存「取回之後才用」的資料。`app_domain` 過濾只能在前端或 action 內做
（見 `custom-app-dev-guide.md` §18）——**且必須先照 §1.2 取完整資料再過濾**，
否則配上 §1.1 的 500 筆上限就會變成「只過濾了前 500 筆」。

### 1.4 `queryAdvanced` 的完整簽名

`src/db.ts` 有 `queryAdvanced`，但規格文件未說明。實際契約：

```typescript
queryAdvanced(table, {
  filters?:  { column, op, value }[],   // op: eq ne gt gte lt lte like ilike in is_null is_not_null
  order_by?: { column, direction }[],   // direction: asc | desc
  search?: string,
  search_columns?: string[],
  select?: string[],                    // 建議指定，可大幅減少傳輸量
  limit?: number,
  offset?: number,
})
```

### 1.5 兩個資料平面的過濾契約不同（★ 同名 `filters`、兩套鍵名，寫錯不一定報錯）

> 2026-09-02 實測（租戶 tli1956；proxy 面經 Custom App `/proxy/{app}/...` 與 Hosted 容器內
> `/open/proxy/...` 兩路確認）＋原始碼核對（`app_data_proxy._build_filter_clause`、
> `data_center/query_builder._build_filters`）。

| | 自建表 records 平面 | 預設表 proxy 平面 |
|---|---|---|
| 端點 | `GET /data-center/tables/{key}/records`（`ctx.db.query_table`／`queryTable`；Hosted 容器內加 `/open`） | `POST /proxy/{app}/{table}/query`（`queryAdvanced`；Hosted 容器內 `/open/proxy/{table}/query`） |
| 過濾位置 | query string `filters=[…]` | body `filters: […]` |
| 項目鍵名 | `field` / `op` / `value` | **`column`** / `op` / `value` |
| 合法運算子 | `eq` `contains` `gte` `lte`（依欄位型別再限縮：text 只有 eq/contains） | `eq` `ne` `gt` `gte` `lt` `lte` `like` `ilike` **`in`** `is_null` `is_not_null` |
| **`in`** | ❌ | ✅ |
| OR | ❌ | ❌ |
| 不合法運算子 | **422 列出合法集合** | 400「不支援的運算子」 |
| 錯鍵名 | 422「需要 field/op/value 三個鍵」 | 400「不合法的欄位名稱: 」（欄位名是空字串） |
| **不合法過濾形狀** | 422 | **200 回整表（靜默）**——`where`、`filter`、`conditions`、`{k: v}` 任何形狀都不生效 |
| 回傳 | `{items, total, page, page_size}` | 裸陣列、上限 500、無 total（§1.1） |
| 排序 | 單欄 `sort` | 多欄 `order_by`，必帶唯一鍵（§1.2） |

- **最危險的一格是 proxy 的靜默整表**：「找 contacted 階段」查成「整表第一列」不會有任何訊號，
  下游就在錯的列上寫資料。proxy 查詢寫完先用一個必然不存在的值打一次，回整表就是形狀錯
- `not_in`、`neq`、`!=`、`equals`、`contains`、`between` 在 proxy 面都是 400——`contains` 是 records 面的字
- records 面 `gte`／`lte` 對 `date`／`datetime` 的字串值（如 `"2020-01-01"`）：
  **2026-09-03 測試租戶實測 200**，已可用；若在其他租戶撞到 500 `DataError` 先懷疑部署落差

---

## 2. 寫入 TIMESTAMP 欄位：不可帶時區（★ 帶 `Z` 一律 500）

平台的 TIMESTAMP 欄位是 **offset-naive**。送出結尾帶 `Z` 的字串會讓 asyncpg 拋
`can't subtract offset-naive and offset-aware datetimes`，回 **500**。

| 送出的值 | 結果 |
|---|:-:|
| `2026-07-31T15:10:02.123Z`（`toISOString()` 原樣） | **500** |
| `2026-07-31T15:10:02.123` | 200 |
| `2026-07-31T15:10:02` | 200 |
| `2026-07-31 15:10:02`（空白取代 `T`） | **500** |
| `2026-07-31`（純日期） | 200 |

```typescript
// 寫入原生 TIMESTAMP 欄位時
const stamp = new Date().toISOString().slice(0, 19);   // 去掉 Z 與毫秒
```

`custom_data`（JSONB）內的時間字串不受此限，但統一寫法可避免混淆。

另有一個相關陷阱：`new Date(y, m, d).toISOString().slice(0, 10)` 在 UTC+8 會**退回前一天**
（本地午夜轉 UTC）。要輸出本地日期請自行組字串，不要走 `toISOString()`。

---

## 3. 平台 seed 表：只能宣告 read

部分表是**系統依其他操作衍生產生**的，宣告 create／update／delete 權限會被拒：

```json
HTTP 403
{"code": "seed_table_readonly",
 "table": "stock_quants",
 "message": "「stock_quants」為平台 seed／系統產生表，僅可宣告 read 權限"}
```

已確認屬此類的表（非完整清單）：

| 表 | 由什麼產生 |
|---|---|
| `stock_moves` | 確認領退料單／生產工單時產生的異動明細 |
| `stock_quants` | `stock_moves` 累計後的結存量 |
| `mrp_workorders` | 確認生產工單時依配方 routing 展開的工序 |

限制在**前後端一致**：Server Action 內 `ctx.db.insert("stock_moves", ...)` 同樣回 403。

**正確做法**：寫入可寫的**來源單據**（`stock_pickings`／`mrp_productions`／`sale_orders`），
再用 `ctx.erp.*` 觸發平台流程去產生衍生資料。見下一節。

---

## 4. `ctx` 的完整命名空間與 `ctx.erp`

### 4.1 `ctx` 實際有 20 個成員

規格文件列了 8 個，實測還有這些：

```
action_name  app_id   approval  crypto   csv    db      env    erp
http         knowledge  mcp     messaging  params  response  secrets
tenant_id    user     user_id   user_permissions  user_roles
```

`ctx.env` 是字串（正式站為 `"online"`）。`ctx.db`／`ctx.erp` 等是遠端代理物件，
**`dir()` 取不到方法名**，必須實際呼叫才知道方法存不存在。

### 4.2 `ctx.erp` 是方法級白名單

實測可用的六個方法（以不存在的 UUID 呼叫會回 `False`，代表已接到真實業務邏輯）：

| 方法 | 回傳 |
|---|---|
| `confirm_sale_order(id)` | `bool` |
| `confirm_purchase_order(id)` | `bool` |
| `post_move(id)` | `bool` |
| `confirm_payment(id)` | `bool` |
| `validate_picking(id)` | `bool` |
| `confirm_payroll_run(id)` | `dict`：`{ok, state, move_id}` |

不在白名單的方法名（例如自己臆測的 `create_picking`／`confirm_production`）會由閘道回
**403**（`/internal/ctx/invoke`），而不是 `AttributeError`。

> 判讀原則：**403 代表「該方法不在白名單」，不代表「該能力不存在」。**
> 其他未文件化的命名空間同理——`ctx.messaging.list_channels()` 可用，
> 但同一物件上的 `send_message`／`list_threads` 都回 403。

### 4.3 `validate_picking` 的實測行為（含冪等陷阱）

對一張 `state=assigned`、帶一筆 `stock_moves`（需求 3）的領退料單呼叫後：

| 觀察對象 | 前 | 後 |
|---|---|---|
| `stock_moves.state` | `assigned` | **`done`** |
| `stock_moves.quantity`（完成數） | `0` | **`3`** |
| `stock_quants` 筆數 | `0` | **`2`**（來源 −3、目的 +3） |
| `stock_pickings.date_done` | `null` | 已寫入 |
| `stock_pickings.state` | `assigned` | **仍是 `assigned`** |

**注意最後一列**：單據 `state` **不會**轉成 `done`，只寫 `date_done`。
真正反映完成的是 `stock_moves.state`。

因此**冪等判定必須看明細狀態，不能看單據 state**——否則守門永遠不會生效：

```python
# 錯：picking.state 不會變成 done，這個條件永遠是 False
if (picking["state"] or "").lower() in {"done", "cancel"}:
    return skip()

# 對：看明細
all_done = all((m["state"] or "").lower() in {"done", "cancel"} for m in moves)
if all_done:
    return skip()
```

平台本身對已完成的明細不會重複扣帳（重複呼叫後 `stock_quants` 未再變動），
但守門仍必要——避免無謂呼叫，也避免回報「已扣帳」這種誤導性訊息。

**沒有 `stock_moves` 明細的單據，呼叫 validate 不會產生任何庫存異動**——不報錯、
也不回 `False`，就是什麼都沒發生。而 `stock_moves` 是 seed 表、App 寫不了（§3），
所以由 Custom App 自行建立的 `stock_pickings` 必須先在平台 ERP 補上明細才可扣帳。
**UI 應該在明細為空時就把按鈕停用**，不要讓使用者按一個必定無效的按鈕：

```typescript
const moves = await query("stock_moves", { picking_id: picking.id });
const canValidate = moves.length > 0 &&
  !moves.every((m) => ["done", "cancel"].includes((m.state || "").toLowerCase()));
// moves.length === 0 → 提示「請先於 ERP 補上明細」，而不是讓他按下去
```

---

## 5. Builder API 的兩個必填／衝突

### 5.1 刪除 VFS 檔案需帶 `expected_version`

`DELETE /api/v1/builder/apps/{id}/source/files` 的 body 是
`{"paths": [...], "expected_version": N}`。少了樂觀鎖會回：

```
400 {"detail": "缺少 expected_version（樂觀鎖必填）"}
```

`scripts/aigo_sync.py` 目前只封裝了 PATCH，沒有封裝刪除。

### 5.2 發布若會移除既有 action，會回 409

```json
HTTP 409
{"code": "ACTION_REMOVAL",
 "message": "本次發布將移除既有 action，請確認後再發布",
 "removed_actions": ["actions/probe_erp.py"]}
```

這是保護機制（避免綁在該 action 上的 webhook／排程被靜默斷開）。
目前**未找到可在 API 層帶的確認參數**（已試 `confirm`／`force`／
`confirm_action_removal`／`allow_action_removal` 等 body 與 query 形式皆無效）。

暫時的解法是把該 action 檔案放回去再發布；要真的移除 action 請引導用戶到 Builder 後台操作。

---

## 6. 租戶空間網址與 Internal App 執行期網址

### 6.1 全平台網址規則：`https://[tenant].ai-go.app/*`

> 來源：核對平台原始碼（`backend/app/core/workspace_host.py`、`api/auth.py`、
> `frontend/src/middleware.ts`），2026-08-08。

登入頁與**所有 API** 都在租戶子網域下。租戶是由 **Host header** 解出來的——
`{tenant}.ai-go.app/api/*` 同源代理到後端並保留 Host，所以「網址說哪個工作區，
就只在那個工作區找帳號」。

| 寫法 | 結果 |
|---|---|
| `https://urfit.ai-go.app/login`、`/api/v1/*` | **正確** |
| `https://ai-go.app/login` | 主站 apex，已收斂成 **workspace finder**（找工作區的頁面），不是登入頁 |
| `https://ai-go.app/api/v1/auth/login` | **401「帳號或密碼錯誤」**（實測，正確帳密；apex 推不出租戶 → fail-closed） |
| `https://xxx.apps.ai-go.app/*` | Custom App 沙箱域，不是 API host |

實測對照（2026-08-08，同一組正確帳密）：

```
POST https://ai-go.app/api/v1/auth/login       → 401 {"detail":"帳號或密碼錯誤"}
POST https://urfit.ai-go.app/api/v1/auth/login → 200 {"access_token": ...}
```

⚠️ **401 有兩種成因且平台刻意讓兩者無法分辨**（反帳號列舉）：「密碼錯」與
「這個 email 不在這個租戶／根本沒有租戶範圍」回**完全相同**的 `401 帳號或密碼錯誤`
——狀態碼、detail、甚至是否跑滿一次 bcrypt 都一樣。所以打錯租戶的症狀會**完美偽裝成
憑證問題**，往密碼方向查一定查不到底。查 401 時**先確認 base_url 的租戶前綴**。

本 Skill 的 `aigo_auth.resolve_base_url()` 因此**直接擋掉 apex，且不留任何預設值**。

### 6.2 Internal App 的執行期網址

```
https://{tenant}.ai-go.app/runtime/{slug}
```

| 寫法 | 結果 |
|---|---|
| `{tenant}.ai-go.app/runtime/{slug}` | **正確** |
| `{tenant}.ai-go.app/{slug}` | 404 |
| `{subdomain}.apps.ai-go.app` | 導向獨立登入頁（供 external app 用） |

另外兩點對自動化測試有影響：

- App 渲染在 **Shadow DOM** 內，`document.body.innerText` 讀不到內容，
  需遞迴找 `shadowRoot` 才能取得畫面文字。
- `src/db.json` **恆為 `{}`**，即使 Data Reference 都註冊成功——它是執行期注入檔、
  不存在 VFS。要確認引用狀態請查 `GET /api/v1/refs/apps/{app_id}`，不要看 `db.json`。

---

## 7. Server Action 必須發布後才可呼叫

同步（PATCH VFS）後尚未 publish 時呼叫，會得到：

```
404 {"detail": "Action 'xxx' 不存在（runtime=online）"}
```

開發循環是 **sync → compile → publish → 才能 run action**，不能只 sync 就測。

---

## 8. 原生 TIMESTAMP／DATE 是 offset-naive 的 UTC（★ 前端解析會差 8 小時）

平台混用兩種時間欄位，回傳格式不同，前端不可一視同仁：

| 欄位 | 型別 | 回傳樣式 | JS `new Date(s)` 的解讀 |
|---|---|---|---|
| `created_at`／`updated_at` | timestamptz | `2026-08-01T04:37:02.221146+00:00` | 正確（UTC） |
| `check_in`／`date_from`／`date_done`／`work_date` | TIMESTAMP／DATE | `2026-08-01T04:37:03` | **當成本地時間** |

naive 欄位存的內容是 UTC，但 ECMAScript 規定「不帶時區的 date-time 字串視為本地時間」，
於是在 UTC+8 直接差 8 小時。實測：相隔 6 分鐘的上下班打卡被算成 **8.1 小時**工時。

解析時必須補 `Z`：

```ts
const NAIVE_TS = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$/;

export function toTime(d: unknown): number | null {
  if (d === null || d === undefined || d === "") return null;
  if (typeof d === "number") return Number.isFinite(d) ? d : null;
  let s = String(d);
  if (NAIVE_TS.test(s)) s = s.length <= 10 ? `${s}T00:00:00Z` : `${s.replace(" ", "T")}Z`;
  const t = new Date(s).getTime();
  return Number.isFinite(t) ? t : null;
}
```

顯示時同樣不可直接切字串（`ts.replace("T"," ").slice(0,16)` 會顯示 UTC）；
推導日期也不可用 `new Date().toISOString().slice(0,10)`，那是 UTC 日期，
在 UTC+8 的凌晨 0–8 點會退回前一天，拿去比對 DATE 欄位會整批對不上。

> ⚠️ **`toTime()` 對 DATE-only 值補的是 `T00:00:00Z`，只在非負偏移時區（UTC+0 以東）安全。**
> 本檔驗證環境是 UTC+8：`2026-08-01` → UTC 午夜 → 本地 08:00，仍落在 8/1。
> 但在負偏移時區（如 UTC−5）同一個值會被顯示成 7/31，**日期整批退一天**。
> **DATE-only 欄位（`work_date`、`date_from` 這類純日期）建議一律以字串比對與顯示**
> （`row.work_date === "2026-08-01"`），不要轉成時間戳；需要排序時字串排序即可。
> `toTime()` 留給真正帶時間的 TIMESTAMP 欄位用。

---

## 9. NOT NULL 欄位只有在真的送出時才會浮現

`GET /api/v1/refs/tables/{table}/columns` 不回傳 nullable 資訊，型別也看不出來，
因此以下欄位在實測前都是隱形的。它們都會回 500（`NotNullViolationError`）：

| 表 | 必填欄位 | 備註 |
|---|---|---|
| `hr_attendances` | `check_in` | 不能只補一列 `check_out`，下班打卡要 update 既有列 |
| `hr_leaves` | `holiday_status_id` | 沒有假別就送不出請假單 |
| `hr_leave_allocations` | `date_from` | |
| `stock_pickings` | `picking_type_id` | 需先查 `stock_picking_types` |
| `mrp_productions` | `product_id` | 要的是 `product_products`（變體），不是 `product_templates` |
| `account_moves` | `date` | 與 `invoice_date` 是兩個不同欄位 |
| `import_jobs` | `user_id` | 見第 10 節 |
| `msg_threads` | `contact_type` | 平台既有列用 `system_customer_service` |

另外 `hr_shifts.start_time`／`end_time` 是 TIME 型別，但送純時間字串
（`"08:00"`／`"08:00:00"`／`"08:00:00+08:00"`）一律 500
（asyncpg：`'str' object has no attribute 'hour'`），必須送完整 ISO datetime，例如
`1970-01-01T08:00:00`。

---

## 10. 取得登入者：身分與權限是兩條管道，`user.ts` 不一定在 VFS 裡

「登入者是誰」與「登入者能做什麼」由**兩套獨立機制**提供，容易混為一談：

| 要什麼 | 管道 | 來源 |
|---|---|---|
| **身分**（user id / email / tenant） | 解 `__APP_TOKEN__` 的 JWT payload | 一律可用 |
| **權限**（roles / permissions） | `__USER_ROLES__`／`__USER_PERMISSIONS__` 全域，由 `src/user.ts` SDK 封裝 | **僅 internal 且非匿名渲染**才注入 |

`custom-app-dev-guide.md` §6 講的是**權限**那一條，本節講的是**身分**那一條，兩者不衝突。

### 10.1 執行期全域變數的實際注入條件

| 全域 | internal | external | 匿名渲染 |
|---|:-:|:-:|:-:|
| `__API_BASE__`、`__APP_ID__`、`__APP_TOKEN__`、`__APP_SLUG__` | ✅ | ✅ | ✅ |
| `__CUSTOM_APP_ROOT__`（Shadow DOM 掛載點） | ✅ | ✅ | ✅ |
| `__USER_ROLES__`、`__USER_PERMISSIONS__` | ✅ | ✗ | ✗ |
| `__IS_EXTERNAL__`、`__AUTH_TYPE__` | ✗ | ✅ | — |
| `__IS_AUTHENTICATED__`、`__PUB_API_BASE__` | ✗ | ✗ | ✅ |

三點要注意：

- **`__CURRENT_USER__` 在任何模式都不存在**，不是「internal 沒有、external 有」。
  （1.6.0 的本節誤記為 external 有注入，已更正。）
- **`__IS_EXTERNAL__` 在 internal 是 `undefined`**，不是 `false`——平台 SDK 一律寫
  `!!(window as any).__IS_EXTERNAL__`，你自己判斷時也要這樣寫。
- **`__IS_AUTHENTICATED__` 只在匿名渲染注入，而且恆為 `false`**。
  拿它當「是否已登入」判斷，在 internal／external 都會讀到 `undefined`——
  這個變數只能用來偵測「是不是匿名模式」。

### 10.2 `src/user.ts` 不是每個 App 都有（★ 直接 import 會編譯失敗）

SDK 檔案有兩個來源，涵蓋範圍不同：

| 檔案 | 建立 App 時就有 | 到 Builder 後台開「開發」分頁才補上 |
|---|:-:|:-:|
| `src/api.ts`、`src/action.ts` | ✅ | 沿用 |
| `src/db.ts`（有引用表時）、`src/approval.ts`、`src/user.ts` | ✗ | ✅ |

也就是說**純走 API 建立、從未在 Builder 後台開過的 App，VFS 裡不會有 `src/user.ts`**——
本 skill 的開發流程正是這一種。`import { hasPermission } from "../user"` 會直接編譯失敗。

補救有兩條，擇一：

1. 請用戶到 Builder 後台把該 App 開一次「開發」分頁，平台會自動補齊 SDK 檔案；
2. 不依賴 SDK 檔，直接讀注入的全域（行為與 `user.ts` 等價）：

```ts
function injected(key: string): string[] {
  try {
    const raw = (window as any)[key];
    const arr = typeof raw === "string" ? JSON.parse(raw) : raw;
    return Array.isArray(arr) ? arr.filter((x) => typeof x === "string") : [];
  } catch { return []; }
}

const PERMS = injected("__USER_PERMISSIONS__");   // external／匿名恆為 []
export const isAdmin = () => PERMS.includes("system.admin");
export const hasPermission = (p: string) => isAdmin() || PERMS.includes(p);
```

> 不論走哪一條，**都不要自己打 `/api/v1/auth/me`**（本 skill 禁止），
> 也不要在 App 內另建角色表——見 `SKILL.md` 核心規則 23。

### 10.3 從 `__APP_TOKEN__` 取身分

`__APP_TOKEN__` 是 JWT，payload 內含 `sub`（平台 user id）、`email`、`tenant_id`：

```ts
export function currentIdentity(): { userId: string; email: string; tenantId: string } | null {
  try {
    const seg = ((window as any).__APP_TOKEN__ || "").split(".")[1];
    if (!seg) return null;
    const b = seg.replace(/-/g, "+").replace(/_/g, "/");
    const bin = atob(b + "===".slice((b.length + 3) % 4));
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    const p = JSON.parse(new TextDecoder("utf-8").decode(bytes));
    return p?.sub ? { userId: p.sub, email: p.email || "", tenantId: p.tenant_id || "" } : null;
  } catch { return null; }
}
```

這不只是顯示用途——`import_jobs.user_id` 是 NOT NULL，取不到就無法新增（見 §9）。

> ⚠️ **解出來的 `sub` 只能當 UX 預設值，不能當授權依據。**
> token 存在 `window` 上，前端可以竄改後再送出。凡是要寫進**身分欄位**的值
> （`import_jobs.user_id`、建立者、簽核申請人…），一律在 Server Action 內
> 用 `ctx.user_id` 覆蓋前端傳來的值，不要相信 params。
> 這與「前端隱藏只是 UX 不是安全邊界」（`custom-app-dev-guide.md` §6、
> `SKILL.md` 核心規則 23）是同一條原則。
>
> ```python
> def execute(ctx):
>     payload = dict(ctx.params.get("job") or {})
>     payload["user_id"] = ctx.user_id          # ★ 一律覆蓋，不用前端送的
>     ctx.response.json(ctx.db.insert("import_jobs", payload))
> ```

## 11. 空渲染偵測：掛載後 8 秒內必須渲染出東西（2026-08 起）

平台會監看 Shadow DOM root：bundle 掛載後 **8 秒內** root 完全沒有任何元素或非空白文字，
就自動回報一則 runtime error，並對使用者顯示 banner
「**App 已載入但沒有顯示任何內容——程式很可能在啟動時就失敗了。請聯絡此 App 的擁有者。**」
（原始碼 `frontend/src/lib/emptyMountWatch.ts`）。

- 判定是聯集：`root.firstElementChild` 存在**或** `textContent.trim()` 非空即算有內容；
  寬限期內**曾經**出現過內容就不回報；逾時當下會重新量一次再決定
- 本意是抓「啟動即拋例外」的 app（例外發生在 app 自己的執行環境時，
  平台的 window 層攔截不到，以前只會一片空白）
- **反面效應**：app 若「先跑長 API、成功後才第一次渲染」，超過 8 秒就會被誤報一次
- **對策（開發規則）**：啟動時立刻渲染 skeleton／loading 佔位，資料到了再替換。
  這同時也是正確的 UX——不要讓使用者對著空白等

## 12. App API 權限閘（通用權限 gate）：現況 audit，enforce 前要做的準備

2026-08 起 internal app bundle 注入的 `__APP_TOKEN__` 已改為 **app 憑證**
（短效，claims = 該 app 宣告的 API 範圍 ∩ 使用者權限），不再是使用者本人的完整平台 JWT。
閘門本體目前是 **audit 模式**：判定照跑、記錄 would-deny，但**一律放行**——
所以現在打範圍外的 API 還不會壞，**切 enforce 後會 403**。

**現在就生效的一條**：自建表實體名的保留名母體已擴大到**平台地板表名**
（`users`／`tenants`／`audit_logs`／`api_keys`／`countries` 等 76 張）。
撞名在**建表當下就回 409**（訊息「與平台保留表名衝突」；ERP 撞名與 SQL 保留字
各有自己的訊息）。只擋新建、不回溯既有表。撞到地板名**沒有事後補救管道**，
建表規格階段就要避開（→ `data-center.md` §1）。

> ⚠️ **2026-09-01 實測：`GET /api/v1/apps/{app_id}/api-grants` 在 prod 回 404**
> ——授權管理後端已 merge 尚未部署，本節的「準備動作」目前做不了，先記著等它上線。
> 保留表名 409 也尚未生效（實測仍可建成，見 `data-center.md` §1）。

**enforce 前的準備（寫 code 時就做，不要等）**：

1. Builder（`/builder/{app_id}`）的「**API 權限**」分頁列出此 app 的 API 群授權。
   app 的宣告範圍是從 `actions/*.py` **靜態推導**的——只涵蓋 server-side `ctx` 面，
   **不含前端（瀏覽器 SDK）直接呼叫的 API**。只在前端打的 API 群要在面板手動開啟，
   否則 enforce 後前端呼叫全面 403
2. 面板的寫入權限是 `builder.manage_access`（敏感群另需 `system.admin`）；
   無權限時整面唯讀
3. 資料中心面 enforce 後：未授權的表回 404 並落入「待允許清單」，
   管理員可一鍵允許——但地板表刻意不收錄
4. 陷阱：面板「撤回全部」＝刪列＝回到 baseline 全開；但 baseline 以外若還有殘留列，
   effective 會塌成**全部停用**。儲存是逐群多次呼叫、非原子，中途失敗會停在部分套用

> enforce 切換時程未定（manifest 明寫「MODE 一律維持 audit」直到既有 app 的
> 前端呼叫面補宣告完畢）。本節的意義是：**新開發的 app 從現在起就把 API 權限面板
> 對齊實際呼叫面**，enforce 落地時才不用回頭救。
