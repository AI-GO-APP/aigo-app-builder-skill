# Hosted App（「自訂 App」）產品線指南

> **這不是 Custom App 的部署模式，是一條平行產品線**（平台文件明文「勿混稱」）。
> 本 skill 的主流程（Phase 2–4）不適用於 Hosted App；Phase 1.5 判斷走這條線時讀本檔。
> 內容核對自平台原始碼與文件（2026-09-01），部分端點已實測（見下）。

### ⚠️ 部署落差（2026-09-01 對 prod 實測）

本檔以平台 monorepo `main` 為準，**prod 落後 main 約一週**。實測結果：

- ✅ 可用：`GET /hosted-apps`（含 visibility 欄）、`GET .../deployments`、
  `GET|PUT .../runtime-settings`、`GET /deploy-tokens`
- ❌ 尚未部署（404 或回應缺欄位）：`GET .../resource-usage`；
  `runtime-settings` 回應**沒有** `env_availability`／`persistent_disk` 欄位
  ——env 執行期/建置期標記、持久碟、以及 §2.8 之後的多數新功能（網域、檔案／終端、
  記錄工具、複製、圖示）在 prod 生效與否**未逐項驗證**，使用前先打一次確認
- **判讀原則**：對著本檔宣稱的端點拿到 404 或回應缺欄位，**先懷疑部署落差**，
  不是文件錯也不是你打錯——隔幾天再試或問平台

## 1. 是什麼：與 Custom App 的邊界

| | Custom App（本 skill 主流程） | Hosted App |
|---|---|---|
| 產物 | Builder 產的 React bundle（VFS + Shadow DOM） | **任意技術棧原始碼 → 容器映像** |
| 建置 | 平台 esbuild | zbpack 自動偵測語言（免 Dockerfile；有 Dockerfile 就走 Dockerfile） |
| 執行 | 平台 runtime 內 | Knative 容器，**scale-to-zero** |
| 網址 | 主站內 `/runtime/...` | `https://{slug}.deploy.ai-go.app`（可綁自訂網域） |
| 取平台資料 | `ctx` SDK／前端 SDK | 注入的 `AIGO_*` env + Open Proxy REST |
| 適合 | 平台內業務介面、直接吃租戶資料 | 遷入整套既有服務、自選框架、常駐進程、WebSocket |

### ★ 命名地雷（先讀，讀錯會改錯 API）

- code identifier 的 **`CustomApp` 永遠指 Builder 產物**；UI 繁中「**自訂 App**」指的卻是 **Hosted App**
- `custom_apps` 資料表**兩條產品線共用**——不可由「在 custom_apps 裡」推論它是 Builder 產物

### 入口與權限

- 列表＋建立：`/builder` 頁「我的 Apps」→「自訂 App」區塊；建立彈窗的**中區卡片**
  （上區兩張是 Custom App 起手式）
- 詳情頁：`/dashboard/ai-apps/hosted/{id}?tab=...`，九分頁
  （`overview│deploy│logs│files│terminal│domain│env│data│settings`）
- 權限：**`hosted_apps.deploy`**——權限不足時整塊 UI **不渲染**（不是報錯）
- **付費檔限定**：免費檔註冊 app 回 403 `hosted_app_requires_paid_plan`（升級才解，重試無用）

## 2. 應用形狀硬規則（★ 失敗率最高的來源，動手前逐條核）

| 規則 | 違反時的症狀 |
|---|---|
| **只能有單一 HTTP port**（Dockerfile 也只能一個 `EXPOSE`） | precheck 警告＋rollout 失敗 |
| **監聽 `$PORT`（平台注入）且綁 `0.0.0.0`** | `connection refused`／readiness probe 失敗 |
| **單一前台行程**——不可 supervisord／pm2／compose 多服務／Procfile worker | precheck `daemon` Issue |
| **必須提交 lockfile**（go.sum／pnpm-lock.yaml…） | `missing go.sum`／`ERR_PNPM_NO_LOCKFILE` |
| 建置包絡 **2 CPU / 4 GiB**、預設 900 秒 | `OOMKilled`／`exit code 137`／timeout |
| 不可是 monorepo／空目錄；無法辨識的目錄會 fallback 成 static 站 | precheck Issue／部署出來是靜態檔 |

