---
name: aigo-builder
description: >
  AI GO Custom App 開發者工具。引導用戶完成帳號設定、現有 Code Review、專案建立、
  前端 (React 18 + TypeScript) 與後端 (Python Server-Side Actions) 開發、
  雲端部署及 E2E 驗證的完整流程。全域安裝，可跨多專案使用。
---

# AI GO Custom App Builder

本 Skill 協助 AI Agent 開發 AI GO Custom App。支援 Antigravity / Claude Code / Cursor。

## 設計理念

AI GO Custom App 採用 **TypeScript（前端）+ Python（後端）** 的精選語言組合，
具備低出錯率、靜態型別安全、LLM 生成最佳化等特性，最適合 AI Coding 新手與非技術工作者
開發可靠的公司內部系統。

資料存取統一走 API，不直連資料庫——避免非技術 AI Coder 重複建立類似的表或欄位。
AI GO 預先定義了中小企業通用的資料庫結構（SaaS 表），同時保有 Custom Table 擴充彈性。

> 詳見 `references/custom-app-dev-guide.md` §21 架構設計理念。

## Phase 0：Review 現有 Code（★ 強制步驟）

> **每次開始任何開發工作前，必須先執行此步驟。**

### 流程

1. 確認 `.aigo/config.json` 中 `email` 和 `app_id` 已設定
2. 請用戶臨時提供密碼（不儲存）
3. 呼叫 Login API 取得 JWT
4. `GET /api/v1/builder/apps/{app_id}` 取得完整 App 資訊含 VFS
5. 分析 VFS 結構並輸出 Review 報告：
   - 列出所有檔案及大小
   - 標記 SDK 檔案 `[SDK]`（不可修改：api.ts, db.ts, action.ts）
   - 標記 Runtime 注入檔 `[INJ]`（不可修改：data.json, db.json, actions.json）
   - 解析 App.tsx 路由結構
   - 解析 _manifest.json 頁面清單
   - 解析 data.json Custom Table 定義
   - **解析 db.json Data Reference 定義**（★ 重要）：
     - 列出所有 SaaS 表名稱和欄位結構
     - 標記哪些表有 `custom_data`（JSONB）欄位
     - 列出每張表的權限（read/create/update/delete）
     - 統計現有資料筆數和 `app_domain` 分布
   - 解析 actions/manifest.json
   - 檢查 App.css Shadow DOM 相容性
6. **確認已完全理解現有結構後，才可進入開發**

可使用 `scripts/aigo_review.py` 的 `review_app()` 和 `format_review_report()` 輔助。

## Phase 1：環境設定

### 配置檔 `.aigo/config.json`

```json
{
  "base_url": "https://ai-go.app",
  "email": "",
  "app_id": "",
  "app_slug": "",
  "app_name": "",
  "access_mode": "internal",
  "app_domain": ""
}
```

### 設定流程

