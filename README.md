# AI GO Custom App Builder Skill

> 用於 AI IDE（Antigravity / Claude Code / Cursor）的 Skill，協助開發者完成 **AI GO Custom App** 的完整開發流程。

## 功能特色

| 階段 | 說明 |
|------|------|
| **Phase -1** | Skill 自我更新檢查 — 比對遠端 `VERSION`，有新版時提示並徵詢是否更新（見「保持更新」） |
| **Phase 0** | Review 現有 Code（強制） — 分析雲端 VFS 狀態、檔案分類、路由結構、CSS 合規性與 Server Actions |
| **Phase 1** | 環境設定 — 帳號登入、取得 Token、初始化 `.aigo/config.json` |
| **Phase 2** | 專案腳手架（單頁/多頁） — 從雲端 VFS 下載到本地，自動排除 SDK 保護檔 |
| **Phase 3** | 開發指引（React 18 + TypeScript + Shadow DOM） — 元件開發規範、CSS 限制、Server Actions 撰寫 |
| **Phase 4** | 部署（sync → compile → publish） — 差異同步、樂觀鎖版本控制、自動 CSS 修復 |
| **Phase 5** | E2E 驗證 — 全自動化測試涵蓋認證、VFS 同步、編譯、自建表 CRUD、發布 |

同時涵蓋：

- **資料架構雙軌分流** — 依資料性質在「資料中心自建表」（租戶級真實資料表）
  與「Data Reference」（引用平台預設表）之間判定，建表前強制盤點避免重複建表
- **Webhook** — manifest 宣告、多端點、驗簽、冪等要求
- **App 排程** — 結構化排程、tier 限制、重疊與自動暫停語義
- **現有系統遷入** — Supabase / Google Sheet / MySQL 的 Schema 映射與資料遷移

## 安裝方式

