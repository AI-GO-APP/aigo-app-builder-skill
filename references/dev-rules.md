# 開發硬規則（Phase 3 規則 18–32 的完整版）

> `SKILL.md` Phase 3「核心規則」的規則 18 起在此展開。規則 1–17 是一行講完的，留在 SKILL.md。
> **每條都是 ★ 強制或會靜默出錯的**——動手前逐條核，不要憑印象。

## 目錄

- 規則 18：資料承載體：雙軌分流
- 規則 18.5：自建表命名規範：實體名一律英文
- 規則 19：app_domain 標籤規範
- 規則 20：Webhook / 排程 action 必須冪等
- 規則 21：Webhook 宣告只在發布後生效
- 規則 22：排程的四個硬限制
- 規則 23：角色／權限沿用平台，不要自建一套
- 規則 24：預設表寫入可能被簽核攔截
- 規則 25：表沒有 `tenant_id` 不等於沒保護
- 規則 26：`offset` 分頁一律帶唯一鍵排序
- 規則 27：`ctx.erp.validate_picking` 的冪等要看明細，不能看單據 state
- 規則 28：原生 TIMESTAMP／DATE 是 offset-naive 的 UTC，解析前必須補 `Z`
- 規則 29：所有 API 一律走租戶空間 `https://[tenant].ai-go.app/*`
- 規則 30：啟動先渲染 skeleton，不要讓長 API 擋住首次渲染
- 規則 31：Internal app 前端禁止直呼自建表 SDK
- 規則 32：禁止以 Hosted App 承載資料庫或 storage

---

18. **資料承載體：雙軌分流**（★ 強制）

    資料存在哪裡，依**資料的性質**決定，不是依「哪個比較方便」：

    | 資料性質 | 走哪一軌 | 理由 |
    |---------|---------|------|
    | **平台有同語意的實體**（案件追蹤、往來對象、專案、交付物、待辦…——先用業務語言查 `references/default-table-lookup.md` §2） | **Data Reference**（原生欄位優先） | 與平台功能共用同一份資料；舉證責任在「為什麼不用預設表」 |
    | 預設表缺欄位，且 **app 執行期要讀寫它** | 預設表的 `custom_data` JSONB，或整個實體改走**自建表** | ★ **延伸欄位在 app 內取不到值**（action 打 EAV 端點 401、前端要 `builder.access`）——`data-center.md` §10 通道表 |
    | 預設表缺「租戶級正式欄位」，且**只在資料中心 UI 維護、app 不讀** | Data Reference 的**延伸欄位**（EAV） | 有型別、全租戶可見；讀寫走獨立端點（`data-center.md` §10） |
    | 平台**沒有**同語意實體（查過查表與 Meta API 仍無：領域專屬紀錄、公開爬蟲資料…） | **自建表** | 租戶級真實資料表，跨 app 共用 |
    | app 私有標記（`app_domain`）、臨時、鬆散、不值得定義欄位 | 預設表的 `custom_data` JSONB | 免定義成本 |

    完整決策樹（表級 → 欄位級，直接開發與遷入同一棵）見
    `references/custom-app-dev-guide.md` **§19（SSOT）**——與本表出入時以 §19 為準。

    - ★ **不是資料層的東西（強制）**：runner 本機檔案（action 用 `open()` 寫 `.json`／sqlite／
      pickle 當輕量 db）、程序內全域變數、前端 `localStorage`／IndexedDB
      **都不能承載業務資料或 app 狀態**，一律落上表的三軌之一。
      runner **不擋** `open()`——語言級沙箱已整個拆掉，`/tmp` 可寫、連續呼叫讀得回前一次的檔
      （2026-09-13 測試租戶實打）——但檔案只活在 pod 的 `emptyDir`：已發布 runner 縮到零即清空，
      每次 publish 換新 revision 也清空。**試跑跑在租戶共用的 dev-runner，開發期永遠測不出來**，
      上線後才「打開是舊數字」。要「不能消失」＝自建表；要「跨請求快取」＝不做、每次重算。
      機制、實測與症狀對照見 `references/custom-app-dev-guide.md` §19「禁止項」。
    - **自建表不是「最後手段」，也不是遷入的預設答案**——它是租戶級的真實 Postgres 表（200 張配額，付費檔），
      該用就用；但遷入的表語意落在 CRM、專案、銷售採購、HR、會計時**預設引用預設表**，
      只有平台真的沒有對應實體才自建。每張自建表都要附「已對照 <預設表>／不採用理由」
      （Phase 1.5 第 3 項的資料承載表；issue #53：跳過對照的計畫把 13 張表做成 40 張）
    - **既有表欄位不夠 ≠ 換軌或塞 json**：自建表可直接**加實體欄位**
      （`data-center.md` §7）；預設表本體不可改，擴充點有兩個——
      **app 要讀寫的欄位一律 `custom_data`（或整個實體改走自建表）**，
      **延伸欄位**（EAV，`data-center.md` §10）只給「app 不讀、管理者在資料中心 UI 維護」的
      租戶級正式欄位。選型第一問是「app 要不要讀它」，不是「要不要型別」（issue #71）。
    - **判「平台有沒有這個欄位」只認引用面 `GET /refs/tables/{t}/columns`**——
      Meta 面的 `fields` 是 Workspace 用的策展白名單，比實體表少欄是常態
      （`hr_employees`：20 vs 42）；依 Meta 面判會誤以為欄位不存在（issue #70、查表 §0）。
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
    - ★ **禁止把成員管理面當成 app 的身分來源**：`GET /api/v1/members`、`/members/roles`、
      `/invitations` 都是管理面。`GET /api/v1/members` 掛 `hr.member_manage`——**開發者帳號
      多半有、一般員工沒有**，拿它做 ACL 會做出「自己測全綠、使用者全 403」的 app。
      要 email／部門這類員工主檔欄位走預設表 `hr_employees`；要角色／權限走上面的快照
    - ★ **「我打過回 200」不是能力證明**：app-scoped token 今天打得到平台管理面，是因為
      `APP_SCOPED_TOKEN_MODE=audit`（未登記路由記 log 後放行），切 `enforce` 就整批 403。
      判端點能不能用看兩件事：**在不在 app 的 route catalog**、**一般使用者有沒有那個 permission**
    - 詳見 `references/custom-app-dev-guide.md` §6「User Context」與 §7、
      `references/member-admin.md` §3.6（身分與 ACL 的來源對照表）
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
    - **例外：app 的執行期網址不受本條管**——external Custom App 本來就在 `*.apps.ai-go.app`
      （有 `subdomain` 走 `{subdomain}.apps.ai-go.app/ext-runtime`，沒有走 `runtime.apps.ai-go.app/ext-runtime/{slug}`），
      internal 在 `{tenant}.ai-go.app/runtime/{識別碼}`；測試版各多一段 `version-test`。
      要給用戶連結時照 `platform-behaviors.md` §6.2 那張表，不要自己拼、不要拿本條判它錯
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
