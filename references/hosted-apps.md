# Hosted App（「自訂 App」）產品線指南

> **這不是 Custom App 的部署模式，是一條平行產品線**（平台文件明文「勿混稱」）。
> 本 skill 的主流程（Phase 2–4）不適用於 Hosted App；Phase 1.5 判斷走這條線時讀本檔。
> **Phase 4.2 驗證閘門的等價物是 §3.4——部署後必過，未通過不得對外交付。**
> 內容核對自平台原始碼與文件（2026-09-01），部分端點已實測（見下）。

### ⚠️ 部署落差（prod 現況：**v1.13.0，2026-09-07 10:35Z 部署成功**）

本檔以平台 monorepo `main` 為準。**2026-09-07 起 prod 與 main 只差一個觀測性修補**
（v1.13.0 tag 落在 main 倒數第二個 commit；prod openapi 實查已含本檔所有端點）。
下列 2026-09-01／09-02 的實測紀錄是**歷史**——當時缺的東西已隨 v1.13.0 補齊，留著是給
「下一次 prod 又落後 main」時當判讀範本：

- ✅ 可用：`GET /hosted-apps`（含 visibility 欄）、`GET .../deployments`、
  `GET|PUT .../runtime-settings`、`GET /deploy-tokens`
- ❌（**已於 v1.13.0 補齊**：prod openapi 有 `resource-usage`，`runtime-settings` schema 含
  `env_availability`／`persistent_disk`／`resources`）2026-09-01 當時尚未部署：`GET .../resource-usage`；
  `runtime-settings` 回應**沒有** `env_availability`／`persistent_disk` 欄位
  ——env 執行期/建置期標記、持久碟、以及 §2.8 之後的多數新功能（網域、檔案／終端、
  記錄工具、複製、圖示）在 prod 生效與否**未逐項驗證**，使用前先打一次確認
- ❌（**已於 v1.13.0 補齊**：三支都在 prod openapi）2026-09-02 當時仍 404：`POST /{id}/restart`、
  `POST /{id}/redeploy`、`POST /{id}/logs/interpret`（§11 表列為可用，主線原始碼確有，prod 未跟上）。
  需要「讓新設定生效」時**等傳播**（§4），需要「重跑建置」時**重新上傳**（§3.2）
- ✅ 2026-09-02 實測可用：`/open/data-center/*`（自建表記錄面，§5）、
  `GET|POST /api/v1/refs/apps/{整合 id}`（預設表引用，§5）
- **v1.13.0 帶上 prod 的三塊**（openapi 實查＋**2026-09-08 測試租戶實打一輪**：靜態站 CodeBuild
  建置 46 秒 active、caddy 起得來、`runtime-starts` 有資料、`resources` 在共用池回 403——本檔各節
  標「實打」處即為實測）：
  ① 建置引擎搬 **AWS CodeBuild**（§1／§2；UAT 2026-09-05、prod 隨 v1.13.0 切換，平台 0907 漂移
  runbook 明記「prod 已切 CodeBuild」）；② 記錄分頁改版——`GET /{id}/runtime-starts`「先前啟動」與
  `POST /{id}/logs/interpret-line`（§8）；③ `runtime-settings` 多一欄 **`resources`**（per-app 執行上限，
  §4）——`PUT` 的全量語意從四欄變**五欄**；租戶 app 數配額（舊 429「預設 5 支」）已整條移除（§10）
- **靠旗標不靠版本的兩條**：租戶專屬節點 `TENANT_DEDICATED_NODES` 在 **UAT 與 prod 都是 `ops-only`**
  （租戶自助開機未開放，要平台替租戶開）⇒ §4.1 的 `resources` 在多數租戶會 403；
  租戶資料存取規則 `POLICY_GATE_MODE` **prod＝off**（§5 末條）
- **判讀原則**：對著本檔宣稱的端點拿到 404 或回應缺欄位，**先懷疑部署落差**，
  不是文件錯也不是你打錯——隔幾天再試或問平台

## 1. 是什麼：與 Custom App 的邊界

| | Custom App（本 skill 主流程） | Hosted App |
|---|---|---|
| 產物 | Builder 產的 React bundle（VFS + Shadow DOM） | **任意技術棧原始碼 → 容器映像** |
| 建置 | 平台 esbuild | zbpack 自動偵測語言（免 Dockerfile；有 Dockerfile 就走 Dockerfile）；**跑在 AWS CodeBuild（東京）叢集外**（ADR 0028；UAT 2026-09-05、prod v1.13.0 2026-09-07 起）——對開發者的差別只在建置包絡與 OOM 語意（§2） |
| 執行 | 平台 runtime 內 | Knative 容器，**scale-to-zero** |
| 網址 | 主站內 `/runtime/...` | `https://{slug}.deploy.ai-go.app`（可綁自訂網域） |
| 取平台資料 | `ctx` SDK／前端 SDK | 注入的 `AIGO_*` env + Open Proxy REST |
| 適合 | 平台內業務介面、直接吃租戶資料 | 遷入整套既有服務、自選框架、常駐進程、WebSocket（★ 單請求 300 秒上限＋最多 2 實例，§2——長連線要重連、狀態不能留在行程內） |

### ★ 命名地雷（先讀，讀錯會改錯 API）

- code identifier 的 **`CustomApp` 永遠指 Builder 產物**；UI 繁中「**自訂 App**」指的卻是 **Hosted App**
- `custom_apps` 資料表**兩條產品線共用**——不可由「在 custom_apps 裡」推論它是 Builder 產物

### 入口與權限

- 列表＋建立：`/builder` 頁「我的 Apps」→「自訂 App」區塊；建立彈窗的**中區卡片**
  （上區兩張是 Custom App 起手式）
- 詳情頁：`/dashboard/ai-apps/hosted/{id}?tab=...`，九分頁
  （`overview│deploy│logs│files│terminal│domain│env│data│settings`）
- 權限：**`hosted_apps.deploy`**——權限不足時整塊 UI **不渲染**（不是報錯）

## 2. 應用形狀硬規則（★ 失敗率最高的來源，動手前逐條核）

