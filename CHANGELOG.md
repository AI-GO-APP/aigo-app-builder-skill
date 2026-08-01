# Changelog

版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。
**每次改動 Skill 內容（SKILL.md / CONTEXT.md / references / scripts）都要同步更新 `VERSION`**，
否則使用者端的更新檢查（`scripts/check_update.py`）不會提示。

## 1.6.0

### `platform-behaviors.md` 新增四節：時區、NOT NULL、登入身分、扣帳判定

承 1.4.0，這批來自 26 支 Custom App 的逐頁實機測試（含每個寫入動作比對資料庫實際內容），
補的是「只有真的按下按鈕才會浮現、看文件與型別都看不出來」的行為。

- **§8 原生 TIMESTAMP／DATE 是 offset-naive 的 UTC**（★ 靜默出錯）：平台混用 timestamptz
  （`created_at`，帶 `+00:00`）與原生 TIMESTAMP／DATE（`check_in`／`date_from`／`work_date`）。
  後者存的是 UTC，但 ECMAScript 規定不帶時區的字串視為本地時間，在 UTC+8 直接差 8 小時——
  實測相隔 6 分鐘的上下班打卡被算成 **8.1 小時**工時並寫進 `hr_attendances.worked_hours`。
  附可直接沿用的 `toTime()`；顯示與日期推導同樣不可切字串。
- **§9 NOT NULL 欄位只有在真的送出時才會浮現**：`GET /refs/tables/{table}/columns` 不回
  nullable 資訊，列出實測到的 8 張表必填欄位，以及 TIME 欄位不收純時間字串（要送完整 ISO datetime）。
- **§10 internal runtime 不注入 `__CURRENT_USER__`**：改解 `__APP_TOKEN__` 的 JWT payload
  取 `sub`／`email`／`tenant_id`，不需呼叫本 skill 禁止的 `/api/v1/auth/me`。
  這不只是顯示用途——`import_jobs.user_id` 是 NOT NULL，取不到就無法新增。
- **§11 `validate_picking` 之後 `state` 不會變**：補上 §4.3 未涵蓋的一項——沒有 `stock_moves`
  明細的單據呼叫 validate 不會產生任何庫存異動，而明細是 seed 表、App 寫不了，UI 應直接擋掉。

`troubleshooting.md` 同步補 8 條徵狀速查。

> 待辦（下一版處理）：§10 與 `custom-app-dev-guide.md` §6（User Context / `user.ts`）、
> §13（Runtime 全域變數）口徑需對齊；§11 與 §4.3 內容重疊應合併；§8 屬「不拋例外的靜默出錯」，
> 依 1.4.0 的判準應升為 `SKILL.md` 核心規則。

## 1.5.0

### 憑證改以 `~/.aigo/.env` 為預設位置（★ 避免更新 Skill 洗掉憑證）

`npx skills update` 的實作是重跑 `add`，而 installer 對目標資料夾先做
`rm(path, { recursive: true, force: true })` 再整包複製——**整個 skill 目錄會被刪掉重建**。
先前文件卻引導使用者在 skill 目錄下執行 `aigo_auth.py setup`（`cd scripts` 跑 E2E 亦同），
憑證因此會落在 `<skill>/.aigo/.env`，一次更新就全數消失；又因被 `.gitignore` 忽略、
不在任何 commit 內，無從還原。（git clone 安裝走 `git pull --ff-only` 不受影響——
pull 不會刪除 ignored 檔案。）

- `aigo_auth.load_env_file()` 改為依序讀 `<專案>/.aigo/.env` → `~/.aigo/.env`，
  **先讀到的優先**（環境變數仍最優先）。專案級只需寫要覆寫的鍵，其餘沿用機器級。
- `aigo_auth.py setup` 不帶參數時改寫 `~/.aigo/.env`；要寫進特定專案改用
  `setup <專案路徑>`。新增 `credentials_path()` 供其他腳本取得位置。