- 執行資源：單 app limits 約 **800m CPU / 1.6 GiB**；容器內可 root（隔離靠 gVisor）
- 建置時可連的公網來源是**白名單**（npm/PyPI/Docker Hub 等）——私有 registry 會被擋

## 3. 部署

### 3.1 憑證：Deploy Token vs 登入 session

- **Deploy Token**（`POST /api/v1/deploy-tokens`，scope 固定 `hosted_apps.deploy`，
  raw 只在發行當下給一次；預設 90 天，UI 在詳情頁「設定」）——**只夠日常部署面**
- 下表「Token ❌」的端點（改名／複製／刪除／網域／檔案／終端／憑證三動詞）
  **一律要登入 session**——用 Deploy Token 打會 403，**不是 bug 不要重試**

### 3.2 部署流程（API）

```
POST /api/v1/hosted-apps  (create_deployment=true)
  → 回 dispatch bundle {upload_token, deployd_upload_url, build_deadline_seconds, ...}
POST {deployd_upload_url}  (原始碼 tarball + upload_token)
  → 入建置佇列；排隊不吃建置時鐘
輪詢 GET /hosted-apps/{id}/deployments/{deployment_id}
  → queued → building → active｜failed｜superseded
建置日誌：GET .../deployments/{deployment_id}/logs?after={cursor}（增量 cursor）
```

- **redeploy**（`POST /{id}/redeploy`）＝重跑**最後一次成功上傳**的原始碼，不需重傳；
  沒有可重跑的來源回 409
- **restart**（`POST /{id}/restart`）不重建映像
- **設定變更（env／持久碟）立即生效**，不重建、不耗建置資源
- 重複部署**網址不變**（slug 不變）
- 部署建議走 CLI（§3.3）；REST 流程留給 CLI 裝不了的環境

### 3.3 CLI（`aigo`，建議的部署路徑）

安裝（macOS Apple Silicon／Linux x86_64／Windows 要在 **Git Bash** 下跑；
Intel Mac 尚無 build）：

```bash
curl -fsSL https://raw.githubusercontent.com/AI-GO-APP/aigo-cli-releases/main/install.sh | bash
```

裝到 `~/.local/bin`（不在 PATH 就自己加）。binary-only 發佈，原始碼私有。

**★ 指令面以 `aigo --help` 為權威，本檔不複製**——CLI 獨立發版，
快照必過期。agent 用之前先跑 `--help`。以下只寫 `--help` 講不了的穩定契約：

- **鑑權優先序**：env `AIGO_DEPLOY_TOKEN` ＞ `aigo login --token` 存的 profile
  ＞ 瀏覽器 session。Deploy Token 從詳情頁「設定」tab 發行（raw 只給一次）；
  token 值用 stdin 餵 `aigo login --token`，別放指令列參數（進 shell history）
- **⚠️ `--slug` 語意**：命中既有 slug＝**redeploy**，否則**註冊新 app**（吃配額名額）；
  未給則取目錄名 normalize。打錯 slug 不會報錯、會多一個 app——部署前先 `aigo hosted list` 核對
- **專案目錄＝cwd**（沒有 `--path`）；打包自動排除 `.git`／`node_modules`
- **⚠️ base origin 預設就是 `https://ai-go.app`（apex）**，租戶身分由 Deploy Token 承載
  ——這是 hosted CLI 自己的契約，**不要拿核心規則 29（租戶空間網址）去「糾正」它**
- **exit code**：`0` 成功／`1` 業務失敗（401、配額 429、建置 failed、superseded——
  重試前先修因）／`2` 用法錯／`3` 連不上 backend（可重試）
- 尚未接 CLI 的操作（刪除、網域、檔案／終端等 §11 標 ❌ 的面）→ Dashboard 或 REST

