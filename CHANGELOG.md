# Changelog

版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。
**每次改動 Skill 內容（SKILL.md / CONTEXT.md / references / scripts）都要同步更新 `VERSION`**，
否則使用者端的更新檢查（`scripts/check_update.py`）不會提示。

## 1.16.0

### ★ builder.access 執行期破口：internal app 前端禁止直呼自建表 SDK（規則 31）

2026-08-31 prod 盤點揭露：44 支 internal app 的前端直呼 `queryTable` 等自建表方法，
以**登入者身分**過 `builder.access` 閘——一般員工執行期必 403，另有 18 支未爆彈。
開發帳號必有 `builder.access`，所以既有驗證流程**永遠測不出**這個問題。
（源碼核對：記錄 CRUD 在 router 層掛閘；`ctx.db.*` 走 app 憑證不受影響；
external 走 `/ext/data-center` 不受影響）

- **SKILL.md 核心規則 31**：internal app 自建表存取一律包 Server Action＋
  `runAction`；前端 SDK 僅限 external app 或全員持 `builder.access` 的開發工具
- **Phase 1.5 加受眾盤點**：計畫階段先問「受眾有沒有無開發權限的一般員工」，
  據此決定資料存取層寫法
- **Phase 0 加破口偵測**：`aigo_review.py` 自動標記前端直呼自建表 SDK 的檔案
  （internal＝🚨 必改；external＝ℹ️ 資訊性；legacy CustomObject 前端方法掛同一道閘，
  一併偵測）
- **`data-center.md` §7.5**：三通道身分對照、存量修復五步流程、
  **授權語意警告**（包 action 後「看得到 app 就打得到」，必須用
  `ctx.user_permissions` 補閘——跳過會把 403 破口修成資料過度開放）、
  假修法排除清單（改 external 不可行、發 `builder.access` 給全員是反模式）
- **troubleshooting 修正**：「呼叫 action 403」的 `builder.access` 項只適用
  `use_dev=true` 開發預覽，已發布 action 只需登入＋可見度；新增
  「一般使用者資料載不出來＋`/data-center` 403」症狀列

## 1.15.0

### 資料承載體總決策 SSOT（dev-guide §19 重寫）＋ 延伸欄位 prod 實測

分流指引原本散在規則 18／§19／§22.1／migration-workflow §2.4 各處，各自演化有
drift 風險。本版收斂為單一權威：

- **§19 改寫為「資料承載體總決策（SSOT）」**：一棵決策樹（表級 → 欄位級）涵蓋
  四種承載體——SaaS 原生欄位／延伸欄位（EAV）／`custom_data`／自建表（重用加欄或新建）
  ——並明訂「**直接開發與現有應用遷入用同一棵樹**，遷入不放寬任何判定」；
  新增入口情景對照（直接開發／Custom 遷入／Hosted 遷入——分流結果相同，
  Hosted 只是存取改走 Open Proxy）與禁止項（CustomObject、app 內自建使用者表）
- 其他決策點全部改為 §19 的投影並標注「出入時以 §19 為準」：
  SKILL.md 規則 18 的表擴成四行（補延伸欄位與 custom_data 定位）、
  migration-workflow §2.4 開頭指回同一棵樹
- **CONTEXT.md 術語表四個詞 → 五個詞**：新增「延伸欄位」條目
  （不是實體欄位也不是 custom_data；⚠️ ERP 既有 CRUD 不回傳其值）
- **延伸欄位 prod 唯讀實測通過**（2026-09-01）：`GET /ext-fields/{erpKey}` 200 `[]`、
  `batch-get` 對不存在 row 回 200 `{}`（「缺值不回填」同步證實）——
  §10 的「未實測」註記升級為實測結果，寫入面仍標注未驗證

### 稱謂盤點：「SaaS 表」全面停用，改用官方分類「預設表」

平台的表官方只有**預設表／自建表**兩大類；「SaaS 表」是本 skill 自創行話、
「ERP 表」是平台 code 內部命名，兩者都不該對用戶使用。全庫（9 檔、70+ 處）統一：

- 「SaaS 表」「ERP／SaaS 表」→ **預設表**；描述功能連動的「ERP／SaaS 功能」→
  「平台既有功能」；prose 的「ERP 表」→ 預設表（API 參數 `erp_table_key`／`{erpKey}`
  等技術識別名**保留原樣**）