| 規則 | 違反時的症狀 |
|---|---|
| **只能有單一 HTTP port**（Dockerfile 也只能一個 `EXPOSE`） | precheck 警告＋rollout 失敗 |
| **監聽 `$PORT`（平台注入）且綁 `0.0.0.0`**——★ 看的是**框架實際綁的介面**，不是有沒有讀 `$PORT`（見下） | `connection refused`／readiness probe 失敗／**ksvc ready 逾時但 runtime-logs 顯示已就緒** |
| **單一前台行程**——不可 supervisord／pm2／compose 多服務／Procfile worker | precheck `daemon` Issue |
| **必須提交 lockfile**（go.sum／pnpm-lock.yaml…） | `missing go.sum`／`ERR_PNPM_NO_LOCKFILE` |
| 建置包絡：**CodeBuild 整台 `BUILD_GENERAL1_MEDIUM`（ARM，8 GiB）**，OOM 只在整台用盡時發生（ADR 0028；UAT／prod 皆已切換）；v1.13.0 之前是 k8s Job 的 2 CPU / 4 GiB。預設時限 900 秒。★ 建置工具會依 CPU 數開多個 worker 各占一份 heap，包絡再大也要限 worker 數 | `OOMKilled`／`exit code 137`／timeout；**容器級 OOM 時日誌可能全空**（§8） |
| 不可是 monorepo／空目錄；無法辨識的目錄會 fallback 成 static 站 | precheck Issue／部署出來是靜態檔 |
| **單一請求上限 300 秒**（ksvc `timeoutSeconds=300`，平台常數，核自 prod tag v1.13.1 `orchestrate/runtime.go`）——SSE／WebSocket 長連線**滿 300 秒必斷**，長任務不能在一個請求裡跑完 | 長連線每 5 分鐘斷一次；client 沒做自動重連就「偶爾失聯」；>300 秒的匯出／報表請求 504 |
| **最多 2 個實例**（`max-scale=2`，平台常數，同上出處）——**行程內狀態（記憶體 session、in-process 佇列、本機快取）不跨實例共享**，也沒有 sticky session | 使用者「登入後一半請求變未登入」、佇列消費一半不見；狀態一律落平台的表或 `/data`（§7） |
| **容器只保留 `NET_BIND_SERVICE` 一個 capability**（`drop ALL` 後恆補這一顆，2026-09-05 起；gVisor 已拆除，隔離靠 seccomp＋PSA baseline） | 執行檔帶其他 file capability（`setcap` 過的二進位）會 `exec …: operation not permitted`；只綁 <1024 埠的 caddy／nginx-unprivileged **現在可以**（UAT 09-05、prod v1.13.0 起；2026-09-08 prod 實打 zbpack static 站＝caddy 映像，rollout 成功） |

- 執行資源：共用池與免費租戶固定 **800m CPU / 1.6 GiB**（平台常數）；**專屬節點租戶**可在
  `runtime-settings.resources` 自設（§4），沒填＝**整台**（一台機器扣掉平台保留後的全部）。
  專屬節點目前 **UAT／prod 都是 `ops-only`**——由平台替租戶開，租戶自助尚未開放。
  容器內可 root，但沒有任何 capability（上表）
- 建置時可連的公網來源是**白名單**（npm/PyPI/Docker Hub 等）——私有 registry 會被擋

**★ 綁定介面陷阱（2026-09-02 實測，Next.js 16 standalone）**：k8s 會把容器的
`HOSTNAME` 設成 pod 名稱，而**以 `process.env.HOSTNAME` 決定 bind 位址的框架**
（Next standalone 的 `server.js` 是其一）就只綁 pod IP、不綁 loopback——
Knative queue-proxy 從 127.0.0.1 探測連不上。症狀是**競態不是必現**
（同一份碼 1 次成功後連 3 次失敗），且平台錯誤訊息把方向指向「未聽 PORT」——
PORT 其實有聽。判讀與處置：

- runtime-logs 印出 `Local: http://<pod 名稱>:8080` 而不是 `0.0.0.0` → 就是這個問題；
  pod `Running`、框架顯示 Ready、但整段生命週期**沒有任何請求進來** = 探針連不上，不是 app 掛
- 處置：Dockerfile runner 階段加 `ENV HOSTNAME=0.0.0.0`（加上後連續 7 次部署穩定）；
  手寫服務一律 `listen(port, "0.0.0.0")`
- **後遺症**：綁 `0.0.0.0` 後 Next 從 request 推算的 origin 會變成 `https://0.0.0.0:8080`，
  凡是用「本次請求 origin」組絕對網址的地方（OAuth `redirect_uri`、`redirect(origin + …)`、
  金流 success/cancel URL、通知信連結）都會導錯。**對外網址一律由 env（如 `APP_URL`）指定，
  不從 request 推算**——放進 §4 的遷入 env 清單

**★ 建置記憶體陷阱（同日實測）**：Next 依 CPU 數開 static-generation worker，
2 CPU 就兩份 heap；限制成單 worker（`experimental.cpus: 1`、`workerThreads: false`）
並把 `NODE_OPTIONS=--max-old-space-size` 設在包絡的 **60–65%（4 GiB → 約 2560）**
才穩定——**設太高反而變成無日誌的容器級 OOM**（V8 heap 之外還有原生記憶體與 worker；
3072 在程式碼長大後就爆，降到 2560 即過）。其他框架依同一原理處理。
**CodeBuild 上（UAT 2026-09-05、prod v1.13.0 起）包絡是整台 8 GiB 且沒有 cgroup `--memory`**——
OOM 只在整台用盡時發生，上面「4 GiB 的 60–65%」是舊引擎的實測數字，新引擎按 8 GiB 重算
（約 5000）；但「限單 worker」的原則不變，因為 CodeBuild 那台也是多 vCPU。
⚠️ 新引擎下的 OOM／無日誌失敗矩陣**尚未在 prod 實打**（平台 T15 也列為待驗），撞到時先照 §8 順序處理。

## 3. 部署

### 3.0 `always_on` 決策閘（★ 部署前必過；預設 `false`，開了就佔叢集資源）

平台預設 **scale-to-zero**（`runtime-settings.always_on` 在 prod openapi 的 `default: false`，2026-09-08 實查），
開常駐是**主動動作**：那支 app 會永遠佔一個實例的保留量，沒人用也在扣叢集資源（issue #40 的實例：
一支 `always_on=true` 的 app 日誌裡只有啟動與健康檢查、零真實請求）。**agent 不得自己決定開，
也不得把「要不要常駐」直接丟給 owner 選**——非技術 owner 答不出來、也不知道成本落在誰身上。
問業務問題，由 agent 換算：

