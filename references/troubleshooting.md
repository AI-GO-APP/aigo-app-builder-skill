# 錯誤速查

> 任何一步失敗、或收到非預期狀態碼時查這裡。**先查表再動手**——
> 下面多數症狀有明確成因，自行推測修法通常會改錯地方。

---

## 錯誤速查表

| 錯誤 | 解法 |
|------|------|
| 白屏 | 確認 `src/main.tsx` 正確掛載 React |
| 路由不動 | 使用 `HashRouter`，不可用 `BrowserRouter` |
| 頁面無法捲動 | Layout 需 `height: 100vh; overflow-y: auto` |
| CSS 不生效 | 確認 `main.tsx` 中 `import "./App.css"` |
| CSS 變數遺失 | `:root` 改為 `:host, :root` |
| `db.update()` 400 | 用 `{"data": {...}}` 包裝 payload |
| `db.ts` 500 | 確認 Data Reference 已建立並發布 |
| `hasPermission()` 全 false／`getRoles()` 空陣列 | 權限快照（`__USER_ROLES__`／`__USER_PERMISSIONS__`）**只注入 Internal App 且非匿名渲染**，External／匿名恆為空——不是 bug，UI 要有降級路徑；也別改用 `/api/v1/auth/me` 硬撈 → `custom-app-dev-guide.md` §6 |
| `import ... from "../user"` 編譯失敗／找不到模組 | `src/user.ts`（連同 `db.ts`／`approval.ts`）**要在 Builder 後台開過「開發」分頁才會進 VFS**，純 API 建立的 App 沒有。請用戶開一次分頁，或改直接讀注入的全域 → `platform-behaviors.md` §10.2 |
| 角色改名後條件顯示失效 | 判斷寫死了角色名稱；改用 permission 標籤（`模組.動作`），`system.admin` 自動通過 |
| 回傳帶 `approval_status: "pending"` | 命中租戶簽核流程，**既非成功也非失敗**。記錄已寫入但未生效，**不可重試 insert**（會重複建單）→ `custom-app-dev-guide.md` §24 |
| Action 拋「需要簽核審批」 | `ctx.db.update/remove` 或 `ctx.erp.*` 的 pre-guard，操作**未執行**、payload 已暫存，核准後平台自動執行 → **不重試、不換路徑繞過**（§24） |
| 寫入「成功」但 SaaS 表資料沒變 | 十之八九是簽核攔截：先看回傳有無 `approval_status` / 例外訊息，不要往 Data Reference 權限或 500 方向誤診 |
| **登入回 401「帳號或密碼錯誤」** | 兩種成因**平台刻意讓它同形**：① 密碼錯 ② `base_url` 指到**別的租戶**——同一組帳密在其他租戶等同不存在。先確認網址是 `https://[tenant].ai-go.app`（tenant = 用戶登入時網址列第一段），**別一路往密碼方向查**。`aigo_auth.py status` 會印出實際生效的租戶空間 → `platform-behaviors.md` §6.1 |
| 打 `https://ai-go.app/...` 沒反應／導去找工作區的頁面 | apex 已不是租戶入口，`/login` 被收斂成 workspace finder。全平台規則是 `https://[tenant].ai-go.app/*` → `platform-behaviors.md` §6.1 |
| 401 | Token 過期，重新登入 |
| 409 Conflict | VFS 版本衝突，重新 GET 後重試 |
| 409 `ACTION_REMOVAL` | 本次發布會移除既有 action（回應的 `removed_actions` 列出是哪些）。目前未找到 API 層的確認參數，暫以「把該 action 檔放回再發布」處理 → `platform-behaviors.md` §5.2 |
| 423 Locked | 有待審核的發布，等待或取消 |
| 寫入日期時間欄位回 500 `offset-naive and offset-aware` | 送了帶 `Z` 的 `toISOString()`。TIMESTAMP 欄位吃 offset-naive，改用 `toISOString().slice(0, 19)` → `platform-behaviors.md` §2 |
| 宣告 create/update 權限回 403 `seed_table_readonly` | 該表是平台衍生表（`stock_moves`／`stock_quants`／`mrp_workorders` 等），只能 read。改寫來源單據再用 `ctx.erp.*` 觸發 → `platform-behaviors.md` §3 |
| `filters` 指到 `custom_data` 回 400 `不合法的欄位名稱` | JSONB 不支援伺服器端過濾。要篩選的維度請放原生欄位 → `platform-behaviors.md` §1.3 |
| 分頁取回的筆數比實際少 | `offset` 分頁沒指定唯一鍵排序，預設 `created_at` 有重複值時會跨頁重複又漏抓。加 `order_by: [{column:"id",direction:"asc"}]` → `platform-behaviors.md` §1.2 |
| 刪除 VFS 檔案回 400 缺 `expected_version` | `DELETE /source/files` 的樂觀鎖必填，body 為 `{paths, expected_version}` → `platform-behaviors.md` §5.1 |
| `ctx.erp.xxx` 回 403（來自 `/internal/ctx/invoke`） | 該方法不在閘道白名單。可用的六個見 `platform-behaviors.md` §4.2；403 是「方法未開通」不是「能力不存在」 |
| Action 超時 | 控制在 30 秒內，長任務切批次；若 timeout 出在對外呼叫，先確認不是 raw httpx 直連（見下一列） |
| **Action 打第三方 API 連不出去** | 先看症狀對症：**timeout（約 20 秒）** = raw `import httpx/requests` 直連——runner 是 default-deny egress，必改 `ctx.http.call(<egress-slug>, <path>)`；**`ctx.http.call` 仍失敗** = slug 沒有同名「外部服務」或服務未授權給本 App → 引導用戶到 Builder（`/builder/{app_id}`）「外部服務」tab 建立（base_url 域名白名單）並授權本 App；**401** = 外部 API 拒絕憑證——閘道不注入也不剝除 `Authorization`（域名驗證 only，ADR 0010），檢查 action 自組的 header 與 `ctx.secrets` 金鑰（app 側問題，別改外部服務設定）。前兩種設定問題**停止改 code**；建立需本 App 擁有者或 admin，權限不足請管理員代設 → `custom-app-dev-guide.md` §25 |
| pub/ API 403 | 確認 `allow_anonymous_access=true`；且**只有 `external` / `self_built` 能啟用匿名**，`internal` app 開不了 |
| **呼叫 action 回 403** | 依序查：① **有 publish 嗎**——sync 與 compile 都不會讓 action 上線，觸發看的是**發布快照**（最常見成因）② action 在 `actions/manifest.json` 裡嗎、`is_enabled` 是不是 false、名字與 `runAction()` 傳的字串是否完全一致 ③ 帳號缺 `builder.access`（403 是權限，401 才是 token 過期）④ 403 是否其實來自 action **內部**——看執行紀錄的 `error`，不要只看外層狀態碼 |
| Compile 產物驗證失敗 | 檢查 main.tsx 入口和 App.css import |
| CRUD 驗證失敗 | 確認自建表已建立且欄位實體名正確 |
| Action 驗證失敗 | 檢查 execute(ctx) 函式、依賴模組是否可用 |
| Publish 一致性失敗 | 重新 sync → compile → publish 完整循環 |
| 建表 403 | 帳號非 `system.admin`，改輸出建表規格引導用戶到資料中心 UI 自建 |
| 建表／加欄 409 | 撞配額或實體名撞名 → 配額數值見 `data-center.md` §4 |
| 刪表／刪欄被擋 | 兩段式刪除：先取 `/impact`，確認值必須是**實體名**不是顯示名 |
| webhook 端點 404 | manifest 缺 `"webhook": true`，或**改完沒 republish** |
| webhook 驗簽失敗 | 用了重新序列化的 body；必須用 `ctx.params["body"]` 原字串 |
| 同一事件處理兩次 | 第三方登記了新舊兩條 URL，或 action 沒做冪等 |
| 建排程 400 | 撞 tier 限制 → 數值見 `event-triggers.md` §2.4；或 app 還是草稿 |
| 排程建了不跑 | `nextcall` 計算中（正常，稍候）／app 未發布／已被自動暫停 |
| 排程突然停了 | 看 `paused_reason`：403×2、error×10、或降檔 tier 違規 |
| 排程 action 逾時 | 超過上限要切批次；**webhook 的上限比 cron 短**，見 `event-triggers.md` §1.6／§2.6 |
| 工時／天數算出來多 8 小時 | 原生 TIMESTAMP 是 offset-naive 的 UTC，JS 會當成本地時間 → 解析前補 `Z`，見 `platform-behaviors.md` §8 |
| 顯示的時間比牆上時間早 8 小時 | 直接切字串顯示了 UTC 值 → 一律走本地時區的格式化函式 |
| 日期比對整批對不上／少一天 | 用了 `toISOString().slice(0,10)`（UTC 日期）→ 改用本地日期 |
| 負偏移時區下 DATE 欄位顯示早一天 | `toTime()` 對 DATE-only 值補 `T00:00:00Z`，只在 UTC+0 以東安全。DATE-only 欄位改用字串比對／顯示，別轉時間戳 → `platform-behaviors.md` §8 |
| 新增回 500 `NotNullViolationError` | columns API 不回 nullable，必填欄位清單見 `platform-behaviors.md` §9 |
| `'str' object has no attribute 'hour'` | TIME 欄位不收純時間字串，要送完整 ISO datetime |
| `window.__CURRENT_USER__` 是 undefined | 這個全域**任何模式都不存在**（不是 internal 才沒有）。要身分改解 `__APP_TOKEN__` 的 JWT payload；要權限用 `__USER_PERMISSIONS__` → `platform-behaviors.md` §10 |
| `__IS_AUTHENTICATED__` 讀到 undefined／恆為 false | 它只在**匿名渲染**注入且恆為 `false`，不能拿來判斷「是否已登入」→ `platform-behaviors.md` §10.1 |
| 扣帳成功但單據還是「未扣帳」 | `stock_pickings.state` 不會變，只有 `date_done` 會寫；冪等要看 `stock_moves.state` → `platform-behaviors.md` §4.3 |
| validate 後庫存沒動、也不報錯 | 該單沒有 `stock_moves` 明細；明細是 seed 表 App 寫不了，要先在 ERP 補。UI 應在明細為空時停用按鈕 → `platform-behaviors.md` §4.3 |
| 身分欄位被填成別人的 id | 前端從 token 解出的 `sub` 可被竄改。Server Action 一律用 `ctx.user_id` 覆蓋前端送來的值 → `platform-behaviors.md` §10.3 |

---

## 查不到怎麼辦

1. 對照 `references/data-center.md` §7 / `references/event-triggers.md` §3 的分項速查
2. 狀態碼語義：**403**＝權限（看是 `system.admin` 還是 `builder.access`）；
   **409**＝配額或衝突；**422**＝輸入不合法（欄位／型別／查詢契約）；
   **400**＝業務規則拒絕（tier 超限、草稿 app 建排程、暫停排程 run-now）
3. 仍無解 → 回報用戶，附上完整請求與回應，**不要反覆重試**
