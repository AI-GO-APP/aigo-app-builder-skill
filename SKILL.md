---
name: aigo-builder
description: >
  Use when working on an AI GO Custom App (ai-go.app)：開發前端（React + TypeScript）
  或 Server-Side Action（Python）、部署與驗證、從零規劃新 App（需求盤點、
  Custom App／Hosted App 產品線判斷）、規劃使用者授權架構（角色、app 角色白名單、
  批次邀請內外部人員）、規劃資料架構（資料中心自建表 / Data Reference）、
  接 Webhook 或設定 App 排程、將現有系統或整套專案
  （前端＋後端＋DB；Supabase / Google Sheet / MySQL 等）搬入／遷入 AI GO。
---

# AI GO Custom App Builder

本 Skill 協助 AI Agent 開發 AI GO Custom App。支援 Antigravity / Claude Code / Cursor。

## 設計理念

AI GO Custom App 採用 **TypeScript（前端）+ Python（後端）** 的精選語言組合，
具備低出錯率、靜態型別安全、LLM 生成最佳化等特性，最適合 AI Coding 新手與非技術工作者
開發可靠的公司內部系統。

資料存取統一走 API，不直連資料庫——避免非技術 AI Coder 重複建立類似的表或欄位。
AI GO 預先定義了中小企業通用的資料庫結構（預設表），同時保有**自建表**的擴充彈性。

> 詳見 `references/custom-app-dev-guide.md` §21 架構設計理念。
> **術語先讀 `CONTEXT.md`**——表只有**預設表／自建表**兩大類；
> 「CustomObject / Data Reference / 延伸欄位 / app_domain」是機制詞不是第三類表。
> 六個詞容易混用，混了就會寫錯 code。（舊文件的「SaaS 表」＝預設表，已停用）

## Phase -1：Skill 自我更新（每次觸發時執行，發現新版即強制同步）

> 若已裝 SessionStart hook（見 README「保持更新」），本階段會自動被跳過（節流），
> 不必重複執行。

```bash
python scripts/check_update.py     # macOS / Linux 用 python3
```

- **零相依、不走 uv**——標準函式庫實作，任何專案下都能直接跑。
- **腳本自己動手，不徵詢**：只要遠端 `VERSION` 比本地新，腳本就**直接把本機所有已註冊
  安裝強制同步到遠端 main**——git 安裝 `fetch` + `reset --hard` + `clean`，複製式安裝
  （skills CLI）下載 `main.zip` 鏡像覆蓋。本地修改、分岔的 commit、多出來的檔案一律被
  遠端取代；不問使用者、不等回覆。你不需要也**不可以**替使用者做「要不要更新」的決定。
- **無輸出 = 沒事**：已是最新版、離線、或同一版本差 3 小時內已失敗過一次都靜默結束，
  直接進 Phase 0。（節流只抑制網路抓取與失敗重試；版本比對每次都做，
  所以本機多份安裝共用遠端快取，任一份落後都抓得到。）
- **有輸出 = 已經同步過了（或同步失敗）**，逐行處理：
  - **「已同步」**→ **立刻重新讀取 `SKILL.md` 與相關 `references/`**，讓新版指令在本回合
    就生效；把版本落差與變更摘要**告知**使用者（告知，不是徵詢——更新已完成，
    沒有拒絕的選項）。
  - **「失敗」**→ 把失敗原因與腳本印出的手動指令給使用者，請他們處理完再繼續。
    若同時有「破壞性變更」警語（`--json` 為 `"breaking": true`）：這類版本代表
    **停在舊版就會失敗，且失敗訊息通常不指向真正的原因**（例如 1.7.0 的租戶網址規則，
    症狀是與密碼錯完全同形的 401）——明確告訴使用者「不處理的話會遇到什麼」，
    後續遇到相關錯誤時**優先回頭懷疑版本落差**，不要往其他方向深掘。
  - **「開發副本，略過」**→ 那份是正在改 skill 的工作區（本地版本高於遠端，或 git 不在
    main／master 分支），不是安裝，不用處理也不用提。
- **註冊表只認得執行過 1.17.0+ 檢查的安裝**——使用者若提到其他專案也裝了本 skill
  卻沒被同步到，提醒他們到該專案觸發一次 skill，之後那份就會入列、下次一起被同步。
- **禁止繞過**：不要為了保住本地修改而跳過本階段、改用 `--check-only`、或建議使用者
  這麼做。要改 skill 內容，走 repo 的 PR；裝在本機的副本只能是遠端 main 的鏡像。

## 源頭意圖分流（進入流程前先判讀）

任何工作開始前，先分清用戶的意圖是哪一種——三條線的起手完全不同：

| 意圖 | 走法 |
|------|------|
| **開發新 App**（從零做新功能） | 走主流程（Phase 0 →），**但建 app 之前必先完成 Phase 1.5 §1.0 的需求盤點**（四問＋Custom App 能力邊界核對，對稱遷入線的 §2.0）——用戶開場的一句話是題目不是需求；產品線判斷（Custom／Hosted／混合）與授權架構（誰能開、掛什麼角色）在 Phase 1.5 定案後才建 app |
| **現有 App 遷入**（有既存系統／repo／DB 要搬進 AI GO） | **先讀 `references/migration-workflow.md`，從 §2.0 的 stack 盤點做起**（架構師視角：先盤前端／後端／資料的結構，再分流產品線），之後才回主流程 |
| **資料操作，不開發 app**（查、改、批次、匯出自己有權限的資料） | **走 `references/data-operations.md` 的短流程**：`aigo_auth.py status` → `aigo_data.py me` → `perm-check` → `openapi` 查路由 → `call`／`export`。不進 Phase 0 的 VFS review、不建 app、不走 proxy——用登入者自己的 token 與權限。**寫入前必過該檔 §3.5 的寫入閘門**——這條線打的是唯一一份正式資料，沒有沙箱也沒有還原路徑 |
| **成員／角色管理，不開發 app**（批次邀請、建連結、開角色、改權限、設 app 角色白名單） | **走 `references/member-admin.md`**（§2 端點、§4 邀請流程、§5 角色 CRUD）：登入者本人的 JWT，不建 app、不走 `/open/*`；寫入同樣過 `data-operations.md` §3.5 閘門（邀請與改角色都是不可逆的正式資料） |

**資料操作意圖的偵測訊號**：用戶要「查一下／改一批／匯出／灌資料」而沒有提到畫面、功能、
app；或問「我有沒有權限看某表」。這條線的權限是使用者在平台介面上的權限：預設表依模組
角色（`sale.read` 等），自建表需 `builder.access`——先跟用戶說清楚再動手，寫入前必經用戶確認。

**遷入意圖的偵測訊號**（出現任一就主動確認，不要等用戶自己說「遷移」）：
用戶提到現有系統、既有網站、某個 repo、Supabase／Google Sheet／MySQL 等資料來源、
「搬過來」「轉移」「改用 AI GO」等字樣；或 Phase 0 時發現工作目錄是一個
非 AI GO 結構的完整專案。判成遷入後，多系統（≥2 個）再疊加 Phase 1.25 的全局盤點。

## Phase 0：Review 現有 Code（★ 強制步驟）

> **每次開始任何開發工作前，必須先執行此步驟。**

### 流程

1. **找工作區、定目標**：先跑 `uv run --project scripts python scripts/aigo_auth.py status`
   ——它會從目前目錄往上找最近的 `.aigo/config.json`（工作區＝一個租戶），印出生效的租戶、
   身分來源、app 登錄表與警告。需要 app 的工作一律用 `aigo_auth.resolve_app()` 取目標
   （`--app`／`AIGO_APP` → `default_app` → 登錄表唯一一筆 → 多筆未指定就**報錯列出 alias，不猜**），
   **不要自己讀 config 抓 `app_id`**。登錄表為空是合法狀態（純資料中心工作不需要 app）——
   只有要動 VFS／發布時才要求有 app。找不到工作區 → 進 Phase 1 建立
2. 呼叫 `aigo_auth.get_token()` 取得 JWT——**不要向用戶要密碼**。
   該函式依序嘗試「未過期的 Token 快取 → refresh_token 換發 → 用憑證檔
   （`<專案>/.aigo/.env` → `~/.aigo/.env`）的帳密登入」，正常情況下完全無感。
   - 只有在兩個憑證檔與環境變數都沒有憑證時才會拋 `RuntimeError`，
     此時把它的訊息原樣轉給用戶（內含設定指引），請對方**自己**填一次憑證檔。
   - **絕不代替用戶輸入或寫入密碼**，也不要把密碼放進指令列
     （會留在 shell 歷史紀錄）。用戶若在對話中貼出密碼，提醒對方改填 `~/.aigo/.env`
     並更換該密碼。
4. `GET /api/v1/builder/apps/{app_id}` 取得完整 App 資訊含 VFS
5. 分析 VFS 結構並輸出 Review 報告：
   - 列出所有檔案及大小
   - 標記 SDK 檔案 `[SDK]`（不可修改：api.ts, db.ts, action.ts）
   - 標記 Runtime 注入檔 `[INJ]`（不可修改：data.json, db.json, actions.json）
   - 解析 App.tsx 路由結構
   - 解析 _manifest.json 頁面清單
   - **Legacy 偵測**：`data.json` 有內容、或 code 用 `listRecords`／`submitRecord`／
     `ctx.db.query_object` → 標記為 legacy CustomObject（見 `CONTEXT.md`）。
     存量功能維持原樣即可運作，**但不要往上加東西**，新資料需求一律開自建表
   - **builder.access 破口偵測**（★ internal app 必查，規則 31）：前端檔
     （排除 `src/api.ts` 本體）有 import `../api` 或呼叫 `queryTable`／`insertRow`
     等自建表方法 → 一般員工執行期必 403，**標記為必改**並列出受影響檔案，
     修復流程見 `references/data-center.md` §7.5（`aigo_review.py` 會自動標記）
   - **解析 actions/manifest.json 的 webhook 宣告**：列出所有 `"webhook": true` 的 action
     與 `receive_webhook`，這些是對外端點
   - **盤點 Data Reference**（★ 重要）：用 `GET /api/v1/refs/apps/{app_id}`，
     **不要讀 `src/db.json`**——它是執行期注入檔，VFS 裡實測恆為 `{}`，
     即使引用全部註冊成功也一樣（見 `references/platform-behaviors.md` §6）
     - 列出所有預設表名稱和欄位結構
     - 標記哪些表有 `custom_data`（JSONB）欄位
     - 列出每張表的權限（read/create/update/delete）
     - 統計現有資料筆數和 `app_domain` 分布
   - 檢查 App.css Shadow DOM 相容性