- `status` 同時列出機器級與專案級憑證檔及其存在狀態。
- 找不到憑證時的 `RuntimeError` 訊息改指向 `~/.aigo/.env`。
- `README.md`／`SKILL.md` 補上「憑證不得放進 Skill 安裝目錄」的警告與查找順序表；
  README 的 E2E 範例改用 `AIGO_PROJECT_ROOT` 指向使用者的 app 專案。

> 既有把憑證放在專案 `.aigo/.env` 的使用者不受影響，行為完全相容。
> 若你的憑證目前在 skill 目錄裡，請儘快搬到 `~/.aigo/.env`。

## 1.4.0

### 新增 `references/platform-behaviors.md`：實測平台行為補遺

以正式站單一租戶實跑 API 取得，補上規格文件沒寫、但一踩就卡住的行為。
全部條目都附驗證方式與實測數字。

- **DB Proxy 查詢**：單次硬上限 500 筆、回傳是裸陣列（無 `total` 信封）；
  `offset` 分頁**必須指定唯一鍵排序**，否則預設的 `created_at` 有重複值時會
  跨頁重複又漏抓（實測某表 1866 筆只取回 1860 筆，且不會拋任何錯）。
- **`custom_data` 不能在伺服器端過濾**：四種 JSONB path 語法全部回 400。
  衍生的設計規則是「要被篩選／排序／分頁的維度一律放原生欄位」。
- **補上 `queryAdvanced` 的完整簽名**（`src/db.ts` 有，但文件未載）。
- **寫入 TIMESTAMP 欄位不可帶時區**：`toISOString()` 結尾的 `Z` 會讓 asyncpg 回 500，
  附可接受／不可接受的格式對照表。另記一個 UTC+8 下 `toISOString().slice(0,10)`
  會退回前一天的日期陷阱。
- **平台 seed 表只能宣告 read**：新增錯誤碼 `seed_table_readonly` 的說明與
  已知表清單（`stock_moves`／`stock_quants`／`mrp_workorders`），
  以及「寫來源單據 + `ctx.erp.*` 觸發」的正確做法。
- **`ctx` 實際有 20 個命名空間**（平台規格文件列 8 個），並補上 `ctx.erp` 的六個白名單方法
  與回傳型別。釐清 `/internal/ctx/invoke` 的 **403 代表「方法不在白名單」**，
  不是「能力不存在」——`dir()` 對遠端代理物件取不到方法名，只能實際呼叫判斷。
- **`ctx.erp.validate_picking` 的冪等陷阱**：實測成功後 `stock_pickings.state`
  **不會**轉為 `done`（只寫 `date_done`），真正反映完成的是 `stock_moves.state`。
  以單據 state 做冪等判定會導致守門永遠不生效。
- **Builder API 兩個必填／衝突**：`DELETE /source/files` 需 `expected_version`；
  發布若會移除既有 action 會回 409 `ACTION_REMOVAL`。
- **Internal App 執行期網址**為 `{tenant}.ai-go.app/runtime/{slug}`，
  並註明 App 渲染在 Shadow DOM 內（自動化測試會踩到）。
- **Server Action 必須 publish 後才可呼叫**，只 sync 會回 404。

`troubleshooting.md` 同步新增 8 條錯誤速查，皆指向本檔對應章節。

### `db.json` 不再是 Data Reference 的判定依據（★ 修正既有指引）

實測 `src/db.json` 在 VFS 內恆為 `{}`，即使 Data Reference 全部註冊成功——
它是執行期注入檔。原先 SKILL.md Phase 0 有一條 ★ 重要步驟要「解析 db.json 列出
SaaS 表、欄位、權限、`app_domain` 分布」，照做只會拿到空清單。

- `SKILL.md` Phase 0 步驟 5、Phase 1.5 盤點步驟改走
  `GET /api/v1/refs/apps/{app_id}`，並明說 db.json 不可作為判定依據。
- `custom-app-dev-guide.md` §19 兩軌差異表、§19 決策流程、§22.x 加入引用流程、
  `CONTEXT.md` 同步改口徑。

### 靜默出錯的兩條升為核心規則