| 問 owner 的業務問題 | 答「是」的意思 | 設定 |
|---|---|---|
| 「這個系統**自己**有沒有東西要定時跑？」（容器內 cron／APScheduler／背景執行緒／佇列消費者） | 縮到零時沒有任何入站請求會把它叫醒（§7）——背景工作會停 | `true` |
| 「有沒有要**一直連著**的東西？」（WebSocket／SSE／長輪詢；注意單請求 300 秒上限，§2） | 沒實例就沒連線 | `true` |
| 「第一個人打開時等 **N 秒**能不能接受？」——要問出實際容忍秒數，不要預設「快比較好」 | 容忍不了冷啟動（實測數十秒等級） | `true`，並寫下依據 |
| 以上皆否 | 純網頁／API、有人用才需要在 | **`false`**（預設，不要動） |

- **最容易誤判的一條**：Custom App 的**平台排程**（`event-triggers.md` §2）是平台時鐘打進來的入站請求，
  會喚醒縮到零的 runner，**不需要**常駐（dev-guide §28）。只有把排程器寫在 Hosted 容器裡的才需要
- 開了就要在計畫與交付說明各留一句：「常駐＝開，理由是 X；退場條件 Y（例如改成平台排程後關掉）」
  ——計畫的落點是**需求盤點表 §四.1 ＋ app 分配表該列**（`new_app_requirements_template.md`），
  交付說明的落點是 **§3.4「全部通過」那行**；§3.4 部署後會 `GET runtime-settings` 讀回核對，
  讀到 `true` 卻拿不出這句＝未通過
- 設定方式：`PUT /{id}/runtime-settings` 五欄一起送（§4）；共用池／免費租戶的常駐可能被平台方案擋
- Dashboard 直接建站的 owner 不會經過本 skill——遇到「不知道為什麼開著」的常駐 app，
  先照上表問一次，答案皆否就關掉

### 3.1 憑證：Deploy Token vs 登入 session

- **Deploy Token**（`POST /api/v1/deploy-tokens`，scope 固定 `hosted_apps.deploy`，
  raw 只在發行當下給一次；預設 90 天，UI 在詳情頁「設定」）——**只夠日常部署面**
- §11 表「Token ❌」的端點（**建立**／改名／複製／刪除／網域／檔案／終端／憑證三動詞）
  **一律要登入 session**——用 Deploy Token 打會 403，**不是 bug 不要重試**
- **建立 app 是 session-only**（ADR 0019）：per-app token 綁的是既有 app，
  建立當下 app 還不存在——讓它能建，這把鑰匙就同時是「開新門」的鑰匙。
  Deploy Token 與 App 憑證打 `POST /` 回固定 403 訊息；
  帳號需 `hosted_apps.deploy` 權限，登入走租戶子網域（SKILL.md 規則 29）

### 3.2 部署流程（API）

```
POST /api/v1/hosted-apps  (create_deployment=true)   ← 登入 session（§3.1）；後續兩步 Deploy Token 即可
  → 201 detail；dispatch bundle 在 latest_deployment.dispatch
    {upload_token, deployd_upload_url, build_deadline_seconds, token_expires_at, ...}
POST {deployd_upload_url}  ← multipart/form-data，第一個欄位必須叫 tarball（.tar.gz）；
  header Authorization: Bearer {upload_token}；上限 200 MiB   → 202 {deployment_id}
  → 入建置佇列；排隊不吃建置時鐘
輪詢 GET /hosted-apps/{id}/deployments/{deployment_id}
  → queued → building → active｜failed｜superseded
建置日誌：GET .../deployments/{deployment_id}/logs?after={cursor}（增量 cursor）
```

- **redeploy**（`POST /{id}/redeploy`）＝重跑**最後一次成功上傳**的原始碼，不需重傳；
  沒有可重跑的來源回 409
- **restart**（`POST /{id}/restart`）不重建映像（⚠️ prod 2026-09-02 仍 404，見檔頭）
- **設定變更（env／持久碟）不重建、不耗建置資源，但不是瞬間生效**：平台對現行版次重送
  spec，新 revision 接手需**數分鐘**（實測 1–6 分鐘）。在延遲窗內驗證會誤判成「沒生效」，
  接著做不必要的重建——先等，別急著重新上傳（§4 有判讀方式）
- **無日誌失敗先原樣重送一次**：同一份 tarball 有「約 100 秒就 failed、日誌空、重送即好」
  的偶發型（2026-09-02 實測 3 例）。第二次仍失敗再開始查自己的 Dockerfile（§8）
- 重複部署**網址不變**（slug 不變）
- **rollout 失敗期間對外仍是舊 revision**，平台不顯示「目前服務的是哪一版」——
  驗證新版時在回應加 version marker，別把舊版行為當成新版的 bug（2026-09-02 曾因此誤判）
- **`active` 的語意已收緊**（#1464；prod v1.13.0 起）：結清改等**新 revision 真的接手**
  （WaitRevisionLive 三道判準），新 revision 起不來（如 exec EPERM）會落 `failed`，不再把舊 revision
  的 Ready 誤報成 `active`。所以 `active`＝新版已在服務（2026-09-08 prod 實打：只含 `index.html` 的
  tarball，`queued`→`building`→`active` 共 46 秒，`build_job_name` 形如
  `codebuild:ap-northeast-1:aigo-hosted-build:<uuid>`，`active` 當下第一發 GET 就拿到帶 marker 的 200）；
  仍留 version marker 是因為它能一併抓到「路由到錯的 app」與「打到快取」。
  「起不來會落 failed」那一半（負向）未實打
- 部署建議走 CLI（§3.3）；REST 流程留給 CLI 裝不了的環境
- **部署流程本身不碰 `always_on`**：新建 app 的常駐預設就是 `false`，deploy／redeploy 也不會改它。
  只有 §3.0 判 `true` 的 app 才在 `active` 之後 `PUT /{id}/runtime-settings` 五欄一起送（§4）；
  判 `false` 的什麼都不用做——但 §3.4 仍要讀回確認（Dashboard 那端隨時可能有人手動開）

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
- **多 app／多租戶裝置的建議做法（1.22.0）**：把 token 放工作區 `.aigo/.env` 的
  `AIGO_DEPLOY_TOKEN__<ALIAS 大寫>`，用 `aigo_auth.py run <alias> -- aigo hosted deploy …`
  執行——它會匯出成 `AIGO_DEPLOY_TOKEN`（優先序最高），CLI 的全域 profile 不會互相蓋；
  app 本身先 `aigo_auth.py app add <alias> --id <hosted app uuid>` 登錄（SKILL.md Phase 1）
