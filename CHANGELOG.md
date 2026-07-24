# Changelog

版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。
**每次改動 Skill 內容（SKILL.md / CONTEXT.md / references / scripts）都要同步更新 `VERSION`**，
否則使用者端的更新檢查（`scripts/check_update.py`）不會提示。

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