1. 檢查專案目錄下 `.aigo/config.json` 是否存在
2. 不存在 → 建立骨架（可用 `scripts/aigo_auth.py` 的 `init_config()`）
3. 引導用戶：
   - 前往 AI GO 後台 (https://ai-go.app/dashboard)
   - 確認帳號具備 `builder.access` 權限
   - 進入 Builder → Custom Apps → 記下 App 的 UUID (`app_id`)
   - 填入 `.aigo/config.json` 的 `email` 和 `app_id`
4. 驗證連線：用戶臨時輸入密碼 → Login API → GET App → 自動回填 `slug`、`name`、`access_mode`
5. **密碼不儲存到任何檔案中**

## Phase 1.25：多系統遷入盤點（條件觸發）

> **觸發條件**：用戶明確表示有 **2 個以上外部系統**（各自帶 Supabase / Google Sheet / MySQL 等 DB）要遷入 AI GO。
> 若僅遷入 1 個系統或純新建 App，跳過此步驟直接進入 Phase 1.5。

### 目的

在任何單一 App 開始 Phase 1.5 之前，先建立**全局視圖**，避免各 App 各自為政導致資料架構混亂。

### 盤點流程

1. **外部系統清單**
   - 列出所有要遷入的系統名稱、用途、技術棧、DB 類型
   - 每個系統的核心資料表 / Sheet 清單與主要欄位

2. **跨系統資料表交叉比對**
   - 找出語意相同的表（如都有「客戶」「專案」「訂單」）
   - 判斷是否指向同一群實體（同一批客戶？不同市場的客戶？）
   - 決定合併（進同一張 AI GO 表）或分離（各自獨立表）
   - 詳細的決策框架見 `references/custom-app-dev-guide.md` §22

3. **AI GO App 規劃**
   - 決定做成幾個 AI GO App
   - 每個 App 的 `app_domain` 初步命名（避免碰撞）
   - 確定遷入順序：主資料（客戶、產品）先於交易資料（訂單、案件），無依賴者先行

4. **產出：遷入全景表**
   - 格式：`| 外部系統 | 對應 AI GO App | app_domain | 遷入順序 | 語意重疊的表 |`
   - 此表在後續各 App 的 Phase 1.5 中持續參照

## Phase 1.5：實作計畫（★ 強制步驟）

> **在任何開發工作開始前（包含從模板建立），必須先提出實作計畫並獲得用戶確認。**
> **禁止跳過此步驟直接進入 Phase 2 寫 code。**

### 計畫內容必須包含

1. **需求分析**
   - 用戶要實現的功能清單
   - 每個功能的目標使用場景
   - 預期的使用者流程

2. **場景拆分與 App 邊界建議**
   - 若需求涵蓋 2 群以上不同功能與目的的情景，**必須建議用戶分別做成不同的 Custom App**
   - 例如：「客戶管理」和「財務報表」應為 2 個獨立 App
   - 每個 App 的 `app_domain` 標籤建議值

3. **資料架構設計**（★ 必須遵循 Data Reference 優先策略，見 Phase 3 規則 18）
   - 先呼叫 `GET /api/v1/refs/available-tables` 取得所有可用 SaaS 表清單
   - 對候選表呼叫 `GET /api/v1/refs/tables/{name}/columns` 查看欄位結構
   - 列出所有需要的資料表
   - 逐表說明：使用現有 SaaS 表（db.json）還是建立 Custom Table（data.json）
   - 每個使用 SaaS 表的場景，說明如何利用 `custom_data`（JSONB）欄位擴充
   - 若全部使用 Custom Table，需明確說明為何 SaaS 表不適用
   - 若決定使用的 SaaS 表尚未在 db.json 中，引導用戶到 Builder 後台加入 Data Reference

4. **頁面架構**
   - 路由結構（單頁 / 多頁）
   - 主要頁面和功能
   - Server Action 需求

5. **app_domain 標籤設計**
   - 確定此 App 的 `app_domain` 值（snake_case，如 `patent_os`、`crm_leads`）
   - 說明標籤用途：所有寫入 SaaS 表的資料都會帶上此標籤

6. **現有系統遷移評估**（若適用）

   **a. 語言與架構評估**
   - 若現有系統不是 TypeScript + Python：
     - **務必解釋**為什麼 AI GO 選擇 TypeScript + Python（見設計理念 / §21）
     - **建議用戶建立新的 AI GO 專案來重構**，而非嘗試直接移植原始碼
     - **原自身本地專案不更動**，AI GO 專案獨立開發
   - 若已是 TypeScript + Python，可評估程式碼遷移可行性

   **b. 外部 Schema → AI GO 架構映射**（★ 必要）
   - 列出外部系統所有資料表 / Sheet 與其欄位結構
   - 逐表對照 AI GO SaaS 表（先跑 Phase 1.5 第 3 點的 Refs API）：
     - 可直接對應的欄位 → SaaS 表原生欄位
     - 無原生對應的欄位 → `custom_data` JSONB 擴充
     - 完全不適用 SaaS 表的資料 → Custom Table
   - 處理外部表之間的外鍵 / 關聯（AI GO 需用 ID 欄位 + 程式邏輯維護參照完整性）
   - 產出「外部 Schema ↔ AI GO 映射表」（模板見 `resources/migration_mapping_template.md`）
   - 若有 Phase 1.25 的全景表，映射須與全景表的合併 / 分離決策一致
   - 詳見 `references/custom-app-dev-guide.md` §22

   **c. 資料遷移計畫**（★ 若需遷入歷史資料）
   - 遷移範圍：全量 / 部分 / 僅結構不帶資料
   - 遷移方式：Server Action 批次匯入 / API 逐筆寫入
   - ID 體系轉換：外部自增 ID / Sheet 行號 → AI GO UUID 的對應方案
   - 遷移後驗證：筆數比對、關鍵欄位抽驗
   - 詳見 `references/custom-app-dev-guide.md` §23

### 計畫閘門

- **必須等待用戶明確回覆「同意」或提供修改意見後，才可進入 Phase 2**
- 若用戶修改需求，需更新計畫後再次確認
- 計畫確認後將 `app_domain` 值記錄到 `.aigo/config.json`

## Phase 2：專案腳手架

基於 Phase 0 Review 結果決定策略：

- **VFS 為空**：生成全新專案結構
  - 詢問用戶：單頁 App 或多頁 App？
  - 單頁：直接渲染，不使用 Router
  - 多頁：HashRouter + Sidebar 導航
  - 可用 `scripts/aigo_scaffold.py` 的 `scaffold_new_project()`

- **VFS 有內容**：下載到本地進行增量開發
  - 將雲端 VFS 下載為本地檔案結構
  - 保留現有所有程式碼
  - 可用 `scripts/aigo_scaffold.py` 的 `download_vfs_to_local()`

## Phase 3：開發指引

### 核心規則（必須嚴格遵守）

1. **框架**：React 18 + TypeScript
2. **路由**：多頁用 `HashRouter`（禁用 `BrowserRouter`）；單頁可不用 Router
3. **CSS**：全域 `App.css`，不支援 CSS Modules / Tailwind
4. **CSS 變數**：必須用 `:host, :root { }` 雙選擇器
5. **HTML 重設**：必須用 `html, :host { }` 雙選擇器
6. **入口點**：必須是 `src/main.tsx`，且 `import "./App.css"`
7. **Layout**：最外層容器必須 `height: 100vh; overflow-y: auto`
8. **Runtime 模組**：react, react-dom, lucide-react, react-router-dom, react-hot-toast 由 Runtime 提供，不可自行安裝
9. **SDK 不可修改**：api.ts, db.ts, action.ts, data.json, db.json, actions.json
10. **Server-Side Actions**：Python，放在 `actions/` 目錄，定義 `execute(ctx)` 函式
11. **Shadow DOM 限制**：`confirm()` / `alert()` / `prompt()` 不可用 → 改用 React state 或 react-hot-toast
12. **db.update() Bug**：需用 `{"data": {...}}` 包裝 payload（直接 fetch，不走 SDK）
13. **db.insert() Bug**：同上，需用 `{"data": {...}}` 包裝
14. **VFS 限制**：最多 200 檔案、單檔 ≤ 1MB、編譯超時 30 秒
15. **完整程式碼原則**：每次更新 VFS 檔案必須提供 100% 完整內容，禁止 `// ...省略` 佔位符
16. **不支援動態 import**：`import()` 語法不支援（lazy loading 除外，esbuild 支援 code splitting）
17. **不支援 Node.js 原生模組**：fs, path, crypto 等無法使用
18. **Data Reference 優先策略**（★ 強制）
    - 所有資料需求必須**優先查看 db.json 中的 SaaS 表**是否已有合適的表
    - SaaS 表通常包含 `custom_data`（JSONB）欄位，可存放任意結構化擴充資料
    - **只有確認所有 SaaS 表都無法滿足需求時**，才可使用 Custom Table（data.json）
    - 決策優先順序：
      1. 使用現有 SaaS 表 + `custom_data` JSONB 欄位
      2. 使用現有 SaaS 表 + 新增 Custom Table 補充
      3. 僅使用 Custom Table（最後手段）
19. **app_domain 標籤規範**（★ 強制）
    - 所有寫入 SaaS 表（Data Reference）的資料，都必須在 `custom_data` JSONB 中包含 `app_domain` 欄位
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

### Server-Side Action 撰寫

```python
def execute(ctx):
    # ctx.params — 前端傳入的參數
    # ctx.db.query(table, limit=N) — 查詢
    # ctx.db.insert(table, data) — 新增
    # ctx.http.call(service, endpoint) — 外部 API
    # ctx.secrets.get(key) — 金鑰
    # ctx.response.json(data) — 回應
    # ctx.csv.export(rows) — CSV 匯出
    data = ctx.params.get("key", "default")
    ctx.response.json({"result": data})
```


### 前端呼叫 Action

```typescript
import { runAction, downloadFile } from "../action";
const { data, file } = await runAction("my_action", { key: "value" });
if (file) downloadFile(file);
```

## Phase 4：部署 + 自動驗證（★ 每次 code 變更後必須執行）

> **原則：每次 code 變更後，都必須完成「同步 → 編譯 → 驗證」循環。**
> 只有通過驗證閘門，才可進入發布或繼續下一輪開發。
> 極小變更（如僅修改文字、CSS 微調）可跳過 Custom Data 和 Action 測試，但編譯驗證不可跳過。

### 4.1 標準部署流程

1. **同步 VFS**：讀取本地檔案 → PATCH `/api/v1/builder/apps/{id}/source/files`
   - 腳本：`scripts/aigo_sync.py` 的 `sync_to_cloud()`
   - ★ 內建二次驗證：PATCH 後自動 GET 確認 vfs_version 遞增 + 檔案確實寫入
2. **編譯**：POST `/api/v1/compile/compile/{slug}?dev=true`
   - 腳本：`scripts/aigo_compile.py` 的 `compile_app()`
3. **編譯失敗**：解析錯誤 → 嘗試自動修復 → 重新同步 → 重新編譯（最多 5 次）
4. **編譯成功 → 進入驗證閘門**（Phase 4.2）

### 4.2 驗證閘門（Verification Gate）

每次編譯成功後，根據**變更範圍**自動決定需要執行的驗證項目：

#### 變更範圍判斷規則

| 變更類型 | 影響範圍 | 需執行的驗證 |
|---------|---------|------------|
| **CSS 微調**（僅 App.css 變動） | 極小 | ✅ Compile 產物 |
| **文案/UI 修改**（僅 TSX 變動，無新 import） | 小 | ✅ Compile 產物 |
| **元件新增/重構**（新增 TSX、修改路由） | 中 | ✅ Compile 產物 + ✅ Publish 一致性 |
| **Custom Data 相關**（修改了使用 api.ts/db.ts 的程式碼） | 中 | ✅ Compile 產物 + ✅ Custom Data CRUD |
| **Server Action 變更**（actions/*.py 修改） | 中 | ✅ Compile 產物 + ✅ Server Action 呼叫 |
| **多個範圍同時變動** | 大 | ✅ 全部 4 項驗證 |
| **首次部署或架構變更** | 大 | ✅ 全部 4 項驗證 |

#### 驗證項目詳細定義

使用 `scripts/aigo_runtime_verify.py` 執行。

**① Compile 產物驗證**（★ 每次必跑）
```
verify_compile_output(compile_result)
  ✓ compile_success == true
  ✓ html 含 <!DOCTYPE> 和 id="root"
  ✓ bundle_js 含 React（> 500 bytes）
  ✓ css 非空（> 50 bytes）
```

**② Publish 一致性驗證**（元件新增 / 路由變更 / 發布後必跑）
```
verify_publish_consistency(base_url, token, app_id)
  ✓ status == "published"
  ✓ published_at 已更新
  ✓ published_vfs 與 vfs_state 檔案路徑一致
  ✓ published_vfs 與 vfs_state 內容一致
```

**③ Custom Data CRUD 驗證**（使用了 api.ts / db.ts 時必跑）
```
verify_custom_data_crud(base_url, token, table_id)
  ✓ CREATE → 201 + 回傳 id
  ✓ GET 確認寫入（二次驗證）
  ✓ DELETE → 204
  ✓ GET 確認刪除（二次驗證）
```

**④ Server Action 呼叫驗證**（actions/*.py 變更時必跑）
```
verify_server_action(base_url, token, app_id, action_name, params)
  ✓ HTTP 200
  ✓ execution_id 非空
  ✓ status == "success"
  ✓ result 非 null
  ✓ 無 error
  ✓ 執行時間 < 30 秒
```

### 4.3 驗證後決策

| 驗證結果 | 下一步 |
|---------|--------|
| ✅ 全部通過 | 可進入發布（4.4）或繼續開發 |
| ❌ Compile 失敗 | 回到 Phase 3 修復程式碼 |
| ❌ CRUD/Action 失敗 | 檢查 API 使用方式、表結構、Action 邏輯 |
| ❌ Publish 一致性失敗 | 重新 sync → compile → publish |

### 4.4 發布

只有通過驗證閘門後才可發布：

1. POST `/api/v1/builder/apps/{id}/publish`
   - 腳本：`scripts/aigo_publish.py` 的 `publish_app()`
   - ★ 內建二次驗證：POST 後自動 GET 確認 status == "published"
2. 發布後執行 Publish 一致性驗證

### 樂觀鎖

- GET App 時記錄 `vfs_version`
- PATCH 時帶入 `expected_version`
- 409 → 重新 GET → 合併 → 重試

### 自動修復策略

| 偵測問題 | 自動修復 |
|---------|--------|
| `:root {` 無 `:host` | → `:host, :root {` |
| `html {` 無 `:host` | → `html, :host {` |
| BrowserRouter | → HashRouter |
| 缺少 `import "./App.css"` | → 在 main.tsx 頂部加入 |

可使用 `scripts/aigo_sync.py`、`aigo_compile.py`、`aigo_publish.py`。

## Phase 5：完整 E2E 驗證（里程碑驗證）

> Phase 4 的驗證閘門在每次迭代中自動執行。
> Phase 5 是在**開發里程碑完成**（例如功能全部完成、準備交付）時執行的完整驗證。

### 完整驗證 = Phase 4 所有項目 + 以下補充

5. **全功能 Runtime 驗證**
   ```python
   from aigo_runtime_verify import run_full_runtime_verification, format_verification_report
   results = run_full_runtime_verification(
       base_url, token, app_id, slug,
       table_id="...",          # Custom Data 表 UUID
       action_name="..."        # 任一 Server Action 名稱
   )
   print(format_verification_report(results))
   ```
6. **External Auth**（可選）— 註冊 → 登入 → 取得用戶 → 登出
7. **Public 匿名**（可選）— 設定公開 → pub/ API 讀取 → 確認寫入被拒

可使用 `scripts/aigo_e2e.py` 和 `scripts/aigo_runtime_verify.py`。

## 驗證流程快速參照

```
每次 code 變更：
  sync → compile → ✅ Compile 產物驗證
                   └─ (若涉及 Data) → ✅ Custom Data CRUD
                   └─ (若涉及 Action) → ✅ Server Action 呼叫
                   └─ (若涉及路由/元件) → publish → ✅ Publish 一致性

里程碑交付：
  上述全部 + External Auth + Public 匿名（如適用）
```

## 錯誤處理速查

| 錯誤 | 解法 |
|------|------|
| 白屏 | 確認 `src/main.tsx` 正確掛載 React |
| 路由不動 | 使用 `HashRouter`，不可用 `BrowserRouter` |
| 頁面無法捲動 | Layout 需 `height: 100vh; overflow-y: auto` |
| CSS 不生效 | 確認 `main.tsx` 中 `import "./App.css"` |
| CSS 變數遺失 | `:root` 改為 `:host, :root` |
| `db.update()` 400 | 用 `{"data": {...}}` 包裝 payload |
| `db.ts` 500 | 確認 Data Reference 已建立並發布 |
| 401 | Token 過期，重新登入 |
| 409 Conflict | VFS 版本衝突，重新 GET 後重試 |
| 423 Locked | 有待審核的發布，等待或取消 |
| Action 超時 | 控制在 30 秒內 |
| pub/ API 403 | 確認 `allow_anonymous_access=true` |
| Compile 產物驗證失敗 | 檢查 main.tsx 入口和 App.css import |
| CRUD 驗證失敗 | 確認 Custom Table 已建立且欄位正確 |
| Action 驗證失敗 | 檢查 execute(ctx) 函式、依賴模組白名單 |
| Publish 一致性失敗 | 重新 sync → compile → publish 完整循環 |

## 參考文件

詳細 API 規格和進階功能請查閱 `references/custom-app-dev-guide.md`。
