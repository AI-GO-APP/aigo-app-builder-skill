# 事件觸發：Webhook 與 App 排程

> 術語定義見根目錄 `CONTEXT.md`。

這兩者是**同一套投遞機制的兩個事件源**——同一個 dispatcher、同一條佇列語義、
同一套可靠性保證。所以合寫一份。

---

## 0. 先讀這條：at-least-once ⇒ action 必須冪等

平台保證事件**至少執行一次**，代價是**可能重複執行**。以下情況都會產生重複：

- dispatcher 硬死（OOM／節點故障）後訊息重投
- invoke 超時（實際上 runner 可能仍跑完了）
- 運維人員從 DLQ redrive 補跑
- 滾動更新的重疊窗口

**因此每個 webhook / cron action 都必須寫成冪等。** 這不是最佳實務建議，是硬需求——
平台的設計取捨是「遺失不可接受，重複由 action 吸收」。

### 怎麼做

優先用**事件本身的業務 id** 去重（LINE 的 `webhookEventId`、Stripe 的 `event.id`、
訂單編號…）；沒有業務 id 時用平台給的 `ctx.params["delivery_id"]`。

```python
def execute(ctx):
    event_id = ctx.params.get("delivery_id")   # 或 payload 裡的業務事件 id

    # 用自建表當去重紀錄
    seen = ctx.db.query_table("webhook_dedup", {
        "filters": [{"field": "event_id", "op": "eq", "value": event_id}],
        "page_size": 1,
    })
    if seen["total"] > 0:
        ctx.response.json({"skipped": "duplicate"})
        return

    ctx.db.insert_row("webhook_dedup", {"event_id": event_id})
    # …真正的處理…
```

寫入類的副作用（建單、扣款、發信）沒有去重就是**重複扣款等級的 bug**。
純讀取或天然冪等的操作（設定某欄位為固定值）可以不做。

---

## 1. Webhook

### 1.1 宣告：manifest 加旗標

在 `actions/manifest.json` 把 action 的 meta 加上 `"webhook": true`：

```json
{
  "receive_webhook": { "description": "預設 webhook", "timeout_ms": 30000, "is_enabled": true },
  "line_events":     { "description": "LINE 事件", "timeout_ms": 30000, "is_enabled": true, "webhook": true },
  "stripe_events":   { "description": "Stripe 回呼", "timeout_ms": 30000, "is_enabled": true, "webhook": true }
}
```

每個標記的 action 各得一條獨立對外端點。`receive_webhook` 是歷史預設端點，**無需宣告**。

**未標記 `webhook` 的 action 絕對無法從公開端點觸發**——這個 opt-in 旗標是唯一的授權界線。

### 1.2 ★ 宣告只在發布後生效

線上端點以**最近一次發布的快照**為準，草稿編輯不影響線上。

**新增／刪除／停用 webhook 端點，都必須重新 publish 才會生效。**
改完 manifest 沒 republish 就去測，一定 404。

### 1.3 URL 推導

| 情況 | URL |
|---|---|
| app 有 `subdomain` | `https://{subdomain}.apps.{domain}/webhook/{hook_name}` |
| 沒有 subdomain（相容端點，永不下線） | `https://ai-go.app/api/v1/custom-apps/webhook/{slug}/{hook_name}` |

- 省略 `/{hook_name}` 即預設端點（→ `receive_webhook`）。
- `hook_name` 正規：`^[A-Za-z0-9_-]{1,64}$`。
- **不要自己硬拼**——Builder 後台的服務 tab 會直接列出對外 URL 與複製按鈕，優先叫用戶從那裡複製。

⚠️ **同一個事件源不可同時登記兩條 URL。** 新舊 URL 觸發同一個 action，
第三方對兩條各送一次 = **執行兩次**（兩個獨立請求 = 兩個 dedup key）。切換時換掉，不要並存。

### 1.4 action 收到的 `ctx.params`

| 欄位 | 內容 |
|---|---|
| `webhook_event` | 固定 `"incoming"` |
| `body` | **原始 request body 字串**——要自己 `json.loads()` |
| `headers` | request headers dict |
| `hook_name` | 解析後的 hook 名（預設端點為 `"receive_webhook"`） |
| `query_params` | query string dict |
| `method` / `path` | HTTP method 與請求路徑 |
| `delivery_id` | 每次請求唯一，可作冪等去重 key |
| `body_base64` | **僅當 body 非 UTF-8 時附上**（此時 `body` 是替代字元 fallback 解碼的結果） |

```python
import json

def execute(ctx):
    payload = json.loads(ctx.params.get("body") or "{}")   # body 是字串！
    headers = ctx.params.get("headers", {})
    ...
```

### 1.5 ★ `headers` 不可信

Webhook gateway 是**無認證的公開入口**，任何人都能對你的端點 POST 任意 headers。