## 4. 環境變數（詳情頁「環境變數」tab；`PUT /{id}/runtime-settings`）

| 規則 | 值（違反 → 422） |
|---|---|
| key 格式 | `^[A-Z][A-Z0-9_]*$`、≤64 字元 |
| 數量 | ≤ **128** 顆 |
| 單值 | ≤ **32 KiB**（UTF-8 bytes） |
| **全部 key+value 總量** | ≤ **128 KiB** |
| 保留 | `PORT`（平台注入）、`K_*` 前綴、**`AIGO_*` 整族** |

- 每顆可標 `runtime`／`build`／`both`（缺漏視為 `runtime`）
- 🚨 **「build」不是 compile-only**：標 build 的值會寫進映像的 `ENV`，
  **出現在租戶可見的建置日誌**、也留在執行中行程——只該留在伺服器的機密**不要**標 build
- 🚨 **`PUT /runtime-settings` 是全量替換不是 merge**：省略 `env_vars`＝清空、
  省略 `always_on`＝關、省略 `persistent_disk`＝卸掛——
  **四欄（env_vars／env_availability／always_on／persistent_disk）一律一起送**

### 平台注入的六顆（不佔上限）

`AIGO_API_TOKEN`／`AIGO_PLATFORM_API_URL`／`AIGO_APP_ID`／`AIGO_TENANT_ID`／
`AIGO_APP_URL`／`AIGO_ENV`。持久碟開啟時另有 `AIGO_DATA_DIR=/data`。

## 5. 取平台資料（隨附整合 + Open Proxy）

- 註冊 app 時平台自動建 1:1 整合與一把 API Key，**憑證只經 k8s Secret 注入容器**，
  不出現在任何 API 回應
- 容器內：`Authorization: Bearer $AIGO_API_TOKEN` 打 `$AIGO_PLATFORM_API_URL/api/v1/open/...`
- ⚠️ `AIGO_PLATFORM_API_URL` 是**叢集內部位址**——本機開發要改打公開租戶網域
- ⚠️ **ERP 表預設零授權**：新 app 打任何 `/open/proxy/{table}` 都是 403，
  要先在詳情頁「資料存取」tab 加引用並發布；資料中心自建表預設是整租戶可用
- 憑證三動詞（session-only，**互不替代**）：`POST /{id}/credential/provision`（補建，冪等）
  ／`rotate`（輪替，新舊重疊 30 分鐘）／`revoke`（立即失效）

## 6. 可見度與 internal app 的 401 處置

- `PUT /{id}/access-settings`：`visibility` = `public`（預設）／`internal`（僅租戶成員，
  可再限角色）。**internal app 沒有預覽截圖**
- internal app 的認證由平台 proxy 處理，**app 端幾乎不用做事**，只有一條要寫對：
  - HTML 導覽 → proxy 自己 302 去登入
  - **背景 fetch/XHR → 401 + JSON `{code: "hosted_app_auth_required", ...}`**
  - 前端**用 `code` 判斷**（不要只看 401），正確處置是 `window.location.reload()`
    發起頂層導覽；**不要**自己導去回應裡的 `login_origin`（CSRF nonce 只在
    HTML 導覽路徑鑄造，自導必失敗）；不要無限重試
- session 24 小時；平台 cookie 會在進容器前被剝掉——**容器內看不到、也不用管**平台 cookie

## 7. 持久化語意（★ 資料放哪裡才不會消失）

| 位置 | 持久？ |
|---|---|
| 容器檔案系統（含用「檔案」tab／終端寫入的） | ❌ 重部署／重啟／縮到零就消失 |
| `persistent_disk=true` 掛載的 **`/data`**（`AIGO_DATA_DIR`） | ✅ 10 GiB EFS；關旗標只卸掛不刪，刪 app 才刪 |
| 平台資料（Open Proxy 寫入的自建表等） | ✅ 在平台側 |

- **複製（clone）不複製 `/data` 內容**，也不複製 Deploy Token 與部署歷史
- 縮到零**不會**因排程或背景工作自動喚醒——需要常駐就開 `always_on`

