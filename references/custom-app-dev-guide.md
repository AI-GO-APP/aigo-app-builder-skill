# AI GO Custom App 開發者指南（精簡版）

> 完整文件：https://www.ai-go.app/zh-TW/docs/custom-app-dev

## 1. 什麼是 Custom App

- VFS（Virtual File System）：以 JSON `{"路徑": "內容"}` 儲存原始碼
- esbuild 編譯器：React TSX → JS bundle
- Runtime 沙箱：在 Shadow DOM 隔離環境中執行
- 三種模式（access_mode）：`internal`（組織內部）/ `external`（對外客戶）/ `self_built`（第三方自建應用，走 API Key 存取 Proxy）
- 匿名存取：功能旗標（`allow_anonymous_access` + `is_public_readable`），走 /pub/* 端點（見 §15）。**`internal` app 不可啟用**（400），僅 `external` / `self_built` 可以
- 語言選擇：TypeScript（前端）+ Python（後端），為 AI Coding 最佳化的精選組合（詳見 §21）
- 資料架構：統一走 API 存取，不直連資料庫——避免結構混亂（詳見 §21）
- 事件觸發：Webhook（外部系統打進來）與 App 排程（平台時鐘）——見 `event-triggers.md`

## 2. 認證與連線

**網址規則：`https://[tenant].ai-go.app/*`**——登入與所有 API 都走租戶子網域，
主站 apex `https://ai-go.app` 不是租戶入口（`/login` 已是 workspace finder）。

```http
POST https://urfit.ai-go.app/api/v1/auth/login
{"email": "...", "password": "..."}
→ {"access_token": "...", "refresh_token": "...", "expires_in": 3600}
```

所有 Builder API 需帶 `Authorization: Bearer {access_token}`。Token 有效期 1 小時。

⚠️ 租戶由 **Host** 決定：同一組帳密打到別的租戶子網域，平台一律回 **401「帳號或密碼錯誤」**
——與密碼真的打錯**完全同形**（反帳號列舉）。查 401 先確認網址列的租戶前綴。

## 3. VFS 標準檔案樹

```
package.json
src/main.tsx          ★ 入口點
src/App.tsx           路由 + Layout
src/App.css           全域樣式
src/api.ts            [SDK] 自建表 CRUD（+ legacy CustomObject 方法）
src/db.ts             [SDK★] DB Proxy
src/action.ts         [SDK] Server Action
src/approval.ts       [SDK★] 簽核操作（見 §24.4）
src/user.ts           [SDK★] 登入者角色／權限快照（見 §6）
src/data.json         [INJ] legacy CustomObject 定義（已退場，見 CONTEXT.md）
src/db.json           [INJ] Data Reference
src/actions.json      [INJ] Action 清單
src/pages/            頁面元件
src/components/       共用元件
actions/manifest.json Action 註冊
actions/*.py          Action 實作
```

> **★ 標記的 SDK 檔案不是建立 App 時就有的**——只有 `api.ts` / `action.ts` 隨 App 建立產生，
> `db.ts` / `approval.ts` / `user.ts` 要**到 Builder 後台開一次「開發」分頁**才會補進 VFS。
> 純走 API 的開發流程 `import "../user"` 會編譯失敗，補救見 `platform-behaviors.md` §10.2。
> SDK 檔案開頭都有 `/* @ai-go-sdk */` 標記，平台以此判斷可否覆寫——**不要動它們**。

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

### 自建表 (api.ts)

```typescript
import { listTables, queryTable, insertRow, updateRow, deleteRow } from "../api";
```

完整用法見 `data-center.md` §7。

> 同一支 `api.ts` 還有 `listRecords` / `submitRecord` / `updateRecord` / `deleteRecord`——
> 那是 **legacy CustomObject** 的雙軌保留，存量 app 可繼續用，**新開發不要用**。

### DB Proxy (db.ts)

```typescript
import { query, queryAdvanced, insert, update, remove } from "../db";
```

⚠️ **前端 `db.ts` 的** `update()` / `insert()` 需用 `{"data": {...}}` 包裝（SDK bug）。
> 這只適用前端。**Server Action 的 `ctx.db.insert(table, data)` 收扁平 dict**，
> 包成 `{"data": ...}` 會被欄位過濾濾光並回 400。兩者同名不同軌，別搞混。

### Server Action (action.ts)

```typescript
import { runAction, downloadFile } from "../action";
const { data, file } = await runAction("name", params);
```

### User Context (user.ts)

沿用**主站的角色／權限**做條件顯示，**不要自己打 `/api/v1/auth/me`**。
資料是 Runtime 載入時注入的唯讀快照（`window.__USER_ROLES__` / `__USER_PERMISSIONS__`）；
**只有 Internal App 且非匿名渲染才注入**，External／匿名一律空陣列。

```typescript
import { getCurrentUser, getRoles, getPermissions,
         hasPermission, hasAnyPermission, hasAllPermissions, isAdmin } from "../user";

if (hasPermission("sale.write")) { /* 顯示新增訂單按鈕 */ }
if (isAdmin()) { /* system.admin 全開 */ }
```

⚠️ **`src/user.ts` 不是每個 App 的 VFS 都有**——它是**在 Builder 後台開「開發」分頁時**
才注入的 SDK 檔（`api.ts` / `action.ts` 建立 App 就有，`db.ts` / `approval.ts` / `user.ts` 沒有）。
純走 API 建立的 App 直接 `import "../user"` 會編譯失敗；
快照全域本身仍有注入，可自行讀取——兩條補救路徑見 `platform-behaviors.md` §10.2。

⚠️ **這裡只解決「能做什麼」，不解決「是誰」。** 快照裡沒有 user id／email；
要取登入者身分請解 `__APP_TOKEN__` 的 JWT payload（`platform-behaviors.md` §10.3）。
`window.__CURRENT_USER__` **在任何模式都不存在**，不要找它。

⚠️ **用 permission 標籤（`模組.動作`）判斷，不要用角色名稱**——角色可被租戶改名，
標籤才穩定；`system.admin` 自動通過所有 `hasPermission`。
⚠️ **前端隱藏只是 UX 不是安全邊界**：機敏資料差異必須在 action 用
`ctx.user_permissions` 分流（§7），或靠 Data Reference 授權把關。
同理，**寫入身分欄位的值要在 action 用 `ctx.user_id` 覆蓋**，
不要相信前端從 token 解出來後送上來的 id（`platform-behaviors.md` §10.3）。

## 7. Server-Side Actions

```python
def execute(ctx):
    ctx.params              # 前端參數（webhook / cron 事件也走這裡）
    ctx.user_id             # 觸發者 UUID（排程等無使用者上下文為 None）
    ctx.user_permissions    # 觸發者權限標籤 list[str]（★ 角色分流的後端強制點）
    ctx.user_roles          # 觸發者角色名稱 list[str]（顯示用，勿用於判斷授權）
    ctx.db.query(t)         # Data Reference 查詢
    ctx.db.insert(t, d)     # Data Reference 新增
    ctx.db.list_tables()    # 自建表清單
    ctx.db.query_table(t,o) # 自建表查詢（回傳分頁信封）
    ctx.db.insert_row(t, d) # 自建表新增
    ctx.http.call(slug, path, method=..., body=...)  # 對外 HTTP（經 egress 閘道，見 §25）
    ctx.secrets.get(k)      # 金鑰（webhook 驗簽等非對外憑證用）
    ctx.response.json(d)    # 回應
    ctx.csv.export(r)       # CSV
    ctx.erp.confirm_sale_order(id)  # 觸發平台業務流程（方法級白名單，見 §24 與下方註）