- CONTEXT.md 升級：開頭明訂「表只有兩大類」，新增「預設表」條目與**稱謂對照表**
  （正式稱謂 vs 平台內部 erp 命名 vs Builder UI「現有資料表」vs 已停用舊稱 SaaS 表）；
  延伸欄位條目一併修訂
- 六個術語：預設表／自建表（兩大類）＋ CustomObject／Data Reference／延伸欄位／
  app_domain（機制詞，不是第三類表）

## 1.14.0

### 遷入情景補強：前+後+DB 整套專案搬入 AI GO 的完整引導

針對「用戶把一個前端＋後端＋DB 專案移進 AI GO」情景的四項缺口修補：

**1. 產品線與模式三向判斷（`migration-workflow.md` §2.1，新）**
- 兩問定四象限：先問「原系統的登入使用者是誰」（internal / external），
  再問技術形狀（Custom / Hosted）——原本三個判斷散在三處且遷移文件不引用
- 明寫不可逆警示：access_mode 建立後不可改、internal 不能開匿名、
  Hosted 付費檔限定；「員工後台＋客戶前台」要拆兩個 App
- §1 多系統盤點改為逐系統過 §2.1，全景表新增「產品線／模式」欄
- SKILL.md Phase 1.5 第 1.5 點與第 6 點接線

**2. 專案解構清單（`resources/project_deconstruction_template.md`，新）**
- 元件落點對照：routes／背景排程／webhook 接收／檔案儲存／第三方 API／
  金鑰／realtime 各自落到 AI GO 的哪裡
- **使用者表特殊處理**：不進 Schema 映射（建成自建表 = 規則 23 反模式）；
  internal 走成員邀請、external 走 custom-app-auth 且密碼 hash 不可遷
- DB 層邏輯（trigger／view／RLS／procedure／edge functions）上移 Server Action 的對照
- 前端可移植性核對：即使原專案是 React+TS，CSS 與依賴幾乎必然重寫
  （§2.3 同步補核對清單，修正原「已是 TS 可評估遷移」的過度樂觀）

**3. 資料抽取路徑與型別對照（`custom-app-dev-guide.md` §23.6／§23.7，新）**
- MySQL/Postgres 直連**只能在本地做**——`ctx.http.call` 講不了 DB 線協定，
  「Server Action 直連源 DB」這條路不存在
- 本地腳本寫入端兩軌：自建表走 `aigo_data_center.insert_record()`；
  SaaS 表／需匯入邏輯走匯入 action 的 run 端點分批呼叫
- 大量資料：分批迴圈放本地、記斷點、匯入 action 要冪等
- 外部型別 → 自建表 9 型別降級對照表（enum→select、array→json、
  附件先下載重傳 Storage 等）

**4. Hosted App 遷入時原 DB 的三個去向（`hosted-apps.md` §7.1，新）**
- ★ 原始碼核對（operator NetworkPolicy，未實機驗證）：**執行期出站只放 TCP 443**
  ——Postgres 5432／MySQL 3306 連不出去，連線字串直連原 DB 這條路不存在
- 三選項：A 外接原 DB（僅限有 HTTPS 介面者）／B 遷自建表＋Open Proxy
  （要共用資料的正解；Hosted 沒有 `ctx.db`，匯入在本地做）／C `/data` 自帶
  （max-scale=2，共享 EFS 上 SQLite 併發寫有風險，單寫低併發限定）

另：SKILL.md description 補「整套專案（前端＋後端＋DB）搬入」觸發語；
`migration_mapping_template.md` 標注使用者表不進映射流程。

**5. 政策校正：Hosted 遷入的資料一律進平台、原 DB 退場（`hosted-apps.md` §7.1 重寫）**
- §7.1 從「中性三選項」改為單一預期路徑：業務資料依雙軌分流遷入
  **預設（SaaS）表引用＋自建表**、app 改用 Open Proxy、原 DB 退場——
  「Hosted = 整套搬」指程式不指資料（SKILL.md Phase 1.5 同步加警語）