- **⚠️ `--slug` 語意**：命中既有 slug＝**redeploy**，否則**註冊新 app**；
  未給則取目錄名 normalize。打錯 slug 不會報錯、會多一個 app——部署前先 `aigo hosted list` 核對
- **專案目錄＝cwd**（沒有 `--path`）；打包自動排除 `.git`／`node_modules`
- **⚠️ base origin 預設就是 `https://ai-go.app`（apex）**，租戶身分由 Deploy Token 承載
  ——這是 hosted CLI 自己的契約，**不要拿核心規則 29（租戶空間網址）去「糾正」它**
- **exit code**：`0` 成功／`1` 業務失敗（401、配額 429、建置 failed、superseded——
  重試前先修因）／`2` 用法錯／`3` 連不上 backend（可重試）
- 尚未接 CLI 的操作（刪除、網域、檔案／終端等 §11 標 ❌ 的面）→ Dashboard 或 REST
- **常駐不在 deploy 指令裡**：`--help` 有沒有 runtime-settings／常駐相關子命令以它為準；沒有就走
  REST `PUT /{id}/runtime-settings`（§4）或 Dashboard。無論哪條路，**開之前都要先過 §3.0**；關掉不需要過閘

### 3.4 部署後驗證閘門（★ 未通過不得對外交付）

Custom App 線每次變更都要過 SKILL.md Phase 4.2 的驗證閘門；Hosted App 不走 Phase 2–4，
**本節是它的等價物**。`deployment` 變成 `active` 只代表**建置與 rollout 成功**，
不代表對外服務的就是你這一版——rollout 失敗時對外仍是舊 revision，而平台**不顯示
目前服務中的版本**（§3.2）。沒有 version marker 就沒有「新版已生效」的證據。
（v1.13.0 起 `active` 已改為「新 revision 真的接手」，正向半邊 2026-09-08 已實打，「起不來落 `failed`」的負向半邊未實打，
本節的 version marker 要求不放寬——見 §3.2。）

| 變更範圍 | 先等 | 必驗項目 |
|---|---|---|
| **只改 env／持久碟** | **1–6 分鐘**傳播（§4）；延遲窗內驗證會誤判成沒生效 | ① `GET /{id}/runtime-settings` 讀回確認值 ② 實測**依賴那顆 env 的路徑**（登入、OAuth 導向、第三方呼叫），不是只看設定頁 |
| **常駐設定**（首次部署、改 runtime-settings、接手既有 app 的第一次驗證都要做） | — | ① `GET /{id}/runtime-settings` 讀回 `always_on`，**必須等於 §3.0 的決策**（沒過閘＝`false`）② 讀到 `true` 就要拿得出計畫裡那句「常駐＝開，理由 X；退場條件 Y」，拿不出來視同未通過 |
| **程式碼變更**（deploy／redeploy） | 建置完成 | ① `deployments/{id}` 狀態 `active`（不是 `queued`／`building`／`failed`／`superseded`）② **version marker**：回應帶得到本次版本識別 ③ 主要路由各打一次拿 200 ④ `runtime-logs` **看得到請求進來**——pod `Running`、框架顯示 Ready 卻整段沒有請求 = 探針連不上（§2 綁定介面陷阱） |
| **首次部署／遷入既有系統** | 同上 | 上列全部（**含常駐設定列**）＋ §4「遷入 env 清單」逐顆核 ＋ 持久化落點（§7：容器檔案不持久，資料要落平台）＋ 取平台資料的路徑（§5：容器內要 `/open` 前綴、隨附整合要加引用） |
| **自訂網域** | DNS／憑證 | `POST /{id}/domains/{domain_id}/verify` 走到 `active`（§9；**session-only，Deploy Token 打不了**），再用**該網域**重跑一次主要路由，不是只驗 `*.ai-go.app` |

**驗證後決策**：

| 結果 | 下一步 |
|---|---|
| 全部通過 | 可交付；交付說明附 version marker 的值（對照基準）＋**常駐狀態一句**：`常駐＝關（預設）` 或 `常駐＝開，理由 X；退場條件 Y` |
| `always_on` 讀回 `true` 但沒有決策紀錄 | 回 §3.0 問一次業務問題；皆否 → `PUT runtime-settings` 關掉（五欄一起送）再驗一次；有一項是 → 補寫理由與退場條件到計畫與交付說明 |
| 建置 `failed` 且日誌全空 | **原樣重送一次**（偶發型），再失敗往建置記憶體查 → §8 |
| ksvc ready 逾時但 runtime-logs 顯示已就緒 | 綁定介面陷阱 → §2，不要改 PORT |
| 改動「沒生效」 | 先確認上一次 rollout 成功（失敗＝對外還是舊版）→ §3.2；只改 env 就再等滿傳播窗 → §4 |
| 登入後 401／導向 `https://0.0.0.0:8080` | env 沒帶齊或對外網址從 request 推算 → §4、§2 |
| 任一項未通過 | **不得對外交付、不得回報完成**；先對症出口，不要重新上傳一次碰運氣 |

⚠️ **不要在延遲窗內判定失敗**：env 傳播與 rollout 都不是瞬間的，急著重建會把偶發問題
變成連鎖問題（2026-09-02 曾因此誤判）。等滿再判。

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
  省略 `always_on`＝關、省略 `persistent_disk`＝卸掛、省略 `resources`＝回平台預設——
  **五欄（env_vars／env_availability／always_on／persistent_disk／resources）一律一起送**
  （v1.13.0 起五欄，prod openapi 的 `HostedAppRuntimeSettingsUpdate` 已含 `resources`）
- 建置期 env 走 SSE-KMS 輸入物件（CodeBuild），不再落在 Job env；建置階段讀不到某顆 env 時，
  平台的失敗提示會指向「環境變數」頁的**建置階段**——先核那顆有沒有標 `build`／`both`，
  不是去查 Dockerfile
