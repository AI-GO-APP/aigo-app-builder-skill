# 現有系統遷入 AI GO

> 只有「用戶有現存系統要遷入」時才需要這份。純新建 App 完全用不到。
>
> 這是 Phase 1.25 與 Phase 1.5 的**遷移分支**，接在 SKILL.md 的主流程上：
> §1 在任何單一 App 開始 Phase 1.5 之前做；§2 在該 App 的 Phase 1.5 計畫中做。

---

## 1. 多系統遷入盤點（2 個以上外部系統時）

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

---

## 2. 單一系統的遷移評估

### a. 語言與架構評估
- 若現有系統不是 TypeScript + Python：
  - **務必解釋**為什麼 AI GO 選擇 TypeScript + Python（見設計理念 / §21）
  - **建議用戶建立新的 AI GO 專案來重構**，而非嘗試直接移植原始碼
  - **原自身本地專案不更動**，AI GO 專案獨立開發
- 若已是 TypeScript + Python，可評估程式碼遷移可行性

### b. 外部 Schema → AI GO 架構映射（★ 必要）
- 列出外部系統所有資料表 / Sheet 與其欄位結構
- 逐表對照（先跑 Phase 1.5 第 3 點的雙邊盤點）：
  - 與 ERP／SaaS 功能連動的資料 → SaaS 表原生欄位；無原生對應的欄位 → `custom_data` JSONB
  - 租戶自有的新業務實體（**遷入案例的主力**）→ 自建表
  - 租戶已有語意相同的自建表 → 直接重用，不要新建
- 處理外部表之間的外鍵 / 關聯（AI GO 需用 ID 欄位 + 程式邏輯維護參照完整性）
- 產出「外部 Schema ↔ AI GO 映射表」（模板見 `resources/migration_mapping_template.md`）
- 若有 Phase 1.25 的全景表，映射須與全景表的合併 / 分離決策一致
- 詳見 `references/custom-app-dev-guide.md` §22

### c. 資料遷移計畫（★ 若需遷入歷史資料）
- 遷移範圍：全量 / 部分 / 僅結構不帶資料
- 遷移方式：Server Action 批次匯入 / API 逐筆寫入
- ID 體系轉換：外部自增 ID / Sheet 行號 → AI GO UUID 的對應方案
- 遷移後驗證：筆數比對、關鍵欄位抽驗
- 詳見 `references/custom-app-dev-guide.md` §23

---

## 3. 詳細參考

- Schema 映射決策框架、語意重疊表的合併／分離、外鍵處理 → `custom-app-dev-guide.md` §22
- 遷移策略矩陣、批次匯入範例、ID 體系轉換、驗證 checklist → `custom-app-dev-guide.md` §23
- 映射表模板 → `resources/migration_mapping_template.md`