- 「暫連原 DB 的 HTTPS 介面」降格為**須明寫遷移終點的短期過渡例外**；
  「`/data` 自帶」限縮為**僅非業務資料**（快取、暫存、衍生產物）
- 解構模板的 Hosted 註記改寫：資料層改寫（ORM/SQL → Open Proxy）列為必做工項，
  要求盤點原專案所有下 SQL 的位置作為工作量依據
- `migration-workflow.md` §2.5 加顯式閘門：**映射表未產出／未經用戶確認前
  不可執行任何匯入**，兩條產品線都受約束

**6. 既有表加欄位：三種擴充機制補齊（新增 `data-center.md` §10）**
- 釐清「既有表欄位不夠」的正解：**自建表直接加實體欄位**（§7 既有端點）；
  **SaaS 表本體不可改，但可加「ERP 延伸欄位」**（EAV overlay，2026-08 起，
  端點核對自平台原始碼、prod 未逐項實測）——`custom_data` 不是 SaaS 表唯一擴充點
- 新 §10 完整記載：三選項比較表（原生欄位／延伸欄位／custom_data 各自時機）、
  端點速查、與自建表同一套 9 型別與欄數配額、
  ★ 讀寫契約（`ctx.db`/`db.ts` **不回傳**延伸欄位值，要另打 `:batch-get`
  ≤200 rows／PATCH 寫值；缺值不回填 default；無 DB 級 FK/unique；SDK 無封裝）
- 注入各決策點：SKILL.md 規則 18 加「欄位不夠 ≠ 換軌或塞 json」、
  Phase 1.5 第 3 點「重用的表欄位不足 → 加實體欄位」、
  dev-guide §19 決策流程與 §22.1 映射流程、
  映射表模板的對應方式新增 `延伸欄位` 與 `既有自建表加欄` 兩個選項

## 1.13.0

### 問題回報支援附加截圖（--image）

`report_issue.py submit` 新增 `--image <路徑>`（可重複，最多 10 張；
png/jpg/webp/gif 單張 ≤8MB）：先上傳到回報系統的物件儲存，再隨卡片建立，
**截圖會直接內嵌在開發團隊的 Notion 卡片裡**——UI／畫面類問題附圖能大幅
縮短來回。`show` 會列出訊息附帶的圖片網址。

- 任何一張上傳失敗即整筆中止（不建缺圖的卡）
- 隱私提醒：上傳前先確認畫面上沒有機密（token、個資、客戶名單）
- `references/issue-reporting.md`、SKILL.md「問題回報」節同步

## 1.12.0

### 新功能：API 建立 App，不必先走 UI 拿 UUID（實測通過）

`custom-app-dev-guide.md` 新增 §26（2026-09-01 對 prod 實測
create → GET 驗收 → delete → 404 全通過）：

- `POST /api/v1/builder/apps`：`name` + `template_slug` 必填（**模板驅動**，
  不能建純空白 app）；`access_mode` 由模板決定、建立後不可改；
  app slug 系統自動生成；回應 `id` 即 `app_id`
- **起手式情景對照**：`starter-internal`（租戶成員內部工具、權限快照注入）
  vs `starter-external`（對外應用、custom-app-auth 自助註冊、快照恆空）；
  `self_built` 屬 Hosted App 隨附整合，不要手動指定
- **起手式非全空白**：實測 seed 23 檔含 leads 示範 action——Phase 0 會看到，
  與需求無關就清掉
- 刪除 `DELETE /apps/{app_id}` **沒有兩段式確認**，代用戶刪除前必須明確確認
- SKILL.md Phase 1 設定流程改為雙路徑（既有 App 走 UI 抄 UUID／新 App 走 API）

## 1.11.2

### ★ 實測回填：prod 落後 main 約一週，1.11.0 的部分宣稱尚未上線

對 prod（urfit 租戶）跑唯讀 smoke test（2026-09-01）：

- ✅ 實測可用：`GET /hosted-apps`（含 visibility）、`.../deployments`、
  `.../runtime-settings`、`GET /deploy-tokens`、`GET /data-center/tables`
- ❌ 已 merge 未部署：`GET /api/v1/users`（404）、`.../api-grants`（404）、
  `.../resource-usage`（404）、**平台保留表名 409 檢查**（`users` 表實際建成了
  ——測試表已刪）、`runtime-settings` 回應缺 `env_availability`／`persistent_disk`
