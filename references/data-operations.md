# 資料操作模式：不開發 app，以使用者身分直接讀寫 AI GO 資料

> 用戶的目的是**操作資料**（查、改、批次、匯出），不是做 app。這條線不進 Phase 0 的 VFS review、
> 不建 app、不走 Custom App proxy——用登入者自己的 token 打平台 API，權限就是他在平台介面上的權限。
> 2026-09-03 於測試租戶以擁有者帳號（`system.admin`）逐條實測；平台原始碼核對日期同。

## 1. 四條資料面（登入使用者身分）

| 資料面 | 端點 | 權限閘 | 腳本 |
|---|---|---|---|
| **預設表** | 各模組 REST：`/api/v1/client`（客戶）、`/sale`、`/crm`、`/hr`、`/stock`、`/purchase`、`/accounting`、`/mrp`、`/project`、`/supplier` | `<module>.read`／`.write`／`.delete`（與平台 UI 同一套 RBAC；`system.admin` 直通） | `aigo_data.py call`（路由現查 openapi） |
| **自建表** | `/api/v1/data-center/tables/{key}/records` 記錄 CRUD；結構操作另有端點 | 記錄 CRUD `builder.access`；建改結構 `datacenter.schema_write`；刪表刪欄 `system.admin` | `aigo_data_center.py`（已封裝） |
| **批次匯出／匯入** | `POST /api/v1/exports` → 輪詢 → `/download`；`/api/v1/imports`（csv／excel／json，有對應引擎） | 匯出：該表模組的 read；匯入：`system.data_import`（admin 直通） | `aigo_data.py export`；匯入走平台 UI |
| **結構與值域** | `/api/v1/data-center/meta/tables`（193 張：85 預設＋108 自建）、`/meta/tables/{key}` | 登入即可 | `aigo_data.py meta` |

沒有「表名 → 記錄」的通用端點給登入使用者用在預設表上：`/proxy`、`/unified`、`/open/proxy` 都要 app 或整合 id
並走 Data Reference 授權。預設表的使用者身分路徑**就是各模組 REST**。

平台內建的 Cowork agent 另有一層以使用者 RBAC 讀寫 18 張白名單表的存取器（讀 200 筆、寫 100 筆上限），
那是平台介面裡的 AI，不是本 skill 的路。

## 2. 「依用戶自身授權」在兩類表上意義不同（★ 先跟用戶說清楚）

- **預設表：真的依角色。** 只有 `sale.read` 就只能讀銷售；讀寫刪三段分開，與他在平台介面看到的一致。
- **自建表：`builder.access` 一刀切。** 沒有的人一律 403；有的人租戶內**全表**可讀可寫，沒有表級 ACL。
  純資料工作的用戶若沒有開發權限，自建表這一半碰不到——請管理員授權，或改由有權限的人匯出。
- `system.admin` 在所有閘都直通；一般員工帳號**未實測**，權限對照以上表為準。

## 3. 流程（★ 固定順序）

```
1. aigo_auth.py status              ← 工作區＝租戶；登錄表可為空（這條線不需要 app）
2. aigo_data.py me                  ← 身分、角色、permissions 清單（/api/v1/auth/me 直接帶）
3. aigo_data.py perm-check METHOD PATH   ← 推估權限並對照；❌ 就停，請管理員授權，不要試
4. aigo_data.py openapi paths --prefix /api/v1/sale   ← 路由現查，不猜；op 看參數與 body schema
5. aigo_data.py call ...            ← 寫入前把「租戶／身分／端點／body」印給用戶確認
6. 讀回驗證（GET 單筆或 --all 比對筆數）
```

寫入前**一定**要用戶確認：這裡打的是正式資料，沒有 app 沙箱、沒有草稿版。

## 4. 各模組 REST 的實測慣例（測試租戶 2026-09-03）

