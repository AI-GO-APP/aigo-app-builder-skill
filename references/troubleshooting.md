# 錯誤速查

> 任何一步失敗、或收到非預期狀態碼時查這裡。**先查表再動手**——
> 下面多數症狀有明確成因，自行推測修法通常會改錯地方。
> 查完表仍無解、開始懷疑平台 → 先走 `pre-report-self-grill.md` 六輪自審：
> **預設平台必定正確、失敗是自己操作有誤**，排除完才能回報。

---

## 錯誤速查表

| 錯誤 | 解法 |
|------|------|
| 白屏 | 確認 `src/main.tsx` 正確掛載 React；**先開 console**——有 `ReferenceError` 看下一列 |
| **白畫面＋console `Uncaught ReferenceError: Cannot access 'Ee' before initialization`，堆疊首幀在 `esm.sh/scheduler…`** | **app 自己的 use-before-declaration（TDZ）**，不是平台或 esm.sh 壞了。compile 走 esbuild**只轉譯不驗型別**，`compile_errors: []` 照樣過；`'Ee'` 是自家 bundle 的 minified 變數名（每次編譯會變）。定位（兩種，都不必手動比對 bundle offset）：① **bundle 內含 inline source map（含 sourcesContent，2026-09-03 實測）**——devtools 開著 JS source maps，把 console 那則錯誤的堆疊展開，esm.sh 那幾幀下面就是 `src/App.tsx:行號` 的原始位置；② 本機跑 `aigo_typecheck.py`，TS2448 直接指到原始檔行號。修法：把宣告移到使用之前。**發布前跑 typecheck 就不會發生**（SKILL.md Phase 4 步驟 1.5） |
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
| 寫入「成功」但預設表資料沒變 | 十之八九是簽核攔截：先看回傳有無 `approval_status` / 例外訊息，不要往 Data Reference 權限或 500 方向誤診 |
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
| VFS 寫入回 400 `無效的檔案路徑` | 路徑含 `\`、以 `/` 開頭、或含 `..` 段。用 POSIX 相對路徑（`actions/foo.py`）；`Actions/`→`actions/` 等大小寫會被自動折疊 → `custom-app-dev-guide.md` §10 |
| 使用者回報看到「App 已載入但沒有顯示任何內容」 | 平台空渲染偵測（掛載後 8 秒 root 全空）。真啟動失敗 → 查 runtime-errors；app 其實沒壞 → 是「長 API 擋住首次渲染」的誤報，改成先渲染 skeleton → `platform-behaviors.md` §11 |
| 試跑回「draft runner not ready」 | 有 requirements.txt pin 時試跑走專屬 draft runner，冷啟最長約 60 秒——稍候重試，不是壞了 → `custom-app-dev-guide.md` §16.2 |
| 發布／試跑回 422 `WHEELHOUSE_*` | `actions/requirements.txt` 出界：格式限 `name==version`、≤20 行、wheel 合計 ≤80 MiB；`WHEELHOUSE_RESOLVE_FAILED` 常見成因是套件沒有 aarch64 預編譯 wheel → `custom-app-dev-guide.md` §16.2 |
| Builder 引用頁籤 jsonb 欄顯示 `[object Object]`／存檔炸 invalid JSON | 舊版顯示 bug 已修（2026-08）：現在顯示與輸入都是 JSON 字面值——字串要帶引號（`"pro"`），物件寫 `{"k":"v"}` |
| Action 全面逾時、且最近改過 requirements.txt | 依賴安裝失敗會讓 runner 起不來（不帶病上線）。先回頭檢查 requirements.txt 的 pin，不要改 action 邏輯 → `custom-app-dev-guide.md` §16.2 |
| `ctx.erp.xxx` 回 403（來自 `/internal/ctx/invoke`） | 該方法不在閘道白名單。可用的六個見 `platform-behaviors.md` §4.2；403 是「方法未開通」不是「能力不存在」 |
| Action 超時 | 先看 manifest `timeout_ms`（1000～120000，prod v1.13.0 起真的生效；**v1.13.0 前發布的 app 要 republish 一次**才換上新 ceiling，否則仍 30 秒被切）；超過 120 秒的工作切批次；若 timeout 出在對外呼叫，先確認不是 raw httpx 直連（見下一列）→ `custom-app-dev-guide.md` §7 |
| **Action 打第三方 API 連不出去** | 先看症狀對症：**timeout（約 20 秒）** = raw `import httpx/requests` 直連——runner 是 default-deny egress，必改 `ctx.http.call(<egress-slug>, <path>)`；**`ctx.http.call` 仍失敗** = slug 沒有同名「外部服務」或服務未授權給本 App → 引導用戶到 Builder（`/builder/{app_id}`）「外部服務」tab 建立（base_url 域名白名單）並授權本 App；**401** = 外部 API 拒絕憑證——閘道不注入也不剝除 `Authorization`（域名驗證 only，ADR 0010），檢查 action 自組的 header 與 `ctx.secrets` 金鑰（app 側問題，別改外部服務設定）。前兩種設定問題**停止改 code**；建立需本 App 擁有者或 admin，權限不足請管理員代設 → `custom-app-dev-guide.md` §25 |
| pub/ API 403 | 確認 `allow_anonymous_access=true`；且**只有 `external` / `self_built` 能啟用匿名**，`internal` app 開不了——「內部工具想給訪客看一頁」拆成 Hosted public，不是把 app 改 external |
| **特定使用者開 app 拿 404「App 不存在」，別人正常** | 他的角色不在 app 的 `access_role_ids` 白名單內（fail-closed，刻意與查無此 app 同形、不用 403）。Custom：`PATCH /builder/apps/{id}/settings`；Hosted：`PUT /hosted-apps/{id}/access-settings`。先查白名單再查發布狀態；外部人員（經銷商／客戶）同樣是租戶成員，把他們的角色加進名單即可 → `member-admin.md` §3 |
| **`POST /invitations`／建角色／指派角色回 403，帳號明明有 `hr.member_manage`** | 後端子集規則：目標角色的 permissions 不是呼叫者權限的子集（例如想派「系統管理員」）、或建角色時要求的權限字串超出自己所有。印出差集給用戶，請更高權限者操作；不要換角色硬塞 → `member-admin.md` §2／§8 |
| **匯入 job `completed` 但 `imported_count: 0`，`sources[].status: "parked"`、無錯誤訊息** | 目標是自建表（`self_built_table`／`new_table`）——prod 的 import-worker 沒有 tier-3 旗標，靜默 park（API 回的 `tier3_write_enabled: true` 是另一顆 pod 的值）。改走本地腳本逐筆寫自建表；**已回報平台（2026-09-08）**，不必重複開單 → `data-operations.md` §5 |
| **匯入 job `failed`、每列「寫入失敗：必填欄位缺值（非空約束）」** | 目標預設表的必填欄沒對到來源欄——定稿前看 mapping 回應的 `table_required_columns`；已定稿改不了（PUT／retarget 409），補欄後重新上傳。CHECK 值域用 `aigo_data.py meta table` 查 → `data-operations.md` §5 |
| **`PUT /imports/{job}/mapping` 或 `retarget` 回 409「job 狀態 'x' 不可覆核定稿／不可切表重跑」** | 只有 `awaiting_mapping_review` 能改；PUT 一送出就派送 worker 寫入，不是「存草稿」。要改對應只能重新上傳 → `data-operations.md` §5 |
| **匯入 job 停在 `ready` 一分多鐘** | worker 是 scale-to-zero，冷啟動 40 秒～1.5 分鐘是正常；超過 3 分鐘才 `POST /{job}/execute` 重派 → `data-operations.md` §5 |
| **外部人員（無員工列的帳號）在 app 內全部 403 `policy_denied`** | 租戶資料存取規則的 `restrict` 用到 `$user.employee_id`／`department_id`／`manager_id`，對非員工帳號解不出→整列 deny。app 端無解；請管理員對外部角色改用 `$user.id`／`$user.role_ids` 或設 app 級規則放行 → `custom-app-dev-guide.md` §27、`member-admin.md` §1 |
| **一般使用者用 internal app 時資料載不出來／操作沒反應，network 見 `/data-center/...` 403** | **builder.access 破口**：前端直呼了自建表 SDK（`queryTable` 等），以登入者身分過 `builder.access` 閘，無開發權限的員工必 403。修法**只有一條**：包成 Server Action（`ctx.db.*`）＋前端 `runAction`，並在 action 內補授權分流；**不要**發 `builder.access` 給全員、也**不能**改成 external（`access_mode` 不可改）。開發帳號測不出此問題（必有 `builder.access`）→ `data-center.md` §7.5、SKILL.md 規則 31 |
| **呼叫 action 回 403** | 依序查：① **有 publish 嗎**——sync 與 compile 都不會讓 action 上線，觸發看的是**發布快照**（最常見成因）② action 在 `actions/manifest.json` 裡嗎、`is_enabled` 是不是 false、名字與 `runAction()` 傳的字串是否完全一致 ③ `use_dev=true`（開發預覽）才要求 `builder.access`——**已發布 action 只需登入＋app 可見度**；一般使用者連已發布 action 都 403 時查 app 的存取角色設定，不是叫他要開發權限（403 是權限，401 才是 token 過期）④ 403 是否其實來自 action **內部**——看執行紀錄的 `error`，不要只看外層狀態碼 |
| Compile 產物驗證失敗 | 檢查 main.tsx 入口和 App.css import |
| CRUD 驗證失敗 | 確認自建表已建立且欄位實體名正確 |
| Action 驗證失敗 | 檢查 execute(ctx) 函式、依賴模組是否可用 |
| Publish 一致性失敗 | 重新 sync → compile → publish 完整循環 |
| 建表 403 | 帳號缺 `datacenter.schema_write`（也非 `system.admin`），改輸出建表規格引導用戶到資料中心 UI 自建；**刪表／刪欄另限 `system.admin`**（建改與刪除是兩段權限）→ `data-center.md` §2 |
| 建表／加欄 409 | 撞配額（`table_quota_exceeded` / `field_quota_exceeded`，數值見 `data-center.md` §4）或實體名撞名；「**與平台保留表名衝突**」= 撞到平台地板表名（users/tenants/api_keys…），沒有補救管道，換個實體名（⚠️ 2026-09-01 實測此檢查 prod 尚未生效——沒被擋≠可以用，一律自律避開）→ `data-center.md` §1 |
| 文件宣稱的端點回 404／回應缺欄位 | 先懷疑**部署落差**——prod 由 `v*` tag 觸發，可能落後 main 數天到一週；**判準是查 prod 的 `GET /api/v1/openapi.json`（免登入）有沒有那條路徑**，不是文件錯也不是打錯。2026-09-07 prod＝v1.13.0，與 main 幾乎同步；歷史紀錄見 `hosted-apps.md` 檔頭與 `data-center.md` §9 |
| 刪表／刪欄被擋 | 兩段式刪除：先取 `/impact`，確認值必須是**實體名**不是顯示名 |
| **Hosted App rollout 卡「ksvc ready 逾時」，runtime-logs 卻顯示已 Ready** | 框架綁到 pod 名稱、不綁 loopback（`HOSTNAME` 被 k8s 設成 pod 名）。看 runtime-logs 的 `Local:` 是否印 pod 名稱；Dockerfile 加 `ENV HOSTNAME=0.0.0.0`。平台訊息「未聽 PORT」是錯方向；症狀時好時壞 → `hosted-apps.md` §2 |
| **Hosted App 建置 failed、日誌全空、「builder 未留下 termination message」** | 先**原樣重送一次**（偶發型）；再失敗往建置記憶體查：限制建置 worker 數、`--max-old-space-size` 設包絡 60–65%（設太高反而無日誌 OOM）→ `hosted-apps.md` §8 |
| Hosted App 剛部署的改動「沒生效」／新端點 404 | 先確認上一次 rollout 有沒有成功——失敗時對外仍是舊 revision，平台不顯示服務中的版本。回應加 version marker 再判斷 → `hosted-apps.md` §3.2 |
| Hosted App 改了 env 容器讀不到 | 傳播需數分鐘（實測 1–6 分鐘），`apply_state` 不反映容器狀態。等，不要重建；用「移除變數」測最乾淨 → `hosted-apps.md` §4 |
| Hosted App 登入後每個操作都 401／OAuth 導去 `https://0.0.0.0:8080` | 原系統 env 沒帶過來（session 密鑰、對外網址、第三方 key）。逐顆補進 runtime-settings → `hosted-apps.md` §4 遷入 env 清單 |
| Hosted App 容器內打 `/api/v1/data-center/...` 回 401 `Invalid authentication token` | 少了 `/open` 前綴，不是憑證問題 → `hosted-apps.md` §5 |
| `/open/proxy/{table}` 403「App 未被授權存取表」 | 「App」指隨附整合。`POST /api/v1/refs/apps/{整合 id}` 加引用（登入 session），立即生效 → `hosted-apps.md` §5 |
| `/open/*` 403 且 body 帶 `reason`／`rule_id`，引用明明加了 | 租戶「資料存取規則」擋的：app 身分沒有 user，`restrict` 規則一用 `$user.*` 就整列判 deny。請租戶對 app 身分另設規則；app 端無解 → `hosted-apps.md` §5、dev-guide §27 |
| 預設表 proxy query 帶了 `where` 卻回整表 | `where`／`filter`／`conditions` 被**靜默忽略**，只有 `filters:[{column,op,value}]` 生效 → `platform-behaviors.md` §1.5 |
| 自建表 records `filters` 回 422「不支援的運算子」 | records 平面只有 `eq/contains/gte/lte`，且 `gte/lte` 僅 number／date／datetime，text 只有 `eq/contains`；沒有 `in`、沒有 OR → `platform-behaviors.md` §1.5 |
| 自建表 records POST 回 422 `not_null_violation` 但欄位明明有給 | body 沒包 `{"data": {...}}`，整包被忽略後報第一個必填欄位 → `data-center.md` §7 |
| 建自建表 relation 回 422「無法解析 target_erp_key」 | 預設表目標只有部分可解析，無法事先查。改 `text` 存 UUID，唯一性用 `legacy_id`(unique) 承載 → `data-center.md` §3 |
| 自建表 `select` 欄位建欄 422 `Input should be a valid string` | `options` 必須是**純字串陣列**，不收 `{label,value}` → `data-center.md` §3 |
| **模組 REST 分頁抓不齊／筆數與 `total` 對不上**（資料操作線） | 分頁參數**分兩派**：`client`／`sale`／`hr`／`stock`／`purchase` 用 `skip`＋`limit`，`crm` 用 `page`＋`page_size`；單頁上限多為 500（`client` 未設上限、預設 100）。不要手刻翻頁，用 `aigo_data.py call --all` 依 openapi 自動判形狀 → `data-operations.md` §4 |
| 匯出 `/download` 回 409「匯出尚未完成」 | 匯出是**非同步任務**（`queued` → `completed`，實測數十秒）。先輪詢任務狀態再下載，不是壞了 → `data-operations.md` §5 |
| 匯出送自建表回 failed（`custom object not in tenant`／`badly formed hexadecimal UUID string`） | `source_type: custom_table` 指的是**舊 CustomObject**，**資料中心自建表不在匯出範圍**（白名單只有 6 張預設表）。整表取出改用 `call GET /api/v1/data-center/tables/{key}/records --all` → `data-operations.md` §5 |
| `aigo_data.py perm-check` 回 ✅ 卻仍 403 | perm-check 是**推估不是權威**，少數端點另有細權限（`hr.leave_manage`、`accounting.post`）。403 就停、請管理員授權，**不要換路徑繞** → `data-operations.md` §6、`pre-report-self-grill.md` Q3.7 |
| Git Bash 下路徑參數變成 `C:/Program Files/Git/api/v1/...` | MSYS 路徑轉換，不是腳本壞了。`aigo_data.py` 會自動剝除，也接受省略前綴（`call GET client`）；根治在指令前加 `MSYS_NO_PATHCONV=1` 或改用 PowerShell → `data-operations.md` §4 |
| 預設表寫入回 500 `CheckViolationError` | 欄位值不在 CHECK 值域內，columns 端點不回值域。查 `custom-app-dev-guide.md` §20.2 的值域表或 Meta API |
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
| **前端 `db.update()` 回 405** | 舊版注入的 `src/db.ts` 送 `PUT`，資料代理只收 `PATCH`（2026-09-01 修 SDK 模板）。換成最新模板或直接 fetch 用 `PATCH`；不是權限問題 → SKILL.md 規則 12 |
| **呼叫 action 回 503「app runner 暫時不可用」且 body 帶 `quota_hint`** | 租戶運算配額吃緊、pod 建不出來（2026-09-03 起 backend 會把配額說明接在 `detail` 後並帶頂層 `quota_hint`）。**不是 code 問題**：轉告用戶、引導到「運算資源」頁或找管理員；沒有 `quota_hint` 的 503 才依 `Retry-After` 退避重試 |
| **資料層 403、body 帶 `reason`（`policy_denied`／`hidden_column_write`／`policy_invalid`／`runner_unavailable`／`app_data_access_suspended`）＋`rule_id`** | 租戶「資料存取規則」（Auth gate）擋的，**app 端改 code 無解**——把 `rule_id` 轉給租戶管理員到 Builder「資料存取規則」分頁看；`hidden_column_write`＝payload 碰到被遮蔽欄位；UAT on／prod off（2026-09-07）→ `custom-app-dev-guide.md` §27 |
| 使用者開 app 看到整頁「資料存取暫停」 | 管理員對這支 app 按了「封鎖資料存取」（萬用 deny 規則），平台 host 直接接管畫面。找租戶管理員解除，app 沒壞 → dev-guide §27.2 |
| 清單少了欄位／少了列，API 回 200 | 命中 `restrict` 規則：`where` 併進查詢、`hide` 欄位從回應消失——**預期行為**。hide 欄位寫進 `filters`／search 回 400「未授權的篩選欄位」（與欄位不存在同形）、寫進 `order_by` 被靜默略過——都不是 403，別往權限查 → dev-guide §27.2 |
| **已發布 app 閒置一陣子後第一次呼叫 action 很慢／逾時，之後就正常** | runner scale-to-zero 冷啟動，不是 action 壞。付費租戶可 `PATCH /api/v1/builder/apps/{id}/runtime-settings {"always_on": true}`（`builder.publish`）或在 Builder App 設定「執行模式」切常駐；免費 403 `ALWAYS_ON_REQUIRES_PAID_PLAN`、未發布 422、綁通訊渠道的 app 本來就常駐（`locked_reason: messaging_trigger`）→ `custom-app-dev-guide.md` §28 |
| 排程 action 在 120 秒被切、回 `status: "timeout"` | runner 內層 ceiling 最高 120000（2026-09-07 起），cron 的 280 秒只是 dispatcher 外層；切批次到 120 秒內 → `event-triggers.md` §2.6。**30 秒**就被切且 manifest 設更大＝該 app 在 v1.13.0 前發布、還沒 republish（#1518） |
| **pub/ API 或 external app 終端使用者拿 404「App 不存在」，開發者自己預覽正常** | 匿名對外服務**未經平台核可**（開旗標≠核可；核可前刻意與不存在同形，app 使用者 token 也擋）。查 app 的 `anonymous_access_requested_at`／`approved_at`，未申請就 `POST /apps/{id}/anonymous-access-request`，已申請請用戶找平台 → `custom-app-dev-guide.md` §15.1 |
| 分享的 `/runtime/{slug}?…#/page` 深連結登入後落回首頁 | 已修（`?next=` 承載 search+hash，prod v1.13.0 起）；不要在 app 內自己補 localStorage 復原；仍發生就回報平台 → `platform-behaviors.md` §6.2 |
| 用戶回報「找不到此應用」 | 訊息依身分分三層：匿名／token 失效＝通用訊息（刻意不區分未發布與不存在）；已登入同租戶＝「尚未發布」；已登入查不到＝網址錯或跨租戶。先問**登入了沒、同租戶嗎**再定方向 → `platform-behaviors.md` §6.2 |
| 前端 toast「輸入內容格式不正確，請檢查後重試」 | 平台前端把 422 的 pydantic 陣列收斂成通用提示（2026-09 起；只有 backend validator 自寫的 `value_error` 訊息原樣顯示）。**API 回應的 `detail` 仍是完整的**——開 network 看 response，別叫用戶重填 |
| Storage `413`／`403「無權存取此路徑」`／`list` 對不到剛傳的檔 | 413 有兩個來源（單檔 100 MB、整包 109 MiB）；403 是路徑逃出 app 前綴（含 `..`，2026-09-02 起）；`list` 非遞迴且 `folder` 要與上傳時同一個 → `custom-app-dev-guide.md` §12 坑表 |
| Hosted App `PUT /runtime-settings` 回 422 `RESOURCE_LIMIT_EXCEEDS_MACHINE`／403 `RESOURCES_REQUIRE_DEDICATED_NODES` | per-app 執行上限超過租戶機型單台可用量（body `hint_instance_type` 是最小裝得下的規格）／共用池租戶不能設 `resources`。租戶到「運算資源」頁換規格或開專屬機器，app 端無解 → `hosted-apps.md` §4.1 |
| Hosted App rollout 失敗 `exec /usr/bin/caddy: operation not permitted` | 執行檔帶 file capability、容器 `drop ALL`。只需 `NET_BIND_SERVICE` 的（caddy／nginx-unprivileged）平台已恆補（UAT 09-05、prod v1.13.0）；仍撞到＝該二進位要別的 cap，換掉它 → `hosted-apps.md` §2 |
| Hosted App 建 app 回 429 `hosted_app_quota_exceeded` 說 app 數超額 | 租戶 app 數配額已於 v1.13.0 移除（只剩建置時限那條 429）；仍看到 app 數超額訊息就回報平台 → `hosted-apps.md` §10 |
| Hosted App 記錄頁「先前啟動」標「閒置停止」但用戶說 app 當掉 | `idle` 是**推定**（排除法），節點汰換也會被標成閒置；只有 `crash`（`container_restarted[:oom_killed]`）是有證據的異常。看 `reason_evidence`，別拿 idle 當「沒問題」 → `hosted-apps.md` §8 |

---

## 查不到怎麼辦

1. 對照 `references/data-center.md` §7 / `references/event-triggers.md` §3 的分項速查；
   不開發 app、直接讀寫資料的情境 → `references/data-operations.md`（§3.5 寫入閘門、§7 出口）
2. 狀態碼語義：**403**＝權限（看是 `system.admin` 還是 `builder.access`）；
   **409**＝配額或衝突；**422**＝輸入不合法（欄位／型別／查詢契約）；
   **400**＝業務規則拒絕（tier 超限、草稿 app 建排程、暫停排程 run-now）
3. 仍無解 → 回報用戶，附上完整請求與回應，**不要反覆重試**
4. **懷疑「平台全域故障」之前，先做乾淨對照**：同一個瀏覽器 profile 連開多支 app 交叉比對時，
   快取分區污染會讓「沒動過的 app」也呈現同樣的白畫面，強化全平台壞掉的錯覺。
   可信的對照只有兩種——無痕視窗／新 profile 開同一支 app，或新建一支 hello-world app。
   對照結果乾淨才可能是平台問題；否則回頭查自己的 bundle（上表白畫面列）。
   2026-09-03 曾因此誤發兩張平台事故單