- 回填四處：`hosted-apps.md` 檔頭加「部署落差」節與判讀原則（404/缺欄位先懷疑
  落差，不是文件錯）；`data-center.md` §1／§9 加實測註記（保留名未生效更要自律
  避開）；`platform-behaviors.md` §12 註記準備動作目前做不了；troubleshooting
  加「端點 404 先懷疑部署落差」條目

## 1.11.1

### Hosted App CLI 入口（保有入口、指令面另外管理）

`hosted-apps.md` 新增 §3.3：`aigo` CLI 安裝一行指令與穩定契約——
鑑權優先序（`AIGO_DEPLOY_TOKEN` env ＞ profile ＞ session）、`--slug` 語意
（命中既有 slug＝redeploy，打錯會**多建一個 app 吃配額**）、exit code 語意、
以及「CLI base origin 預設 apex 是它自己的契約，不要拿核心規則 29 糾正它」。

**指令面以 `aigo --help` 為權威，skill 不複製**——CLI 獨立發版（binary-only，
原始碼私有），快照必過期；此決策對齊平台 ADR 0016（CLI 文件只留 pointer）。

## 1.11.0

### 平台同步（至 2026-09-01）：Hosted App 產品線納入 + Custom App 面更新

**新增 `references/hosted-apps.md`——Hosted App（UI 繁中「自訂 App」）是與
Custom App 平行的獨立產品線**（任意技術棧原始碼 → 容器 → Knative，
網址 `{slug}.deploy.ai-go.app`）。SKILL.md Phase 1.5 新增「產品線判斷」（1.5 項）；
參考檔涵蓋：命名地雷（code 的 `CustomApp` 指 Builder 產物、繁中「自訂 App」指
Hosted App）、應用形狀六條硬規則、env 規則（128 顆／單值 32 KiB／總量 128 KiB、
`AIGO_*` 保留、PUT 全量替換）、部署 API 與 Deploy Token vs session 權限矩陣、
`AIGO_*` 資料契約（ERP 表預設零授權）、internal app 401 處置（判 `code` 後
`reload()`）、持久化語意（唯一持久是 `/data`）、錯誤碼對照（分清重試會好與不會好）。

**Custom App 面更新**（皆核對平台原始碼）：

- **`actions/requirements.txt` per-app wheelhouse**：action 可宣告 pip 依賴
  （`name==version`、≤20 行、≤80 MiB、aarch64 only-binary；解析只在試跑／發布；
  有 pin 時試跑走 draft runner 冷啟 ~60s）——`custom-app-dev-guide.md` §16.2
- **VFS 路徑寫入前正規化**：非法路徑 400、`Actions/`→`actions/` 大小寫折疊——§10
- **空渲染偵測**：掛載後 8 秒 root 全空 → 自動回報 runtime error + 使用者 banner；
  升為核心規則 30（先渲染 skeleton）——`platform-behaviors.md` §11
- **權限 gate 現況（audit）**：`__APP_TOKEN__` 已改 app 憑證；enforce 前要在
  「API 權限」分頁補前端呼叫面（Phase 1.5 新增 4.7 項）；自建表撞平台保留表名
  （users／tenants 等）現在建表當下 409——`platform-behaviors.md` §12、`data-center.md` §1
- **data-center**：結構權限拆出 `datacenter.schema_write`（刪除仍限 `system.admin`）；
  配額超限錯誤碼；新端點 `GET /api/v1/users` 租戶使用者目錄與「自建表關聯使用者」
  的正確做法（目前不能建 relation 指向 users）——`data-center.md` §2／§4／§9
- **External Auth**：自助端 `PATCH .../me` 改顯示名稱；邀請成員可指定落點
  `redirect_url: "/app-login/{slug}"`（白名單、純 ASCII）——`custom-app-dev-guide.md` §14
- **平台標識改版**：右下角常駐藥丸 → 首次造訪頂部橫條 5 秒自動消失；
  不要嘗試蓋掉（有自癒防護）——§9
- troubleshooting 新增 7 條速查（VFS 400、WHEELHOUSE 422、draft runner、
  空渲染誤報、保留表名 409、jsonb 引用頁籤、requirements 改壞導致 action 全逾時）