6. **盤點租戶既有自建表**（★ 強制，不可跳過）
   - `GET /api/v1/data-center/tables`（`aigo_data_center.py` 的 `list_tables()`）
   - 自建表是**租戶級**資源、**不在 VFS 裡**——同租戶的其他 app 建的表，這個 app 也看得到、用得到
   - 列出每張表的實體名、顯示名、欄位結構
   - 這一步的目的是**避免重複建表**：兩個 app 各建一張「客戶」表 = 資料分裂成兩份
   - **順手掃命名**（★ 規則 18.5）：看每張表的 `physical_name`——
     命中 `^tbl(_\d+)?$`、欄位 `^col(_\d+)?$`、延伸欄位 `^ext(_\d+)?$` 就是中文顯示名生出來的保底名
     （`aigo_data_center.py` 的 `audit_table_naming()`／`format_naming_audit()` 已封裝），
     記進盤點結果（分級與處置見 `references/data-center.md` §11.1）。
     **這一步只盤不動手**——重建式改名是另一條流程，要先出計畫書給用戶同意
7. **盤點既有排程**（若 app 已上線）
   - `GET /api/v1/builder/apps/{app_id}/crons`（`aigo_review.py` 的 `fetch_app_crons()`；App 開發面，`builder.access` 可讀），
     確認有哪些排程綁在本 app 的 action 上
   - republish 或改動 action 名稱前必須知道這些，否則會把排程觸發到自動暫停
8. **盤點對外呼叫與 Egress**（若 code 內有 `ctx.http.call` 或 `import httpx` 等對外請求）
   - 從既有 action 原始碼撈出所有 `ctx.http.call` 的 egress slug 與殘留的對外網域，列成清單
   - 提醒用戶到 Builder（`/builder/{app_id}`）的「外部服務」tab 確認每個 slug 都已
     建立**同名外部服務**（base_url 域名白名單）**且授權給本 App**——
     舊 code 能跑不代表新加的服務也通
   - 舊 app 若靠平台代灌金鑰（不自帶 `Authorization`）→ **標記為必改**：
     閘道已不再注入憑證（ADR 0010），金鑰要改存 `ctx.secrets`、action 自組 header
   - 發現 raw `import httpx / requests / urllib.request` 直連外部的 action → **標記為必改**：
     runner 是 default-deny egress，raw 連線一律 timeout（見 Phase 3「呼叫外部 API」）
9. **確認已完全理解現有結構後，才可進入開發**

`scripts/aigo_review.py` 的 `review_app()` 一次做完 VFS 分析 + 步驟 6／7 的租戶級盤點，
`format_review_report(app_info, analysis, custom_tables, crons)` 輸出完整報告。

> ⚠️ `fetch_custom_tables()` 取不到時回**空清單**（權限不足／端點異常）。
> 空清單不等於「租戶沒有表、可以放心建新的」——要先確認是真的沒有。

## Phase 1：環境設定

### 租戶空間網址規則（★ 不可違反）

**所有登入與 API 一律走租戶子網域：`https://[tenant].ai-go.app/*`**

```
https://urfit.ai-go.app/api/v1/auth/login     ✅
https://demo.ai-go.app/api/v1/builder/apps/…  ✅
https://ai-go.app/api/v1/auth/login           ❌ 主站 apex，不是租戶入口
https://xxx.apps.ai-go.app/…                  ❌ Custom App 沙箱域，不是 API host
```

- `tenant` = 用戶平時登入時**網址列的第一段**。不確定就直接問用戶，或請對方貼登入後的網址。
- 平台是用 **Host header** 解租戶的（`{tenant}.ai-go.app/api/*` 同源代理到後端並保留 Host），
  所以 base_url 打哪個 host，就等於宣告「要登入哪個租戶」。
- apex `https://ai-go.app/login` 已被收斂成 **workspace finder**（找工作區的頁面），不是登入頁；
  apex 的 **API 登入實測已回 401**（2026-08-08，正確帳密）。
- ⚠️ **打錯租戶的症狀是 401「帳號或密碼錯誤」**——平台的反帳號列舉設計讓「這個 email 不在
  這個租戶」與「密碼打錯」回**完全相同**的 401（連是否跑滿一次 bcrypt 都一樣）。
  看到 401 時**先確認 base_url 的租戶對不對**，不要一路往密碼方向查。
- 腳本端已把規則寫死在 `aigo_auth.resolve_base_url()`：**沒有預設值**，
  填 apex 會直接被擋下並印出規則。不要在任何地方硬編 `https://ai-go.app`。

### 三層模型：裝置 → 工作區 → app（1.22.0 起）

同一套機制從「1 租戶 1 app」平順長到「N 租戶 N app」，使用者不需要先自我歸類：

| 層 | 落點 | 範圍 | 規則 |
|---|---|---|---|
| 裝置 | skill **一份**（user scope）；`~/.aigo/.env` 放預設帳密 | 每台機器 | 不 by app、不 by 租戶裝多份；`AIGO_TENANT` 可選，多租戶機器建議留空 |
| 身分 | `<工作區>/.aigo/.env` 覆寫 → `~/.aigo/.env` | 每人每租戶 | 同 email 在不同租戶是不同帳號，租戶不同就在工作區覆寫 |
| 工作區 | 含 `.aigo/config.json` 的目錄＝**一個租戶**，內含 0..n 個 app | 每個目錄 | 多一個租戶＝多一個目錄；多一個 app＝登錄表多一筆；token.json 跟工作區走 |

### 配置檔 `.aigo/config.json`（schema 2）

```json
{
  "schema": 2,
  "base_url": "https://urfit.ai-go.app",
  "email": "",
  "default_app": "erp",
  "apps": {
    "erp":  {"kind": "custom", "id": "<uuid>", "slug": "", "name": "", "access_mode": "internal", "app_domain": "erp"},
    "site": {"kind": "hosted", "id": "<uuid>", "slug": "", "name": "", "integration_id": "", "path": "../site-src"}
  }
}
```

- `apps` 以 **alias** 當 key——alias 是對話與指令用的短名，UUID 只從表裡查；`apps` 可為空
- 舊格式（頂層 `app_id`…）讀入時自動升級成 `apps.default` 一筆，檔案不動；
  `aigo_auth.py config migrate` 才會改寫檔案
- Hosted App 的 `integration_id` 是隨附整合 id，預設表引用的 API 用它當 key（`hosted-apps.md` §5）；
  Deploy Token 放工作區 `.aigo/.env` 的 `AIGO_DEPLOY_TOKEN__<ALIAS 大寫>`，
  `aigo_auth.py run <alias> -- aigo hosted deploy …` 會匯出成 `AIGO_DEPLOY_TOKEN` 再執行

**選 app 的順序固定，不猜**（`resolve_app()`）：`--app`／`AIGO_APP`（alias、UUID 或前綴）
→ `AIGO_APP_ID`（相容舊版）→ `default_app` → 登錄表唯一一筆 → 其餘報錯列出 alias。
單 app 工作區永遠走到「唯一一筆」，感覺不到登錄表存在。

| 指令 | 作用 |
|---|---|
| `aigo_auth.py setup-workspace <dir>` | 在租戶目錄建 `.aigo/config.json` 骨架＋工作區 `.env` 範本（拒絕 skill 安裝目錄） |
| `aigo_auth.py app add <alias> --id <uuid>` | 登錄 app：打平台自動判定 custom／hosted 並回填 slug、name、access_mode／integration_id |
| `aigo_auth.py app list`／`default <alias>`／`remove <alias>` | 登錄表維護 |
| `aigo_auth.py status` | 唯一診斷入口：工作區、租戶與來源、身分與來源、app 表、token、警告（cwd 在 skill 目錄內、多份安裝、shell 覆寫與 config 不同） |
| `aigo_auth.py run <alias> -- <cmd>` | 在該 app 環境下執行指令（Hosted CLI 用） |

#### base_url 的三層來源（`resolve_base_url()`，特定性越高越優先）

| # | 來源 | 定位 |
|---|------|------|
| 1 | shell 環境變數 `AIGO_BASE_URL` → `AIGO_TENANT` | 臨時覆寫、CI |
| 2 | `<專案>/.aigo/config.json` 的 `base_url` | 這個專案綁定的租戶 |
| 3 | `.env` 的 `AIGO_BASE_URL` → `AIGO_TENANT`（`~/.aigo/.env`） | 機器級預設 |

- **建議做法**：只服務單一租戶的機器，在 `~/.aigo/.env` 填 `AIGO_TENANT=urfit`
  即可全機器通用——寫前綴比每次抄整串網址不容易錯。
- **② 必須贏過 ③**：機器級 `.env` 是預設值不是唯一值。要在同一台機器開別的租戶的專案，
  就在該專案 `config.json` 填完整 `base_url` 覆寫。
- 三層都沒有 → 直接拋錯附設定指引，**不會 fallback 到 apex**。
- `aigo_auth.py status` 會印出**實際生效的網址與它來自哪一層**——查 401 的第一站。

### 設定流程

1. `aigo_auth.py status`——從目前目錄往上找工作區（`.aigo/config.json`）
2. 找不到 → `aigo_auth.py setup-workspace <租戶目錄>` 建立骨架（`base_url` 會留空；
   **不可放在 skill 安裝目錄內**，指令會擋）。同一台機器要開第二個租戶＝再開一個目錄
3. 引導用戶：
   - 前往 AI GO 後台 `https://[tenant].ai-go.app/dashboard`
   - **記下網址列的租戶前綴**，填入 `.aigo/config.json` 的 `base_url`
   - 確認帳號具備 `builder.access` 權限
   - **既有 App**：進入 Builder → Custom Apps → 記下 App 的 UUID (`app_id`)
   - **新 App 可直接用 API 建立，不必走 UI**（2026-09-01 實測）：
     `POST /api/v1/builder/apps`，`name` + `template_slug` 必填——
     `starter-internal`（**預設，凡有登入者都是它**——員工與外部人員都是租戶成員，用角色分流）；
     `starter-external` 只在計畫的 app 分配表明寫時才用（匿名頁必須留在 Custom App 內的例外）；
     **access_mode 由模板決定、建立後不可改**，回應的 `id` 就是 `app_id`。
     ★ **新建情景不在這裡臨場選模板**：先完成 Phase 1.5（§1.0 需求盤點 → 產品線與模式判斷
     → 計畫確認），模板 slug 照計畫的 **app 分配表**——計畫未確認前登錄表留空是合法狀態。
     判走 Hosted App 的 app 不走這個端點（`references/hosted-apps.md` §3）。
     完整契約與「起手式帶示範檔案要先清」等注意事項見
     `references/custom-app-dev-guide.md` §26
   - 填入 `.aigo/config.json` 的 `email`；app 用 `aigo_auth.py app add <alias> --id <uuid>` 登錄
     （會自動回填 slug／name／access_mode；第一筆自動成為 `default_app`）。
     一個工作區有多個 app 時每個都登錄一筆，操作時用 alias 指定
