# Phase 0：Review 現有 Code（完整流程）

> `SKILL.md` Phase 0 只留九步標題與三道不可跳過的盤點；每一步要打哪個端點、報告要列什麼、
> 哪些情況標「必改」都在本檔。`scripts/aigo_review.py` 的 `review_app()` 已封裝大部分步驟。

## 目錄

- 步驟 1–2：找工作區、取 Token（不向用戶要密碼）
- 步驟 4–5：取 VFS 與 Review 報告的內容（SDK／注入檔標記、legacy 偵測、builder.access 破口、
  webhook 宣告、Data Reference 盤點、CSS 相容性）
- 步驟 6：租戶既有自建表盤點（★ 避免重複建表；順手掃命名）
- 步驟 7：既有排程盤點
- 步驟 8：對外呼叫與 Egress 盤點（哪些情況標必改）
- 步驟 9：確認理解後才進開發

---

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