## 1.10.0

### 新功能：平台問題回報（AI IDE 內直接回報，不開 UI）

開發中遇到平台自身的問題（實測與文件不符、troubleshooting 查無此症、
被平台缺陷卡死）可直接提報進開發團隊的 Scrum Board，並追蹤處理進度與官方回覆：

- 新增 `scripts/report_issue.py`：`submit`（結構化 BDD 參數
  `--expected/--actual/--steps/--context`，自動組版）／`list`／`show`
- 新增 `references/issue-reporting.md`：回報時機、★ BDD 撰寫規範
  （描述預期行為 vs 實際結果與重現步驟；**不要**提技術建議或實作方式）、
  隱私註記（不要貼機密）
- SKILL.md 新增「問題回報」一節與參考文件索引
- 憑證重用 `~/.aigo/.env` 零設定：回報帳號在本地以 sha256 衍生，
  AI GO 密碼不離開本機；AI GO 密碼變更後自動換用新回報帳號，不會卡死
- 回報系統獨立部署（Cloudflare），平台掛掉時照樣可報

## 1.9.0

### ★ 行為修正：Egress 閘道改為純域名白名單，不再注入／剝除 Authorization

平台已硬切（ADR 0010／0011，2026-07-29，無相容期），舊版文件的憑證模型整個反了：

- **閘道只做域名驗證**：外部服務（EgressService）= slug + base_url 白名單。
  Runtime 不再解密、注入或校驗憑證；寫入 API 拒絕憑證欄位
  （`auth_type ≠ none` 或非空 `connection_config` → 400）。
- **呼叫端 headers（含 `Authorization`）原樣轉送**，只擋 hop-by-hop
  （`Host`、`Content-Length`、`proxy-*`）。舊文件「閘道會剝掉自帶
  Authorization（實測回 401）」的行為已不存在；401 的語義反轉為
  「外部 API 拒絕 app 自帶的憑證」——是 app 側問題，不是平台設定。
- **金鑰責任改在 app**：API key 存 `ctx.secrets`，action 自組
  `headers={"Authorization": ...}` 傳給 `ctx.http.call`（簽名本就收 `headers`）。
- **設定入口搬家**：`/dashboard/settings/integrations` 已移除；唯一入口是
  Builder（`/builder/{app_id}`）的「外部服務」tab，同處做租戶級建立與
  per-app 授權（新建預設授權本 App）。建立需 `builder.access` 且本 App
  擁有者或 `system.admin`；外部服務為租戶共用池、無服務擁有者。
- **授權是兩層**：slug 沒建立（`egress_service_not_found`）與服務未授權給
  本 App（`egress_not_authorized`）都會連不出去，排錯要分開看。

更新範圍：SKILL.md（ctx 模組註解、Action 範例、錯誤處理）、
`custom-app-dev-guide.md` §25 全節、`troubleshooting.md` 對外呼叫症狀列。
依據：平台 ADR 0010（external-service-domain-only）、ADR 0011
（external-service-builder-entry），並經 `connector_proxy.py`、
`egress_services.py`、`action_context.py` 原始碼核對（2026-08-21）。

## 1.8.0

### ★ 破壞性：登入與 API 改走租戶空間 `https://[tenant].ai-go.app/*`

**沒更新到本版的話，AI GO 的登入已經是壞的。**舊版硬編主站 apex，而 apex 實測已回
`401 {"detail":"帳號或密碼錯誤"}`——與密碼真的打錯**完全同形**，所以症狀會偽裝成
憑證問題，往密碼方向查一定查不到底。

```
POST https://ai-go.app/api/v1/auth/login       → 401 帳號或密碼錯誤   ← 舊版走這條
POST https://urfit.ai-go.app/api/v1/auth/login → 200 access_token OK  ← 本版走這條
```

**更新後要做的事**（否則腳本會在第一步停下）：在 `~/.aigo/.env` 加一行
`AIGO_TENANT=你的租戶前綴`（就是登入時網址列的第一段，例如 `urfit`），
然後 `uv run python scripts/aigo_auth.py status` 確認。跨租戶的專案改在該專案
`.aigo/config.json` 填 `"base_url": "https://demo.ai-go.app"`，會蓋過機器級設定。