4. 建立憑證檔（**整台機器只需做一次**）：
   ```bash
   uv run --project scripts python scripts/aigo_auth.py setup    # 產生 ~/.aigo/.env 範本（機器級）
   ```
   請用戶自己在 `~/.aigo/.env` 填入 `AIGO_EMAIL` / `AIGO_PASSWORD`，
   然後 `uv run --project scripts python scripts/aigo_auth.py login` 驗證。
5. 隨時可用 `uv run --project scripts python scripts/aigo_auth.py status` 確認**實際生效的租戶空間**與憑證狀態
6. 驗證連線：`get_token()` → `resolve_app()` → GET App，`assert_remote_matches()` 確認遠端與登錄表一致

### 憑證規則（★ 不可違反）

- 帳密預設放**機器級**的 `~/.aigo/.env`；`<工作區>/.aigo/.env` 可覆寫個別鍵
  （該租戶用另一組帳號、Hosted App 的 `AIGO_DEPLOY_TOKEN__<ALIAS>`），先找到的優先。
  兩者都在 `.gitignore` 涵蓋範圍內。app 的 UUID 放 `config.json` 的登錄表，不放 `.env`
- **絕不把憑證寫進 Skill 安裝目錄**（`.claude/skills/aigo-builder/` 等）：
  `npx skills update` 會刪掉整個 skill 資料夾再重建，放在裡面的 `.env` / `token.json`
  會直接消失且無從還原。執行任何 `aigo_auth.py` 指令前，先確認 CWD 是**用戶的 app 專案**，
  不是 skill 目錄；或用 `AIGO_PROJECT_ROOT` 明確指定。
- **不得**寫進 `config.json`、原始碼、commit、log 或任何指令列參數。
- Token 快取在 `<專案>/.aigo/token.json`，過期自動換新；`aigo_auth.py logout` 可清除。
- Agent **不代為輸入或寫入密碼**——憑證檔一律由使用者本人填寫。

## Phase 1.25：多系統遷入盤點（條件觸發）

> **觸發條件**：用戶有 **2 個以上外部系統**（各自帶 Supabase / Google Sheet / MySQL
> 等 DB）要遷入 AI GO。僅遷入 1 個系統或純新建 App → 跳過，直接進 Phase 1.5
> （純新建從 §1.0 需求盤點起手）。

> 觸發時 → 讀 `references/migration-workflow.md` §1。目的是在任何單一 App 開始
> Phase 1.5 之前建立**全局視圖**，避免各 App 各自為政導致資料架構混亂；
> 產出的「遷入全景表」會在後續各 App 的 Phase 1.5 持續參照。

## Phase 1.5：需求盤點與實作計畫（★ 強制步驟）

> **在任何開發工作開始前（包含建立 app、從模板建立），必須先完成需求盤點、提出實作計畫
> 並獲得用戶確認。禁止跳過此步驟直接進入 Phase 2 寫 code；也禁止在 §1.0 盤點與計畫確認前
> 建立 app**——模板＝`access_mode`，建立後不可改。

### 1.0 需求盤點（★ 新建情景的起手，對稱遷入線的 §2.0）

遷入線靠 `migration-workflow.md` §2.0 把系統的 stack 形狀盤出來再分流；新建線沒有 repo
可盤，**輸入只能來自用戶，所以要主動問**。用戶開場的一句話（「幫我做個報修系統」）
**是題目，不是需求**——拿題目直接寫計畫、再拿計畫過閘門，等於讓用戶替你補作業。

- **資訊不足就問，不猜**；用戶答不出來就給選項（下表右欄），不要替他選
- 一輪把四問問完（不要一題一題擠牙膏），但**四問缺一不進 1.5**
- 已在對話中明確講過的不重問；遷入情景這四問由 §2.0 盤點推導，不另問
- **常見情況幾句話就答完**（內部成員用、沒有對外、沒命中邊界 → 一個 Custom App）——
  問是為了確認沒有例外，不是把簡單需求問成專案訪談

| # | 問什麼 | 為什麼非問不可 | 用戶答不出時給的選項 |
|---|---|---|---|
| 一 | **誰在用**——列出**使用者群**（哪些部門的員工、外部經銷商、客戶、夥伴…），以及有沒有**不登入就要能看**的頁 | 使用者群餵第 1.7 項授權架構（每群一個角色、每支 app 一份角色白名單）；**凡有登入者一律 internal**，內外人員都是租戶成員，不因「有外部人」改模式；只有匿名頁才影響產品線（問題三） | 「只有員工」／「員工＋外部經銷商（或客戶）」／「還有不登入就要看的頁」 |
| 二 | **做什麼**——功能清單、每個功能的使用場景與使用者流程、涉及哪些資料實體 | 計畫第 1 項全部來自這裡；資料實體清單餵第 3 項的雙軌分流 | 請用戶用「誰、在什麼時候、要完成什麼」各講一句 |
| 三 | **對外面向**——需不需要自有網域、SEO、讓匿名訪客瀏覽整站？ | 公開 web 資產 → Hosted App；Custom App 的 `/runtime`＋HashRouter 做不了 SEO 與自有網域，`/pub` 只適合少數公開頁 | 「純內部、登入後才能用」／「有幾頁不登入也要看」／「整個站要對外、要自己的網址」 |
| 四 | **機制需求**——逐條核對 `references/product-line-decision.md` §2 的 **Custom App 能力邊界表** | 命中的每一條是 Hosted 訊號或要改設計；**留到寫 code 才發現＝整段白做** | 把邊界表拿給用戶逐條勾 |

另外順帶盤（不決定產品線，計畫第 4.5–4.7 項要用）：第三方 API、外部 webhook、定時工作、檔案上傳。

**產出：需求形狀結論**（照 `resources/new_app_requirements_template.md` 填，帶進 1.5）：

```
使用者群：<群名清單>（有登入者 → internal；匿名頁 → 見面向）
面向：應用介面 / 公開 web 資產 / 混合（→ 拆）
邊界命中：<條目，每條標「Hosted」或「改設計」>；或「無」
功能群：<群名 → 功能清單>（2 群以上不同目的 → 第 2 項拆分）
資料實體：<清單>
外部整合：API <slug 清單> / webhook <來源> / 排程 <頻率> / 檔案 <有無>
```

### 計畫內容必須包含

1. **需求分析**（新建：由 §1.0 問題二的答案整理；遷入：由 §2.0／§2.2 盤點整理）
   - 用戶要實現的功能清單
   - 每個功能的目標使用場景
   - 預期的使用者流程

1.5. **產品線與模式判斷**（Custom App vs Hosted App；登入者一律 internal；★ 結果不可逆）
   - **SSOT 在 `references/product-line-decision.md`**，兩條路共用——判斷前讀它
   - **預設立場：一個 Custom App `starter-internal`**。新建 app 絕大多數就是這個答案；只有命中訊號才偏離：
     功能群目的不同 → 多個 Custom App；
     公開 web 資產（自有網域／SEO／整站匿名）→ Hosted App；邊界表命中「Hosted」→ Hosted 或**混合**
     （業務介面 Custom ＋ 命中的部分獨立 Hosted，共用資料落平台側、Hosted 走 Open Proxy）
   - **使用者有內有外不改模式、不拆模式**：員工與外部經銷商／客戶都是租戶成員，差別在角色與
     app 角色白名單（第 1.7 項）；要拆也是拆成兩支 internal app 各掛不同 `access_role_ids`
   - **兩問定位，先問有沒有登入者、再看形狀**：問題一「有登入者嗎、誰是匿名的」——有登入者 → internal，
     只有匿名 → Hosted public，兩者都有 → 拆（新建取 §1.0 問題一；遷入問原系統）；
     問題二「形狀」定 Custom／Hosted／混合
     （新建取 §1.0 的面向＋邊界命中；遷入取 §2.0 的 stack 形狀，對照表在 `migration-workflow.md` §2.1）
   - **不可逆與硬前提**：`access_mode` 由模板決定、建立後不可改 → **app 等本計畫確認後才建**；
     `internal` 不能開匿名（400）→「內部工具想給訪客看一頁」要在此刻攤開：拆成 Hosted public 靜態頁，
     拆不成才落到 `starter-external` 這個例外，且匿名**還要平台核可、無 SLA**（dev-guide §15.1）
     → 排程時列成「等平台」的一步；拿不準 Custom vs Hosted 給 `hosted-apps.md` §1 差異表選，
     拿不準有沒有匿名頁回頭問，**不可用預設值帶過**
   - **Hosted 當 Custom 的後端**（常駐進程接在 Custom 介面後面）→ Hosted 設 `public` ＋ 自驗簽章，
     `internal` 的 proxy 會把 Server Action 的呼叫導去登入（`product-line-decision.md` §5）
   - 判走 Hosted App 的 app → `references/hosted-apps.md`，不走本 skill 的 Phase 2–4；
     「Hosted = 整套搬」指程式不指資料，業務資料一律落平台的表（`hosted-apps.md` §7.1）；
     **部署前必過 `hosted-apps.md` §3.0 的 `always_on` 決策閘**——預設 `false`，只有容器內自跑排程／長連線／
     冷啟動業務上不可接受三種情況才開，問 owner 的是業務問題不是「要不要常駐」
   - **產出：app 分配表**（每個 app 一列，寫進計畫、確認後照表建 app）
     `| alias | 產品線 | 模式（模板 slug / visibility） | 負責的功能群 | 拆分理由 |`
     ——預設情況就是一列 `| <alias> | Custom | starter-internal | 全部 | — |`
     ——判走 Hosted 的列，拆分理由欄後附常駐決策：`常駐＝關（預設）`，或 `常駐＝開；理由 X；退場條件 Y`
     （`hosted-apps.md` §3.0 三問的結果，問答填在需求盤點表 §四.1；§3.4 部署後會讀回核對）