- **`apply_state` 的正確讀法**（核自原始碼 schema 註解＋2026-09-02 實測）：只在 **PUT 回應**帶回，
  `GET` 恆為 `null`（不是退回去了）。`applied` 只表示「spec 已送達、現行版次已重送」，
  **不保證容器已換版**——PUT 走 `wait_ready=false`。要確認是否傳播完成，唯一可靠方法是
  **從 app 內讀一個無害變數**（例如加一顆 `APP_BUILD_MARKER`）；用「移除變數」測比新增乾淨

### 4.1 per-app 執行上限 `resources`（★ 只有專屬節點租戶能設；v1.13.0 起，專屬節點 UAT／prod 皆 ops-only）

```json
"resources": {"cpuRequest": "250m", "cpuLimit": "1000m", "memoryRequest": "256Mi", "memoryLimit": "2Gi"}
```

- 四鍵 camelCase、k8s quantity 字串（cpu `^[0-9]+(\.[0-9]+)?m?$`、memory `^[0-9]+(Mi|Gi)$`，
  ≤32 字元）；`request ≤ limit`；request 下限 **50m／64Mi**；形狀錯 → 422
- `cpuLimit`／`memoryLimit` 可**一起留 `null`**＝整台機器（T47 預設）；`resources` 整個省略＝平台常數
- limit 超過租戶目前機型單台可用量 → **422 `RESOURCE_LIMIT_EXCEEDS_MACHINE`**（body 帶
  `max_cpu`／`max_memory`／`hint_instance_type`＝最小裝得下的機型）——改小上限或請租戶到
  運算資源頁換規格，不是重試
- 免費租戶 → 403；**共用池（非專屬節點）租戶 → 403 `RESOURCES_REQUIRE_DEDICATED_NODES`**
  （2026-09-08 prod 實打訊息：「共用池租戶不能自設執行上限（沿用平台常數）；請先在「機器」設定專屬節點」；
  同一支 app 不帶 `resources` 的五欄 PUT 回 200 `apply_state: applied`，`GET` 回應已含 `resources` 鍵）——
  app 端改不了。專屬機器目前 `TENANT_DEDICATED_NODES=ops-only`（UAT／prod 同），**租戶自己在
  「運算資源」頁開不了**，要請平台替租戶開；沒開之前這個 403 是預期
- 租戶換小機型時平台會逐 app 檢查，超限的 app 會擋住換機型（422 帶 `apps[]`）——
  遷入計畫裡把每支 app 的上限與機型一起定
- `GET /{id}/resource-usage` 回設定值；租戶畫面「App 佔用」顯示**已保留（request×副本）**與
  **目前使用**（metrics 取樣，可為「—」），兩者都不是計費口徑——上限不是浪費，實際使用低很正常
- **Builder App（Custom App）沒有租戶 UI 可設**這組值（ops 直改 DB），本節只管 Hosted App

### ★ 遷入既有系統時要重新提供的 env 清單

Hosted App 容器**只帶平台注入的 `AIGO_*`**，原系統的 env 一顆都不會自動過來。
沒帶到的典型症狀是「頁面能開、登入後每個操作都 401／導去奇怪網址」——看起來像資料層或
認證層壞了，其實只是 env 缺席。遷入計畫要逐顆列出並在 runtime-settings 重設：

| 類別 | 例 | 沒帶到的症狀 |
|---|---|---|
| **對外網址** | `APP_URL`／`NEXT_PUBLIC_SITE_URL` | OAuth redirect、金流回跳、信件連結導到 `https://0.0.0.0:8080/...`（§2 綁定介面陷阱） |
| session／簽章密鑰 | `SESSION_SECRET`／`JWT_SECRET`／`NEXTAUTH_SECRET` | 登入後全 401，或每次部署都把使用者登出 |
| 第三方憑證 | OAuth client id/secret、金流 key、郵件服務 key | 對應功能 4xx／5xx |
| 功能開關 | 逐模組切換資料後端的旗標 | 走錯後端 |

- 密鑰類一律標 `runtime`，**不要標 `build`**（會進映像與建置日誌，見上）
- 原系統的 `DATABASE_URL` 一類**不要**搬——資料層改走 Open Proxy（§7.1），直連在網路層不通

### 平台注入的六顆（不佔上限）

`AIGO_API_TOKEN`／`AIGO_PLATFORM_API_URL`／`AIGO_APP_ID`／`AIGO_TENANT_ID`／
`AIGO_APP_URL`／`AIGO_ENV`。持久碟開啟時另有 `AIGO_DATA_DIR=/data`。

## 5. 取平台資料（隨附整合 + Open Proxy）

- 註冊 app 時平台自動建 1:1 整合與一把 API Key，**憑證只經 k8s Secret 注入容器**，
  不出現在任何 API 回應
- 容器內：`Authorization: Bearer $AIGO_API_TOKEN` 打 `$AIGO_PLATFORM_API_URL/api/v1/open/...`
- ⚠️ `AIGO_PLATFORM_API_URL` 是**叢集內部位址**——本機開發要改打公開租戶網域
- **限流：`/api/v1/open/*` 每分鐘 600 次，桶鍵＝這把 API Key（整支 app 共用，不分端點、不分實例）**
  （`rate_limit.py` `OPEN_API_RATE_LIMIT = 600`，核自 prod tag v1.13.1）。超過回 429，`X-RateLimit-Limit`
  寫的是擋住這一發的那個桶。遷入案逐列打 Open Proxy 時用它估時程：16,408 列 ≥ 28 分鐘，
  分批要留餘裕給 app 本身的讀取（`custom-app-dev-guide.md` §23.6）
- ★ **兩個資料平面都要加 `/open` 前綴**（2026-09-02 容器內實測；`open_data_center` router
  核自原始碼）——`data-center.md` §7 速查表的路徑是**登入使用者 token 的平面**，
  用 `AIGO_API_TOKEN` 照抄必 **401 `Invalid authentication token`**（訊息會把你導向憑證方向，
  其實是路徑）：

  | 資料 | 容器內路徑 | 契約 |
  |---|---|---|
  | 自建表 | `GET/POST /api/v1/open/data-center/tables/{key}/records`、`PATCH/DELETE .../records/{id}` | 與 `data-center.md` §7 同一套：query string `filters`（鍵 `field/op/value`）、分頁信封 `{items,total,page,page_size}`、POST body **必須包 `{"data": {...}}`** |
  | 預設表 | `POST /api/v1/open/proxy/{table}/query`、`POST /api/v1/open/proxy/{table}` | proxy 契約：body `filters`（鍵 **`column`**`/op/value`）、裸陣列上限 500 |

  兩平面的過濾契約**鍵名與運算子集合不同**、對錯誤形狀的反應相反——對照表見
  `platform-behaviors.md` §1.5，遷入案的資料層改寫前先讀