---

以下為機制說明。平台的 workspace 子網域上線後，**租戶是由 Host header 解出來的**——
`{tenant}.ai-go.app/api/*` 同源代理到後端並保留 Host，所以 base_url 打哪個 host
就等於宣告「要登入哪個租戶」。apex 推不出任何租戶，`/login` 也已被收斂成
workspace finder（找工作區的頁面）。

401 同形是平台刻意的反帳號列舉設計：狀態碼、detail、是否跑滿一次 bcrypt 三者皆不可
區分。這正是本版**不留任何預設值、直接在 `resolve_base_url()` 擋掉 apex 並印出規則**
的理由——與其讓使用者去查一個無解的「密碼錯誤」，不如當場說清楚。

舊版另有一個獨立的 bug：`get_token()` 只讀環境變數 `AIGO_BASE_URL`、
**完全不看 `config.json` 的 `base_url`**，所以就算把 config 改成租戶網址，登入仍打 apex。

- `scripts/aigo_auth.py` 新增租戶空間的單一權威來源：
  - `resolve_base_url()` 三層優先序，**特定性越高越優先**：
    ① shell 環境變數 `AIGO_BASE_URL` / `AIGO_TENANT`（臨時覆寫、CI）
    ② `<專案>/.aigo/config.json` 的 `base_url`（這個專案綁定的租戶）
    ③ `.env` 的 `AIGO_BASE_URL` / `AIGO_TENANT`（機器級預設）。
    ②必須贏過③：機器級 `.env` 是預設值不是唯一值，否則同一台機器再也開不了
    另一個租戶的專案——而那個錯誤同樣以同形 401 浮現。
  - `AIGO_TENANT` 只給前綴（`urfit`），由 `tenant_base_url()` 組出完整網址。
  - `validate_base_url()`：擋掉 apex、`www`、`*.apps.ai-go.app` 與多層前綴；
    本機與 UAT（`uat-ai-go.app`）等非 `ai-go.app` 命名空間不套此規則。
  - `get_token()` 改走 `resolve_base_url()`；Token 快取加記 `base_url`，
    **換租戶即整份作廢**（Token 綁租戶，跨租戶沿用會變成難查的 403）。
  - `init_config()` 的 `base_url` 改為留空——沒有一個對全部租戶都成立的預設值。
  - `aigo_auth.py status` 會印出**實際生效的租戶空間與它來自哪一層**；
    `login` 遇 401 時直接列出「密碼錯 / 租戶錯」兩種可能，不再只叫人查密碼。
- `scripts/check_update.py` 新增破壞性版本偵測：遠端 CHANGELOG 新版節含「破壞性」
  字樣時，提示語升級為「必須更新」並說明不更新的後果（`--json` 多一個 `breaking` 欄位）。
- `run_e2e_tests.py` / `retest_verification.py` 移除 apex 預設值，改用 `resolve_base_url()`。
- `SKILL.md` Phase 1 新增「租戶空間網址規則」，並依 1.4.0 立下的判準新增**核心規則 29**
  （會誤導的錯誤要放進常駐的 SKILL.md——這條比靜默出錯更糟，401 是主動指向錯誤方向）；
  Phase -1 補上破壞性版本的處置。`README.md`、`custom-app-dev-guide.md` §2、
  `event-triggers.md` §1.3、`platform-behaviors.md` §6.1、`troubleshooting.md` 同步。

> 本版行為以**實機測試**（2026-08-08，同一組正確帳密對打 apex 與租戶空間）
> 加**平台原始碼核對**（`backend/app/core/workspace_host.py`、`backend/app/api/auth.py`、
> `backend/app/services/user_provisioning_service.py`、`frontend/src/middleware.ts`）雙重確認。

## 1.7.0

### 登入身分／權限的口徑統一（★ 修正 1.6.0 的一項錯誤記載）

1.6.0 的 §10 與 `custom-app-dev-guide.md` §6 看起來互相矛盾（一邊說沒有 `user.ts`、
一邊示範 `import "../user"`）。這次比對平台前後端原始碼確認，**兩邊講的是不同管道，
都對，但各缺一半**；同時發現 1.6.0 有一句是錯的。