1.7. **授權架構選型**（★ 強制；SSOT 在 `references/member-admin.md` §1，兩條路共用）
   - **立場**：AI GO 帳號體系是內外人員共用的——凡要登入的人都是租戶成員，用**角色**分「能做什麼」、
     用 app 的 **`access_role_ids`** 分「看得到哪支 app」。不在 app 內另建使用者表、角色表、登入流程
   - **三問**：① 使用者群有哪些 → 每群一個角色（沿用或新開，新開的 permissions 必須是建立者權限的子集）；
     ② 每支 app 誰能開 → `access_role_ids`（空＝全租戶成員；Custom 與 Hosted 都有此欄）；
     ③ 人怎麼進來 → 已是成員／邀請（一人一連結、落點直達 app）／既有系統搬遷（`member-admin.md` §7）
   - **要攤開的陷阱**：非員工帳號沒有員工列，租戶資料存取規則用到 `$user.employee_id` 類欄位會對他們
     整列 deny；Hosted internal app 內**拿不到任何身分**（連使用者 id 都沒有，2026-09-09 實打），
     角色分流只能在門口做，要在畫面內分流就得換 Custom internal app；
     外部人員角色的 permissions 從空集合起步，`system.*`／`hr.*`／`accounting.*` 不給
   - **產出：授權架構表**（與 app 分配表並列寫進計畫；確認後照表建角色、設白名單、發邀請）
     `| app（alias） | 模式 | access_role_ids（角色名） | 角色 → permissions（新開／沿用） | 進入方式／邀請落點 |`
     ——預設情況就是一列 `| <alias> | starter-internal | （空＝全租戶成員） | 沿用既有角色 | 已是成員 |`

2. **場景拆分與 App 邊界建議**
   - 出現任一情況就**必須建議拆成多個 app**：
     - (a) 需求涵蓋 2 群以上不同功能與目的——「客戶管理」和「財務報表」→ 2 個 Custom App
     - (b) 登入後的系統＋不登入就要看的頁——匿名部分 → Hosted public、登入部分 → internal
     - (c) 部分功能命中 Hosted 邊界——Custom + Hosted 混合，分工見 `product-line-decision.md` §5
   - **使用者有內有外不是拆分理由**：同一支 internal app 用角色分流；真要分開也是兩支 internal app
     各掛不同 `access_role_ids`（第 1.7 項），不是拆成兩種模式
   - 拆出來的每個 app **各自過 1.5 的兩問、各自定模式與授權架構**，不是複製同一個答案
   - 每個 Custom App 的 `app_domain` 標籤建議值
   - **拆出來的每個 app（Custom 或 Hosted）都要進工作區登錄表**：建好後
     `aigo_auth.py app add <alias> --id <uuid>`，alias 用 app 分配表的短名；
     之後對話與指令一律用 alias 指稱，UUID 不在對話裡傳遞

3. **資料架構設計**（★ 必須遵循雙軌分流策略，見 Phase 3 規則 18）
   - **受眾承接 1.7 授權架構表，不重問**（★ 決定資料存取層的寫法，見規則 31）：
     受眾中有沒有**無 `builder.access` 的一般成員**（一般員工、外部人員都算）？
     - 有（絕大多數情況）→ 自建表存取**全部包 Server Action**，前端不直呼 `queryTable` 等方法
     - 受眾全員持有 `builder.access` 的開發工具型 app → 前端 SDK 可直呼
   - **盤點兩邊**（順序不可省，★ 兩邊都是硬閘）：
     - `GET /api/v1/data-center/tables` — 租戶既有自建表（Phase 0 已做，此處覆核）
     - **預設表語意對照**——每個實體先用業務語言查 `references/default-table-lookup.md` §2，
       再 `aigo_data.py meta tables --source erp --grep <關鍵字>` 看中文標題；
       `GET /api/v1/refs/available-tables` 只是表名清單（`comment` 實務上為空），不能當語意來源
     - 對候選預設表呼叫 `GET /api/v1/refs/tables/{name}/columns` 查欄位結構
       （Meta key 與引用面表名不同時依查表 §3 換名再打）
       ⚠️ **查到的表沒有 `tenant_id` 是正常的**，不代表不安全，也不要自補過濾——見規則 25
   - 列出所有需要的資料表（來源：§1.0 的資料實體清單），逐表判定走哪一軌（判定標準見規則 18）
   - **產出：資料承載表**（每個實體一列，寫進計畫；模板在 `new_app_requirements_template.md` §五、
     遷入線在 `migration_mapping_template.md` 每張表的對照項）
     `| 實體 | 用業務語言說是什麼 | 已對照的預設表（Meta 標題） | 採用／不採用理由 | 軌 |`
     ——走自建表的列，「已對照」與「不採用理由」兩欄**不得為空**；「沒想到有」不是理由，「查過沒有」才是
   - **重用優先於新建**：既有自建表語意相同就重用，不要新建；
     **重用的表欄位不足 → 直接加實體欄位**（`data-center.md` §7 加欄），
     不要因缺欄就另建新表或把結構化欄位塞進 json 欄
   - 走 Data Reference 的表：說明如何用 `custom_data` JSONB 擴充、`app_domain` 標籤值
   - 走自建表且需要新建的：產出**建表規格表**
     `| 表實體名 | 表顯示名 | 欄位實體名 | 欄位顯示名 | 型別 | 必填 | 唯一 | relation 目標 |`
     ——**兩個實體名欄不得為空且一律英文**（表 `biz_<英文複數>`、欄位 snake_case）；
     中文只能出現在顯示名那兩欄。理由與兩步命名法見規則 18.5
   - 若決定使用的預設表尚未被引用（以 `GET /api/v1/refs/apps/{app_id}` 為準，不是 db.json），
     引導用戶到 Builder 後台加入 Data Reference
   - 需求命中「交易／JOIN／條件式 UPDATE」邊界的實體，在這裡寫出改設計後的寫法
     （dev-guide §23.9），不要留到 Phase 3 才想

4. **頁面架構**
   - 路由結構（單頁 / 多頁）——**在這裡定案**，Phase 2 不再另問
   - 主要頁面和功能
   - Server Action 需求

4.5. **事件觸發需求**（若適用）
   - **Webhook**：列出要對外開放的端點
     `| hook 名稱（= action 名） | 事件來源 | 冪等 key 來源 | 驗簽方式 |`
   - **App 排程**：列出排程需求
     `| 排程名稱 | 觸發哪個 action | 頻率 | 時區 | 固定 params |`
     - **同時確認 tier 放不放得下**——最小間隔與條數上限依付費檔分層，
       超限是 400 不是靜默截斷。數值見 `references/event-triggers.md` §2.4
   - 兩者都要在計畫中明寫「此 action 的冪等策略」——見規則 20
   - 詳見 `references/event-triggers.md`

4.6. **對外 API 呼叫盤點**（★ 若有打第三方 API 就不可省）
   - 列出**所有要連出去的外部服務**
     `| egress slug | base_url（網域） | 用途 | 哪個 action 會用 |`
   - **在計畫階段就提醒用戶去建立外部服務**：Builder（`/builder/{app_id}`）的
     「外部服務」tab，以**同名 slug** 建立（base_url 域名白名單）並授權本 App
     （新建預設授權本 App）
     - 建立需本 App 擁有者或 `system.admin`；權限不足要請租戶管理員代設
   - 外部服務沒建立或沒授權，寫完的 code 一律連不出去——**等部署才發現等於整段白做**
   - 金鑰歸 app 自管：為每個 API 金鑰開 `ctx.secrets` 欄位，action 自組
     `Authorization` header——閘道只驗域名，不代管憑證（ADR 0010）
   - 詳見 `references/custom-app-dev-guide.md` §25

4.7. **平台 API 權限面盤點**（權限 gate 目前 audit，enforce 後前端呼叫會 403）
   - 列出**前端（瀏覽器 SDK）會直接呼叫的平台 API 群**——app 的宣告範圍是從
     `actions/*.py` 靜態推導的，**不含前端呼叫面**
   - 提醒用戶在 Builder（`/builder/{app_id}`）「API 權限」分頁把這些群開啟
     （寫入需 `builder.manage_access`）
   - 詳見 `references/platform-behaviors.md` §12

5. **app_domain 標籤設計**
   - 確定此 App 的 `app_domain` 值（snake_case，如 `patent_os`、`crm_leads`）
   - 說明標籤用途：所有寫入預設表的資料都會帶上此標籤

6. **現有系統遷移評估**（若適用）

   > 用戶有現存系統（Supabase / Google Sheet / MySQL / 既有程式碼）要遷入
   > → 先讀 `references/migration-workflow.md` §2，依序做：stack 盤點（§2.0）、
   > 產品線與模式判斷的遷入輸入（§2.1）、專案解構盤點（§2.2，前+後+DB 完整專案時，
   > 含使用者表與 DB 層邏輯的特殊處理）、語言架構評估、Schema 映射與資料遷移計畫。
   > 純新建 App 跳過本項。

### 計畫閘門

- **新建情景：§1.0 四問未齊、或計畫裡沒有「需求形狀結論」「app 分配表」「授權架構表」「資料承載表」→ 不算完成計畫，
  不得送閘門**——先回 §1.0／1.7／第 3 項補；遷入情景同樣要有這四張表
- **資料承載表裡任何一張自建表缺「已對照的預設表／不採用理由」→ 不算完成計畫**——
  這道閘與 Phase 0 步驟 6 的自建表盤點同級（issue #53：少了它，46 張表的遷入案第一版判了 40 張自建表，對照後只剩 13 張）
- **必須等待用戶明確回覆「同意」或提供修改意見後，才可進入 Phase 2**
- 若用戶修改需求，需更新計畫後再次確認
- 計畫確認後：
  - 依 app 分配表建 app（Phase 1 步驟 3，模板 slug 照表）並 `aigo_auth.py app add` 登錄——
    **這是建 app 的唯一時點**
  - 將 `app_domain` 值記錄到 `.aigo/config.json`
  - 依授權架構表建角色、設 `access_role_ids`、發邀請（`member-admin.md` §3–§5；每一步都過
    `data-operations.md` §3.5 寫入閘門）——白名單沒設，不在名單的人開 app 是 404「App 不存在」
  - 判走 Hosted App 的 app → 轉 `references/hosted-apps.md`；本 skill 的 Phase 2–4 只跑 Custom App