**不可以**拿 header 當授權依據（`if headers.get("X-Api-Key") == ...` 是假保護）。
事件真實性的唯一依據是**簽章驗證**：

```python
import hashlib, hmac, base64, json

def execute(ctx):
    body = ctx.params.get("body") or ""
    sig = ctx.params.get("headers", {}).get("x-line-signature", "")
    secret = ctx.secrets.get("LINE_CHANNEL_SECRET")

    expected = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()

    if not hmac.compare_digest(sig, expected):
        ctx.response.json({"error": "invalid signature"})
        return
    ...
```

> ⚠️ **這個回應不會回給事件來源。** gateway 收下事件後立刻回 `accepted`，action 是
> **非同步**跑的——LINE／Stripe 永遠只看到 accepted，看不到你的錯誤訊息。
> `ctx.response.json()` 的內容只進執行紀錄。所以驗簽失敗要靠**監控執行紀錄**發現，
> 不能指望 sender 因為你回錯誤而重送。

驗簽必須用**原始 body 字串**（`ctx.params["body"]`），不能用 `json.loads` 再 `dumps` 的結果——
重新序列化會改變位元組，簽章必不符。

### 1.6 ★ Webhook action 的執行上限約 90 秒

**不要把 cron 的 280 秒套到 webhook 上。** 兩者走同一個 dispatcher 但常數不同：

| | webhook | cron |
|---|---|---|
| invoke HTTP 上限 | **90 秒** | 300 秒 |
| 建議 action 執行時間 | **< 90 秒** | < 280 秒 |

超過就是必然逾時 → 事件重投 → 重複執行。長工作要在 action 裡快速收下、
寫進自建表，再交給排程慢慢處理。

### 1.7 Meta（FB／IG／WhatsApp）訂閱驗證

平台自動處理 GET 的 `hub.mode=subscribe` 驗證，你不需要寫 code。
只需在 App secrets 設定 verify token：

- 具名端點：`META_VERIFY_TOKEN_{HOOK}`（HOOK = hook_name 轉大寫、`-` 換 `_`）
- 未設定則 fallback 全域 `META_VERIFY_TOKEN`

---

## 2. App 排程（App Cron）

### 2.1 排程不在 VFS 裡

排程是後台的一列 DB 資料，與 app 的發布生命週期**脫鉤**。
你不會在 code 裡「宣告」排程——你寫的只有被排程觸發的那個 action。

管理位置：`/dashboard/settings/app-crons`，或 REST `/api/v1/app-crons`。

### 2.2 Agent 的建立流程

```
1. Phase 1.5 計畫中列出「排程需求表」：
   | 排程名稱 | 觸發哪個 action | 頻率 | 時區 | 固定 params |
   → 交用戶確認（含 tier 限制是否放得下）

2. POST /api/v1/app-crons   （權限 settings.write）
   ├─ 201 → 完成
   └─ 403 → 輸出可照抄的排程規格，引導用戶到
            /dashboard/settings/app-crons 自建
```

| 操作 | 端點 |
|---|---|
| 列表／建立 | `GET` / `POST /api/v1/app-crons` |
| 讀／改／刪 | `GET` / `PATCH` / `DELETE /api/v1/app-crons/{cron_id}` |
| 啟停 | **`PATCH`** `/api/v1/app-crons/{cron_id}/toggle` |
| 立即執行一次 | `POST /api/v1/app-crons/{cron_id}/run-now` |

⚠️ **暫停中的排程 run-now 回 400**——要先 `PATCH .../toggle` 重啟才能手動觸發。

讀取需 `settings.read`，寫入需 `settings.write`。

### 建立的 payload 形狀（★ 欄位名不要猜）

```json
{
  "app_id": "<app UUID>",
  "action_name": "reconcile",
  "name": "對帳排程",
  "schedule_kind": "every_n_minutes",
  "schedule_fields": { "n": 10 },
  "timezone": "Asia/Taipei",
  "params": { "batch_size": 200 },
  "active": true
}
```

- 啟停欄位叫 **`active`**（不是 `is_enabled`／`enabled`）。
- `params` 序列化上限 **16 KiB**。
- **只有已發布（`published`）的 app 可以建排程**——草稿 app 回 400。
- PATCH 是 diff 語義：**只送真正改動的欄位**。一旦帶到
  `schedule_kind` / `schedule_fields` / `timezone`，`nextcall` 就會被歸零重算
  （進入「計算中」最多 5 分鐘）——只改名字卻全量送出，會白白讓排程停擺一個週期。

### 2.3 排程表達式

只收**結構化欄位**，不支援自由 cron expression。

| `schedule_kind` | `schedule_fields` | 語義 |
|---|---|---|
| `every_n_minutes` | `{"n": 30}` | 每 N 分鐘（錨定 UTC epoch，時區不參與） |
| `hourly` | `{"minute": 15}` | 每小時的第 N 分 |
| `daily` | `{"hh": 9, "mm": 0}` | 每天 |
| `weekly` | `{"weekday": 1, "hh": 9, "mm": 0}` | 每週（**0=週日 … 6=週六**） |
| `monthly` | `{"day": 31, "hh": 9, "mm": 0}` | 每月（小月**夾到當月最後一天**，不跳過） |