- **兩條管道分清楚**：「**是誰**」走 `__APP_TOKEN__` 的 JWT payload（一律可用）；
  「**能做什麼**」走 `__USER_ROLES__`／`__USER_PERMISSIONS__` 權限快照
  （**僅 internal 且非匿名渲染**才注入，`src/user.ts` 是它的封裝）。
- **修正**：1.6.0 寫「external App 的執行期**有**注入 `__CURRENT_USER__`」是錯的——
  `__CURRENT_USER__` **在任何模式都不存在**。
- **新發現：`src/user.ts` 不是每個 App 都有。** `api.ts`／`action.ts` 隨 App 建立產生，
  但 `db.ts`／`approval.ts`／`user.ts` 要**到 Builder 後台開一次「開發」分頁**才會注入 VFS。
  純走 API 的開發流程（本 skill 正是）`import "../user"` 會直接編譯失敗。
  §10.2 補上兩條補救路徑（請用戶開一次分頁／直接讀全域，附等價實作）。
- **`custom-app-dev-guide.md` §13 全域變數表改為附注入條件的三欄式**：
  補 `__CUSTOM_APP_ROOT__`、`__USER_ROLES__`／`__USER_PERMISSIONS__`、`__AUTH_TYPE__`、
  `__PUB_API_BASE__`；並註明 `__IS_EXTERNAL__` 在 internal 是 `undefined` 不是 `false`，
  `__IS_AUTHENTICATED__` 只在匿名渲染出現且**恆為 `false`**，不能拿來判斷是否已登入。
- §3 檔案樹標出哪些 SDK 檔要 Builder 後台才會生出來；§6、`SKILL.md` 核心規則 23、
  `troubleshooting.md` 同步改口徑。

### `SKILL.md` 新增核心規則 28：時區解析

依 1.4.0 立下的判準（不拋例外、不報警告的靜默出錯要放進常駐的 `SKILL.md`，
因為 references 是按需讀取），`platform-behaviors.md` §8 符合條件——原生 TIMESTAMP／DATE
是 offset-naive 的 UTC，JS 當成本地時間解析後在 UTC+8 直接差 8 小時，
實測讓相隔 6 分鐘的打卡算成 **8.1 小時**工時並寫進 `hr_attendances.worked_hours`（影響薪資）。
比照規則 26／27 的寫法新增，內文精簡並指向 §8。

### `platform-behaviors.md` §11 併入 §4.3

§11 與 §4.3「`validate_picking` 的實測行為（含冪等陷阱）」內容重複。真正新增的一項
（沒有 `stock_moves` 明細的單呼叫 validate 不會產生任何庫存異動、也不報錯，
而明細是 seed 表 App 寫不了，UI 應直接停用按鈕）併入 §4.3 並補上判斷範例，§11 刪除。
`troubleshooting.md` 原指向 §11 的兩列改指 §4.3。

### 其他

- §8 補上 `toTime()` 的**適用範圍**：對 DATE-only 值補 `T00:00:00Z` 只在非負偏移時區安全，
  負偏移時區會整批退一天；DATE-only 欄位建議一律以字串比對／顯示。
  本檔開頭的驗證環境補記時區為 UTC+8。
- §10.3 的 `currentIdentity()` 補**安全警語**：解出的 `sub` 由前端可竄改，
  寫入身分欄位（如 `import_jobs.user_id`）時必須在 Server Action 用 `ctx.user_id` 覆蓋
  （與「前端隱藏只是 UX 不是安全邊界」、核心規則 23 同一脈絡），附 Python 範例。
  同時把 Annex B 廢棄函式 `escape()` 改成 `TextDecoder` 寫法。
- `troubleshooting.md` 新增 4 條徵狀速查（`import "../user"` 編譯失敗、
  `__IS_AUTHENTICATED__` 誤用、身分欄位被竄改、負偏移時區的 DATE 欄位），
  並改寫 `__CURRENT_USER__` 那一列。


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
  （1.7.0 已併入 §4.3，§11 移除。）

`troubleshooting.md` 同步補 8 條徵狀速查。

> §10 關於 `__CURRENT_USER__` 與 `user.ts` 的記載在 1.7.0 有更正與補充，以 1.7.0 為準。

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