### 7.1 遷入既有服務時：資料一律遷入平台，原 DB 退場

> 遷移評估（`migration-workflow.md` §2.1）判走 Hosted App 後，**預期行為只有一種**：
> 業務資料遷入 AI GO 的表（預設 SaaS 表引用＋自建表），app 改用 Open Proxy 存取，
> **原 DB 退場、不再使用**。「Hosted = 整套搬」指的是**程式**，不是資料。

**預期路徑（唯一的常態）：資料遷入平台 + Open Proxy**

- **落點依雙軌分流**（與 Custom App 同一套規則，SKILL.md 規則 18）：
  要與 ERP／SaaS 功能連動的資料 → 在「資料存取」tab 加**預設（SaaS）表引用**
  （ERP 表預設零授權，要先加引用並發布，§5）；租戶自有的新業務實體 → **自建表**
  （資料中心自建表預設整租戶可用，§5）
- **映射先行**：逐表逐欄做完 Schema 映射（`custom-app-dev-guide.md` §22、
  映射表模板）並經用戶確認，**才可執行匯入**——Hosted 線不因「程式整套搬」而免掉這一步
- **程式的資料層要改寫**：原專案的 ORM／SQL／DB driver 呼叫全部改成
  `Authorization: Bearer $AIGO_API_TOKEN` 打 `$AIGO_PLATFORM_API_URL/api/v1/open/...`
  （§5；Hosted App **沒有** `ctx.db`）。這是 Hosted 遷入的**必做工項**，
  工作量要在計畫階段向用戶如實預告
- **歷史資料匯入在本地做**：走 data-center API 或匯入 action
  （`custom-app-dev-guide.md` §23.6）

**為什麼「繼續連原 DB」不是選項**——★ 執行期出站只放 TCP 443
（核對自平台 operator 的 NetworkPolicy 原始碼
`infra/operator/internal/controller/resources.go`，2026-09-01 main；未實機驗證，
部署落差判讀原則同本檔開頭）：hosted app 容器對外只能連**公網的 443 埠**
（排除叢集私網段）＋ DNS，另可達平台 backend 與同租戶命名空間內的其他 app。
Postgres 5432、MySQL 3306、Redis 6379 一律不通——連線字串直連原 DB 這條路
**在網路層就不存在**，不是 driver 或防火牆設定問題。

**兩個標註後才可用的例外**（都不是與預期路徑並列的選項，用了要在計畫中明寫）：

| 例外 | 允許條件 | 硬前提與陷阱 |
|---|---|---|
| **短期過渡：暫連原 DB 的 HTTPS 介面** | 僅限分批遷移期間，計畫中**必須明寫遷移終點**（哪一批遷完就切斷）；沒有終點的「先這樣跑」不接受 | 只有當原 DB 有**走 443 的 HTTPS 介面**（Supabase REST／Neon、PlanetScale 的 HTTP driver／自架 API 層）才技術可行；程式仍要從連線字串改成 HTTP 呼叫 |
| **`/data` 放非業務資料** | 只放快取、暫存檔、衍生產物——**業務資料不可落在 `/data`** | 10 GiB EFS；⚠️ **max-scale 平台常數為 2**（同前述原始碼核對），可能同時跑兩個實例，共享 EFS 上的 SQLite 併發寫有鎖定風險；clone 不帶 `/data`（§7） |

用戶堅持長期外接原 DB 或把業務資料放 `/data` 時：如實說明這偏離平台預期行為
（資料進不了平台功能、其他 App 用不到、平台也不備援它），確認後照做，
但在計畫文件中留下記錄。

## 8. 日誌與除錯

- **建置日誌**：`GET /{id}/deployments/{dep_id}/logs?after={cursor}`——只有 cursor 增量，
  **沒有** severity／時間篩選（UI 上那兩顆是停用佔位，別宣稱有）
