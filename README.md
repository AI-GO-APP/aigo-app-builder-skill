# AI GO Custom App Builder Skill

> 用於 AI IDE（Antigravity / Claude Code / Cursor）的 Skill，協助開發者完成 **AI GO Custom App** 的完整開發流程。

## 功能特色

| 階段 | 說明 |
|------|------|
| **Phase 0** | Review 現有 Code（強制） — 分析雲端 VFS 狀態、檔案分類、路由結構、CSS 合規性與 Server Actions |
| **Phase 1** | 環境設定 — 帳號登入、取得 Token、初始化 `.aigo/config.json` |
| **Phase 2** | 專案腳手架（單頁/多頁） — 從雲端 VFS 下載到本地，自動排除 SDK 保護檔 |
| **Phase 3** | 開發指引（React 18 + TypeScript + Shadow DOM） — 元件開發規範、CSS 限制、Server Actions 撰寫 |
| **Phase 4** | 部署（sync → compile → publish） — 差異同步、樂觀鎖版本控制、自動 CSS 修復 |
| **Phase 5** | E2E 驗證 — 全自動化測試涵蓋認證、VFS 同步、編譯、Custom Data CRUD、發布 |

## 安裝方式

### 全域安裝（推薦）

```bash
git clone https://github.com/AI-GO-APP/skill-AIGO-Builder.git ~/.gemini/config/skills/aigo-builder/
```

### 專案內安裝

```bash
git clone https://github.com/AI-GO-APP/skill-AIGO-Builder.git .agents/skills/aigo-builder/
```

## 目錄結構

```
aigo-builder/
├── SKILL.md                          # Skill 主文件（前端 + 後端完整流程指引）
├── README.md                         # 本文件
├── LICENSE                           # MIT 授權
├── .gitignore
├── references/
│   └── custom-app-dev-guide.md       # Custom App 開發參考指南
├── resources/
│   └── vfs_template.json             # VFS 範本（單頁/多頁）
└── scripts/
    ├── pyproject.toml                # uv 專案設定
    ├── uv.lock                       # 鎖定依賴版本
    ├── aigo_auth.py                  # 認證模組（登入、Token 管理、App 資訊）
    ├── aigo_review.py                # Review 模組（VFS 分析、CSS 檢查）
    ├── aigo_scaffold.py              # 腳手架模組（VFS 下載到本地）
    ├── aigo_sync.py                  # 同步模組（差異比對、上傳）
    ├── aigo_compile.py               # 編譯模組（呼叫雲端編譯 API）
    ├── aigo_publish.py               # 發布模組（發布 App、狀態檢查）
    ├── aigo_data_center.py           # 資料中心自建表（租戶級：結構 + 記錄 CRUD）
    ├── aigo_e2e.py                   # E2E 整合流程
    └── run_e2e_tests.py              # 完整 E2E 測試腳本
```

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

## 使用方式

1. 在 AI IDE 中開啟任意專案
2. 向 AI 助理提及你要開發 AI GO Custom App
3. Skill 會自動觸發並引導你完成完整開發流程

### 執行 E2E 測試

```powershell
# 設定環境變數
$env:AIGO_EMAIL='your-email@example.com'
$env:AIGO_PASSWORD='your-password'
$env:AIGO_APP_ID='your-app-id'
$env:AIGO_SLUG='your-slug'

# 執行測試
cd scripts
uv run run_e2e_tests.py
```

## 注意事項

- ⚠️ **密碼不儲存**：所有帳密透過環境變數提供，不會寫入任何設定檔
- ⚠️ **`.aigo/` 已在 `.gitignore`**：本地產生的 `.aigo/config.json` 含有 Token，不會被提交
- ⚠️ **SDK 保護檔**：`src/api.ts`、`src/db.ts`、`src/action.ts` 等由平台注入，不可修改
- ⚠️ **Shadow DOM 限制**：Custom App 運行在 Shadow DOM 中，不可使用 `document.querySelector`、全域 CSS 變數等

## License

[MIT](LICENSE)