## Phase 2：專案腳手架

基於 Phase 0 Review 結果決定策略：

- **VFS 為空**：生成全新專案結構
  - 單頁／多頁依 Phase 1.5 計畫第 4 項的頁面架構，**不另問**；計畫沒寫就是計畫不完整，回 1.5 補
  - 單頁：直接渲染，不使用 Router
  - 多頁：HashRouter + Sidebar 導航
  - 可用 `scripts/aigo_scaffold.py` 的 `scaffold_new_project()`

- **VFS 有內容**：下載到本地進行增量開發
  - 將雲端 VFS 下載為本地檔案結構
  - 保留現有所有程式碼
  - 可用 `scripts/aigo_scaffold.py` 的 `download_vfs_to_local()`

## Phase 3：開發指引

### 核心規則（必須嚴格遵守）

1. **框架**：React 18 + TypeScript
2. **路由**：多頁用 `HashRouter`（禁用 `BrowserRouter`）；單頁可不用 Router
3. **CSS**：全域 `App.css`，不支援 CSS Modules / Tailwind
4. **CSS 變數**：必須用 `:host, :root { }` 雙選擇器
5. **HTML 重設**：必須用 `html, :host { }` 雙選擇器
6. **入口點**：必須是 `src/main.tsx`，且 `import "./App.css"`
7. **Layout**：最外層容器必須 `height: 100vh; overflow-y: auto`
8. **Runtime 模組**：react, react-dom, lucide-react, react-router-dom, react-hot-toast 由 Runtime 提供，不可自行安裝
9. **SDK 不可修改**：api.ts, db.ts, action.ts, data.json, db.json, actions.json
10. **Server-Side Actions**：Python，放在 `actions/` 目錄，定義 `execute(ctx)` 函式
11. **Shadow DOM 限制**：`confirm()` / `alert()` / `prompt()` 不可用 → 改用 React state 或 react-hot-toast
12. **前端 `db.ts` 的 db.update() Bug**：需用 `{"data": {...}}` 包裝 payload（直接 fetch，不走 SDK）
    - ⚠️ **2026-09-01 前注入的 `db.ts` 送的是 `PUT`，資料代理只收 `PATCH`——`update()` 恆回 405、
      更新從未生效**（#1416 修正 SDK 模板）。既有 app 若 `src/db.ts` 仍是 `method: 'PUT'` 版本，
      要換成平台最新模板（Builder 重新注入）或直接 fetch 用 `PATCH`；不要把 405 當成權限問題查
13. **前端 `db.ts` 的 db.insert() Bug**：同上，需用 `{"data": {...}}` 包裝
    - ⚠️ **只適用前端**。Server Action 的 `ctx.db.insert(table, data)` 收**扁平 dict**，
      包裝反而會被濾光並回 400。自建表的 `insert_row` / `update_row` 同樣收扁平 dict
14. **VFS 限制**：最多 200 檔案、單檔 ≤ 1MB、編譯超時 30 秒
15. **完整程式碼原則**：每次更新 VFS 檔案必須提供 100% 完整內容，禁止 `// ...省略` 佔位符
16. **不支援動態 import**：`import()` 語法不支援（lazy loading 除外，esbuild 支援 code splitting）
17. **不支援 Node.js 原生模組**：fs, path, crypto 等無法使用
18. **資料承載體：雙軌分流**（★ 強制）

    資料存在哪裡，依**資料的性質**決定，不是依「哪個比較方便」：

    | 資料性質 | 走哪一軌 | 理由 |
    |---------|---------|------|
    | **平台有同語意的實體**（案件追蹤、往來對象、專案、交付物、待辦…——先用業務語言查 `references/default-table-lookup.md` §2） | **Data Reference**（原生欄位優先） | 與平台功能共用同一份資料；舉證責任在「為什麼不用預設表」 |
    | 預設表缺「租戶級正式欄位」 | Data Reference 的**延伸欄位**（EAV） | 有型別、全租戶可見；讀寫走獨立端點（`data-center.md` §10） |
    | 平台**沒有**同語意實體（查過查表與 Meta API 仍無：領域專屬紀錄、公開爬蟲資料…） | **自建表** | 租戶級真實資料表，跨 app 共用 |
    | app 私有標記（`app_domain`）、臨時、鬆散、不值得定義欄位 | 預設表的 `custom_data` JSONB | 免定義成本 |

    完整決策樹（表級 → 欄位級，直接開發與遷入同一棵）見
    `references/custom-app-dev-guide.md` **§19（SSOT）**——與本表出入時以 §19 為準。

    - **自建表不是「最後手段」，也不是遷入的預設答案**——它是租戶級的真實 Postgres 表（200 張配額，付費檔），
      該用就用；但遷入的表語意落在 CRM、專案、銷售採購、HR、會計時**預設引用預設表**，
      只有平台真的沒有對應實體才自建。每張自建表都要附「已對照 <預設表>／不採用理由」
      （Phase 1.5 第 3 項的資料承載表；issue #53：跳過對照的計畫把 13 張表做成 40 張）
    - **既有表欄位不夠 ≠ 換軌或塞 json**：自建表可直接**加實體欄位**
      （`data-center.md` §7）；預設表本體不可改，但可加**延伸欄位**
      （租戶級正式欄位，EAV，`data-center.md` §10）——`custom_data` 不是
      預設表唯一的擴充點，它留給 app 私有標記（`app_domain`）與鬆散暫時性擴充。
    - **建表前必須先 `GET /api/v1/data-center/tables` 盤點**（Phase 0 步驟 6）。
      語意相同的表已存在就重用，不要新建——自建表跨 app 共用，重複建表 = 資料分裂。
    - 建表需 `system.admin`。收到 **403 不重試、不繞路**：輸出可照抄的建表規格，
      引導用戶到資料中心 UI 自建，建完 `GET` 驗收再繼續。
      （`aigo_data_center.py` 會把 403 拋成 `PermissionDenied`；`needs == "system.admin"`
      才走建表降級，用 `format_create_spec()` 產出規格表。`needs == "builder.access"`
      是帳號沒有資料中心存取權，該請用戶開權限，不是叫他去建表）
    - `data.json` / `POST /api/v1/data/objects/batch` 是**已退場的 CustomObject**，
      不是自建表。存量 app 可留，新需求一律不用。
    - 詳見 `references/data-center.md`

18.5. **自建表命名規範：實體名一律英文**（★ 強制；新建與接手都適用）

    實體名（physical name）**建立後永不可變、平台沒有改名 API**，而它是系統從顯示名生成的：
    NFKD 折疊 → 丟掉非 ASCII。**純中文顯示名折疊後是空字串**，實體名於是變成
    `tbl`／`tbl_2`／`col`／`col_2`／`ext_2` 這種保底名，往後所有 code 都得寫
    `queryTable('tbl_3', { filters: [{ field: 'col_7', … }] })`，而且**永遠改不回來**。

    | 對象 | 規範 |
    |---|---|
    | 表實體名 | `biz_<英文實體複數>`，snake_case（`biz_customers`、`biz_patent_cases`） |
    | 欄位實體名 | 英文 snake_case，不加前綴；關聯欄用 `<單數實體>_id` |
    | 延伸欄位實體名 | 同欄位規範 |
    | 顯示名 | 中文照舊，隨時可 `PATCH` 改 |

    - **`biz_` 前綴的三個作用**：與預設表的功能區前綴（`crm_`／`sale_`／`hr_`／`account_`…）
      一眼分得開；**完全避開保留名 409**（保留母體 = SQL 保留字 ∪ 預設表名 ∪ 平台地板表名 76 張，
      沒有一個以 `biz_` 開頭）；不佔用平台自己在用的 `dc_`／`app_`。
    - **兩步命名法（唯一做法）**：`POST /tables` 的 `display_name` 先填**英文實體名**
      → 拿到正確 `physical_name` → 再 `PATCH` 把表與各欄的 `display_name` 改成中文。
      **兩步要在同一次交付內做完**，不要只做第一步就收工。
    - **建完必驗**：`GET /tables` 看 `physical_name` 是不是預期值。拿到 `tbl` / `col_N`
      = 填錯了，**當場刪掉重建**——此時沒資料，成本最低；有資料之後就得走
      `data-center.md` §11 的重建式遷移（建新表→搬資料→改引用→刪舊表，五步不可逆）。
    - **403 降級、引導用戶到資料中心 UI 自建時**，規格表要附一句
      「表名欄請照填 `<英文實體名>`，建好後由我把顯示名改成中文」——
      UI 建表框的 placeholder 就寫「例如：客訴紀錄」，不講清楚用戶一定填中文。
    - **用戶堅持「表名要中文」時**：說明顯示名確實是中文、實體名是資料庫識別字，
      只有開發者在 code 與 API 看得到。不要因此退回中文顯示名建表。
    - **接手既有租戶**：Phase 0 步驟 6 掃 `physical_name`，不合規的**分級**處置
      （`data-center.md` §11.1）——P0 保底名出計畫書、用戶同意後走重建式改名；
      **P2（只是少 `biz_` 前綴但名字可讀）預設不動**，重建一張有資料的表，
      風險遠大於命名一致的收益。**未經用戶書面同意不得動既有表**。
    - 詳見 `references/data-center.md` §1（命名規範與生成規則）、§11（重建式改名）

19. **app_domain 標籤規範**（★ 強制，但**只限 Data Reference 那一軌**）
    - **適用範圍**：只有寫入預設表（Data Reference）的資料需要 `app_domain`。
      **自建表不需要也不應該帶 `app_domain`**——自建表沒有 `custom_data` 欄位，
      而且「跨 app 共用」正是它的設計目的，用標籤隔離是反模式。
    - 所有寫入預設表的資料，都必須在 `custom_data` JSONB 中包含 `app_domain` 欄位
    - `app_domain` 值記錄在 `.aigo/config.json` 中，在 Phase 1.5 決定
    - 格式：snake_case，如 `patent_os`、`crm_leads`、`inventory_mgr`
    - 寫入範例：
      ```typescript
      const newRecord = {
        name: "案件名稱",
        custom_data: {
          app_domain: "patent_os",  // ★ 必須標記
          case_no: "IP-001",
          status: "進行中"
        }
      };
      ```
    - 讀取時應過濾本 App 的資料：
      ```typescript
      const records = allRecords.filter(
        r => r.custom_data?.app_domain === "patent_os"
      );
      ```
