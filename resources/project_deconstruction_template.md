# 既有專案解構清單（前端 + 後端 + DB 完整專案遷入用）

> 本模板用於 `references/migration-workflow.md` §2.2。與 `migration_mapping_template.md`
> （資料表映射）配對使用：那份管「資料放哪」，這份管「程式與服務元件落到哪」。
> 每個要遷入的專案填寫一份。

## 系統資訊

| 項目 | 值 |
|------|---|
| 系統名稱 | |
| 技術棧（前端 / 後端 / DB） | |
| stack 形狀結論（§2.0） | 純前端 / 有後端、可改寫 / 有後端、整搬 |
| 產品線判斷結果（§2.1） | Custom App internal / Custom App external / Hosted App |
| 對應 AI GO App | |

## 元件落點對照（Custom App 線）

逐項盤點原專案，填「原專案現況」欄；「AI GO 落點」欄是固定答案，照表遷。

| 元件 | 原專案現況（填寫） | AI GO 落點 | 參考 |
|------|------------------|-----------|------|
| 頁面／路由 | | Builder VFS：多頁 `HashRouter` + Sidebar／單頁免 Router | SKILL.md Phase 2 |
| 後端 API endpoints | | 讀寫租戶資料 → 前端 SDK 直呼（`db.ts`／`api.ts`）；含業務邏輯、機敏分流、需要伺服器身分 → Server Action | dev-guide §6／§7 |
| 背景排程（cron、queue worker） | | App 排程（綁 action；有執行時間上限與 tier 限制，長任務要切批次） | event-triggers.md §2 |
| 接收外部 webhook | | `actions/manifest.json` 宣告 `"webhook": true` 的 action；必須冪等 + 驗簽 | event-triggers.md §0–1 |
| 檔案上傳／儲存（S3、Supabase Storage…） | | Storage API（單檔 100MB）；歷史檔案要「原系統下載 → 重新上傳 → 資料列裡的 URL/path 改寫」，這是資料遷移的一部分，別漏 | dev-guide §12 |
| 呼叫第三方 API | | `ctx.http.call(slug, ...)` + Builder「外部服務」同名 slug 白名單；**計畫階段就要建** | dev-guide §25 |
| 環境變數／金鑰 | | `ctx.secrets`（Builder「服務」tab 設定）；不進 code、不進 config | SKILL.md 規則、dev-guide §25 |
| 寄信／通知 | | `ctx` 沒有寄信能力——走第三方郵件服務（同「第三方 API」列） | dev-guide §25 |
| Realtime／WebSocket 推播 | | Custom App **無對應**——輪詢替代，或此需求足以改判 Hosted App（回 §2.1 重新判斷） | hosted-apps.md §1 |
| 使用者／認證 | | ★ 特殊處理，見下節——**不進資料表映射流程** | 下節 |
| DB 層邏輯（trigger／view／RLS／procedure） | | ★ 特殊處理，見下下節 | 下下節 |

> **Hosted App 線**：程式整套搬進容器，上表的路由／排程／檔案等元件多半原樣保留，
> 但有一項**必做的改寫工項不可省**——
>
> | 元件 | AI GO 落點 | 參考 |
> |------|-----------|------|
> | **資料層（ORM／SQL／DB driver 呼叫）** | **全部改寫成 Open Proxy REST**（`$AIGO_API_TOKEN` 打 `/api/v1/open/...`）——資料一律遷入平台的表（預設引用＋自建），原 DB 退場；改寫前同樣要先完成逐欄映射 | hosted-apps.md §7.1 |
>
> 另要盤 `hosted-apps.md` §2 的應用形狀硬規則、§4 環境變數。
> 盤點時把原專案所有「開 DB 連線／下 SQL」的位置列成清單，這份清單就是改寫工作量的依據。
> ⚠️ **DB 與 storage 不得自立成 Hosted App**（含 PostgREST 類 REST 包裝，
> SKILL.md 規則 32）——原專案若有 docker-compose 帶 db／redis service，
> 那些 service **不在**「整套搬」的範圍內，資料一律遷入平台的表與 Storage。

## 使用者／認證表（★ 不要當一般資料表遷）

原專案的 `users`／`accounts` 表**不進** `migration_mapping_template.md` 的映射流程。
把它建成自建表 = 在 app 內另建一套帳號體系，正是 SKILL.md 規則 23 禁止的反模式。

| 產品線判斷結果 | 使用者的去向 | 既有帳號怎麼辦 |
|---|---|---|
| Custom App **internal** | 平台租戶成員 + 平台角色權限 | 逐一（或請管理員批次）用成員邀請把人請進租戶，可指定落點直達 App（dev-guide §14.1）；app 內**不建**使用者表 |
| Custom App **external** | custom-app-auth 自助註冊／登入（dev-guide §14） | **密碼 hash 無法遷移**——請既有使用者重新註冊（或走「首次登入重設密碼」的溝通流程）。目前無批次預建帳號的公開 API；帳號量大時先回報平台確認方案再開工 |
| Hosted App internal | 平台 proxy 代處理登入（hosted-apps.md §6） | 同 internal：人要先是租戶成員 |
| Hosted App public | app 自理（原認證系統跟著原始碼一起搬） | 原 users 表跟著 app 的 DB 走（§7.1），平台不介入 |

使用者表上「跟著人走的業務欄位」（偏好設定、等級、標籤…）另拆出來：
internal → 存自建表、以平台 user id 當 key；external → 同樣存自建表、
以 external auth 的 user id 當 key。

## DB 層邏輯（trigger / view / RLS / stored procedure / edge functions）

AI GO 的資料層**不提供**這些機制——邏輯必須上移到程式層，逐條盤點：

| 原機制 | 遷移方式 |
|---|---|
| trigger（寫入時自動算欄位、連動更新） | 改寫進負責該寫入的 Server Action；**所有寫入路徑都要經過這個 action**，前端不得繞過直寫 |
| view（彙總查詢） | Server Action 內查詢後組裝；或前端拉原始資料自算（量小時） |
| RLS policy（列級權限） | internal：action 內用 `ctx.user_permissions`／`ctx.user_id` 分流（SKILL.md 規則 23）；平台租戶隔離已由 DB Proxy 處理，**不要**自己補 tenant 過濾（規則 25） |
| stored procedure | 改寫成 Server Action |
| Supabase edge functions | 改寫成 Server Action；對外呼叫改 `ctx.http.call` |
| Supabase realtime 訂閱 | 無對應——輪詢替代，或改判 Hosted App |
| DB 層 unique／check 約束 | 自建表僅 `select` 型別有 CHECK、欄位可設唯一；複合約束無對應 → Server Action 寫入前檢查 |

盤點結果：

| 原機制（名稱） | 類型 | 遷移方式 | 落到哪個 action |
|---|---|---|---|
| | | | |

## 前端可移植性核對結果（Custom App 線）

> 核對項清單見 `migration-workflow.md` §2.3。這裡記結論，向用戶預告工作量。

| 核對項 | 原專案現況 | 需要的改寫 |
|---|---|---|
| CSS 方案 | | |
| Router | | |
| npm 依賴（Runtime 五件套之外的） | | |
| `confirm`/`alert`/`prompt` 使用處 | | |
| 檔案數／單檔大小 | | |
| 動態 import | | |
