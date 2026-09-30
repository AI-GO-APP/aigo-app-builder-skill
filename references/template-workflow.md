# 模板盤點與「模板當素材」動線（Phase 1.5 §1.0.5／效果繫結表）

> `SKILL.md` Phase 1.5 只留閘門與一句話；本檔是完整做法。
> 端點以平台 v1.15.4（正式站）原始碼核對；UAT（main）在這幾支端點上與正式站相同，沒有 UAT 限定的差異。

## 目錄

- §1 定位：模板是素材，不是安裝來源（單一路徑）
- §2 模板盤點（所有開發都要做，含既有 app 的增量開發）
- §3 讀模板：`preview` 取回全碼、盤效果清單
- §4 拷問效果繫結 → 效果繫結表
- §5 建殼與自行 provision
- §6 端點與權限總表

---

## 1. 定位：模板是素材，不是安裝來源（單一路徑）

模板的讀者是**接手改造的人與 AI**：看完的人要學會在這個平台上正確地做同類的事。在本 skill 的動線上，
模板一律是**素材**——唯讀取回全碼、抄回本地改造——**不是**安裝來源。

- **不用業務模板的 slug 建 app**。`POST /builder/apps {template_slug: <業務模板>}` 的 provisioning 是全套的：
  灌模板全碼、依 `data_center_schema` **建自建表**、依 `data_references_schema` **建資料引用**（只有金鑰例外）。
  走完才下載改造，表已照模板的預設繫結建好；此時若結論是「這個輸入改成打 API、不要建表」，只能事後清，
  而清自建表有副作用
- **即使效果繫結全採預設，也不走那條捷徑**：兩條路並存時，「全採預設」會變成一條平常跑得好好的隱藏分支，
  偏離預設的那條反而驗證覆蓋最少。單一路徑下，自行 provision 的步驟每次都會跑，壞了當天就知道。
  代價是多打幾支 API（建表、建引用），可接受
- **一律**：`preview` 取碼 → 拷問 → 用 `starter-internal`／`starter-external` 建空殼 → 自行 provision → 灌改造後的 VFS

## 2. 模板盤點（★ 所有開發都要做，含既有 app 的增量開發）

Phase 1.5 四問之後、計畫成形之前做（§1.0.5）。「先查現成的、查不到才自建、不用要說為什麼」這條紀律，
在「表」這一層已經有（資料承載表的「已對照的預設表／不採用理由」）；本節是「整支 app／模組」這一層。

- **新建 app** 盤整個需求；**既有 app 的增量開發**（Phase 0 → Phase 1.5）盤**這次新增的那塊功能**——
  「這塊有沒有模板做過」跟新建時一樣值得問
- **查詢面**（都是現成端點，不必新建）：
  - `GET /api/v1/templates`（`builder.access`；可 `?category=`）——每支的 `slug`／`name`／`description`／
    `long_description`／`category`／`tags`／`access_mode`／`setup_schema`／`version`；**不含**各 schema
  - `GET /api/v1/templates/{slug}`（`builder.access`）——多了 `data_center_schema`／`data_references_schema`／`custom_objects_schema`
  - `GET /api/v1/pub/templates`（匿名、欄位白名單、`?category=`）——不需 token 的快速瀏覽
  - 腳本：`aigo_template.py suites`（依前綴列套組）／`list --suite <前綴>`
- **分類要看 slug 前綴，不要只看 `category`**：官方 `category` 類別少且嚴重失衡（例：`operations` 一類混了
  HR／會計／物流／營造／進出口／製造），照它找會盤歪。能回答「有沒有人做過」的軸線是 **slug 前綴的產業套組**
  （`food-`／`rest-`／`mfg-`／`dcx-`／`trad-`／`logi-`／`cnst-`／`cv-`／`hlth-`／`aprl-`／`acct-` 等），
  而且幾乎每套配一支 `*-portal` 對外端。套組與支數以當下 `suites` 的輸出為準
- **不要重用平台的 onboarding 推薦引擎**：它綁 onboarding 轉型計畫、要先有一個 task；直接打 `GET /templates` 自己比對

**結論三選一**（寫進實作計畫，不寫進需求盤點表）：