20. **Webhook / 排程 action 必須冪等**（★ 強制）
    - 平台保證 **at-least-once**：事件至少執行一次，**可能重複執行**
      （dispatcher 硬死、invoke 超時、DLQ redrive、滾動更新窗口都會產生重複）
    - 有寫入副作用的 action（建單、扣款、發信）**沒有去重就是重複扣款等級的 bug**
    - 去重 key 優先用事件本身的業務 id，其次用 `ctx.params["delivery_id"]`
    - 詳見 `references/event-triggers.md` §0
21. **Webhook 宣告只在發布後生效**
    - `actions/manifest.json` 加 `"webhook": true` 後**必須 republish**，草稿不影響線上端點
    - `ctx.params["body"]` 是**原始字串**要自己 `json.loads`；驗簽必須用這個原字串，
      不可用重新序列化的結果
    - **`headers` 不可信**——webhook 是無認證公開入口，授權只能靠簽章驗證
    - 同一事件源**不可同時登記新舊兩條 URL**（會執行兩次）
22. **排程的四個硬限制**
    - **有執行時間上限**，超過必逾時 → 長任務要自己切批次。
      ⚠️ **webhook 與 cron 的上限不同**，別互相套用（`event-triggers.md` §1.6／§2.6）
    - **最小間隔與條數依付費檔分層**，超限回 400（`event-triggers.md` §2.4）
    - **重疊會被跳過**（`skipped` 是預期常態不是錯誤）
    - **自動暫停後不會自動恢復**——⚠️ republish 之後要提醒用戶檢查
      Builder 該 App「排程」分頁的排程狀態（`GET /builder/apps/{app_id}/crons`；`event-triggers.md` §2.8）。
      排程的建立與權限走 App 開發面（`builder.app_cron_manage`），不要把開發者導去 `/dashboard/settings/app-crons`
      （那個入口只有 `system.admin`／`settings.write` 看得到；`event-triggers.md` §2.1）
23. **角色／權限沿用平台，不要自建一套**（★ 強制）
    - Internal app 前端用 `src/user.ts`（`hasPermission` / `hasAnyPermission` /
      `isAdmin` / `getRoles`），資料是 Runtime 注入的登入者權限快照，
      **禁止自己打 `/api/v1/auth/me`**，也不要在 app 內另建角色表
    - ⚠️ **`src/user.ts` 要在 Builder 後台開過「開發」分頁才會進 VFS**，
      純走 API 建立的 app 直接 import 會編譯失敗——改直接讀 `__USER_PERMISSIONS__` 全域
      （`platform-behaviors.md` §10.2）。快照只給「能做什麼」，
      「是誰」要解 `__APP_TOKEN__` 的 JWT（§10.3）；`__CURRENT_USER__` 不存在
    - **前端解出的身分不可信**：寫入 `user_id` 這類身分欄位時，
      一律在 action 內用 `ctx.user_id` 覆蓋前端送來的值
    - **判斷授權用 permission 標籤（`模組.動作`）不要用角色名稱**——角色可被租戶改名；
      `system.admin` 自動通過所有檢查
    - **前端隱藏只是 UX**：機敏資料差異必須在 action 用 `ctx.user_permissions` 分流
    - 匿名渲染下（以及少數判進 external 的 app）roles 與 permissions **恆為空陣列**，
      UI 要有合理的降級路徑（不要因為空陣列就整頁空白）
    - **外部人員也是租戶成員**：經銷商／客戶登入後同樣走這套快照，他們的角色由計畫第 1.7 項定；
      app 內不要另做「外部使用者」的登入或身分判斷
    - 詳見 `references/custom-app-dev-guide.md` §6「User Context」與 §7
24. **預設表寫入可能被簽核攔截**（★ 強制，只限 Data Reference 那一軌）
    - 租戶對該表設了簽核流程時：**insert 照樣寫入但回傳帶 `approval_status: "pending"`**；
      **update / remove 與 `ctx.erp.*` 完全不執行**，payload 暫存、Server Action 收到例外
    - `pending` **既不是成功也不是失敗**：UI 要顯示「已送簽核」，
      ⚠️ **不可重試**（重試 insert = 重複建單 + 重複開簽核單）
    - **沒有旁路**——`db.ts` / `ctx.db` / `ctx.erp` 同一套守衛，不要換路徑硬寫
    - 要免寫後端就讓核准自動改狀態欄位；要做簽核 UI 用 `src/approval.ts` / `ctx.approval`
    - 詳見 `references/custom-app-dev-guide.md` §24
25. **表沒有 `tenant_id` 不等於沒保護**（★ 強制）
    - 查欄位時看到某張預設表**沒有** `tenant_id`（如 `msg_messages`、`announcement_reads`、
      `ir_sequences`、`account_accounts`）**不是 bug**，租戶隔離也沒失效——
      邊界另有欄位別名（`company_id`）、父表歸屬（`EXISTS` 繞父表）、全域表（刻意不過濾）三種形態
    - **不要自己補 `WHERE tenant_id = ...`**：邊界由 DB Proxy 注入，
      手動補在沒有該欄位的表上只會直接失敗
    - **不要因為缺欄位就改用別的表或自己加一層過濾**——判定依據是後端的顯式登記表，不是欄位偵測
    - 詳見 `references/custom-app-dev-guide.md` §20.3
26. **`offset` 分頁一律帶唯一鍵排序**（★ 強制，**不加會靜默漏資料**）
    - DB Proxy 單次最多回 **500 筆**、回傳是裸陣列（無 `total` 信封），要取完整資料
      必須自己 `offset` 迴圈，以「回傳數 < 500」作結束條件
    - 伺服器預設 `ORDER BY created_at DESC NULLS LAST`，時間戳重複時排序不穩定，
      分頁會**跨頁重複又漏抓**——實測某表 1866 筆只取回 1860 筆，
      **不拋例外、不報警告**，只有統計數字會悄悄少一截
    - 每次分頁查詢都要帶 `order_by: [{ column: "id", direction: "asc" }]`
    - 詳見 `references/platform-behaviors.md` §1
27. **`ctx.erp.validate_picking` 的冪等要看明細，不能看單據 state**（★ 強制）
    - 實測成功扣帳後 `stock_pickings.state` **不會**轉成 `done`（只寫 `date_done`），
      真正反映完成的是 `stock_moves.state`
    - 拿 `picking["state"] == "done"` 當冪等守門，條件永遠是 False、守門永遠不生效；
      要改判 `all(m["state"] in {"done","cancel"} for m in moves)`
    - 詳見 `references/platform-behaviors.md` §4.3
28. **原生 TIMESTAMP／DATE 是 offset-naive 的 UTC，解析前必須補 `Z`**（★ 強制，**不補會靜默算錯**）
    - 平台混用兩種時間欄位：`created_at`／`updated_at` 是 timestamptz（帶 `+00:00`，可直接用）；
      `check_in`／`date_from`／`date_done`／`work_date` 是原生 TIMESTAMP／DATE，
      回傳長這樣 `2026-08-01T04:37:03`——**存的是 UTC，但 JS 會當成本地時間**
    - **不拋例外、不報警告**：實測相隔 6 分鐘的上下班打卡被算成 **8.1 小時**工時，
      直接寫進 `hr_attendances.worked_hours`（影響薪資）
    - 解析前補 `Z`；顯示不可切字串（`slice(0,16)` 顯示的是 UTC）；
      推導日期不可用 `toISOString().slice(0,10)`（那是 UTC 日期，UTC+8 凌晨會退回前一天）
    - DATE-only 欄位建議直接以**字串比對／顯示**，不要轉時間戳
    - 可直接沿用的 `toTime()` 與適用範圍見 `references/platform-behaviors.md` §8
29. **所有 API 一律走租戶空間 `https://[tenant].ai-go.app/*`**（★ 強制，**打錯的錯誤訊息會誤導你**）
    - 平台以 **Host header** 解租戶：base_url 打哪個 host = 宣告要登入哪個租戶。
      主站 apex `https://ai-go.app` 推不出租戶，實測登入已回 401
    - **不可硬編任何 base_url**——一律經 `aigo_auth.resolve_base_url()`
      （shell 環境變數 → 專案 `config.json` → `.env` 的 `AIGO_TENANT`／`AIGO_BASE_URL`）
    - ⚠️ **打錯租戶與密碼打錯回完全相同的 401「帳號或密碼錯誤」**（平台反帳號列舉，
      連是否跑滿一次 bcrypt 都一樣）。看到 401 **先跑 `aigo_auth.py status` 確認租戶空間**，
      不要往密碼、Token、權限方向深掘
    - 租戶前綴 = 用戶登入時網址列的第一段；不確定就直接問用戶，別猜
    - 細節見 `references/platform-behaviors.md` §6.1
30. **啟動先渲染 skeleton，不要讓長 API 擋住首次渲染**（★ 強制）
    - 平台會監看掛載後 **8 秒**：Shadow root 全空就自動回報 runtime error，
      並對使用者顯示「App 已載入但沒有顯示任何內容」banner
    - 「先跑長 API、成功後才第一次渲染」的寫法會被誤報——
      一律先渲染 loading／skeleton 佔位，資料到了再替換
    - 詳見 `references/platform-behaviors.md` §11
31. **Internal app 前端禁止直呼自建表 SDK**（★ 強制，**開發時測不出來、上線就爆**）
    - 前端 `src/api.ts` 的 `listTables`／`queryTable`／`insertRow`／`updateRow`／
      `deleteRow` 是以**登入者身分**打 `/api/v1/data-center/*`，記錄 CRUD 一律要求
      `builder.access`——internal app 的一般員工受眾沒有這個權限，**執行期必 403**
    - 開發與驗證帳號必有 `builder.access`，所以 Phase 4/5 怎麼測都是通的；
      2026-08-31 prod 盤點有 44 支 internal app 現行中招——照直覺寫就會踩
    - internal app 的自建表存取一律包成 Server Action（`ctx.db.*` 走 app 憑證，
      不過此閘），前端 `runAction`；並在 action 內用 `ctx.user_permissions`
      分流授權（規則 23）——**跳過補閘會把 403 破口修成資料過度開放，更糟**
    - 前端 SDK 只有一種常態情境可直呼：受眾全員持有 `builder.access` 的開發工具型 app
      （判進 external 的例外 app 自動分流 `/ext/data-center`，不在此閘）
    - 機制、存量修復流程、假修法排除清單見 `references/data-center.md` §7.5