```

> 上面是常用的一組，`ctx` 實測共有 20 個命名空間。`ctx.erp` 只開放六個方法，
> 呼叫白名單外的方法會由閘道回 **403**（意思是「方法未開通」，不是「能力不存在」）。
> 完整清單與回傳型別見 `platform-behaviors.md` §4。

Action 也可由 Webhook 或 App 排程觸發——**兩者都要求 action 冪等**，見 `event-triggers.md`。

依權限分流（前端隱藏不算數，這裡才是強制點）：

```python
def execute(ctx):
    perms = ctx.user_permissions or []
    if "system.admin" in perms or "hr.read" in perms:
        rows = ctx.db.query("sale_orders", limit=100)
    else:
        rows = [strip_sensitive(r) for r in ctx.db.query("sale_orders", limit=100)]
    ctx.response.json({"rows": rows})
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

**平台標識（2026-08 改版）**：舊的右下角常駐藥丸已改為**頂部滿版橫條**
「第三方應用程式｜由 AI GO 平台代管，非官方頁面」——只在每個使用者
**首次造訪**顯示 5 秒後自動消失（per-slug 記在 localStorage），
`pointer-events: none` 不吃點擊。App 不再需要為它避讓右下角；
但**不要嘗試用 CSS/DOM 蓋掉或移除它**——平台有 MutationObserver 自癒
（移除會掛回、竄改樣式會整體重設），這是明文防護面。

## 10. VFS 注入規範

- 每次注入必須提供完整的檔案內容（raw string）
- 禁止字串拼接或模板佔位符
- 禁止 `// ... 省略` 之類的佔位

**路徑會在寫入前正規化（2026-08 起）**：