| 結論 | 後續 |
|---|---|
| **(a) 有現成的可直接用** | 走 §3–§5：拷問效果繫結 → starter 建殼 → 自行 provision |
| **(b) 有近似的** | 同樣走 §3–§5 抄回本地當起點改造；計畫寫明「從哪支改、改了什麼」 |
| **(c) 都不適用** | 照常從零開發；**寫一句為什麼現有的都不適用**（例：「查過 `cnst-` 套組，計價單流程要跨三家分包商對帳，模板只有單一業主」） |

- (c) 的理由一句就過——不是為了擋路，是讓「重造輪子」這個決定被看見。「沒查」不是理由，「查過 X，因為 Y 不適用」才是
- **即使是 (c)，也讀同領域最接近的一兩支**（§3 的 `preview`）：直接可用是少數，可參考是多數。
  讀得到 code 逆推不出來的東西——平台在該場景的慣用寫法（哪些走 action、哪些走 proxy、哪些留前端）、
  已自帶的正式站行為防禦、資料承載的取捨（什麼進自建表、什麼塞 `custom_data`、什麼引用預設表）

## 3. 讀模板：`preview` 取回全碼、盤效果清單

建 app 之前唯一能讀到模板全碼的管道是 **`GET /api/v1/templates/{slug}/preview`**（僅需登入）：
回 `{slug, name, version, files: {路徑: 內容}}`。

```bash
uv run --project scripts python scripts/aigo_template.py preview <slug> <本機參考目錄>   # 目錄須不存在或為空
uv run --project scripts python scripts/aigo_template.py effects <slug>                 # 盤效果清單
```

- **參考目錄不是 app 專案目錄**：app 由 starter 建殼（§5），這裡的碼是抄過去改造的素材；SDK 檔
  （`src/api.ts`／`db.ts`／`action.ts`…）以 starter 注入的為準，不從模板抄
- `preview` 只回 **UTF-8 文字檔**（圖片等二進位檔會被略過），而且**不含 `_template.json`**——
  那個檔是建 app 當下才由平台寫進 VFS。所以模板的 `required_egress` 宣告**沒有唯讀端點看得到**，
  對外呼叫只能從 `actions/*.py` 的字面 `ctx.http.call` slug、README 與 `setup_schema` 推
- **效果清單**：模板若在 `_template_meta.json` 帶了 `effects` 宣告（Template Protocol：每個 I/O 的 `id`、
  預設繫結 `default_binding.via`、可替換繫結 `alternatives`、`binding_params`），**以宣告為準**。
  還沒有宣告的模板（目前多數）從 `data_center_schema`（自建表）、`data_references_schema`（預設表引用）、
  `setup_schema`（參數／金鑰）與 `actions/*.py` 的 `ctx.*` 呼叫推斷——`effects` 指令兩種都會印
- 同時讀 README（「為什麼這樣設計」「對外介面」若有）與 `docs/recipes/`：「刻意不做什麼」是**不能當缺陷修掉**的取捨

## 4. 拷問效果繫結 → 效果繫結表

在 Phase 1.5 完成（下一步就是建 app，過了就來不及）。一輪問完，資訊不足就問、不猜：

1. **第一題：`access_mode`**——`internal`（凡有登入者）或 `external`（匿名頁必須留在 Custom App 內的例外）。
   建立後不可改，決定用哪支 starter 建殼（`custom-app-dev-guide.md` §26.1）；模板本身的 `access_mode` 只是參考
2. **逐個效果問繫結**：這個輸入／輸出要接到哪裡——`owned_table`（自建表）／`platform_table`（預設表引用）／
   `http`（打外部 API）／`frontend`（只在前端顯示）／`approval`（簽核）／`messaging`／`knowledge`／`erp`／`none`（不要這個效果）。
   用業務語言問（「核准後的計價單要留在平台的表，還是送去你們的請款系統？」），不要問「via 要填什麼」
3. 採 `owned_table`／`platform_table` 的列照常過資料承載表（計畫第 3 項）；採 `http` 的列照常過外部 API 盤點（第 4.6 項）

**產出：效果繫結表**（寫進需求盤點表 `resources/new_app_requirements_template.md` 的「效果繫結表」一節，帶進計畫）