`platform-behaviors.md` 是按需讀取的，但 `offset` 分頁與 `validate_picking` 冪等
這兩條**不拋例外、不報警告**，agent 不會因為看到錯誤而去翻文件。故規則本體
放進常駐的 `SKILL.md`（核心規則 26、27）。

### 其他

- `custom-app-dev-guide.md` §7 ctx 清單補 `ctx.erp` 並指向 `platform-behaviors.md` §4.2。
- §18 app_domain 補上「前端過濾 + 500 筆上限」的複合風險警語。

## 1.3.0

### 租戶邊界：補上「表沒有 `tenant_id` 不等於沒保護」

- **起因**：開發者實測回報「`announcement_reads` / `import_mappings` / `ir_sequences` /
  `msg_messages` / `account_accounts` 沒有 `tenant_id`，是 bug 嗎？」——查證結論是
  **五張全部刻意設計、租戶隔離正常**，但本 Skill 先前完全沒有描述租戶邊界形態，
  §20.2 的回應範例又剛好拿了自帶 `tenant_id` 的 `customers` 當例子，等於默認
  「每張表都有 `tenant_id`」。Agent 依此推論會走上兩條錯路：誤判該表不安全而改用別的表，
  或自己補 `WHERE tenant_id = ...`（那些表根本沒這欄位，直接失敗）。
- **新增 `custom-app-dev-guide.md` §20.3「租戶邊界：不要用『有沒有 `tenant_id`』判斷」**：
  列出 DB Proxy 的四種邊界形態（自帶 `tenant_id` ／ 欄位別名 `company_id` ／ 父表歸屬
  `EXISTS` 子查詢 ／ 全域表刻意不過濾）與各自的代表表，並給兩條實作守則
  （不自補 `WHERE tenant_id`、不因缺欄位就改用別的表）。原 §20.3 典型使用流程順延為 §20.4。
- **`SKILL.md` 新增核心規則 25「表沒有 `tenant_id` 不等於沒保護」**（★ 強制）：
  reference 是按需讀取的，但真正會誤判的時點是 Phase 1.5 查欄位結構的當下，
  agent 未必開過指南——故規則本體放進常駐的 SKILL.md，並在 Phase 1.5「資料架構設計」
  盤點步驟就地補一句警語。
- **§20.2 補註**：明示回應範例是「自帶 `tenant_id`」形態，不是每張表都有。
- **§17 常見問題速查**：新增一列，讓 agent 不必讀完 §20 就能命中答案。
- 平台側同步：AI GO repo `docs/integrations/custom-app-agent.md` §7.2 補上第四種形態
  （全域表）與同一條警語。

## 1.2.0

### 對外 API 呼叫改回 `ctx.http.call` 閘道（反轉 1.1.0 的指引）

- **1.1.0「直接 `import httpx`」的指引已被實測推翻**：AI GO runner pod 是
  **default-deny egress**（`httpx`/`requests`/`urllib.request` 在沙箱 denylist，
  出口網路只放行平台閘道與 DNS），raw httpx 直連**必定 timeout**。
  實測（2026-07-28，Developer 平台沙箱）：raw `httpx.get(...)` 20 秒 timeout；
  `ctx.http.call` 3/3 成功。raw httpx 寫法的 action 測不過沙箱，
  而送審門檻要求每支 enabled action 至少一次 success——等於卡死。
- 對外呼叫一律 **`ctx.http.call("<egress-slug>", "<path>", method=..., body=...)`**：
  base_url 與憑證來自租戶在後台 `/dashboard/settings/integrations` 以**同名 slug**
  註冊的 **EgressService**。回傳 dict（`status` + `data`），要自己檢查 status。
- **憑證不可自帶 `Authorization` header**：閘道會剝掉自帶的授權標頭
  （AI GO `connector_proxy._sanitize_headers` 與 Developer 平台 `dev_ctx._STRIPPED`
  兩邊都剝），實測回 **401**。金鑰歸 EgressService，action 不碰，
  也不需要為它開 `ctx.secrets` key（`ctx.secrets.get()` 留給 webhook 驗簽等
  非對外憑證用途）。