- **執行期日誌**：`GET /{id}/runtime-logs?tail=&since=&until=&severity=`
  （tail 1–1000 預設 200；`reason: scaled_to_zero` 也是 HTTP 200，不是錯誤）
- **AI 解讀**：`POST /{id}/logs/interpret`——`source=build` 必帶 `deployment_id`
  且**不吃** tail/since/until/severity；`source=runtime` 相反。走 AI 額度（超額 429）
- **活容器檔案／終端**（session-only）：`GET /{id}/console/instances` 先看有沒有活實例
  （`scaled_to_zero` 要先打一下 app 網址喚醒）；檔案讀寫上限：下載 10 MiB／寫入 5 MiB；
  終端 PTY idle 15 分鐘、上限 1 小時。**都是除錯用途**——寫入不持久（§7）

## 9. 自訂網域（session-only）

```
POST /{id}/domains {domain, kind: bind|redirect|gateway}
  → 回 records[]（要設的 DNS 記錄）→ 用戶去 DNS 商設定
POST /{id}/domains/{domain_id}/verify   → pending_dns → pending_cert → active
```

- 不可用 `ai-go.app` 樹、不支援萬用字元、不可含路徑或埠號
- 要先有 active 版次才會啟用（「版次轉為運行中後才會啟用自訂網域」）
- 「平台憑證名額已滿，請聯絡管理員」= ACM 憑證容量（平台側上限），不是你的配額

## 10. 錯誤碼對照（★ 分清「重試會好」與「不會好」）

| 錯誤 | 含義 | 處置 |
|---|---|---|
| 403 `hosted_app_requires_paid_plan` | 免費檔不能用 Hosted App | 升級方案，重試無用 |
| 429 `hosted_app_quota_exceeded` | 每租戶 app 上限（預設 **5**，刪除會釋放名額） | 刪不用的 app 或請平台調配額 |
| 429（建置 timeout 上限） | `build_timeout_seconds` 超過平台上限（900） | 降回 ≤900 |
| 422（env／timeout 下限） | env 出界（§4）或 timeout <120 | 修參數 |
| 503「建置管線尚未就緒」 | 平台側未就緒，整筆 rollback 不吃名額 | 稍後再試（不是你的問題） |
| 409（redeploy） | 沒有可重跑的成功上傳 | 走完整上傳流程 |
| 403（session-only 端點） | 用了 Deploy Token 打 §11 標 ❌ 的端點 | 換登入 session，**不是 bug** |
| 部署 failed | 看建置日誌＋失敗 stage（build/plan/rollout…） | 對照 §2 應用形狀規則 |

## 11. API 端點速查（前綴 `/api/v1/hosted-apps`）

| 端點 | Deploy Token |
|---|:-:|
| `POST /`（建立）／`GET /`／`GET /{id}` | ✅ |
| `POST /{id}/deployments`／`GET .../deployments*`／`.../logs` | ✅ |
| `POST /{id}/restart`／`GET /{id}/runtime-logs`／`POST /{id}/logs/interpret` | ✅ |
| `GET|PUT /{id}/runtime-settings`／`GET /{id}/resource-usage` | ✅ |
| `GET /{id}/preview`／`POST /{id}/preview/capture` | ✅ |
| `POST /{id}/redeploy`／`clone`／`PATCH /{id}`（改名）／`DELETE /{id}` | ❌ |
| `POST|DELETE /{id}/icon`／`PUT /{id}/access-settings` | ❌ |
| `/{id}/credential/{provision|rotate|revoke}` | ❌ |
| `/{id}/domains*`／`/{id}/ports*` | ❌ |
| `/{id}/files*`／`/{id}/console/*`（含 WS 終端） | ❌ |

另有：`/api/v1/hosted-app-gateways`（多 app 共用 hostname 的 path 路由）、
`/api/v1/deploy-tokens`、`POST /api/v1/hosted-app-session/handoff`（交遞，Token 不可用）。
邀請成員直達 hosted app：`redirect_url` 白名單含 `/hosted-app-handoff/{slug}`
（→ `custom-app-dev-guide.md` §14.1）。