- 非法路徑直接 **400 `無效的檔案路徑`**（不再靜默寫入髒 key）：
  含 `\` 反斜線、以 `/` 開頭、含 `..` 段、normalize 後為空
- 大小寫自動折疊三處：首段 `Actions/`→`actions/`、第二段 `_Shared/`→`_shared/`、
  副檔名 `.PY`→`.py`；其餘路徑段大小寫不動
- `actions/./foo.py` 與 `actions/foo.py` 視為同一檔（last-wins 合併，不再分叉）

action 路徑約定不變：`actions/**.py` 是可呼叫 action（`action_name` = 去前綴去副檔名，
如 `sub/x` ↔ `actions/sub/x.py`）；`actions/_shared/**.py` 是共用模組——
**不是 action**，不要求 `execute(ctx)`、不可用 action_name 呼叫。

## 11. 自建表 API

自建表是**租戶級**的真實 Postgres 表，端點前綴 `/api/v1/data-center/`。
建表／改結構需 `datacenter.schema_write`（2026-08 起，`system.admin` 直通）；
**刪表／刪欄仍限 `system.admin`**；記錄 CRUD 需 `builder.access`。

**完整規格見 `data-center.md`**——型別、配額、兩段式刪除、SDK 用法都在那裡。

> `POST /api/v1/data/objects/batch` 是**已退場的 CustomObject**，不是自建表。
> 見 `CONTEXT.md` 的術語區分。

## 12. Storage API

- POST `/api/v1/ext/storage/upload`（multipart/form-data）
- GET `/api/v1/ext/storage/url?path={path}`
- GET `/api/v1/ext/storage/list?folder={folder}`
- DELETE `/api/v1/ext/storage/file?path={path}`

需 Custom App Token (`window.__APP_TOKEN__`)。單檔 100MB 上限。

## 13. Runtime 全域變數

**注入條件依模式而異**，不是每個變數在每種模式都有值：

| 變數 | 說明 | internal | external | 匿名 |
|------|------|:-:|:-:|:-:|
| `window.__APP_TOKEN__` | JWT Token | ✅ | ✅ | ✅ |
| `window.__APP_SLUG__` | App slug | ✅ | ✅ | ✅ |
| `window.__APP_ID__` | App UUID | ✅ | ✅ | ✅ |
| `window.__API_BASE__` | API 基底 URL | ✅ | ✅ | ✅ |
| `window.__CUSTOM_APP_ROOT__` | Shadow DOM 掛載點（`main.tsx` 用） | ✅ | ✅ | ✅ |
| `window.__USER_ROLES__` / `__USER_PERMISSIONS__` | 權限快照 JSON 字串（`user.ts` 用，見 §6） | ✅ | ✗ | ✗ |
| `window.__IS_EXTERNAL__` / `__AUTH_TYPE__` | 是否為 External 模式 | ✗ | ✅ | — |
| `window.__IS_AUTHENTICATED__` / `__PUB_API_BASE__` | 匿名渲染標記（恆為 `false`）與 /pub 基底 | ✗ | ✗ | ✅ |

> ✗ 代表**該變數根本沒被注入**（讀到 `undefined`），不是 `false`。所以判斷一律寫
> `!!(window as any).__IS_EXTERNAL__`；也**不能**拿 `__IS_AUTHENTICATED__` 當「是否已登入」，
> 它只在匿名渲染出現且恆為 `false`。
> `window.__CURRENT_USER__` **不存在於任何模式**——取登入者身分請解 `__APP_TOKEN__`
> 的 JWT payload。逐項實測與程式碼核對見 `platform-behaviors.md` §10.1。

## 14. External Auth API

端點前綴：`/api/v1/custom-app-auth/{slug}/`

- POST `.../register` → 註冊
- POST `.../login` → 登入
- GET `.../me` → 當前用戶
- **PATCH `.../me`** → 使用者改自己的顯示名稱（2026-08 起）。
  payload 只收 `{"display_name": "..."}`（strip 後非空、≤100 字，違反 422）；
  身分由 token 決定，天然只能改自己；不撤 session
- POST `.../refresh` → 刷新 Token
- POST `.../logout` → 登出

Auth SDK：`window.__auth__.login()`, `.register()`, `.logout()`, `.getToken()`

### 14.1 邀請平台使用者直達 App（internal app 的成員邀請）

邀請成員時**指定落點**，受邀者完成註冊後直接進 App（不指定會落到 dashboard）：

```http
POST /api/v1/members
{"name": "...", "email": "...", "role_ids": [roleId],
 "redirect_url": "/app-login/{slug}",
 "send_email": true}
```

- 需 **`hr.member_manage`** 權限——只有 `builder.access` 會 403，UI 要顯式處理，
  不要讓邀請按鈕靜默失敗
- `redirect_url` 是 fail-closed 白名單（422）：站內路徑、前綴限
  `/app-login/`、`/runtime/`、`/customApp/`、`/builder/`、`/dashboard/` 等；
  **純 ASCII `[A-Za-z0-9/._~-]`**——slug 含中文或空白的路徑組不出合法落點；
  不可含 `?`／`#`、≤256 字
- `POST /members/{id}/resend-invite` 同樣支援；重寄時省略 `redirect_url`
  會沿用該成員上一張邀請的落點（重寄是冪等修復動作）
- `send_email=false` 時平台不寄信，呼叫端要自己轉交回應裡的 `chat_invite_link`，
  且受邀者註冊多一道信箱驗證

## 15. 匿名存取 API（/pub/* 端點）

啟用條件：`allow_anonymous_access=true` + `is_public_readable=true`

- GET `/api/v1/pub/data/{slug}/objects`
- GET `/api/v1/pub/data/{slug}/objects/{table}/records`
- POST `/api/v1/pub/proxy/{slug}/{table}/query`

Rate Limit：120 次/分鐘 per IP。

## 16. 套件管理

### 16.1 前端（bundle）

Runtime 內建：react ^18.x, react-dom ^18.x, react-router-dom ^6.x, lucide-react latest, react-hot-toast latest
不支援：CSS Modules, Tailwind, styled-components, @mui/material, 動態 import, Node.js 原生模組

### 16.2 Python action 依賴：`actions/requirements.txt`（per-app wheelhouse）

Action 可以用第三方 Python 套件了。宣告檔是 VFS 內的 **`actions/requirements.txt`**，
Builder UI 對應「套件」面板（用面板儲存會清掉檔案裡的註解）。

**格式（違反 → 422，code 為 `WHEELHOUSE_*`）**：

- 只收 **`name==version`** 精確 pin，可帶 extras（`requests[socks]==2.32.3`）
- 空行與整行 `#` 註解忽略；**拒絕** option 行（`-r`／`--index-url`）、URL、`git+`、
  範圍運算子（`>=`、`~=`、`*`）
- 最多 **20 行**；解出的 wheel 合計 ≤ **80 MiB**；解析逾時 **90 秒**

**硬限制：目標平台固定 aarch64 / manylinux / cp312、`--only-binary :all:`**——
沒有預編譯 aarch64 wheel 的套件（要現場編譯的）用不了，解析階段就會失敗
（`WHEELHOUSE_RESOLVE_FAILED`），不是部署後才炸。

**時機與行為**：

- 存檔只寫 VFS；**解析只在試跑（try-run）與發布時發生**。發布解析失敗回 422，
  不會發出缺套件的版本
- 有 pin 時試跑改走**專屬 draft runner**（不再是共享 dev-runner），
  冷啟最長約 **60 秒**——第一次試跑看到 `draft runner not ready` 是在等冷啟，不是壞了
- **執行期仍禁止 `pip`**：runtime 內不能動態安裝，一切依賴都要進 requirements.txt
- 安裝失敗的版本不會帶病上線（runner 直接起不來），症狀是 action 全面逾時
  ——先檢查 requirements.txt，而不是改 action 邏輯

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
| Action 連不到第三方 API | 讀回傳 status/error：raw httpx 直連必 timeout → 改 `ctx.http.call`；多為 slug 未註冊 EgressService → §25 |
| 使用者看到「App 已載入但沒有顯示任何內容」banner | 平台的空渲染偵測：掛載後 8 秒 Shadow root 全空就回報 runtime error。啟動先渲染 skeleton，別讓長 API 擋住首次渲染 → `platform-behaviors.md` §11 |
| 想用第三方 Python 套件 | `actions/requirements.txt` 精確 pin → §16.2 |
| 某張表沒有 `tenant_id`，是 bug 嗎？ | **不是**，租戶隔離也沒失效。除了自帶 `tenant_id`，還有欄位別名 / 父表歸屬 / 全域表三種形態 → §20.3。不要自己補 `WHERE tenant_id` |

## 18. 核心策略：app_domain 標籤

### 概念

每個 Custom App 在寫入預設表（Data Reference）時，必須在 `custom_data` JSONB 中標記 `app_domain`，
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

讀取預設表資料時，應用 `app_domain` 過濾，僅處理本 App 建立的資料：

```typescript
const myRecords = allRecords.filter(
  r => r.custom_data?.app_domain === APP_DOMAIN
);
```

> ⚠️ **這個過濾只能在取回後做**——`custom_data` 是 JSONB，伺服器端過濾一律回 400。
> 配上 DB Proxy「單次最多 500 筆」的硬上限，資料一多就會變成
> 「只過濾了前 500 筆」而不自知。表裡資料可能超過 500 筆時，
> **必須先用帶唯一鍵排序的 `offset` 迴圈取完整資料再過濾**——
> 見 `platform-behaviors.md` §1.2、§1.3。這也是為什麼要被篩選／排序／分頁的維度
> 應該放**原生欄位**，不要只存在 `custom_data` 裡。

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

## 19. 資料承載體總決策（★ SSOT——所有分流指引以本節為準）

平台可用的資料承載體有**四種**＋一種已退場：**預設表原生欄位／預設表延伸欄位（EAV）／
預設表 `custom_data` JSONB／自建表（重用加欄或新建）**；CustomObject 已退場僅存量維護。
SKILL.md 規則 18、§22 遷移映射、`migration-workflow.md` §2.4 的分流都是本節這棵樹的投影
——彼此如有出入，以本節為準。

**直接開發與現有應用遷入用同一棵樹**，只是輸入不同：直接開發的輸入是需求分析的
資料表清單；遷入的輸入是外部 schema 的映射表——判定邏輯完全一致，不因「這是搬進來的」
就放寬。

### 決策樹（表級 → 欄位級）

```
一個資料需求（新功能的表／欄位，或遷入映射中的外部表／欄位）
│
├─ 表級：這個實體要與平台既有功能連動嗎？（看板、專案、發票、客戶…）
│   ├─ 是 → Data Reference 軌：把該預設表加入引用；每個欄位進下面「欄位級」
│   └─ 否（租戶自有業務實體——遷入案例的主力）→ 自建表軌：
│       租戶已有語意相同的自建表？
│       ├─ 有 → 重用；欄位不足 → 加實體欄位（data-center.md §7）
│       └─ 無 → 新建自建表（建表規格 → 用戶確認 → POST /data-center/tables）
│
└─ 欄位級（只有預設表需要走這段；自建表缺欄一律加實體欄位）：
    原生欄位語意對得上？ → 原生欄位（永遠優先）
    對不上 → 這欄位是「租戶級業務欄位」還是「app 私有標記」？
    ├─ 租戶級正式欄位（要型別驗證、資料中心 UI 全租戶可見可管理、跨 app 一致）
    │   → 延伸欄位（EAV，data-center.md §10；★ ctx.db／db.ts 不回傳其值，
    │     讀寫走獨立端點——app 要大量讀寫時回頭考慮改自建表）
    └─ app 私有標記（app_domain 恆在此）、暫時性、鬆散擴充
        → custom_data JSONB（標記規範見 SKILL.md 規則 19）
```

### 決策流程（動手前的盤點順序）

1. **先盤點兩邊**：
   - `GET /api/v1/data-center/tables` — 租戶既有自建表（★ 不可跳過）
   - `GET /api/v1/refs/available-tables` — 可引用的預設表（見 §20）
2. 既有自建表語意相同 → **直接重用**，不要新建；重用的表**欄位不足 → 加實體欄位**
   （`data-center.md` §7），不要因缺欄就另建表或把結構化欄位塞進 json 欄
3. 對候選預設表查欄位（§20.2），確認權限是否足夠；缺欄位時依決策樹的欄位級分流——
   租戶級正式欄位用**延伸欄位**（EAV，`data-center.md` §10）、
   app 私有標記與鬆散擴充用 `custom_data` JSONB（預設表本體不可加實體欄位）
4. 每張表／每個欄位走上面的決策樹定案
5. 走 Data Reference → 把表加入引用（引用狀態一律以 `GET /api/v1/refs/apps/{app_id}` 為準，
   **不要看 `db.json`**，見 `platform-behaviors.md` §6）。
   可用 API `POST /api/v1/refs/apps/{app_id}`（`builder.access`，
   body `{table_name, columns[], permissions[]}`），或引導用戶到 Builder 後台操作
   走自建表 → 產出建表規格交用戶確認，再 `POST /api/v1/data-center/tables`

### 選擇矩陣（速查——結論與決策樹一致）

| 條件 | 選擇 | 說明 |
|------|------|------|
| 要與平台既有功能連動（看板、專案、發票、客戶） | **Data Reference** | 與平台功能共用同一份資料 |
| 租戶已有語意相同的自建表 | **重用該自建表** | 自建表跨 app 共用，重複建 = 資料分裂 |
| 重用的自建表缺欄位 | **加實體欄位** | `data-center.md` §7；不要另建表或塞 json |
| 租戶自有的新業務實體（外部系統遷入的主力） | **自建表** | 真實資料表、真外鍵、200 張配額 |
| 需要真正的關聯完整性（刪除被引用列要被擋） | **自建表** | relation → 自建表會建真 FK |
| 預設表缺「租戶級正式欄位」 | **延伸欄位** | EAV overlay；讀寫走獨立端點（`data-center.md` §10） |
| app 私有標記、臨時、鬆散、不值得定義欄位 | **預設表 `custom_data`** | 免定義成本；`app_domain` 恆在此 |

### 入口情景對照（同一棵樹的三個入口）

| 情景 | 輸入 | 走法 |
|------|------|------|
| 直接開發新功能 | Phase 1.5 需求分析的資料表清單 | 每張表／欄位直接走決策樹 |
| 現有應用遷入（Custom App） | `migration-workflow.md` §2.4 的映射表 | 外部每張表／欄位經映射走**同一棵樹**；映射未經用戶確認不得匯入（§2.5 閘門） |
| 現有應用遷入（Hosted App） | 同上 | **分流結果相同**；差別只在存取方式改走 Open Proxy（`hosted-apps.md` §7.1），原 DB 退場 |

### 禁止項（不進決策樹的選項）

- **CustomObject**（`data.json`／`listRecords`／`ctx.db.query_object`）——已退場，
  存量維護、新需求禁用（`CONTEXT.md`、`data-center.md` §8）
- **app 內自建使用者／角色表**——身分與權限沿用平台（SKILL.md 規則 23）；
  遷入專案的 users 表走 `project_deconstruction_template.md` 的認證映射

### 兩軌的關鍵差異

| | Data Reference | 自建表 |
|---|---|---|
| 歸屬 | 引用平台既有表 | 租戶自有的新表 |
| 跨 app | 共用，靠 `app_domain` 區分來源 | 共用，**不需要也不該用** `app_domain` |
| 外鍵 | 無原生 FK | relation → 自建表**有真 FK** |
| 建立方式 | Builder 後台加入引用 | `POST /data-center/tables`（需 `system.admin`） |
| 怎麼盤點 | `GET /refs/apps/{app_id}`（**不是** `db.json`，那個恆為 `{}`） | `GET /data-center/tables`（租戶級，不在 VFS） |

### 預設表常見結構

預設表通常包含以下標準欄位：

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

用於在開發規劃階段（Phase 1.5）探索所有可用的預設表，決定哪些表適合作為 Data Reference。

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

> 上面的回應範例是 `customers` 這類「自帶 `tenant_id`」的表。**不是每張表都有 `tenant_id`**，
> 缺了也不代表沒保護——見 §20.3。

### 20.3 租戶邊界：不要用「有沒有 `tenant_id`」判斷

這是最容易誤判的一點。你會看到某些表的欄位清單裡**沒有** `tenant_id`，例如
`msg_messages`、`announcement_reads`、`import_mappings`、`ir_sequences`、`account_accounts`。

**這些都不是 bug，租戶隔離也沒有失效。** DB Proxy 的租戶邊界依表而定，有四種形態：

| 形態 | 邊界怎麼來 | 例子 |
|---|---|---|
| 自帶 `tenant_id` | 直接過濾（多數表） | `customers`、`sale_orders` |
| **欄位別名** | 租戶欄位存在，但沿用 Odoo 血統叫 `company_id` | `ir_sequences`、`partner_banks` |
| **父表歸屬** | 子表本身無租戶欄位，靠 `EXISTS` 子查詢繞父表驗證 | `msg_messages`→`msg_threads`、`announcement_reads`→`announcements`、`import_mappings`→`import_jobs` |
| **全域表** | 平台 seed 的參考資料，全租戶共用，**刻意不過濾**；讀放行、寫 403 | `countries`、`currencies`、`account_accounts` |

上表的例子是舉例、不是窮舉，**不要拿這份清單當判定依據**（真正的依據見下面守則 2）。
（自建表不在此列，那是另一軌，見 §19。）

**兩條實作守則：**

1. **不要自己補 `WHERE tenant_id = ...`。** 邊界由 Proxy 注入，你手動補在後三種形態的表上，
   只會因為欄位不存在而直接失敗。
2. **不要因為「這張表沒有 `tenant_id`」就改用別的資料表、或自己加一層過濾。**
   平台的判定依據是後端的顯式登記表，不是欄位偵測。

> **反過來也成立**：若你查詢某張表時拿到「欄位不存在」類的 500，代表這張表未被登記為
> 上述任一形態——它不是給 App 引用的表，換一張，不要試圖繞過。

### 20.4 典型使用流程

```
Phase 1.5 實作計畫時：

1. GET /api/v1/refs/available-tables
   → 取得所有可用預設表清單

2. 對每個候選表 GET /api/v1/refs/tables/{name}/columns
   → 確認欄位結構、是否有 custom_data (JSONB)

3. 決定資料架構：哪些需求用預設表、哪些用自建表（見 §19）

4. 在 AI GO Builder 後台將選定的預設表加入 Data Reference

5. 用 GET /api/v1/refs/apps/{app_id} 確認引用已包含所需的表
```

> **重要**：`available-tables` 僅列出可用表名，實際將表加入 App 的 Data Reference 需在 AI GO Builder 後台操作。
> 加入後，該表的 schema 由 Runtime 在執行期注入；**VFS 裡的 `src/db.json` 實測恆為 `{}`，
> 不能用來確認引用狀態**——一律查 `GET /api/v1/refs/apps/{app_id}`（見 `platform-behaviors.md` §6）。

## 21. 架構設計理念

### 為什麼是 TypeScript + Python

TypeScript（前端）和 Python（後端 Server Action）是 AI GO 精選的開發語言組合，基於以下特性選定：

- **低出錯率與高可靠性**：TypeScript 的靜態型別系統和 Python 的清晰語法，大幅降低常見程式錯誤的發生率
- **依賴樹扁平、注入漏洞少**：靜態型別減少了動態語言常見的型別注入與未預期行為，提供更安全的執行環境
- **LLM 生成與閱讀最佳化**：這兩種語言在 LLM 訓練資料中覆蓋度最高，AI Agent 生成的程式碼品質與正確性顯著優於其他語言

因此，TypeScript + Python 最適合 **AI Coding 的新手或非技術工作者**，用來開發需要可靠性的公司內部系統。

### 為什麼資料存取走 API，不直連資料庫

- **避免結構混亂**：直接連線資料庫且 schema 可疊加時，非技術的 AI Coder 容易重複建立類似的表或欄位，造成資料結構混亂
- **通用結構先行**：AI GO 預先定義了中小企業通用的資料庫結構（預設表），涵蓋專案、客戶、銷售、會計等常見業務場景
- **擴充彈性**：同時保有自建表的自訂擴充能力（租戶級真實資料表），以及預設表的 `custom_data`（JSONB）欄位
- **安全與一致性**：中間統一走 API 與反向代理，確保多租戶隔離、權限控制、資料驗證等安全機制

### 現有系統遷移

若用戶的情景屬於「現有系統匯入 AI GO 部署」，且現有系統不是 TypeScript + Python：

1. **解釋語言選擇理由**：說明上述 TypeScript + Python 的精選特性
2. **建議建立新專案重構**：在 AI GO 上建立全新 Custom App 專案，以 AI GO 架構重新設計
3. **原專案不更動**：用戶的本地原始專案保持不變，AI GO 專案獨立開發
4. **業務邏輯遷移**：引導用戶將現有系統的業務邏輯和資料結構，對應到 AI GO 的預設表 + 自建表雙軌架構

## 22. 外部 Schema 映射指引

當用戶要將外部系統（Supabase / Google Sheet / MySQL 等）遷入 AI GO 時，需要將外部 DB 的表結構映射到 AI GO 的資料架構。

### 22.1 映射流程

```
1. 列出外部系統的所有資料表與欄位
2. 盤點兩邊：GET /data-center/tables（既有自建表）＋ Refs API（可用預設表，見 §20）
3. 逐表比對：
   租戶已有語意相同的自建表？    → 重用；欄位不足 → 加實體欄位（data-center.md §7）
   要與平台既有功能連動？      → 預設表原生欄位；無原生對應 →
                                   正式欄位用延伸欄位（data-center.md §10）、
                                   app 私有標記用 custom_data JSONB
   租戶自有的新業務實體？        → 自建表（遷入案例主力）
4. 處理外鍵 / 關聯
5. 產出映射表（模板見 resources/migration_mapping_template.md）
```

### 22.2 語意重疊表的合併 / 分離決策

當多個外部系統有語意相同的表（如都有「客戶表」）時：

| 判斷條件 | 結果 | 說明 |
|---------|------|------|
| 指向同一群實體 + 未來需統一檢視 | **合併** | 進同一張預設表，各 App 用 `app_domain` 標籤區分來源 |
| 指向同一群實體 + 各自獨立運作 | **合併** | 但各 App 只過濾自己 `app_domain` 的資料 |
| 指向不同群實體（如不同市場的客戶） | **分離** | 各自建自建表，或（走預設表時）用不同 `app_domain` 隔離 |
| 欄位結構差異過大（>50% 不同） | **分離** | 硬塞進同一張表會造成 custom_data 過於複雜 |

決策樹：

```
多個外部系統都有語意相同的表
  ├─ 是同一群實體？
  │   ├─ 是 → 合併進同一張預設表 / 自建表
  │   │       ├─ 欄位聯集 → 共有欄位用原生欄位，各自特有欄位放 custom_data
  │   │       └─ 去重策略 → 以 email / 名稱為 key，衝突時由用戶決定保留哪邊
  │   └─ 否 → 分離
  │           ├─ 各自對應不同 AI GO App
  │           └─ 各自做 Schema 映射
  └─ 不確定 → 問用戶確認
```

### 22.3 外鍵 / 關聯處理

外部 DB 的 FK 關係要依「兩端各落在哪一軌」決定轉換方式：

| 外部 FK 類型 | AI GO 處理方式 |
|-------------|---------------|
| `tasks.project_id → projects.id`（兩表都遷自建表） | 自建表的 `relation` 欄位指向自建表 → **建真正的資料庫外鍵**，刪除被引用列會被 DB 擋下（409） |
| 自建表 → 預設表 | `relation` 指向預設表 = **軟關聯不建 FK**（跨 schema），只在寫入時驗證目標存在 |
| `orders.customer_id → customers.id`（兩表都用預設表） | 直接用預設表的 `customer_id` 欄位；無原生 FK 約束 |
| 多對多（junction table） | 建一張自建表存放關聯（兩個 relation 欄位），或在 `custom_data` 存 ID 陣列 |

> **重要**：只有「自建表 → 自建表」的 relation 有真 FK。其餘情況（預設表之間、
> 自建表 → 預設表）的參照完整性需由 Server Action / 前端程式碼維護，
> AI GO 不會自動做 cascading delete。

### 22.4 多系統遷入時的 custom_data 命名空間

> **僅適用 Data Reference 那一軌。** 自建表有自己的實體欄位，不需要命名空間前綴，
> 也不該帶 `app_domain`（見 `CONTEXT.md`）。

當多個 App 共用同一張預設表時，建議在 `custom_data` 中使用 `app_domain` 作為命名空間前綴：

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

**★ 匯入前必查：目標預設表有沒有掛簽核流程（§24）**——這一步漏掉的代價是
「匯 2000 筆歷史資料＝開 2000 張簽核單」，而且規則 24 明訂 pending **不可重試**，
匯入腳本的錯誤重送邏輯會把災難翻倍（重複建記錄＋重複開單）。只影響
Data Reference 軌；自建表不在簽核範圍，不受此限。

- **查法**：請租戶管理員在簽核設定確認目標表；§24.1 列了常設流程的表
  （`sale_orders`、`purchase_orders`、`account_moves`…）——匯入目標命中清單時
  一律當作「有掛」處理，直到管理員確認沒有
- **命中時的處置**（規則 24：`db.ts`／`ctx.db`／`ctx.erp` 同一套守衛，**沒有旁路**，
  不要嘗試換路徑寫入）：
  1. **首選：請管理員暫停該表的簽核流程 → 匯入 → 恢復**。計畫中明寫暫停窗口，
     匯完立即恢復並向用戶確認
  2. 量小（數十筆內）且流程不可暫停 → 接受逐筆 pending，請簽核人批次核准；
     匯入腳本把 `approval_status: "pending"` 視為**已送出**（不成功不失敗），
     絕不重試
  3. 流程不可暫停且量大 → 回頭重新分流：這批資料是否真的必須進該預設表
     （§19 決策樹重走一次，考慮自建表）
- update／remove 型的資料修正（如遷移後補值）被 pre-guard 攔下時同理——
  payload 已暫存進簽核單，重打只會再開一張單

### 23.2 Server Action 批次匯入範例

```python
def execute(ctx):
    """批次匯入外部資料到預設表（Data Reference）或自建表"""
    records = ctx.params.get("records", [])
    table = ctx.params.get("table", "")
    target = ctx.params.get("target", "saas")      # "saas" | "custom_table"
    app_domain = ctx.params.get("app_domain", "")

    results = {"success": 0, "failed": 0, "errors": [], "id_mapping": {}}

    for record in records:
        try:
            # app_domain 只標在預設表；自建表不需要也不該帶
            if target == "saas" and app_domain:
                record.setdefault("custom_data", {})
                record["custom_data"]["app_domain"] = app_domain

            # 記住外部 ID 用於後續關聯映射
            old_id = record.pop("_external_id", None)

            if target == "custom_table":
                result = ctx.db.insert_row(table, record)
            else:
                # ctx.db.insert 收**扁平 dict**——不要包成 {"data": ...}，
                # 那會被欄位過濾濾光並回 400「無有效欄位資料」。
                # 需要 {"data": ...} 包裝的是**前端 db.ts**，不是 ctx.db。
                result = ctx.db.insert(table, record)
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
3. 映射表可存在 Server Action 的回傳結果中，或暫存為一張自建表

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
✓ app_domain 標籤：所有預設表記錄都帶有正確的 app_domain（自建表不檢查此項）
✓ custom_data 結構：JSONB 欄位的 key 符合映射表定義
✓ 延伸欄位值：抽驗列用 :batch-get 取回比對（§23.8；缺值不回填，空 {} ≠ 寫入成功）
✓ 簽核流程已恢復：匯入前暫停的簽核流程已請管理員恢復（§23.1 匯入前必查）
✓ 無殘留測試資料：遷移過程中的測試記錄已清除
```

### 23.6 資料抽取路徑（★ 資料怎麼離開來源系統）

§23.2 的匯入 action 假設 records 已經在 `ctx.params` 裡——**「誰去源頭拉資料」要先定案**。
依來源型態選路徑：

| 來源 | 抽取路徑 |
|------|---------|
| **MySQL / Postgres 直連**（含 Supabase 的 DB 連線字串） | **只能在本地做**：本地腳本用 DB driver 讀出 → 打平台 API 寫入（見下）。`ctx.http.call` 只講 HTTP，講不了 MySQL/Postgres 線協定；runner 又是 default-deny egress——**不存在「Server Action 直連源 DB」這條路**，不要往那個方向設計 |
| **Supabase REST**（PostgREST） | 本地腳本打 REST 抓取（最簡單）；或 Server Action `ctx.http.call` + egress 白名單 `<project>.supabase.co`（§25）——只有「遷移後仍要持續同步」才值得建 egress，一次性遷移用本地路徑就好 |
| **Google Sheet** | 匯出 CSV 本地解析（量小）；或 Sheets API 走 egress（要持續同步時） |
| **CSV / Excel 匯出檔** | 本地解析 → 打平台 API 寫入 |

**本地腳本的寫入端（兩軌各有路）**：

- **自建表**：`scripts/aigo_data_center.py` 的 `insert_record()`
  （`POST /api/v1/data-center/...`，逐筆）——量小直接用
- **預設表、或需要匯入邏輯**（補 `app_domain`、ID 映射、型別轉換）：
  先佈一支 §23.2 的匯入 action，本地腳本分批呼叫
  `POST /api/v1/actions/apps/{app_id}/run/{action_name}`，records 放 params。
  base_url 一律走租戶空間（核心規則 29），token 用 `aigo_auth.get_token()`
- **延伸欄位值**：匯入 action 寫不了（`ctx.db` 無封裝）——本地腳本直打
  REST 逐列寫，見 §23.8

**大量資料（數千筆以上）的節奏**：

- Server Action 有執行時間上限（`event-triggers.md` §1.6）——**分批的迴圈放在本地腳本**，
  每批 100~500 筆呼叫一次 action；不要設計成「一發 action 自己拉完全部」，
  超時中斷後你不知道停在哪
- 本地腳本記錄斷點（已成功的批次序號 / 最後一筆外部 ID），失敗可續傳
- 匯入 action 對「同一批重送」要冪等（以外部 ID 查重），否則斷點續傳會重複建資料

一次性遷移結束後，把只為遷移建立的 egress 外部服務與金鑰**清掉**，不要留白名單。

### 23.7 外部型別 → 自建表型別降級對照

自建表只有 9 種型別（`data-center.md` §3），外部 DB 的型別按此表降級：

| 外部型別 | 自建表型別 | 注意 |
|---------|-----------|------|
| VARCHAR / TEXT / CHAR / UUID | `text` | |
| INT / BIGINT / FLOAT / NUMERIC | `number` | 金額等高精度欄位遷移後**必做抽驗比對**；不容許任何精度損失時改 `text` 保存原字串 |
| BOOLEAN / TINYINT(1) | `boolean` | |
| DATE | `date` | |
| TIMESTAMP / DATETIME | `datetime` | 時區語意先確認（平台側行為見 SKILL.md 規則 28） |
| ENUM / CHECK IN (...) | `select` | 正好對應——必須提供選項集，值受 CHECK 約束 |
| JSON / JSONB | `json` | |
| ARRAY | `json` | 存成 JSON 陣列 |
| 外鍵欄位 | `relation` | 目標是自建表 → 真 FK；目標是預設表 → 軟關聯（§22.3） |
| 圖片 / 附件 URL | `image` 或 `text` | `image` 存 storage key（`data-center.md` §6）——外部檔案要先下載、重新上傳 Storage、再存 key；不遷檔案就用 `text` 暫存外部 URL，並向用戶說明原站關閉後連結會失效 |
| 自增 ID | 不遷 | UUID 自動生成，走 §23.3 的 ID 映射 |
| 複合唯一鍵 / 跨欄 CHECK / DEFAULT 運算 | 無對應 | 約束上移：匯入與後續寫入都經同一支 Server Action，在 action 內檢查 |

### 23.8 延伸欄位的匯入（映射表把欄位分到 EAV 軌時）

§19 決策樹把外部欄位分流到**延伸欄位**時，§23.2 的匯入 action 寫不進去——
延伸欄位讀寫走獨立端點，`ctx.db`／`db.ts` 都沒有封裝（`data-center.md` §10）。
機制如下（端點契約核自平台原始碼；**寫入面尚未 prod 實測**，讀面 2026-09-01 已實測）：

1. **先匯主列**：原生欄位＋`custom_data` 照 §23.2 走匯入 action，
   從回傳的 `id_mapping` 拿到每列的 AI GO row id
2. **再寫延伸值**：**本地腳本**逐列
   `PATCH /api/v1/data-center/ext-values/{erpKey}/{rowId}`（`builder.access`），
   body 帶該列的延伸欄位值——**沒有批次寫入端點**（`:batch-get` 只管讀），
   每列一發；PATCH 覆寫語意天然冪等，斷點續傳不會重複
3. **驗證**：抽驗列用 `POST /ext-values/{erpKey}:batch-get`（`row_ids` ≤ 200）
   取回比對。⚠️ 「缺值不回填」——回傳空 `{}` 代表**沒寫進去**，不是預設值，
   別把空回應當成功
4. **量的紅線**：逐列 PATCH 意味 N 列＝N 個請求。上千列且欄位多時，
   先回頭重新評估這個實體是否該整個走自建表（§10 的建議同源）——
   「大量讀寫延伸欄位」本身就是分流錯誤的訊號

- 延伸欄位定義（建欄）需 `datacenter.schema_write`：匯入前先確認欄位已建好
  （`GET /ext-fields/{erpKey}`），缺欄請有權限者先建，匯入腳本不要動結構
- 匯入順序不可反過來：延伸值掛在 row id 上，主列不存在時寫值必失敗

## 24. 簽核工作流攔截（Approval）

租戶管理者可對預設表設定簽核流程。**流程一旦命中，你的寫入不會照你以為的方式發生**——
這不是錯誤、不能重試，是平台的前置守衛（pre-guard）。**只影響 Data Reference（預設表）那一軌；
自建表與 CustomObject 不在簽核範圍。**

### 24.1 誰會被攔

| 呼叫端 | 受管制操作 | 攔截行為 |
|--------|-----------|---------|
| 前端 `db.ts` | `insert` / `update` / `remove`（預設表） | insert = insert-then-flag；update/delete = pre-guard |
| Server Action `ctx.db` | 同上 | 同上；pre-guard 以例外呈現 |
| Server Action `ctx.erp` | `confirm_sale_order`、`confirm_purchase_order`、`post_move`、`confirm_payment`、`validate_picking`、`confirm_payroll_run` | pre-guard，拋例外 |

常見設流程的表：`sale_orders`、`purchase_orders`、`account_moves`、`account_payments`、
`stock_pickings`、`mrp_productions`、`hr_leaves`。

### 24.2 兩種攔截語意（★ 必須分清）

- **insert －insert-then-flag**：記錄**照樣寫入**（為了拿到 id），但不觸發後續業務邏輯，
  回傳的 dict 多出 `approval_status: "pending"`、`approval_request_id`、`approval_message`。
  ⚠️ **不要因為 pending 重試 insert**——會重複建記錄＋重複開簽核單。
- **update / remove、`ctx.erp.*` －pre-guard**：**完全不執行**；payload 暫存在簽核單裡，
  全部層級核准後由平台自動執行。Server Action 收到的是例外（訊息含「需要簽核審批」與 `request_id`）。
  ⚠️ **不要重試、不要改走另一條路徑寫入**——`db.ts` / `ctx.db` / `ctx.erp` 同一套守衛，沒有旁路。

```typescript
// 前端：pending 既不是成功也不是失敗
const res = await insert("sale_orders", { data: { amount_total: 5000 } });
if (res.approval_status === "pending") {
  toast(res.approval_message || "已送出簽核，待核准後生效");
} else {
  toast.success("建立成功");
}
```

```python
# Server Action：pre-guard 以例外呈現，捕捉後回報，不重試
def execute(ctx):
    try:
        ctx.erp.confirm_sale_order(ctx.params["order_id"])
    except Exception as e:
        if "簽核" in str(e):
            ctx.response.json({"pending_approval": True, "message": str(e)})
            return
        raise
    ctx.response.json({"ok": True})
```

### 24.3 讓核准自動改狀態（免寫後端）

請用戶在建立簽核流程時填 `approved_state_field` / `approved_state_value` /
`rejected_state_value`，引擎會在核准／退回時自動更新該欄位。App 只要查
`state === 'approved'` 即可，**不需要為簽核寫任何 Python**。

### 24.4 要做簽核介面時

- 前端：`src/approval.ts`（**僅 Internal App**，External 呼叫直接拋錯）
  `myPending()`、`recordStatus(resModel, resId)`、`approve(lineId, comment?)`、
  `reject(lineId, comment?)`、`cancel(requestId, reason?)`。
  `myPending()` 已由後端過濾成「本人有資格簽」的項目，**前端不要自己判斷誰能簽**。
- Server Action：`ctx.approval.list_pending / get_record_status / approve / reject / cancel`，
  身分是**觸發 action 的使用者**——app 不能代簽；無使用者身分的 invocation（排程）一律拒絕；
  `cancel` 僅申請人本人。需授權 scope：`approval.read`（低風險）、
  `approval.decide` / `approval.cancel`（高風險，授權擴大需擁有者密碼二次驗證）。

> 完整規格（多層／會簽、非必要層、一表多流程、API 旁路、REST 端點）見公開文件
> [Custom App 開發者指南 §23](https://www.ai-go.app/zh-TW/docs/custom-app-dev)。

## 25. 對外 API 呼叫與 Egress 閘道

### 25.1 怎麼呼叫

Server-Side Action 要打第三方 API，**一律走 `ctx.http.call(<egress-slug>, <path>)` 閘道**：

```python
def execute(ctx):
    # slug 對應租戶註冊的「外部服務」（EgressService）——純域名白名單，
    # base_url 鎖定可打的 host。金鑰由 app 自己帶：存 ctx.secrets、自組 header。
    resp = ctx.http.call(
        "example-api",
        "/v1/orders",
        method="GET",
        headers={"Authorization": f"Bearer {ctx.secrets.get('EXAMPLE_API_KEY')}"},
    )
    if int(resp.get("status") or 500) >= 400:
        ctx.response.json({"error": "外部服務暫時無法使用", "status": resp.get("status")})
        return
    ctx.response.json({"orders": resp.get("data")})
```

- **不要直接 `import httpx / requests / urllib.request`**：runner pod 是
  **default-deny egress**（出口網路只放行平台閘道），raw 連線**必定 timeout**
  （實測約 20 秒後才失敗，還會把 action 拖到逾時）；這些套件也在沙箱 denylist 上。
- **閘道只做域名驗證，不碰憑證**（平台 ADR 0010，2026-07-29 起）：閘道**不代管、
  不注入、也不剝除**任何認證標頭——呼叫端 headers（含 `Authorization`）**原樣轉送**，
  只擋 hop-by-hop（`Host`、`Content-Length`、`proxy-*`）。API 金鑰是 **app 自己的
  責任**：開 `ctx.secrets` 欄位存金鑰，action 自組 `headers={"Authorization": ...}`
  傳給 `ctx.http.call`。
  > 舊行為（閘道注入 EgressService 憑證、剝除自帶 `Authorization` 並回 401）
  > 已**整個移除**，硬切、無相容期——靠平台代灌 key 的舊 app 需改寫。
- 回傳是 dict：`resp["status"]`（HTTP 狀態碼）與 `resp["data"]`（回應 body）——
  **自己檢查 status**，閘道不會替你 raise。
- Webhook 或排程觸發的 action 要**冪等**（見 `event-triggers.md`），
  對外呼叫失敗重試時才不會重複送出。

### 25.2 外部服務註冊與 App 授權（★ 呼叫前的必要設定）

`ctx.http.call` 的第一參數 slug 必須對應租戶已建立的**外部服務**（EgressService）——
以**同名 slug** 登記，填 base_url 鎖定可打的 host。**沒有金鑰欄位**：寫入 API 對
`auth_type ≠ none` 或非空 `connection_config` 直接回 400（域名驗證 only，ADR 0010）。

而且是**兩層設定**：slug 沒建立連不出去；服務存在但**沒授權給本 App** 也連不出去
（`egress_not_authorized`）。

設定位置：**Builder（`/builder/{app_id}`）的「外部服務」tab**——唯一入口，
同一處做租戶級建立／編輯與本 App 授權，新建預設順便授權本 App。
（舊入口 `/dashboard/settings/integrations` 已移除，ADR 0011。）

> 一律用**相對路徑**指引用戶，不要寫死主機名稱——子網域日後可能變動。
> 用戶自己登入的後台網域是什麼就接在前面。

- 建立／編輯權限：`builder.access` 且（本 App 擁有者或 `system.admin`）。
  權限不足時請租戶管理員代設，開發者自己繞不過去。
- 外部服務是**租戶共用池**、無服務擁有者：任一 App 擁有者或 admin 可改／刪／停用，
  其他 App 各自授權使用。

### 25.3 被擋掉時長什麼樣

對外呼叫失敗時，**先完整讀出回傳的 status 與 error message**，再對症：

| 症狀 | 成因 | 處置 |
|------|------|------|
| timeout（約 20 秒） | raw `httpx`/`requests` 直連——default-deny egress，連線被黑洞 | 改寫成 `ctx.http.call` |
| `ctx.http.call` 連不出去／錯誤指向 egress | slug 沒有同名外部服務（`egress_service_not_found`），或服務未授權給本 App（`egress_not_authorized`） | 引導用戶到 Builder「外部服務」tab 建立（base_url）並授權本 App |
| 401 | 外部 API 拒絕請求帶的憑證——閘道不注入也不剝除，`Authorization` 是 action 自己組的 | 檢查 action 是否有帶 `Authorization` header、`ctx.secrets` 的金鑰是否正確 |

給 AI Agent 的處理準則：

1. Action 對外呼叫失敗時，**先把回傳的 error message 完整讀出來**，
   不要立刻假設是程式碼寫錯。
2. 若訊息指向 Egress／權限，**停止改 code**——這是設定問題，改幾次都一樣。
3. 把原始 error message 轉給用戶，並引導到 Builder（`/builder/{app_id}`）的
   「外部服務」tab，以同名 slug 建立／修正外部服務並授權本 App；
   權限不足（非本 App 擁有者且非 admin）→ 請管理員代設。
4. **401 是 app 側問題不是平台設定**：回頭檢查 action 組的 header 與
   `ctx.secrets` 金鑰，別再往外部服務設定找。
5. 確認設定生效後才重試。

### 25.4 規劃階段就要處理

Phase 1.5 實作計畫裡就該**列出所有要打出去的外部服務（egress slug + base_url）**，
讓用戶在寫 code 前先去建立外部服務並授權本 App，同時把各 API 的金鑰存進
`ctx.secrets`——等到部署後才發現連不出去，等於整段開發白做。

## 26. 建立與刪除 App（API，不必走 UI）

> 2026-09-01 對 prod 實測全流程通過（create → GET 驗收 → delete → 404）。

```http
POST /api/v1/builder/apps          （權限：builder.access）
{
  "name": "我的系統",                    // 必填，1–100 字
  "template_slug": "starter-internal",  // 必填——API 是模板驅動，不能建純空白 app
  "subdomain": "...",                   // 選填；撞名 422
  "url_name": "..."                     // 選填；未填由 name 自動產生
}
→ 201 CustomAppResponse——app_id 從回應的 id 拿，回填 .aigo/config.json
```

### 26.1 起手式模板怎麼選（★ 建立前先確認情景）

| slug | access_mode | 情景 |
|---|---|---|
| `starter-internal` | `internal` | **租戶成員用的內部工具**。登入者＝平台成員，Runtime 注入權限快照（`__USER_ROLES__`／`__USER_PERMISSIONS__`），沿用平台角色權限（規則 23） |
| `starter-external` | `external` | **對外應用**。終端使用者透過 custom-app-auth 自助註冊／登入（§14），權限快照恆空、UI 要有降級路徑；執行期 API 走 `/ext/*`（SDK 自動分流）；可開匿名 `/pub` |

- **`access_mode` 由模板決定**——body 裡的 `access_mode` 欄位是殘留 fallback，
  模板必填所以恆被模板蓋掉。建立後不可改模式，選錯要砍掉重建
- 模板商城的其他模板（實測 116 個）也可用其 slug 建立；
  清單：`GET /api/v1/templates`（唯讀）
- `self_built` 是 access_mode 的第三值，但它屬於 Hosted App 隨附整合，
  **不是** builder 起手式的選項，不要手動指定

### 26.2 建立後的注意事項

- app 的 `slug` 系統自動生成（如 `961273541bc6`），**不可指定**
- **起手式不是全空白**：實測 `starter-internal` seed 了 23 個檔案，
  含示範 action（`export_leads_csv.py`／`summarize_leads.py` 等 leads 範例）——
  走 Phase 0 review 時會看到，與需求無關就清掉，不要在範例上疊功能
- 模板會一併 seed 模板定義的自訂表與 Data Reference 引用（起手式兩款不帶）
- 金鑰**刻意不在建立時收**——建立後在 Builder「服務」tab 設定
- 複製既有 app：`POST /apps/{app_id}/duplicate` → 201

### 26.3 刪除

```http
DELETE /api/v1/builder/apps/{app_id}   （builder.access；實測回 200，之後 GET 404）
```

不像自建表有兩段式確認——**打了就刪**。代用戶刪除前必須明確確認過。