32. **禁止以 Hosted App 承載資料庫或 storage**（★ 強制，遷入情景最容易踩）
    - **不得**把 DB 本身（Postgres／MySQL／Redis…）或「包了 REST 的 DB 服務」
      （PostgREST、Hasura、自架 API-over-DB）部署成 Hosted App 供其他 App 存取——
      同租戶 app 間網路互通讓這在技術上做得出來，但它是明文禁止的反模式：
      資料進不了平台功能、繞過簽核與權限閘（規則 23／24）、平台不備援它
    - table schema 一律落平台**預設表／自建表**（規則 18 雙軌分流、§19 SSOT）；
      檔案一律 **Storage API**；Hosted App 自身的資料層一律改寫 **Open Proxy**
      （`hosted-apps.md` §7.1——執行期出站只放 443，直連 DB 在網路層本就不存在）
    - 僅有的兩個過渡例外（短期暫連原 DB 的 HTTPS 介面、`/data` 放非業務資料）
      見 `hosted-apps.md` §7.1，用了必須在計畫中明寫遷移終點

### Server-Side Action 撰寫

```python
def execute(ctx):
    # ctx.params — 前端傳入的參數（webhook / cron 事件也走這裡）
    # ── Data Reference（預設表）
    # ctx.db.query(table, limit=N) / ctx.db.insert(table, data)
    # ctx.db.update(table, row_id, data) / ctx.db.remove(table, row_id)
    # ── 自建表
    # ctx.db.list_tables() / ctx.db.query_table(table, options)
    # ctx.db.insert_row(table, data) / ctx.db.update_row(table, row_id, data)
    # ctx.db.delete_row(table, row_id)
    # ── 其他
    # ctx.http.call(slug, path, method=..., body=..., headers=...) — 對外 HTTP（經 egress 閘道）
    # ctx.secrets.get(key) — 金鑰（外部 API key、webhook 驗簽等，由 app 自管）
    # ctx.response.json(data) — 回應
    # ctx.csv.export(rows) — CSV 匯出
    data = ctx.params.get("key", "default")
    ctx.response.json({"result": data})
```

> `ctx.db` **不提供結構操作**——action 執行期無法建表或改欄，這是刻意的能力邊界。
> 執行逾時：manifest `timeout_ms` 1000～**120000** 現在真的生效（prod v1.13.0 前恆被切在 30 秒；
> 舊 app 要 **republish** 才換上新值），排程 action 實務上限也是 120 秒——
> `references/custom-app-dev-guide.md` §7、`event-triggers.md` §2.6。
> 資料層 403 若 body 帶 `reason`／`rule_id`＝租戶「資料存取規則」擋的，改 code 無解 → dev-guide §27。

**呼叫外部 API：一律走 `ctx.http.call(<egress-slug>, <path>)` 閘道**，
**不要**直接 `import httpx / requests / urllib.request`——runner pod 是
default-deny egress，raw 連線出不去（實測 20 秒 timeout），且這些套件在沙箱 denylist 上。

```python
def execute(ctx):
    # slug 對應租戶註冊的「外部服務」（EgressService）——純域名白名單，只鎖 host。
    # 金鑰由 app 自己帶：存 ctx.secrets，action 自組 Authorization header。
    resp = ctx.http.call(
        "example-api",
        "/v1/send",
        method="POST",
        headers={"Authorization": f"Bearer {ctx.secrets.get('EXAMPLE_API_KEY')}"},
        body={"text": ctx.params.get("text")},
    )
    if int(resp.get("status") or 500) >= 400:
        ctx.response.json({"error": "外部服務暫時無法使用", "status": resp.get("status")})
        return
    ctx.response.json(resp.get("data") or {})
```

> ⚠️ **slug 必須先建立同名「外部服務」（base_url 域名白名單）並授權給本 App，
> 否則連不出去**——見 `references/custom-app-dev-guide.md` §25。這是設定問題，
> 不是程式問題，改 code 改不掉。
> 閘道只做**域名驗證**，**不代管、不注入、也不剝除憑證**（ADR 0010）：
> `Authorization` 等呼叫端 headers 原樣轉送（僅擋 hop-by-hop）。
> API 金鑰請開 `ctx.secrets` 欄位、由 action 自組 header。


### 前端呼叫 Action

```typescript
import { runAction, downloadFile } from "../action";
const { data, file } = await runAction("my_action", { key: "value" });
if (file) downloadFile(file);
```

## Phase 4：部署 + 自動驗證（★ 每次 code 變更後必須執行）

> **原則：每次 code 變更後，都必須完成「同步 → 編譯 → 驗證」循環。**
> 只有通過驗證閘門，才可進入發布或繼續下一輪開發。
> 極小變更（如僅修改文字、CSS 微調）可跳過 Custom Data 和 Action 測試，但編譯驗證不可跳過。

### 4.1 標準部署流程

0. **定目標並印出來**：`app = resolve_app(root, alias)` → `print(app.describe())`
   → GET app 後 `assert_remote_matches(app, info)`。工作區有多個 app 而本次沒指定 →
   `resolve_app` 會報錯列出 alias，**問用戶，不要猜**。`full_deploy()` 自己也會印目標行
1. **同步 VFS**：讀取本地檔案 → PATCH `/api/v1/builder/apps/{id}/source/files`
   - 腳本：`scripts/aigo_sync.py` 的 `sync_to_cloud()`
   - ★ 內建二次驗證：PATCH 後自動 GET 確認 vfs_version 遞增 + 檔案確實寫入
1.5. **語意檢查**（★ 前端有實質修改時必跑）：`uv run --project scripts python scripts/aigo_typecheck.py <專案目錄>`
   - **compile 走 esbuild，只轉譯不驗型別**：`const` 宣告前被使用（TDZ）、找不到名稱、重複宣告
     這類錯誤 compile 全綠、發布後 runtime 白畫面，且堆疊只有 minified 名稱與 esm.sh 的
     React 呼叫鏈（`troubleshooting.md` 白畫面列）。這一步是唯一能在發布前抓到它們的閘
   - 腳本只**阻擋會炸 runtime 的語意錯誤**（TS2448／2454／2451／2300／2304…），
     缺型別套件的噪音只列不擋；本機沒有 Node 會印提示並略過——此時要**告知用戶**
     這道閘沒跑，或請用戶在 Builder AI 用 `check_types` 補跑（平台有此工具但無 REST 端點）
2. **編譯**：POST `/api/v1/compile/compile/{slug}?dev=true`
   - 腳本：`scripts/aigo_compile.py` 的 `compile_app()`
   - ⚠️ `success: true` 且 `compile_errors: []` 只代表**轉譯成功**，不代表程式語意正確（見 1.5）
3. **編譯失敗**：解析錯誤 → 嘗試自動修復 → 重新同步 → 重新編譯（最多 5 次）
4. **編譯成功 → 進入驗證閘門**（Phase 4.2）

### 4.2 驗證閘門（Verification Gate）

每次編譯成功後，根據**變更範圍**自動決定需要執行的驗證項目：

#### 變更範圍判斷規則