- ⚠️ **預設表零授權起步**：新 app 打任何 `/open/proxy/{table}` 都是 403
  「App 未被授權存取表 'x'」——訊息裡的「App」指的是**隨附整合**，不是 hosted app。
  加引用有兩條路：詳情頁「資料存取」tab；或 API
  `POST /api/v1/refs/apps/{attached_integration_id}`（body `{table_name, columns[], permissions[]}`，
  key 是**整合 id**——拿 hosted app id 打會 404「App 不存在」；整合 id 從詳情頁「資料存取」tab
  或 `GET /api/v1/refs/apps/{id}` 試探取得）。此端點**不在 `/hosted-apps` 前綴下**，
  Deploy Token 打不到，要登入 session（帳號有 `hosted_apps.deploy` 即可，不必 `builder.access`）。
  2026-09-02 實測 17 張預設表 201 後容器內 403 隨即轉 200，**不需重新部署**。
  資料中心自建表預設是整租戶可用，不用加引用
- 憑證三動詞（session-only，**互不替代**）：`POST /{id}/credential/provision`（補建，冪等）
  ／`rotate`（輪替，新舊重疊 30 分鐘）／`revoke`（立即失效）
- ★ **Open Proxy 也在租戶「資料存取規則」（Auth gate v1）的執法範圍**（T66；端點與執法碼 v1.13.0
  已在 prod，但 `POLICY_GATE_MODE` **UAT on／prod off**，2026-09-07 核自 k8s manifest）：`/open/*` 的呼叫身分是 **app**（沒有 user）——`deny` 規則照擋（403 body 帶
  `reason`／`rule_id`）；`restrict` 規則只要 `where_dsl` 用到 `$user.*` 就**解不出→整列判 deny**
  （D28），所以租戶一開「依員工過濾」類規則，hosted app 的 Open Proxy 讀取會直接 403 而不是少列。
  遷入案的資料層改寫前把這條告訴租戶：對 app 身分要另設不帶 `$user.*` 的規則、或用 app 級規則放行；
  app 端改 code 無解 → `custom-app-dev-guide.md` §27

### 5.1 Hosted App 當 Custom App 的後端（混合方案的一種）

Custom App 介面 ＋ Hosted App 承接常駐進程／自選框架時，呼叫方是 Custom 的 **Server Action**
（`ctx.http.call`），它**沒有平台登入 cookie**：

- Hosted 設 **`visibility=public`**——`internal` 的 proxy 會把這種呼叫當未登入導去登入頁（HTML 導覽
  302、fetch 401 `hosted_app_auth_required`），Server Action 端看到的是 401／HTML，不是資料
- **app 自驗簽章**：Custom 端把共享金鑰存 `ctx.secrets`，action 自組 `Authorization: Bearer …`
  （egress 閘道原樣轉送 `Authorization`，dev-guide §25）；Hosted 端每個請求驗證，驗不過 401
- Hosted 的網域要先在 Builder「外部服務」以同名 slug 建成 egress 白名單（SKILL.md 計畫第 4.6 項）
- **使用者身分由 Custom 端帶**：action 內用 `ctx.user_id`／`ctx.user_permissions` 分流後，把需要的
  身分欄位放進 request body；Hosted 不自行認人、不另建使用者表
- 前端**不要**跨來源直打 Hosted：帶憑證的 CORS 平台不支援（proxy 只處理同站 cookie）
- 業務資料仍落平台的表：Hosted 用 Open Proxy（§5）讀寫，不自帶 DB（規則 32）

## 6. 可見度與 internal app 的 401 處置

- `PUT /{id}/access-settings`，body `{visibility, access_role_ids}`：`visibility` = `public`（預設）／
  `internal`（需登入 AI GO）。**`internal` ＋ `access_role_ids=[]` ＝ 全租戶已登入成員**；填角色 id
  就只放行那些角色；`public` 下 `access_role_ids` 必須為空（DB CHECK）。需 `hosted_apps.deploy`，
  再收窄到 app 的 `created_by`／admin。**internal app 沒有預覽截圖**。
  角色從哪來、外部人員怎麼進租戶 → `member-admin.md` §1／§3／§4。
  2026-09-08 測試租戶實打：`POST /hosted-apps {create_deployment:false}` 註冊後即可設定；`internal`＋角色 200
  且 GET 立即讀回；`public`＋非空角色 **422「public visibility 不可搭配 access_role_ids」**；不存在的角色
  **400「角色不存在或不屬於此租戶：<id>」**
- **有登入者就是 `internal`**——員工、外部經銷商、客戶都是租戶成員，用 `access_role_ids` 分流；
  `public` 只給沒有登入者的公開站，或當 Custom App 後端時（§5.1）
- **容器收到的身分：一個都沒有**（2026-09-09 測試租戶實打）。部署一支只把收到的 header 原樣印出來的
  app（`internal` ＋ `access_role_ids=[]`），以成員身分走完交遞後開啟：容器只看到 `Host`／`Accept`／
  `Forwarded`／`K-Proxy-Request`／`X-Envoy-Original-Host`／`X-Forwarded-*`／`X-Request-Id` 這類轉送
  header，**一個 `X-Aigo-*` 都沒有**，`Cookie` 也沒有。⇒ **app 分不出這次請求是哪一位使用者**，
  更談不上 email／roles／permissions。
  ⚠️ 1.35.0 以前本節寫「proxy 驗過後注入 `X-Aigo-User-Id`／`-Tenant-Id`／`-App-Id`／`-Population`
  四個 header」是**錯的**——那是平台另一條**尚未接線**的資料面設計，不是 Hosted App 的現況；
  照它寫 app 會拿到一片空白。
- **`AIGO_API_TOKEN` 是 app 身分不是使用者身分**：容器內拿它打 `/api/v1/auth/me`、`/api/v1/members`、
  `/api/v1/members/{id}/linked-roles`、`/api/v1/members/roles` 一律 **401** `Invalid authentication token`
  （API Key 只在 `/api/v1/open/*` 有效）；open proxy 打 `users`／`roles`／`user_role_rel`／`members`
  一律 **403**「App 未被授權存取表」（這四張是平台身分表，引用面根本列不出來）。
  對照組 `/api/v1/open/data-center/tables` 200，證明憑證本身有效。**已回報平台（2026-09-09）**，不必重複開單