| 效果 | 預設繫結 | 本次採用 | 落實動作 |
|---|---|---|---|
| `billing.approved` | `owned_table: cnst_billings` | `http` | 建外部服務（經用戶確認）、設 `BILLING_API_KEY`、改 ports 實作 |
| `projects.list` | `owned_table: cnst_projects` | 同預設 | `POST /data-center/tables` 建表＋登記引用 |

- **落實動作要能執行**：寫成端點或 code 變更，不寫「視情況」
- **每個非預設繫結都要真的改 code**：換掉 ports 層那個函式的實作（`src/ports/`、`actions/_shared/ports.py`），
  其餘 code 不動——不能只是表上寫了、code 還照原樣打 `ctx.db`。模板沒有 ports 層時，找出該效果的**所有呼叫點**逐一改，
  並在計畫裡列出檔案
- ★ **計畫閘門**：效果繫結表每一列的「落實動作」都要在計畫裡有對應項目；表上有、計畫沒有，不得進 Phase 2

## 5. 建殼與自行 provision

計畫經用戶同意後（Phase 1.5 閘門）依序做：

1. **建空殼**：`POST /api/v1/builder/apps {name, template_slug: "starter-internal" | "starter-external"}`
   （依 §4 第一題）→ `aigo_auth.py app add` 登錄。starter 是空白腳手架，平台的表／引用 provisioning 實質是 no-op
2. **清 starter 的示範**：示範 action（`actions/summarize_leads.py` 等 leads 範例）與 **`_template.json`**
   （宣告 `required_egress: openai`）**一起刪**——不刪，發布會 409 `EGRESS_NOT_READY`（只刪 action 仍擋）。
   `_template.json` 是 starter 的宣告，不是本 app 的：本 app 的對外呼叫以 action 裡的字面 `ctx.http.call` slug 為準，
   發布閘門與 `egress_preflight()` 都會掃；**只有動態 slug**（第一參數不是字面字串）才需要自己寫一份
   `_template.json` 的 `required_egress` 把它宣告出來。刪法見 `custom-app-dev-guide.md` §26.2
3. **依效果繫結表 provision**（每一步都是正式資料寫入，過 `data-operations.md` §3.5 寫入閘門）：
   - `owned_table` → 先查租戶既有自建表能不能重用（Phase 0）；要新建 → `POST /data-center/tables`＋
     `POST /data-center/tables/{key}/fields`（兩步命名法，規則 18.5）→ **`POST /refs/apps/{app_id}` 登記引用**
     （REST 建表不會自動登記，沒登記 `ctx.db` 會說表不存在）
   - `platform_table` → `POST /refs/apps/{app_id}`（欄位以引用面 columns 為準）
   - `http` → 外部服務＋授權＋金鑰，**AI 可代設，但每一支都要先過確認**（`custom-app-dev-guide.md` §25.2）
   - `approval`／`messaging`／`knowledge`／`erp` → 依各效果面既有規則（簽核攔截規則 24、`ctx.erp` 白名單等）
4. **灌改造後的 VFS**：模板碼抄進 app 專案目錄改造（非預設繫結改 ports 實作）→ Phase 3–4 的同步、編譯、驗證、發布

## 6. 端點與權限總表（v1.15.4 核對）

| 端點 | 用途 | 權限 |
|---|---|---|
| `GET /api/v1/templates`、`GET /api/v1/templates/{slug}` | 模板清單／詳情 | `builder.access`（或 `system.admin`） |
| `GET /api/v1/templates/{slug}/preview` | 全碼唯讀預覽 | 登入即可 |
| `GET /api/v1/pub/templates` | 匿名快速瀏覽（白名單欄位） | 無 |
| `POST /api/v1/builder/apps` | 建 starter 空殼 | `builder.access` |
| `POST /api/v1/data-center/tables`、`POST …/tables/{key}/fields` | 建自建表、加欄 | `datacenter.schema_write`（`system.admin` 直通） |
| `POST /api/v1/refs/apps/{app_id}` | 登記資料引用 | `builder.access` |
| `POST /api/v1/builder/apps/{app_id}/egress-services`、`PUT …/authorized-egress-services` | 建外部服務（預設授權本 App）、改授權清單 | `builder.access` ＋ 本 App 擁有者或 `system.admin` |
| `POST /api/v1/actions/apps/{app_id}/secrets`、`PUT /api/v1/actions/secrets/{secret_id}` | 設金鑰 | `builder.access`（且看得到這支 app） |
