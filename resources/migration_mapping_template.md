# 外部 Schema → AI GO 映射表

> 本模板用於 `references/migration-workflow.md` §2.4「外部 Schema → AI GO 架構映射」步驟。
> 每個外部系統的每張表填寫一份。
> ⚠️ **使用者／認證表不進本流程**——它們走 `project_deconstruction_template.md`
> 的認證映射（建成自建表是規則 23 禁止的反模式）。

## 系統資訊

| 項目 | 值 |
|------|---|
| 系統名稱 | |
| DB 類型 | （Supabase / Google Sheet / MySQL / Airtable / ...） |
| 對應 AI GO App | |
| app_domain | |

## 表映射

### 外部表：`[表名]` → AI GO：`[預設表名 or 自建表實體名]`

**對照項（★ 每張表必填；走自建表時「已對照」「理由」不得為空）**

| 對照項 | 值 |
|------|---|
| 這張表用業務語言說是什麼 | （例：追蹤中的標案＝商機 pipeline；外部表名不是語意） |
| 已對照的預設表（`references/default-table-lookup.md` §2 ＋ `aigo_data.py meta tables --source erp --grep`） | （例：`crm_leads`（商機管理）＋ `crm_stages`） |
| 採用／不採用理由 | （採用；或：不採用——`hr_expenses.employee_id` 必填而報支人非員工） |
| 軌 | 引用／延伸欄位／custom_data／既有自建表加欄／新建自建表 |

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
> - `直接對應`：外部欄位可直接寫入預設表的原生欄位
> - `延伸欄位`：預設表加租戶級正式欄位（EAV；有型別、全租戶可見，
>   但預設表既有 CRUD 不回傳其值——見 data-center.md §10）
> - `custom_data`：放入預設表的 `custom_data` JSONB 欄位（app 私有標記、鬆散擴充）
> - `既有自建表加欄`：重用租戶既有自建表，缺的欄位用加實體欄位補（data-center.md §7）
> - `自建表`：需建立新自建表來存放（租戶級，建表需 system.admin）
> - `不遷移`：系統欄位，AI GO 自動管理

### 無法對應預設表的欄位 → 自建表（★ 上方對照項「已對照的預設表／理由」為空的表不得列在這裡）

| 外部表.欄位 | 說明 | 自建表實體名 | 自建表顯示名 | 欄位實體名 | 欄位顯示名 | 欄位型別 |
|------------|------|----------------|----------------|----------------|----------------|---------|
| | | biz_xxx | | snake_case | | text / number / date / relation |

> **兩個實體名欄不得為空、一律英文**（表 `biz_<英文複數>`、欄位 snake_case）。
> 實體名建立後永不可改，且系統是從顯示名生成的——純中文顯示名會生出 `tbl_2`、`col_7`。
> 建表時用**兩步命名法**（先用英文實體名當 display_name 建、再 PATCH 改回中文）：
> SKILL.md 規則 18.5、`references/data-center.md` §1。
> 外部欄位名是中文時，這張對照表就是「中文欄位名 → AI GO 英文實體名」的 SSOT，
> 匯入程式的欄位映射一律回查這裡。

### 外鍵關係

| 外部 FK 欄位 | 外部目標表 | AI GO 處理方式 | 備註 |
|-------------|-----------|---------------|------|
| orders.customer_id | customers | 預設表原生 customer_id 欄位 | |
| tasks.project_id | projects | custom_data.project_id | 需在程式碼中維護參照 |

## 資料遷移摘要

| 項目 | 值 |
|------|---|
| 遷移範圍 | 全量 / 部分 / 僅結構 |
| 預估筆數 | |
| 遷移方式 | Server Action 批次 / API 逐筆 |
| ID 轉換 | 需要 / 不需要 |
| 遷入順序 | （在有 FK 時填寫：先匯哪張表） |