`timezone`：IANA 時區字串，預設 `Asia/Taipei`。

### 2.4 ★ Tier 限制：規劃時就要算

| | 免費檔 | 付費檔 |
|---|---|---|
| **最小間隔** | **60 分鐘** | **5 分鐘** |
| 每 app 條數 | 2 | 不限 |
| 每租戶條數 | 10 | 50 |

- **超限直接回 400，不會靜默截斷。** 規劃「每 10 分鐘對帳」前先確認租戶是付費檔，
  否則要改成每小時或請用戶升級。
- 5 分鐘是引擎解析度，付費檔也不可能更密。
- **降檔時違規排程會自動暫停**（reason=`tier`）並通知；**升檔後不會自動恢復**，要人工重啟。

### 2.5 action 收到的 `ctx.params`

| 欄位 | 內容 |
|---|---|
| `cron_event` | 固定 `"scheduled"`（手動 run-now 也是這個值，刻意不分岔） |
| `cron_id` / `cron_name` | 排程識別與名稱 |
| `scheduled_at` | 這一發對應的 slot 時間（ISO，UTC） |
| `params` | 排程設定的固定參數 |

### 2.6 ★ 執行上限 280 秒

- action 的 `timeout_ms` **超過 280000 會收到警告**，超過 300000 **必定失敗**。
- 長任務要自己切批次：每次處理 N 筆、把進度存回自建表，靠下一次觸發接續。
- 不支援「跑很久的任務」是設計取捨，不是缺陷。

### 2.7 ★ 重疊會被跳過（Forbid），不排隊

上一發還在跑、下一個 slot 到了 → 該次直接記 `skipped`，**不會排隊等待**。

高頻 + 長任務的組合下 **`skipped` 是預期常態，不是錯誤**（UI 用琥珀色而非紅色標示）。
如果你看到大量 skipped，代表間隔設得比實際執行時間短——調間隔或縮短任務。

### 2.8 ★ 自動暫停，且不會自動恢復

| 觸發 | 門檻 | 暫停原因 |
|---|---|---|
| app 已下架／action 消失或停用 | 連續 **2** 次 | `consecutive_403` |
| action 執行報錯（runner 回 error） | 連續 **10** 次 | `consecutive_errors` |
| 降檔後違反 tier 限制 | 立即 | `tier` |
| 管理員手動 | 立即 | `manual` |

- 成功一次即歸零兩個計數。
- 傳輸層失敗（網路／基礎設施）**不計帳**，不會冤枉暫停。
- **一律需要人工重啟。**

⚠️ **這對開發流程的直接影響**：unpublish 一個帶排程的 app，或改名／刪掉被排程的 action，
會在兩次觸發後把排程停掉。**每次 republish 之後，要提醒用戶去 `/dashboard/settings/app-crons`
檢查排程狀態並視需要重啟。**

### 2.9 漏跑語義：coalesce，不補跑

平台停擺恢復後，每條排程**至多補發一次**，`nextcall` 直接推進到未來的下一個 slot。
**絕不逐 slot backfill。** 需要「補齊歷史遺漏」的業務邏輯要自己在 action 裡實作
（例如查最後成功處理到哪筆，補處理其後全部）。

新建立的排程 `nextcall` 會短暫是空的（顯示「計算中」），最多 5 分鐘後由平台時鐘填上——
**這是正常狀態，不要重複建立排程。**

---

## 3. 失效排查

| 症狀 | 檢查 |
|---|---|
| webhook 端點 404 | manifest 有 `"webhook": true`？**publish 了嗎？** hook 名合法？ |
| webhook 收到但沒反應 | 執行紀錄看 action 是否報錯——**app 層錯誤不會重投也不會告警** |
| 同一事件被處理兩次 | 第三方登記了新舊兩條 URL？或 action 沒做冪等 |
| 驗簽一直失敗 | 是否用了重新序列化的 body？必須用 `ctx.params["body"]` 原字串 |
| 排程建了不跑 | `nextcall` 還在「計算中」（≤5 分鐘）；或 app 未發布；或排程已被自動暫停 |
| 排程大量 skipped | 執行時間 > 間隔，調間隔或縮短任務 |
| 排程突然停了 | 看 `paused_reason`：403×2（app／action 沒了）、error×10、tier 降檔 |
| 建排程回 400 | 撞 tier 限制（免費檔最小 60 分鐘） |
| 排程 action 逾時 | 超過 280 秒，要切批次 |
| webhook action 逾時 | 超過 **90 秒**（不是 280），把長工作交給排程 |
| run-now 回 400 | 排程在暫停中，要先 toggle 重啟 |
