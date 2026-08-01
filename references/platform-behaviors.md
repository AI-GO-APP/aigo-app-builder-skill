# 平台實測行為補遺

> 本檔記錄**實際打過 API 才知道**的行為，用來補上規格文件沒寫、但一踩就卡住的地方。
> 每一條都標了驗證環境與日期；平台行為可能隨版本變動，發現不符請更新本檔。
>
> 驗證環境：`ai-go.app` 正式站、單一租戶、`ctx.env == "online"`｜日期 2026-07-31 ～ 08-01

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

**推論出的設計規則**：任何需要被**篩選、排序、分頁**的維度，一律放 SaaS 表**原生欄位**；
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

## 6. Internal App 的執行期網址

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

## 10. 取得登入者：internal runtime 不注入 `__CURRENT_USER__`

實測 internal App 的執行期只有這些全域：
`__API_BASE__`、`__APP_ID__`、`__APP_TOKEN__`、`__APP_SLUG__`、`__CUSTOM_APP_ROOT__`。
**沒有** `__CURRENT_USER__`，範本也沒有附 `src/user.ts`。
（external App 的執行期**有**注入 `__CURRENT_USER__`——兩者行為不同。）

`__APP_TOKEN__` 是 JWT，payload 內含 `sub`（平台 user id）、`email`、`tenant_id`，
在前端解自己的 token 即可，不需呼叫本 skill 禁止的 `/api/v1/auth/me`：

```ts
export function currentIdentity(): { userId: string; email: string; tenantId: string } | null {
  try {
    const seg = ((window as any).__APP_TOKEN__ || "").split(".")[1];
    if (!seg) return null;
    const b = seg.replace(/-/g, "+").replace(/_/g, "/");
    const p = JSON.parse(decodeURIComponent(escape(atob(b + "===".slice((b.length + 3) % 4)))));
    return p?.sub ? { userId: p.sub, email: p.email || "", tenantId: p.tenant_id || "" } : null;
  } catch { return null; }
}
```

這不只是顯示用途——`import_jobs.user_id` 是 NOT NULL，取不到就無法新增。

---

## 11. `validate_picking` 之後 `state` 不會變，只有 `date_done` 會寫

實測 `ctx.erp.validate_picking` 成功後：

- `stock_moves.state`：`assigned` → `done`，`quantity` 由 0 變為實際數量
- `stock_quants`：產生實際加減（來源 −N、目的 +N）
- `stock_pickings.date_done`：寫入完成時間
- `stock_pickings.state`：**維持 `assigned` 不變**

因此判斷「這張單是否已扣帳」只能看 `date_done` 或明細的 move 狀態，不能看 picking 的 state。
冪等保護也要建立在 move 狀態上。

另外，**沒有 `stock_moves` 的單據呼叫 validate 一定不會產生任何庫存異動**，
而 `stock_moves` 是 seed 表、App 無法寫入——也就是說由 Custom App 自行建立的
`stock_pickings` 需要在平台 ERP 補上明細後才可扣帳。UI 應該直接擋掉，
不要讓使用者按一個必定失敗的按鈕。