- ⇒ **角色分流只能在門口用 `access_role_ids`**（`member-admin.md` §6）。要在畫面內依角色開關功能，
  三選一：① 該部分做成 Custom internal app（runtime 有 `__USER_ROLES__`／`__USER_PERMISSIONS__`）；
  ② Custom App 當前端 ＋ Hosted 設 `public` 當後端、由 app 自驗簽章（§5.1）；
  ③ 按角色拆成多支 internal Hosted App，各自掛不同 `access_role_ids`
- 邀請成員直達 internal app：`redirect_url` 用 `/hosted-app-handoff/{slug}`（`member-admin.md` §4）
- internal app 的認證由平台 proxy 處理，**app 端幾乎不用做事**，只有一條要寫對：
  - HTML 導覽 → proxy 自己 302 去登入
  - **背景 fetch/XHR → 401 + JSON `{code: "hosted_app_auth_required", ...}`**
  - 前端**用 `code` 判斷**（不要只看 401），正確處置是 `window.location.reload()`
    發起頂層導覽；**不要**自己導去回應裡的 `login_origin`（CSRF nonce 只在
    HTML 導覽路徑鑄造，自導必失敗）；不要無限重試
- session 24 小時；平台 cookie 會在進容器前被剝掉——**容器內看不到、也不用管**平台 cookie
- 已修的一個平台缺陷（#1421，2026-09）：internal app 的 auth proxy 曾把**已登入使用者的冷 miss**
  丟進匿名枚舉的全域佇列（8 名額），枚舉流量一來所有登入者都拿 503。現在只有真匿名才排隊。
  v1.13.0 起 prod 生效；仍見「登入者間歇 503、無 app 端錯誤」先查平台側，不是 app 掛

## 7. 持久化語意（★ 資料放哪裡才不會消失）

| 位置 | 持久？ |
|---|---|
| 容器檔案系統（含用「檔案」tab／終端寫入的） | ❌ 重部署／重啟／縮到零就消失 |
| `persistent_disk=true` 掛載的 **`/data`**（`AIGO_DATA_DIR`） | ✅ 10 GiB EFS；關旗標只卸掛不刪，刪 app 才刪 |
| 平台資料（Open Proxy 寫入的自建表等） | ✅ 在平台側 |

- **複製（clone）不複製 `/data` 內容**，也不複製 Deploy Token 與部署歷史
- 縮到零**不會**因**容器內**的排程或背景工作自動喚醒——這正是 §3.0 決策閘的第一題；
  要開 `always_on` 先過閘，不要看到這句就開（平台排程是入站請求，會喚醒，不算）

### 7.1 遷入既有服務時：資料一律遷入平台，原 DB 退場

> 遷移評估（`migration-workflow.md` §2.1）判走 Hosted App 後，**預期行為只有一種**：
> 業務資料遷入 AI GO 的表（預設表引用＋自建表），app 改用 Open Proxy 存取，
> **原 DB 退場、不再使用**。「Hosted = 整套搬」指的是**程式**，不是資料。

**預期路徑（唯一的常態）：資料遷入平台 + Open Proxy**

- **落點依雙軌分流**（與 Custom App 同一套規則，SKILL.md 規則 18）：
  平台有同語意實體的資料（先用業務語言查 `default-table-lookup.md` §2）→ 在「資料存取」tab 加**預設表引用**
  （預設表零授權起步，要先加引用並發布，§5）；查過仍沒有的 → **自建表**
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

**★ 也不可把 DB 立成一個 Hosted App**（SKILL.md 規則 32）：同租戶命名空間內
app 互通，技術上可以把 PostgREST／Hasura 這類「REST 包裝的 DB」部署成
Hosted App 讓其他 App 打 HTTP 過去——這是明文禁止的反模式，不是巧妙的過渡方案。
它讓業務資料脫離平台的表：進不了平台功能、繞過簽核與權限閘、平台不備援。
遇到用戶提出這個構想，指回上方預期路徑
（資料遷入平台的表＋Open Proxy）。

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
- ★ **建置 failed 但日誌全空**（`{"lines": [], "source": "none"}`，`failure_reason` 只有
  「builder 未留下 termination message」；2026-09-02 實測多次）：主線 watcher 已能區分
  OOMKilled／exit 137／無 termination message 三種，prod 目前只回最泛的那句。處置順序——
  ① **原樣重送一次**（有偶發型，重送即好）；② 仍失敗 → 往**建置記憶體**查（§2 建置記憶體陷阱：
  限制 worker 數、heap 設包絡的 60–65%）；③ 還是不明 → 三段對照各部署一次定位失敗點：
  最小 Node 服務（無建置）→ 真實 `package.json` 只跑 `npm ci` 不 build → 完整專案。
  日誌為空時檔頭的「先懷疑部署落差」原則不適用——這是使用者側建置失敗，只是沒訊息
- **執行期日誌**：`GET /{id}/runtime-logs?tail=&since=&until=&severity=`
  （tail 1–1000 預設 200；`reason: scaled_to_zero` 也是 HTTP 200，不是錯誤）
- **AI 解讀**：`POST /{id}/logs/interpret`——`source=build` 必帶 `deployment_id`
  且**不吃** tail/since/until/severity；`source=runtime` 相反。走 AI 額度（超額 429）