- 同步改寫：
  - `SKILL.md`：Phase 0 步驟 8（盤點 egress slug、raw httpx 標記必改）、
    Phase 1.5 項目 4.6（盤點表改 `slug + base_url`、金鑰不開 secret key）、
    Phase 3「呼叫外部 API」範例、ctx API 清單補 `ctx.http.call`、
    「錯誤處理：Action 對外呼叫失敗」（timeout／401 對症分流）
  - `custom-app-dev-guide.md` §25：全面改寫（呼叫寫法、EgressService 註冊、
    症狀對照表、規劃階段盤點）；§7 ctx API 清單補回 `ctx.http.call`；§17 速查列同步
  - `troubleshooting.md`：「Action 打第三方 API 連不出去」「Action 超時」兩列
- 寫法對齊 aigo-template-transfer-skill v0.4.0（鐵律 6、pollution-signals、
  `raw_http_outbound` 掃描規則）。

## 1.1.1

- 後台頁面一律改用**相對路徑**指引（`/dashboard/settings/integrations`、`/dashboard`），
  不再寫死主機名稱——子網域日後可能變動。
  與 `event-triggers.md` 既有的 `/dashboard/settings/app-crons` 寫法一致。
- §25.2 補上這條慣例，避免後續文件又寫回完整 URL。

## 1.1.0

### 對外 API 呼叫與 Egress 白名單

- **移除 `ctx.http.call` 的所有記述**（SKILL.md、`custom-app-dev-guide.md` §7）。
  原本把它列為呼叫外部 API 的方式，會把 agent 帶往錯誤路徑。
- Server-Side Action 呼叫第三方 API 一律**直接 `import httpx`**，
  金鑰走 `ctx.secrets.get()`，並強制設 `timeout=`。
- 新增 `custom-app-dev-guide.md` **§25 對外 API 呼叫與 Egress 白名單**：
  呼叫寫法、白名單設定位置（後台 → Settings → Integrations）、
  權限不足時的處置、被擋掉時的診斷準則。
- Egress 白名單納入流程各階段：
  - Phase 0 新增步驟 8「盤點對外呼叫與 Egress」
  - Phase 1.5 新增計畫項目 4.6「對外 API 呼叫盤點」——規劃階段就要列出網域並提醒申請
  - SKILL.md「錯誤處理」新增「Action 對外呼叫失敗」小節
  - `troubleshooting.md` 新增對應速查列
- 核心準則：對外呼叫失敗時**先讀 API 回傳的 error message**；
  指向 Egress 或權限就停止改 code，引導用戶設定白名單
  （看不到設定頁 = 權限不足，請租戶管理員代設）。

### 憑證與 Token

- 新增 `aigo_auth.get_token()` 作為所有 API 呼叫的統一入口：
  依序嘗試「未過期 Token 快取 → `refresh_token` 換發 → `.aigo/.env` 帳密登入」。
- Token 快取於 `.aigo/token.json`，剩餘不足 5 分鐘提前換新
  （平台 Token 效期 1 小時，避免長流程中途 401）。
- 憑證改放 `.aigo/.env`（`.gitignore` 已涵蓋 `.aigo/`），**每台機器設定一次**即可，
  不必每次開發前設環境變數；環境變數仍為合法來源。
- `aigo_auth.py` 新增 CLI：`setup` / `login` / `status` / `logout`
  （`status` 不顯示秘密值）。
- Phase 0 明訂 agent **不得向用戶索取、代為輸入或寫入密碼**；
  憑證檔一律由使用者本人填寫。
- `run_e2e_tests.py`、`retest_verification.py` 改讀 `.aigo/.env`。

## 1.0.0

- 首次標記版本號。
- 新增 Skill 自我更新檢查機制：`VERSION`、`scripts/check_update.py`、
  SKILL.md「Phase -1：Skill 自我更新檢查」、Claude Code / Codex SessionStart hook 範本。
