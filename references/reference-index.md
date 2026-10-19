# 共用規則與按需參考索引

外部 IDE 與 Builder 以 `SKILL.md` 的 `shared-rules` 標記區為共用開發規則 SSOT；
本索引決定核心文件與依工作需要補入的章節，不另複製一份大型提示詞。

**邊界判準**：資料結構＝表、欄位、資料引用、權限、外部服務、排程的**定義**
（Builder 入口可依平台 ContextSnapshot 自動取得摘要）；業務資料＝表內**記錄**、個資與金鑰值
（不自動讀取，寫入前必須具體確認）。

| 檔案 | 用途（一句） | 載入時機 | 入口 | 邊界 |
|---|---|---|---|---|
| `CONTEXT.md` | 統一資料承載體、事件觸發、App 模式與資料邊界術語。 | 核心 | 兩者 | 資料結構 |
| `references/dev-rules.md` | 展開 Phase 3 規則 18–34 的資料、事件、權限、時間與部署硬規則。 | 核心 | 兩者 | 資料結構 |
| `references/reference-index.md` | 列出兩種入口共用的核心與按需知識載入契約。 | 按需 | 兩者 | 無 |
| `references/custom-app-dev-guide.md` | 提供 Custom App 架構、SDK、API、Actions 與存取通道規格。 | 按需 | 兩者 | 資料結構 |
| `references/data-center.md` | 說明自建表與延伸欄位的結構、權限、配額及操作契約。 | 按需 | 兩者 | 資料結構 |
| `references/data-operations.md` | 規範不開發 app 時的正式資料查詢、寫入、匯入與匯出閘門。 | 按需 | IDE | 業務資料 |
| `references/default-table-lookup.md` | 將業務語言對照預設表、欄位、必填值域與唯讀限制。 | 按需 | 兩者 | 資料結構 |
| `references/environment.md` | 設定本機租戶工作區、憑證檔、登入與 app 登錄。 | 按需 | IDE | 業務資料 |
| `references/event-triggers.md` | 定義 Webhook 與 App 排程的宣告、投遞、冪等和限制。 | 按需 | 兩者 | 資料結構 |
| `references/hosted-apps.md` | 說明 Hosted App 邊界、部署、環境變數及驗證閘門。 | 按需 | 兩者 | 資料結構 |
| `references/hosted-migration-runbook.md` | 引導既有正式站遷入 Hosted App、切換、回滾與退場。 | 按需 | IDE | 業務資料 |
| `references/issue-reporting.md` | 規範以本機腳本建立平台問題卡及追蹤進度。 | 按需 | IDE | 業務資料 |
| `references/member-admin.md` | 規劃角色與 app 存取並操作成員邀請及角色管理。 | 按需 | IDE | 業務資料 |
| `references/migration-workflow.md` | 盤點既有系統並映射程式、資料結構、身分與切換方案。 | 按需 | IDE | 業務資料 |
| `references/planning.md` | 展開需求盤點、產品線、授權與資料承載計畫閘門。 | 按需 | 兩者 | 資料結構 |
| `references/platform-behaviors.md` | 彙整分頁、時區、Runtime 網址與權限閘等實測平台行為。 | 按需 | 兩者 | 資料結構 |
| `references/pre-report-self-grill.md` | 在回報平台問題前執行六輪自審與證據排除。 | 按需 | IDE | 無 |
| `references/product-line-decision.md` | 判斷 Custom、Hosted 或混合產品線及不可逆模式選擇。 | 按需 | 兩者 | 無 |
| `references/review-workflow.md` | 用本機工作區與 Python 腳本完成現有 App 的九步盤點。 | 按需 | IDE | 資料結構 |
| `references/template-workflow.md` | 盤點模板、取回預覽碼並把效果繫結落成平台資源。 | 按需 | IDE | 資料結構 |
| `references/troubleshooting.md` | 依症狀與錯誤碼診斷平台、設定、編譯和執行期問題。 | 按需 | 兩者 | 無 |
| `references/uat-environment.md` | 規劃隔離的 UAT 拓撲、憑證、測試資料與退場。 | 按需 | IDE | 業務資料 |
| `references/verification-details.md` | 用本機工具執行編譯、資料 CRUD、Action 與發布一致性驗證。 | 按需 | IDE | 業務資料 |

## Builder 入口不載入的內容

Builder 入口不載入 `SKILL.md` 的 Phase -1 自我更新、Phase 1 憑證與工作區設定，
也不載入 `scripts/` 的任何腳本；這些由 Builder 端的 ContextSnapshot 與操作契約取代（T14 實作）。

## Builder 入口

入口模板：[builder/ENTRY.md](../builder/ENTRY.md)，由知識包載入。
展開器：[scripts/builder_entry.py](../scripts/builder_entry.py) 的 `render_entry(root)` 將共用規則 include 展開；供 CLI／知識包產生器使用，模型不執行腳本。