- **記錄分頁改版（v1.13.0，三支端點 prod openapi 已實查）**——三個子分頁「即時日誌／先前啟動／建置日誌」：
  - `GET /{id}/runtime-starts`：最近 **7 天**每一次**容器執行段**（同一實例內容器重啟＝新的一段）
    的起迄、時長與 `reason`（2026-09-08 prod 實打回應形狀：`{app_id, since, starts:[{pod_name, run_index,
    started_at, ended_at, time_source, line_count, revision_seq, reason, reason_evidence, source}]}`，
    執行中那段 `ended_at`／`reason` 皆 `null`、`source: "live"`）：`idle` 閒置停止／`rollout` 版次更新／`crash` 異常結束
    （`reason_evidence` 為 `container_restarted[:oom_killed]`）／`unknown` 已停止／`null` 執行中。
    ⚠️ **`idle` 是推定不是觀測**（冷啟動＋非重啟＋無新版次證據的排除法），節點汰換也會被標成
    閒置停止——別拿它當「app 沒問題」的證據；`crash` 才是有證據的異常
  - `GET /{id}/runtime-starts/{pod_name}/logs`：單一實例的執行期 log；`pod_name` 只能是本 app
    的實例名（前綴不符 422）。租戶面叫「實例／短 ID」，wire 欄位仍是 `pod_name`
  - `POST /{id}/logs/interpret-line`：AI 解讀單行——只送定位（實例名＋行 hash），伺服器自己重抓
  - 三支都收 Deploy Token；`reason` 對應的白話文案由平台給，回報用戶時照平台的說法
    （「記憶體超過上限被停掉」「App 一直重啟」），不要自己講 OOM／pod
  - 運算資源頁「App 佔用」表每列另帶 `restartCount`／`lastTerminatedReason`（T48）：任一非空即標
    「有狀況」，點了開 Agent 面板問「這支 App 為什麼掛掉」。五種原因對白話：`OOMKilled` 記憶體超過上限、
    `Evicted` 機器整體記憶體吃緊、`FailedScheduling`／`exceeded quota` 機器保留量已滿、
    `CrashLoopBackOff` App 啟動後很快退出（通常是程式問題）
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
| 429 `hosted_app_quota_exceeded` | **只剩一種成因：`build_timeout_seconds` 超過平台上限（900）**（`quota: max_build_duration_seconds`）。租戶 app 數上限（舊「預設 5 支」）已於 2026-09-07 整條移除——app 能裝幾支由專屬機器容量決定 | 降回 ≤900 |
| 422（env／timeout 下限） | env 出界（§4）或 timeout <120 | 修參數 |
| 422 `RESOURCE_LIMIT_EXCEEDS_MACHINE` | `resources` 的 limit 超過租戶機型單台可用量（§4.1） | 改小上限或換機型；body 的 `hint_instance_type` 是最小裝得下的規格 |
| 403 `RESOURCES_REQUIRE_DEDICATED_NODES` | 共用池租戶送了 `resources` | 租戶先開專屬機器；app 端無解 |
| 建置 failed、rollout 時 `exec /usr/bin/xxx: operation not permitted` | 執行檔帶 file capability（caddy／nginx-unprivileged 常見） | 只需 `NET_BIND_SERVICE` 的已由平台恆補（UAT 2026-09-05、prod v1.13.0）；仍撞到＝該二進位要的是別的 cap，換掉它 |
| 副本起不來、`GET /tenant/compute` 的 `limit.reached=true`／事件 `exceeded quota` | 租戶機器的保留量已滿（不是本 app 的錯） | 引導租戶到「運算資源」頁加機器／尖峰加開，或降其他 app 的 request |
| 503「建置管線尚未就緒」 | 平台側未就緒，整筆 rollback 不吃名額 | 稍後再試（不是你的問題） |
| 409（redeploy） | 沒有可重跑的成功上傳 | 走完整上傳流程 |
| 403（session-only 端點） | 用了 Deploy Token 打 §11 標 ❌ 的端點 | 換登入 session，**不是 bug** |
| 部署 failed | 看建置日誌＋失敗 stage（build/plan/rollout…） | 對照 §2 應用形狀規則 |
| 部署 failed、日誌空、「builder 未留下 termination message」 | 偶發型或容器級 OOM | 先原樣重送；再失敗查建置記憶體（§8） |
| 「Knative Service 未能就緒…ksvc ready 逾時（2m0s）」但 runtime-logs 顯示 Ready | 框架綁到 pod 名稱不綁 loopback | `ENV HOSTNAME=0.0.0.0`（§2 綁定介面陷阱）；訊息裡的「未聽 PORT」是錯方向 |
| 容器內打 `/api/v1/data-center/...` 回 401 `Invalid authentication token` | 路徑少了 `/open` 前綴 | 改 `/api/v1/open/data-center/...`（§5），不是憑證問題 |
| `/open/proxy/{table}` 403「App 未被授權存取表」 | 整合尚未引用該預設表 | `POST /refs/apps/{整合 id}` 或 UI 加引用（§5），立即生效 |

## 11. API 端點速查（前綴 `/api/v1/hosted-apps`）

| 端點 | Deploy Token |
|---|:-:|
| `GET /`／`GET /{id}` | ✅ |
| `POST /`（建立）——session-only（ADR 0019，§3.1；固定 403 訊息） | ❌ |
| `POST /{id}/deployments`／`GET .../deployments*`／`.../logs` | ✅ |
| `POST /{id}/restart`／`GET /{id}/runtime-logs`／`POST /{id}/logs/interpret`（⚠️ restart／interpret prod 2026-09-02 仍 404，v1.13.0 已補） | ✅ |
| `GET /{id}/runtime-starts`／`GET /{id}/runtime-starts/{pod_name}/logs`／`POST /{id}/logs/interpret-line`（§8；v1.13.0，prod openapi 已實查） | ✅ |
| `GET|PUT /{id}/runtime-settings`／`GET /{id}/resource-usage` | ✅ |
| `GET /{id}/preview`／`POST /{id}/preview/capture` | ✅ |
| `POST /{id}/redeploy`（⚠️ prod 2026-09-02 仍 404，v1.13.0 已補）／`clone`／`PATCH /{id}`（改名）／`DELETE /{id}`（回 `{status: deleted, teardown: completed}`，2026-09-08 實打） | ❌ |
| `POST|DELETE /{id}/icon`／`PUT /{id}/access-settings` | ❌ |
| `/{id}/credential/{provision|rotate|revoke}` | ❌ |
| `/{id}/domains*`／`/{id}/ports*` | ❌ |
| `/{id}/files*`／`/{id}/console/*`（含 WS 終端） | ❌ |

另有：`/api/v1/hosted-app-gateways`（多 app 共用 hostname 的 path 路由）、
`/api/v1/deploy-tokens`、`POST /api/v1/hosted-app-session/handoff`（交遞，Token 不可用）、
`GET|POST /api/v1/refs/apps/{attached_integration_id}`（預設表引用，§5；不在前綴下，
Deploy Token 的路徑白名單只認 `/hosted-apps` 前綴，**要登入 session**）。
邀請成員直達 hosted app：`redirect_url` 白名單含 `/hosted-app-handoff/{slug}`
（→ `member-admin.md` §4）。
