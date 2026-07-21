# 外部 Schema → AI GO 映射表

> 本模板用於 Phase 1.5 第 6 點 b「外部 Schema → AI GO 架構映射」步驟。
> 每個外部系統的每張表填寫一份。

## 系統資訊

| 項目 | 值 |
|------|---|
| 系統名稱 | |
| DB 類型 | （Supabase / Google Sheet / MySQL / Airtable / ...） |
| 對應 AI GO App | |
| app_domain | |

## 表映射

### 外部表：`[表名]` → AI GO：`[SaaS 表名 or 自建表實體名]`

| 外部欄位 | 外部型別 | AI GO 對應方式 | AI GO 表 | AI GO 欄位 | 備註 |
|---------|---------|---------------|---------|-----------|------|
| id | INT / UUID | 不遷移 | - | - | AI GO 自動生成 UUID |
| name | TEXT | 直接對應 | customers | name | |
| email | TEXT | 直接對應 | customers | email | |
| company | TEXT | custom_data | customers | custom_data.company | JSONB 擴充 |
| level | TEXT | custom_data | customers | custom_data.level | JSONB 擴充 |
| notes | TEXT | 直接對應 | customers | description | 欄位名稱不同但語意一致 |
| created_at | TIMESTAMP | 不遷移 | - | - | AI GO 自動生成 |

> 對應方式填寫規則：
> - `直接對應`：外部欄位可直接寫入 SaaS 表的原生欄位
> - `custom_data`：放入 SaaS 表的 `custom_data` JSONB 欄位
> - `自建表`：需建立自建表來存放（租戶級，建表需 system.admin）
> - `不遷移`：系統欄位，AI GO 自動管理

### 無法對應 SaaS 表的欄位 → 自建表

| 外部表.欄位 | 說明 | 自建表顯示名 | 欄位顯示名 | 欄位型別 |
|------------|------|------------------|------------------|---------|
| | | | | text / number / date / relation |

### 外鍵關係

| 外部 FK 欄位 | 外部目標表 | AI GO 處理方式 | 備註 |
|-------------|-----------|---------------|------|
| orders.customer_id | customers | SaaS 表原生 customer_id 欄位 | |
| tasks.project_id | projects | custom_data.project_id | 需在程式碼中維護參照 |

## 資料遷移摘要

| 項目 | 值 |
|------|---|
| 遷移範圍 | 全量 / 部分 / 僅結構 |
| 預估筆數 | |
| 遷移方式 | Server Action 批次 / API 逐筆 |
| ID 轉換 | 需要 / 不需要 |
| 遷入順序 | （在有 FK 時填寫：先匯哪張表） |