用 [`skills`](https://github.com/vercel-labs/skills) CLI 安裝（支援 Claude Code /
Antigravity / Cursor / Codex 等 70+ 種 agent，會自動偵測並裝到正確位置）：

```bash
npx skills add AI-GO-APP/aigo-app-builder-skill
```

指定 agent 或安裝範圍：

```bash
npx skills add AI-GO-APP/aigo-app-builder-skill --agent claude-code --scope project
```

其他常用指令：`npx skills list`（看已安裝）、`npx skills update`（更新）。

<details>
<summary>手動安裝（不使用 CLI）</summary>

直接 clone 到 agent 的 skills 目錄，例如：

```bash
# 專案內
git clone https://github.com/AI-GO-APP/aigo-app-builder-skill.git .agents/skills/aigo-builder/

# Claude Code 專案內
git clone https://github.com/AI-GO-APP/aigo-app-builder-skill.git .claude/skills/aigo-builder/
```

⚠️ 手動安裝務必保留完整目錄結構——`SKILL.md` 會指向 `references/` 與 `CONTEXT.md`，
只複製單一檔案會讓指引斷鏈。

</details>

## 一台裝置怎麼整理：一份 skill、幾個租戶就幾個目錄、app 在目錄裡登錄

skill 本身沒有任何租戶或 app 專屬內容，**不要 by app 或 by 租戶裝多份**（多份會漂移，
更新時還會洗掉放在裡面的憑證）。租戶與 app 都在工作區的 `.aigo/` 裡：

```
~/.claude/skills/aigo-builder/        skill，只此一份（user scope）
~/.aigo/.env                          預設帳密；AIGO_TENANT 可選（會存取多個租戶就留空）
~/work/urfit-erp/.aigo/config.json    工作區＝一個租戶（base_url=urfit），apps 登錄表列該租戶的 app
~/work/demo-lab/.aigo/config.json     另一個租戶；同目錄 .aigo/.env 可覆寫另一組帳密
```

- **多一個租戶＝多一個工作區目錄**（token 是租戶級，跟目錄走）
- **多一個 app＝登錄表多一筆**：`aigo_auth.py app add <alias> --id <uuid>`，之後用 alias 指稱；
  單 app 工作區不必指定，腳本自動選唯一那筆；多 app 未指定會**報錯列出 alias，不猜**
- Hosted App 原始碼是獨立 repo 時仍不裝 skill 進去，登錄表的 `path` 指過去即可
- 純資料中心工作（建表、CRUD）不需要 app，登錄表可為空
- `project` scope 安裝只留給需要鎖 skill 版本的團隊 repo；本機超過一份時
  `aigo_auth.py status` 與更新檢查都會提醒

## 保持更新

Skill 內含版本標記（`VERSION`）與更新檢查腳本（`scripts/check_update.py`），
比對本地與 GitHub 上的 `VERSION`，有新版才提示。腳本零相依（只用 Python 標準函式庫、
不經 uv），離線或逾時一律靜默略過。節流 3 小時：遠端版本抓一次後快取
（狀態存在 `~/.aigo/update_check.json`），同一組版本差 3 小時內只提示一次；
**版本比對每次都做**，不受節流影響。

**多安裝同步**：本機每份安裝執行檢查時會把自身路徑登記進共用狀態檔，
累積成安裝清單。任一安裝偵測到新版時會列出其他落後的已註冊安裝，並提供
`--apply-all` 一次更新所有 git 安裝（複製式安裝只列指令不代動）。
限制：只認得「至少跑過一次檢查」的安裝——從未在任何 session 觸發過的副本無從發現。

**任何 agent 都適用（預設）**：`SKILL.md` 的 Phase -1 會在每次 Skill 觸發時執行檢查，
有新版時由 AI 告知你並詢問是否更新。缺點是 `SKILL.md` 已載入 context，更新後需重新讀取
才會在當回合生效。

**Claude Code / Codex（推薦加裝）**：改用 SessionStart hook，在 Skill 載入**之前**完成檢查，
沒有上述時序問題。範本在 `resources/hooks/`，把 `<SKILL_DIR>` 換成本機 skill 路徑後合併進設定：

| Agent | 設定檔 | 範本 |
|-------|--------|------|
| Claude Code | `~/.claude/settings.json` 或 `<專案>/.claude/settings.json` | `resources/hooks/claude-code.settings.example.json` |
| Codex CLI（>= v0.124.0） | `~/.codex/config.toml` 或 `<repo>/.codex/config.toml` | `resources/hooks/codex.config.example.toml` |

手動檢查與更新：

```bash
python scripts/check_update.py --force      # 忽略節流立即檢查（macOS/Linux 用 python3）
python scripts/check_update.py --json       # 機器可讀輸出
python scripts/check_update.py --apply      # git 安裝：就地 pull --ff-only（僅本安裝）
python scripts/check_update.py --apply-all  # 更新註冊表裡所有落後的 git 安裝
```

`--apply`／`--apply-all` 只對 git 安裝實際更新；用 `npx skills add` 安裝的複製式安裝
會印出 `npx skills update` 讓你自己執行。任一情況都**不會**覆寫你的本地修改
（`--ff-only` 遇到分岔或髒工作區會直接失敗）。

> 維護者注意：改動 Skill 內容後要同步 bump `VERSION` 並在 `CHANGELOG.md` 補一節，
> 否則使用者端不會收到更新提示。

## 目錄結構

```
aigo-builder/
├── SKILL.md                          # Skill 主文件（工作流骨架 + 核心規則）
├── CONTEXT.md                        # 術語表（預設表／自建表兩大類＋機制詞、稱謂對照）
├── README.md                         # 本文件
├── VERSION                           # 版本標記（更新檢查的比對基準）
├── CHANGELOG.md                      # 版本變更紀錄
├── LICENSE                           # MIT 授權
├── references/                       # 依需要載入的參考文件
│   ├── custom-app-dev-guide.md       # 核心 API 規格與架構理念
│   ├── data-center.md                # 資料中心自建表完整規格
│   ├── event-triggers.md             # Webhook 與 App 排程
│   ├── migration-workflow.md         # 有現存系統要遷入時
│   ├── verification-details.md       # 要執行驗證時
│   ├── data-operations.md            # 資料操作模式：不開發 app，以使用者身分直接讀寫資料
│   └── troubleshooting.md            # 出錯時
├── resources/
│   ├── vfs_template.json             # VFS 範本（單頁/多頁）
│   ├── migration_mapping_template.md # 外部 Schema ↔ AI GO 映射表模板
│   ├── project_deconstruction_template.md # 既有專案解構清單（前+後+DB 遷入用）
│   └── hooks/                        # SessionStart 更新檢查 hook 範本
│       ├── claude-code.settings.example.json
│       └── codex.config.example.toml
└── scripts/
    ├── pyproject.toml                # uv 專案設定
    ├── check_update.py               # Skill 自我更新檢查（零相依，不走 uv）
    ├── uv.lock                       # 鎖定依賴版本
    ├── aigo_auth.py                  # 認證（登入、Token 管理、App 資訊）
    ├── aigo_review.py                # Review（VFS 分析、CSS 檢查、租戶級資源盤點）
    ├── aigo_scaffold.py              # 腳手架（VFS 下載到本地）
    ├── aigo_sync.py                  # 同步（差異比對、上傳）
    ├── aigo_compile.py               # 編譯（呼叫雲端編譯 API）
    ├── aigo_publish.py               # 發布（發布 App、狀態檢查）
    ├── aigo_data_center.py           # 資料中心自建表（租戶級：結構 + 記錄 CRUD）
    ├── aigo_data.py                  # 資料操作模式：me／perm-check／openapi 查路由／通用 call 翻頁／匯出／Meta 值域
    ├── aigo_runtime_verify.py        # Runtime 驗證（編譯產物／發布一致性／CRUD／Action）
    ├── aigo_e2e.py                   # E2E 整合流程
    ├── retest_verification.py        # 驗證重跑工具
    └── run_e2e_tests.py              # 完整 E2E 測試腳本
```

> `SKILL.md` 只放工作流與硬規則，細節按**使用分支**下放到 `references/`——
> 遷移、驗證細節、錯誤排查只在真的需要時才載入。

## 腳本依賴

本 Skill 的 Python 腳本使用 [uv](https://docs.astral.sh/uv/) 管理依賴，主要依賴 `httpx`。

```bash
cd scripts
uv venv .venv
uv pip install httpx
```

或直接使用 `uv sync`（會依據 `pyproject.toml` 和 `uv.lock` 安裝）：

```bash
cd scripts
uv sync
```

## 憑證設定（每台機器只需一次）

```bash
uv run --project scripts python scripts/aigo_auth.py setup
```

會產生 **`~/.aigo/.env`**（家目錄，機器級）。用編輯器打開，填入你自己的帳密：

```ini
AIGO_EMAIL=your-email@example.com
AIGO_PASSWORD=your-password
```

驗證：

```bash
uv run --project scripts python scripts/aigo_auth.py login
```

之後 Skill 內所有 API 呼叫都走 `aigo_auth.get_token()`——Token 快取在
`<工作區>/.aigo/token.json`，過期自動換新，**不會再問你密碼**。

> ⚠️ **不要把憑證放進 Skill 安裝目錄**（`.claude/skills/aigo-builder/` 之類）。
> `npx skills update` 會**刪除整個 skill 資料夾再重新複製**，放在裡面的
> `.aigo/.env`、`.aigo/token.json` 會連同一起消失，而且因為被 `.gitignore` 忽略、
> 不在任何 commit 裡，救不回來。所以 `setup` 預設寫家目錄——它與 Skill 安裝位置無關。
> （git clone 安裝 + `git pull --ff-only` 不會刪除 ignored 檔案，但別依賴這點。）

### 憑證的查找順序

| 順序 | 位置 | 用途 |
|---|---|---|
| 1 | 環境變數 `AIGO_EMAIL` / `AIGO_PASSWORD` … | 臨時覆寫、CI |
| 2 | `<工作區>/.aigo/.env` | 工作區專用（該租戶用不同帳號；Hosted App 的 `AIGO_DEPLOY_TOKEN__<ALIAS>`） |
| 3 | `~/.aigo/.env` | 機器級預設，**建議放帳密** |

先找到的優先；工作區級只寫你要覆寫的鍵，其餘自動沿用機器級。

### 租戶空間網址（★ 必填，無預設值）

AI GO 的登入與 API 一律走租戶子網域：

```
https://[tenant].ai-go.app/*     例如 https://urfit.ai-go.app、https://demo.ai-go.app
```

`tenant` 就是你平時登入時**網址列的第一段**。主站 apex `https://ai-go.app` 已不是登入入口
（`/login` 是找工作區的頁面），填 apex 會被腳本直接擋下。

**最省事的設定**：在 `~/.aigo/.env` 加一行前綴，整台機器通用——

```
AIGO_TENANT=urfit
```

完整的查找順序（**特定性越高越優先**）：

| 順序 | 位置 | 定位 |
|---|---|---|
| 1 | shell 環境變數 `AIGO_BASE_URL` 或 `AIGO_TENANT` | 臨時覆寫、CI |
| 2 | `<工作區>/.aigo/config.json` 的 `base_url`（從目前目錄往上找最近的） | 這個工作區綁定的租戶 |
| 3 | `.env` 的 `AIGO_BASE_URL` 或 `AIGO_TENANT` | 機器級預設 |

第 2 層會蓋過第 3 層——所以同一台機器可以一邊用 `AIGO_TENANT=urfit` 當預設，
一邊讓 demo 租戶的工作區在自己的 `config.json` 填 `"base_url": "https://demo.ai-go.app"`。
會存取多個租戶的機器建議 `AIGO_TENANT` 留空：沒有 config 的目錄就會明確報錯，
不會默默連到錯的租戶。

> ⚠️ **打錯租戶的症狀是 401「帳號或密碼錯誤」**——平台為了防帳號列舉，
> 讓「帳號不在這個租戶」與「密碼打錯」回完全相同的錯誤。看到 401 先跑
> `aigo_auth.py status` 確認租戶空間，再懷疑密碼。

| 指令 | 作用 |
|---|---|
| `aigo_auth.py setup` | 建立 `~/.aigo/.env` 範本（加工作區路徑才寫進該工作區，如 `setup ./urfit-erp`） |
| `aigo_auth.py setup-workspace <dir>` | 在租戶目錄建立 `.aigo/config.json`（schema 2）與工作區 `.env` 範本；拒絕 skill 安裝目錄 |
| `aigo_auth.py login` | 驗證憑證並快取 Token |
| `aigo_auth.py status` | 工作區、租戶與來源、身分與來源、app 登錄表、Token 與警告（不顯示秘密值） |
| `aigo_auth.py app add <alias> --id <uuid>` | 登錄 app（自動判定 custom／hosted 並回填）；`app list`／`default`／`remove` |
| `aigo_auth.py run <alias> -- <cmd>` | 在該 app 環境下執行指令；Hosted 的 Deploy Token 從工作區 `.env` 的 `AIGO_DEPLOY_TOKEN__<ALIAS>` 匯出 |
| `aigo_auth.py config migrate` | 把舊格式 config.json 改寫成 schema 2（讀取時本來就自動升級，這只是落檔） |
| `aigo_auth.py logout` | 清除 Token 快取 |

> 密碼請直接填進 `.env`，**不要**放在指令列（會留在 shell 歷史紀錄），
> 也不要貼進 AI 對話框（會留在對話紀錄）。

## 使用方式

1. 在 AI IDE 中開啟任意專案
2. 向 AI 助理提及你要開發 AI GO Custom App
3. Skill 會自動觸發並引導你完成完整開發流程

### 執行 E2E 測試

帳密沿用 `~/.aigo/.env`；目標 app 從工作區登錄表解析（多筆時用 `AIGO_APP=<alias>` 指定），
用 `AIGO_PROJECT_ROOT` 指向工作區：

```bash
cd scripts
AIGO_PROJECT_ROOT=/path/to/workspace AIGO_APP=erp uv run run_e2e_tests.py
```

PowerShell 改成 `$env:AIGO_PROJECT_ROOT='C:\path\to\workspace'` 再執行。
不指定時以目前目錄為工作區——**別讓它落在 skill 目錄裡**（見上方警告）。
舊的 `AIGO_APP_ID`／`AIGO_SLUG` 仍可用（相容）。

## 注意事項

- ⚠️ **密碼只存在 `~/.aigo/.env`**（或你自訂的專案 `.env`）：不寫入 `config.json`、原始碼或 commit，也不放在指令列
- ⚠️ **憑證不要放進 Skill 安裝目錄**：`npx skills update` 會刪除整個 skill 資料夾重建
- ⚠️ **`.aigo/` 已在 `.gitignore`**：`.env`（帳密、Deploy Token）與 `token.json` 都在裡面，不會被提交；
  `config.json` 只有租戶網址與 app 登錄表，沒有秘密
- ⚠️ **SDK 保護檔**：`src/api.ts`、`src/db.ts`、`src/action.ts` 等由平台注入，不可修改
- ⚠️ **Shadow DOM 限制**：Custom App 運行在 Shadow DOM 中，不可使用 `document.querySelector`、全域 CSS 變數等

## License

[MIT](LICENSE)
