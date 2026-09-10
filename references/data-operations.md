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
| **成員／邀請／角色／app 角色白名單** | `/api/v1/invitations`、`/api/v1/members`、`/api/v1/members/roles`、`PATCH /builder/apps/{id}/settings`、`PUT /hosted-apps/{id}/access-settings` | `system.invitations`／`hr.member_manage`／`system.roles_manage`／`builder.manage_access`／`hosted_apps.deploy` | `aigo_data.py call`；流程與邊界見 `member-admin.md` |

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
5. aigo_data.py call ...            ← 寫入一律先過 §3.5 寫入閘門（估影響面→備份→試一筆→確認）
6. 讀回驗證（GET 單筆或 --all 比對筆數）
```

寫入前**一定**要用戶確認：這裡打的是正式資料，沒有 app 沙箱、沒有草稿版——完整四步見 §3.5。

## 3.5 寫入閘門（★ 不可逆，四步缺一不動手）

**觸發**：任何 `POST`／`PUT`／`PATCH`／`DELETE`，含批次與匯入。

開發線的不可逆決策（`access_mode`）擋在 Phase 1.5 的計畫閘門後面；這條線的不可逆是
**直接改寫租戶的正式資料**——沒有 app 沙箱、沒有草稿版、沒有發布快照可回退。
遷入線匯錯了還有來源系統可以重匯，這條線的目標**就是唯一一份資料**。

1. **估影響面**：先用**同一組 filter** 跑一次 GET，把「會被改到幾筆」印出來
   （信封的 `total`，或 `call --all` 數列數）。算不出影響筆數 → **不准跑批次**。
2. **取現值備份**：對將被改／刪的記錄先 GET 存成本地 JSON
   （`call GET <path> --all --out before_<表>_<日期>.json`）。
   刪除後 GET 回 404（§4 實測），**本 skill 未知任何還原端點**——這份檔案是唯一退路。
   備份寫不出來（權限不足、量太大）就停下來問用戶，不要「先做再說」。
3. **先試一筆**：批次一律先跑 **1 筆**，讀回驗證通過才放大；之後分批 ≤100 筆、逐批讀回。
   中途失敗要能說出「已經改到第幾筆」——說不出來代表沒有分批。
4. **給用戶確認**：把**租戶／身分／端點／body／影響筆數／備份檔路徑**一起印出來，
   等明確同意才送。用戶沒回覆 = 沒同意。

**DELETE 預設不做**：先問能不能用狀態欄代替（`sale_orders.state → cancel` 之類，
值域用 `meta table` 查）。用戶明確要求真刪，才走上面四步，且備份步驟不可省。

大量寫入仍優先走平台匯入 UI（§5）——它有 profiling 與人工覆核，比腳本硬灌安全。

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
- **匯入（`/api/v1/imports`，`system.data_import` 限定；核自 `api/imports.py`、`services/import_*.py`，
  2026-09-08 main；同日測試租戶擁有者帳號**實打**，★ 標記＝實測）**——**預設表**批次灌資料的首選路徑，
  AI IDE 可以代跑整條 API，映射定稿仍給用戶覆核：
  - 格式 csv／xlsx／xls／xlsm／json；單次 ≤20 檔、單檔 ≤50 MB、總量 ≤200 MB、單來源 ≤10 萬列
    （413／400 訊息會直接說拆檔或分批）。★ 副檔名不支援**不是 400**：回 200，job `status: failed`、
    `error_message`「所有上傳檔皆解析失敗」——看 job 狀態，不要只看 HTTP 碼
  - **目標三種，prod 只有一種真的會寫**：
    - 既有預設表（`existing_table`）★ 可用：3 列 CSV 定稿後 10 秒內 `completed`、`imported_count: 3`
    - **既有自建表（`self_built_table`）與自動新建自建表（`new_table`）★ 在 prod 被靜默 parked**：
      job `completed`、`imported_count: 0`、`sources[].status: "parked"`、`error_detail: null`——沒有任何錯誤字樣。
      原因核自 `infra/k8s/prod`：`IMPORT_TIER3_WRITE_ENABLED=true` 只以顯式 env 給 backend API pod，
      **import-worker 只 `envFrom backend-env`，旗標在 worker 上是預設 false**；mapping 回應的
      `tier3_write_enabled: true` 是 API pod 的值，會誤導。**自建表匯入改走本地腳本**：
      `aigo_data_center.py insert_record` 逐筆，或 dev-guide §23.2 的 Server Action 批次；
      **已回報平台（2026-09-08，含平台 UI 對照：UI「確認定稿並開始匯入」同樣 parked）**，不必重複開單；
      修好前遇到同症狀就照上面走本地腳本。憑證／金流類敏感表在 denylist，映射不到
  - **流程與狀態機**（★）：`POST /imports`（multipart，回 job＋profiling，`awaiting_mapping_review`）
    → `POST /{job}/suggest-mapping`（建議＋`candidate_tables`＋**`table_required_columns`**）
    → 要換表就 `POST /{job}/mapping/retarget {source_id, target_ref}`（只能換到 `candidate_tables` 內的表，
    否則 400「target_ref 'x' 不在此 source 的候選表集內，無法切表重跑」）
    → **`PUT /{job}/mapping` 定稿＝立刻派送 worker 開始寫**（`ready` → `importing` → `completed`／`failed`）；
    `POST /{job}/execute` 只是 `ready` 卡住時的重派（SQS 失敗），對已完成／失敗的 job 冪等回現況，
    對未定稿的 job 409「job 狀態 'awaiting_mapping_review' 尚未定稿，無法執行匯入」
    → `GET /{job}` 輪詢；worker 是 KEDA scale-to-zero，**冷啟動實測 40 秒～1.5 分鐘才從 `ready` 轉走**，這段不是卡住
  - **定稿前必看 `table_required_columns`**（★）：目標表的必填欄沒有對到來源欄 → 整批 `failed`、
    `failed_count`＝列數、`sources[].error_detail.errors[{row, error: "寫入失敗：必填欄位缺值（非空約束）"}]`；
    定稿後就改不了（PUT／retarget 在非 `awaiting_mapping_review` 狀態一律 409），只能重新上傳。
    必填欄的 CHECK 值域用 `aigo_data.py meta table <key>` 查（例：`purchase_suppliers.supplier_type ∈ company/individual`）
  - **同檔重匯不去重**（★）：mapping 顯示 `dedup_key: ["email"]`、`on_conflict: null`，同一份 3 列 CSV 匯兩次 →
    表裡 6 列、`skipped_count: 0`。匯入前先用同 filter GET 估影響面（§3.5），匯錯要自己用模組 REST 逐筆刪
  - `column_map` 每欄必帶 `tier`（缺了 422 `Field required`）；`tier-2`（對不到既有欄）的來源欄去向
    是延伸欄位，模組 REST 讀不到，**未實打驗證**；`transform` 目前 passthrough。
    ⚠️ 進了延伸欄位的資料 **app 執行期也讀不到**（`data-center.md` §10 通道表）——
    匯入的欄位若要在 app 畫面上出現，`tier-2` 這條路不能用，回 dev-guide §19 改分流
  - **引導用戶「匯出檔案丟給 AI IDE」而不是給 DB 連線字串**：檔案走這條有 profiling、必填預警與覆核；
    DB 直連只能在本地做（`custom-app-dev-guide.md` §23.6），只在需要 ID 映射、FK 轉換或遷後持續同步時才要，
    且要求唯讀帳號、用完撤銷；Supabase 直接走 REST 匯出，不必給連線字串
  - 使用者／認證表不進匯入（`member-admin.md` §7）；目標預設表掛簽核流程時先按 dev-guide §23.1 處置
  - 逐筆 API 寫入（`call POST`／`aigo_data_center.py insert_record`）適合小量、需要程式邏輯、以及**自建表**
    （見上），仍過 §3.5 閘門

## 6. 這條線不做的事

- 不為了讀資料建 app 或整合，不走 `/proxy`、`/open/proxy`——那是 app 的資料面，授權模型不同
- 不猜權限：`perm-check` 是推估（少數端點另有細權限如 `hr.leave_manage`、`accounting.post`），
  ❌ 就停；拿到 403 也不換路徑繞
- 不繞過簽核；不用 `system.admin` 帳號替一般使用者做他自己沒權限的事而不告知
- 大量寫入前先問「有沒有匯入 UI 能做」；自建表大量寫入見 `custom-app-dev-guide.md` §23

---

## 7. 出錯與回報（本線的出口）

- **收到非預期狀態碼／症狀不明** → 先查 `troubleshooting.md`，**不要自行推測修法**。
  表裡對本線有效的列包括：模組 REST 分頁抓不齊、匯出 409／自建表不在匯出範圍、
  `perm-check` ❌ 與 403、MSYS 路徑改寫、401 租戶同形、預設表 `CheckViolationError` 值域、
  簽核 `approval_status` 不可重試、自建表 records 要包 `{"data"}`、建表 403／409、
  「端點 404 先懷疑部署落差」。
- **查完仍懷疑平台** → 走 `pre-report-self-grill.md` 六輪自審再回報。
  ⚠️ **本線有一個例外**：第 6 輪 Q6.1（「去掉 app 程式碼、用純 API 重現」）在這條線上
  **恆真**——我們本來就是純 API，它不構成任何證據。改用該檔 Q6.1b 的替代判準
  （平台 UI 同帳號同操作對照、換帳號／換表的對照組）。
