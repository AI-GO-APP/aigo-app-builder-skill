# Changelog

版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。
**每次改動 Skill 內容（SKILL.md / CONTEXT.md / references / scripts）都要同步更新 `VERSION`**，
否則使用者端的更新檢查（`scripts/check_update.py`）不會提示。

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
