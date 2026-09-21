# 環境設定（Phase 1 的完整版）

> `SKILL.md` Phase 1 只留三條硬規則與最短設定路徑；租戶網址規則的推導、三層模型、
> `config.json` schema 2 的欄位與 `base_url` 三層來源、逐步設定流程、憑證規則細節都在本檔。

## 目錄

- 租戶空間網址規則（★ 不可違反）：為什麼 apex 打不通、401 的兩種同形成因
- 三層模型：裝置 → 工作區 → app
- 配置檔 `.aigo/config.json`（schema 2）：欄位、apps 登錄表、`base_url` 的三層來源
- 設定流程：六步
- 憑證規則（★ 不可違反）：檔案落點、不得代填、不得印出 token

---

### 租戶空間網址規則（★ 不可違反）

**所有登入與 API 一律走租戶子網域：`https://[tenant].ai-go.app/*`**

```
https://urfit.ai-go.app/api/v1/auth/login     ✅
https://demo.ai-go.app/api/v1/builder/apps/…  ✅
https://ai-go.app/api/v1/auth/login           ❌ 主站 apex，不是租戶入口
https://xxx.apps.ai-go.app/…                  ❌ Custom App 執行期網域，不是 API host
```

> 這條只管**登入與 API 的 base_url**。app 的**執行期網址**是另一套形狀——internal 在
> `{tenant}.ai-go.app/runtime/…`，external 在 `*.apps.ai-go.app/ext-runtime…`，各有正式／測試兩版；
> 唯一權威表 `references/platform-behaviors.md` §6.2，別拿本條去「糾正」它。

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