- **路由權威是 `/api/v1/openapi.json`**（免登入、733 條路徑、675 個 schema）。本 skill 不手抄路由；
  `aigo_data.py openapi op POST /api/v1/client` 會把 body schema 展開成欄位與必填
  （例：`CustomerCreate` 必填 `name`、`customer_type`）。openapi **沒有權限標註**，權限用 §1 的表推估
- **分頁形狀不一致**：`client`／`sale`／`hr`／`stock`／`purchase` 用 `skip`＋`limit`，`crm` 用 `page`＋`page_size`；
  回應多為 `{items, total, …}` 信封。單頁上限多為 **500**（`sale/orders`、`hr/employees`、`stock/pickings`、
  `crm/leads`；`client` 未設上限，預設 100）。`call --all` 依 openapi 自動判斷形狀翻頁，安全上限 20000 列
- ⚠️ **Windows Git Bash 會把 `/api/v1/...` 參數改寫成 `C:/Program Files/Git/api/v1/...`**（MSYS 路徑轉換）。
  `aigo_data.py` 會自動剝掉前面的垃圾，也接受省略前綴（`call GET client`）；
  要根治就在該指令前加 `MSYS_NO_PATHCONV=1`，或改用 PowerShell
- **實測往返**：`POST /api/v1/client` → 200 建立；`PUT /client/{id}` 更新；`DELETE` 回 `{"status":"success"}`，
  之後 GET 404。`GET /sale/orders`、`/crm/leads`、`/hr/employees`、`/stock/pickings`、`/purchase/orders` 皆 200
- **值域**：CHECK 約束的合法值從 `columns` 端點看不到（`custom-app-dev-guide.md` §20.2），
  用 Meta API：`aigo_data.py meta table crm_clients` → `customer_type ∈ [company, individual]`；
  `sale_orders` → `state ∈ [draft, sent, sale, done, cancel]`。
  ⚠️ **Meta key 不一定等於 proxy／refs 面的表名**（客戶是 `crm_clients`，proxy 面叫 `customers`）——先 `meta tables --grep` 再取
- **簽核流程仍然生效**：模組 REST 寫入命中租戶簽核設定時行為同 `custom-app-dev-guide.md` §24，不要重試

## 5. 匯出與匯入

- 匯出白名單只有 **6 張預設表**（`export_service.ERP_EXPORT_REGISTRY`）：`sale_orders`、`purchase_orders`、
  `stock_quants`、`crm_leads`、`hr_employees`、`account_moves`；格式 `json`／`csv`；可帶 `filters`。
  任務非同步（`queued` → `completed`，實測數十秒），`/download` 回 `binary/octet-stream`；
  未完成先下載回 409「匯出尚未完成」。實測 `sale_orders` csv 1877 列、793 KB
- ⚠️ `source_type: custom_table` 指的是**舊 CustomObject**（target_ref 是 custom_object_id），
  **資料中心自建表不在匯出範圍**——送自建表 id 會 failed「custom object not in tenant」，
  送 physical_name 會 failed「badly formed hexadecimal UUID string」。自建表整表取出用
  `call GET /api/v1/data-center/tables/{key}/records --all`
- 不在白名單的預設表（如客戶）：`call GET /api/v1/client --all --out customers.json`
- 匯入：`/api/v1/imports` 上傳 csv／excel／json → profiling → 對應引擎建議 → 人工定稿 → 背景寫入；
  `system.data_import` 限定。有 UI 流程與覆核，**建議引導用戶走平台介面**而不是腳本硬灌；
  逐筆 API 寫入只適合小量或需要程式邏輯的情況

## 6. 這條線不做的事

- 不為了讀資料建 app 或整合，不走 `/proxy`、`/open/proxy`——那是 app 的資料面，授權模型不同
- 不猜權限：`perm-check` 是推估（少數端點另有細權限如 `hr.leave_manage`、`accounting.post`），
  ❌ 就停；拿到 403 也不換路徑繞
- 不繞過簽核；不用 `system.admin` 帳號替一般使用者做他自己沒權限的事而不告知
- 大量寫入前先問「有沒有匯入 UI 能做」；自建表大量寫入見 `custom-app-dev-guide.md` §23