| 變更類型 | 影響範圍 | 需執行的驗證 |
|---------|---------|------------|
| **CSS 微調**（僅 App.css 變動） | 極小 | ✅ Compile 產物 |
| **文案/UI 修改**（僅 TSX 變動，無新 import） | 小 | ✅ Compile 產物 |
| **元件新增/重構**（新增 TSX、修改路由） | 中 | ✅ Compile 產物 + ✅ Publish 一致性 |
| **Custom Data 相關**（修改了使用 api.ts/db.ts 的程式碼） | 中 | ✅ Compile 產物 + ✅ Custom Data CRUD |
| **Server Action 變更**（actions/*.py 修改） | 中 | ✅ Compile 產物 + ✅ Server Action 呼叫 |
| **多個範圍同時變動** | 大 | ✅ 全部 4 項驗證 |
| **首次部署或架構變更** | 大 | ✅ 全部 4 項驗證 |

> 要**實際執行**這四項驗證 → `references/verification-details.md` §1
> 有每一項的完整檢查條目與函式簽名。

### 4.3 驗證後決策

| 驗證結果 | 下一步 |
|---------|--------|
| ✅ 全部通過 | 可進入發布（4.4）或繼續開發 |
| ❌ Compile 失敗 | 回到 Phase 3 修復程式碼 |
| ❌ CRUD/Action 失敗 | 檢查 API 使用方式、表結構、Action 邏輯 |
| ❌ Publish 一致性失敗 | 重新 sync → compile → publish |

> 任何一項失敗 → 先查 `references/troubleshooting.md` 對症狀，再動手改。
> ⚠️ CRUD 驗證打預設表時，回傳 `approval_status: "pending"` 或「需要簽核審批」例外
> **不算驗證失敗**——那是租戶簽核流程攔截（核心規則 24），不要當成 bug 去改程式。

### 4.4 發布

只有通過驗證閘門後才可發布：

1. POST `/api/v1/builder/apps/{id}/publish`
   - 腳本：`scripts/aigo_publish.py` 的 `publish_app()`
   - ★ 內建二次驗證：POST 後自動 GET 確認 status == "published"
2. 發布後執行 Publish 一致性驗證

### 樂觀鎖

- GET App 時記錄 `vfs_version`
- PATCH 時帶入 `expected_version`
- 409 → 重新 GET → 合併 → 重試

### 自動修復策略

| 偵測問題 | 自動修復 |
|---------|--------|
| `:root {` 無 `:host` | → `:host, :root {` |
| `html {` 無 `:host` | → `html, :host {` |
| BrowserRouter | → HashRouter |
| 缺少 `import "./App.css"` | → 在 main.tsx 頂部加入 |

可使用 `scripts/aigo_sync.py`、`aigo_compile.py`、`aigo_publish.py`。

## Phase 5：完整 E2E 驗證（里程碑驗證）

> Phase 4 的驗證閘門每次迭代自動執行；Phase 5 是**開發里程碑完成**
> （功能全部完成、準備交付）時的完整驗證。

> 要執行時 → `references/verification-details.md` §2 有完整清單與呼叫範例。

## 驗證流程快速參照

```
每次 code 變更：
  sync → compile → ✅ Compile 產物驗證
                   └─ (若涉及 Data) → ✅ Custom Data CRUD
                   └─ (若涉及 Action) → ✅ Server Action 呼叫
                   └─ (若涉及路由/元件) → publish → ✅ Publish 一致性

里程碑交付：
  上述全部 + 角色白名單實測（用不在 `access_role_ids` 內的帳號開 app 應 404）+ 匿名存取（僅判進 external 的 app）

Hosted App 線（不走 Phase 2–4）：
  deploy/redeploy → ✅ hosted-apps.md §3.4 部署後驗證閘門（含讀回 `always_on`＝§3.0 決策；未通過不得對外交付）

資料操作線（不開發 app）：
  寫入前 → ✅ data-operations.md §3.5 寫入閘門（估影響面 → 備份 → 試一筆 → 用戶確認）
```

## 錯誤處理

> 任何一步失敗、或收到非預期狀態碼 → 先查 `references/troubleshooting.md`，
> **不要自行推測修法**。多數症狀有明確成因，猜測通常會改錯地方。
> 查無此症、或照表處理仍卡死 → **自動**進入下方「問題回報」的五步流程
> （先自審、確認是平台問題後才問使用者送不送），不要反覆重試、不要繞道硬改。

常見狀態碼的語義分野：**403** 權限（分 `system.admin` / `builder.access` 兩種，
降級動作不同；body 帶 `reason`／`rule_id` 則是租戶資料存取規則，見 dev-guide §27）｜
**409** 配額或衝突｜**422** 輸入不合法｜**400** 業務規則拒絕｜
**503「app runner 暫時不可用」且 body 帶 `quota_hint`**＝租戶運算配額吃緊（pod 建不出來），
**不是 code 問題**——把 `quota_hint` 原文轉給用戶、引導到「運算資源」頁或找管理員，別改 action。

### Action 對外呼叫失敗（★ 別急著改 code）

**先完整讀出回傳的 status 與 error message**，再對症：

- **timeout／連不出去**：① action 是不是 raw `import httpx / requests` 直連？
  runner 是 default-deny egress，raw 連線必 timeout——改寫成 `ctx.http.call`
  ② 已是 `ctx.http.call` → slug 沒有同名「外部服務」，或服務未授權給本 App
- **401**：外部 API 拒絕請求帶的憑證——閘道**不注入也不剝除** `Authorization`
  （域名驗證 only，ADR 0010）。檢查 action 是否自組了正確的
  `Authorization` header、`ctx.secrets` 的金鑰對不對——這是 app 側問題，
  不用去動外部服務設定

訊息指向 Egress／權限時：

1. **立刻停止修改程式碼**——這是設定問題，改幾次結果都一樣
2. 把原始 error message 轉給用戶，引導到 Builder（`/builder/{app_id}`）的
   「外部服務」tab，以同名 slug 建立外部服務（base_url 域名白名單）並授權本 App
3. 建立需 `builder.access` 且為本 App 擁有者（或 `system.admin`）；
   權限不足請租戶管理員代設
4. 外部服務確認生效後才重試

詳見 `references/custom-app-dev-guide.md` §25.3。

## 問題回報（平台問題 → 開發團隊）

> ★ **預設平台必定正確；開發或使用失敗，預設是自己的 Agent 操作有誤。**
> 回報前**必須**走完 `references/pre-report-self-grill.md` 的六輪自審：每個分支都要有
> 指令＋輸出的證據排除「是我錯」，前沿為空、且純 API 可穩定重現（或 5xx／硬阻斷）
> 才算平台問題。**不確定就不報。送出與否由使用者決定，但問的人是 agent。**
> `submit` 沒帶 `--ruled-out` 或 `--user-confirmed` 會被拒收，不建卡。

**使用者流程（固定五步；agent 主動推進，使用者只做最後一個決定）**：

1. **自動觸發**：`troubleshooting.md` 查無此症、照表處理仍卡死、實測與 `references/` 明文不符、
   端點 5xx／流程被硬阻斷——任一成立就**自動**進入六輪自審。不必使用者要求、不先問「要不要查」、
   不反覆重試、不繞道硬改
2. **自審**：照 `pre-report-self-grill.md` 六輪逐題跑指令留證據；一次只審一個症狀
3. **判定**：
   - 不是平台問題（app 側／部署落差／文件缺口／平台刻意設計）→ 直接修或等，
     **跟使用者說結論即可，不問送不送**
   - 前沿還有「待查」→ 不確定就不報：把自審紀錄與缺的證據交給使用者，
     問的是「要不要繼續追」，不是「要不要送」
   - 兩個送出條件成立（`pre-report-self-grill.md` §3）→ 進第 4 步
4. **主動問使用者要不要送**：先給一段摘要——情境（想完成什麼）、操作、結果、預期、已排除清單，
   情境與結果用非技術的話寫——再問「要不要提交給開發團隊？」（有 AskUserQuestion 就用它）。
   **不得替使用者決定送或不送**
5. **同意 → 送出**：`submit … --ruled-out … --user-confirmed`；
   不同意 → 自審紀錄留在專案（例如 `docs/issues/<日期>-<症狀>.md`），不送

遇到「平台自身」的問題——實測與文件不符、troubleshooting 查無此症或照表仍卡死、
被平台缺陷擋住流程——走完五步、使用者點頭後**直接回報給開發團隊**，不要繞道硬改：

```bash
uv run --project scripts python scripts/report_issue.py submit "一句話標題" \
  --given "情境：想完成什麼、當時在什麼狀態" --when "操作：做了什麼" \
  --then "結果：實際發生什麼（錯誤原文關鍵段落）" --expected "預期：依文件應該怎樣" \
  --ruled-out "版本：…
身分：…
契約：…
生命週期：…
文件：…
重現：…" \
  --user-confirmed \
  --image 截圖.png   # UI 問題附截圖（可重複，最多 10 張），會內嵌在卡片裡；
                      # --user-confirmed 只在第 4 步已做、使用者說了「送」之後才帶
```

- 憑證重用 `~/.aigo/.env`，零設定；在 AI IDE 內直接執行，不開任何 UI、
  不經平台（回報系統獨立部署，平台掛掉時照樣可報）
- ★ 內容寫**行為**不寫解法，骨架固定「情境（想完成什麼）→ 操作 → 結果 → 預期」，重心是
  「嘗試做什麼、結果是什麼」；三段缺一拒收，內文出現「建議把／應該改／修法／根因是」等開藥方措辭也拒收——
  **不要**替用戶提出技術建議或實作方式，完整規範見 `references/issue-reporting.md`
- ★ `--ruled-out` 是自審紀錄濃縮成的**已排除清單**（每行一項、至少三項），會附在卡片裡
  讓開發團隊快速 triage；寫不出這段就代表還沒排除完
- ★ `--user-confirmed` 代表第 4 步已做且使用者同意；缺少即拒收。CLI 驗不了旗標真假，
  靠的是對話裡留下的摘要與問句可稽核——沒問過就帶，是本節最嚴重的違規
- 追蹤進度與官方回覆：`report_issue.py list`／`show <ticket_id>`
- `submit` 會先做**開單前查既有卡**並印一行結果（同症狀的卡已修復／處理中／沒有）。
  **第一階段只記錄，不改流程**——不論結果都照常送出，不要據此自行決定不報或跟使用者
  說「已經修好了」；那是第二階段的事，等命中率看得到再開（`references/issue-reporting.md`）

## 參考文件

| 檔案 | 內容 |
|------|------|
| `CONTEXT.md` | ★ 術語表——預設表／自建表兩大類＋四個機制詞（含稱謂對照與禁用詞：舊稱 SaaS 表與外部產品名都不出現） |
| `references/custom-app-dev-guide.md` | 核心 API 規格與架構理念；**§15.1 匿名存取的平台核可三態**、§12 Storage 坑表、**§27 租戶資料存取規則（Auth gate：403 帶 `reason` 的來源）**、§28 冷啟動／常駐（`always_on`） |
| `references/data-center.md` | 自建表完整規格（型別、配額、權限、SDK）＋ 延伸欄位（§10） |
| `references/default-table-lookup.md` | **判「平台有沒有同語意實體」時（Phase 1.5 第 3 項、遷入 §2.4 每張表必查）**：業務語言→預設表速查、表名前綴讀法、Meta 面↔引用面對照、必填欄與唯讀表、遷入常見誤判 |
| `references/event-triggers.md` | Webhook 與 App 排程（冪等要求、宣告、限制） |
| `references/product-line-decision.md` | **Phase 1.5 判產品線與模式時（兩條路共用 SSOT）**：預設 Custom App 與偏離訊號、Custom App 能力邊界核對表、兩問四象限（登入者一律 internal）、混合方案分工（含 Hosted 當 Custom 後端）、不可逆前提、app 分配表 |
| `references/member-admin.md` | **Phase 1.5 第 1.7 項授權架構選型的 SSOT ＋ 成員／角色管理 playbook**：內外人員共用帳號體系的立場、三問與授權架構表、邀請／角色端點與權限、`access_role_ids`（兩條線）、批次邀請流程與四個邊界、Hosted internal 拿不到任何身分、既有系統使用者搬遷、403 解讀 |
| `references/migration-workflow.md` | **有現存系統要遷入時**：stack 盤點（§2.0，最先做）、產品線判斷的遷入輸入（§2.1）、專案解構、Schema 映射、資料遷移 |
| `references/verification-details.md` | **要執行驗證時**：四項驗證的完整定義、Phase 5 里程碑 |
| `references/troubleshooting.md` | **出錯時**：錯誤速查表 |
| `references/pre-report-self-grill.md` | **回報平台問題前（必走）**：預設平台正確、六輪自審排除樹、送出條件、已排除清單 |
| `references/issue-reporting.md` | **回報平台問題時**：BDD 撰寫規範、指令、進度追蹤 |
| `references/platform-behaviors.md` | **實測行為補遺**：DB Proxy 分頁與筆數上限、`custom_data` 不可伺服器端過濾、TIMESTAMP 格式、seed 表唯讀、`ctx.erp` 白名單、深連結與「找不到此應用」三層（§6.2）、空渲染偵測、API 權限閘（app 軸；人軸見 dev-guide §27） |
| `references/hosted-apps.md` | **Hosted App（「自訂 App」）產品線**：與 Custom App 的邊界、應用形狀硬規則、部署 API、**部署後驗證閘門（§3.4＝Phase 4.2 的等價物）**、env 規則、錯誤碼對照——Phase 1.5 判斷走這條線或混合方案時讀 |
| `references/data-operations.md` | **資料操作模式（不開發 app）**：四條使用者身分資料面與權限閘、**寫入閘門（§3.5，正式資料不可逆）**、模組 REST 慣例、匯出白名單、Meta 值域、出錯與回報出口（§7）——源頭意圖判成「資料操作」時讀 |
