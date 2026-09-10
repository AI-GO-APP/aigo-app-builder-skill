# AI GO 預設表查表（用業務語言找表）

> **用途**：回答分流決策樹的第一問「**平台有沒有同語意的實體？**」（`custom-app-dev-guide.md` §19）。
> 舉證責任在「為什麼不用預設表」——每張想自建的表都要先在這裡與 Meta API 找過一輪、寫下對照結果，
> 才能進計畫（SKILL.md Phase 1.5 第 3 項的**資料承載表**）。
>
> **撰寫規範（★ 本檔與所有引用本檔的文件都適用）**：只用 AI GO 自己的詞——「預設表」「功能區」
> 「表名前綴」「Meta 面／引用面」「歷史欄位名」。不出現任何外部產品名，不用「對應某系統」「血統」
> 「某某式命名」這類指向外部系統的措辭；平台原始碼註解裡若有外部系統名稱，**不得**帶進文件或對話。
> 表的稱謂依 `CONTEXT.md`：只有「預設表／自建表」兩大類。

---

## 0. 什麼時候查、怎麼查

**時機**：Phase 1.5 第 3 項「資料架構設計」逐實體判定時；遷入線在 `migration-workflow.md` §2.4 映射每張外部表時。
新建與遷入用同一套步驟，不因「這是搬進來的」放寬。

**三步**（每個實體都走，結果寫進資料承載表）：

1. **用業務語言在 §2 找候選**——不是拿外部表名硬對，是問「這張表在講什麼」：追蹤中的案件、往來機關、
   協力廠商、里程碑、費用、待辦提醒……§2 依功能區列了使用者會怎麼說、對應哪張預設表、最常被誤建成什麼。
2. **兩個端點分工，缺一不可**（★ 順序與職責都不能換）：
   - **找表、讀語意**用 Meta 面：`uv run --project scripts python scripts/aigo_data.py meta tables --source erp --grep <關鍵字>`
     列出預設表的中文標題與功能區；`meta table <key>` 看欄位的中文 label、select 值域、relation 目標。
   - **判「有沒有這個欄位」一律用引用面**：依 §3 把 key 換成引用面表名，打
     `GET /api/v1/refs/tables/{table_name}/columns`（`custom-app-dev-guide.md` §20.2）。
     Meta 面的 key 與引用面的表名不一定相同（§3）**只是換名的理由之一**；
     真正的理由是下面那條 ⚠️ ——**Meta 面的欄位清單本身就不完整**。
3. **定案並寫下理由**：命中 → Data Reference 軌（缺欄走 §19 欄位級分流——**app 要讀寫的欄位用
   `custom_data` 或改走自建表**，延伸欄位只給 app 不讀的租戶級正式欄位，`data-center.md` §10）；
   沒命中 → 自建表，但資料承載表那一列要寫「已對照 <候選表>，不採用因為 <欄位語意／必填欄／唯讀>」。
   「沒想到有」不是理由，「查過沒有」才是。

⚠️ **Meta 面的 `fields` 是策展白名單，不是欄位全集——絕對不能拿來判定「平台有沒有這個欄位」。**
平台在後端維護一份「哪些欄位要出現在 Workspace 的 grid 與表單」的標注清單，
`GET /meta/tables/{key}` 的 `fields` **就等於那份清單**；實體表有、但清單未列的欄位一律不輸出
（核自平台原始碼 `erp_field_annotations.py` 檔頭與 `meta_registry._reflect_fields`，2026-09-10）。
清單的內容是 2026-07 一次性從舊前端快照機械遷移來的，**逐表落差隨機**：

| 表 | Meta 面 fields | 引用面 columns | 缺了什麼 |
|---|---|---|---|
| `hr_employees` | 20 | 42 | `registered_address`（戶籍地址）、`contact_address`（通訊地址）、`private_zip`、`passport_id`、`emergency_contact`、`work_location_id`… |
| `customers`（Meta key `crm_clients`） | 含地址欄 | — | 同樣的地址欄在這張表**有**標注 |

所以「別的表 Meta 有這個欄位」推不出「這張表沒有」，反之亦然。集合關係恆為
**Meta 面 ⊆ 引用面**，判定站在引用面永遠安全。依 Meta 面判「沒有 → 自建表」會系統性地
把該走 Data Reference 的實體推去自建（issue #70）。

⚠️ `GET /api/v1/refs/available-tables` 回的 `comment` **實務上是空的**（平台的業務表沒有宣告表註解），
359 張純表名不能當語意來源——**標題**要從 Meta API 拿，本檔 §2 是它的業務語言索引。
（只有標題；欄位仍以引用面為準，見上一條。）

---

## 1. 表名讀法：功能區前綴

AI GO 預設表的命名慣例是 **`<功能區前綴>_<實體複數>`**。看懂前綴就能把 359 張表分到功能區，
不需要任何外部參照：

| 前綴 | 功能區（Meta 的 `section_path` 第一層） | 例子 |
|------|----------------------------------------|------|
| `crm_` | CRM 客戶關係 | `crm_leads` 商機、`crm_stages` 銷售階段、`crm_activities` 活動排程 |
| `customer_` | CRM 客戶關係（往來對象本體） | `customers` 客戶、`customer_contacts` 聯絡人、`customer_tags` 客戶標籤 |
| `utm_` | CRM 客戶關係／設定（行銷追蹤） | `utm_campaigns`、`utm_sources`、`utm_mediums` |
| `sale_` | 銷售管理 | `sale_orders`、`sale_order_lines`、`sale_order_templates` 報價範本 |
| `product_` | 銷售管理／產品 | `product_templates` 產品、`product_categories`、`product_supplierinfo` 供應商價格 |
| `purchase_` | 採購管理 | `purchase_orders`、`purchase_order_lines`、`purchase_requisitions` 採購請求 |
| `supplier` | 採購管理（往來對象本體） | `suppliers`、`supplier_contacts` |
| `stock_`／`inventory_` | 庫存／倉儲 | `stock_pickings` 調撥揀貨、`stock_lots` 批號、`inventory_check_batches` 盤點 |
| `mrp_` | 製造 MRP | `mrp_productions` 生產訂單、`mrp_boms`、`mrp_workcenters` |
| `account_`／`analytic_` | 會計財務 | `account_moves` 發票／帳單／傳票同一張表、`account_payments`、`analytic_accounts` |
| `project_` | 專案管理 | `project_projects`、`project_tasks`、`project_milestones`、`project_updates` |
| `hr_` | 人力資源 | `hr_employees`、`hr_expenses`、`hr_leaves`、`hr_timesheets` |
| `msg_` | 訊息（平台通訊渠道） | `msg_threads`、`msg_messages`、`msg_contacts` |

**兩個命名面**：平台對同一張預設表有兩套 key——

- **Meta 面**（`/api/v1/data-center/meta/tables/{key}`、延伸欄位端點的 `{erpKey}`）：key 依功能區分組，
  例如 `crm_clients`、`purchase_suppliers`、`accounting_invoices`。約 85 張，有中文標題與欄位 label。
  ⚠️ 它的 `fields` 是**表現層策展白名單**（Workspace grid／表單），比實體表少欄是常態——
  只能用來讀語意（標題、label、值域），**不能用來判欄位有無**（§0 的 ⚠️）。
- **引用面**（`/api/v1/refs/*`、Open Proxy、`ctx.db`／`db.ts`）：key 就是實體表名，例如 `customers`、
  `suppliers`、`account_moves`。359 張，含子表與明細表。
  **這一面才是欄位的權威**：`GET /refs/tables/{t}/columns` 回的是實體表全欄，也正是 app 執行期
  `ctx.db.query` 撈到的 key 集合（實測 `hr_employees` 兩邊皆 42）。

多數表兩面同名（`crm_leads`、`sale_orders`、`project_tasks`、`hr_employees`…）；不同名的列在 §3。
**Meta 回 404 不代表表不存在**——可能只是這張表不在 Meta 的 85 張裡（例如 `hr_expenses`、`customer_contacts`），
改打引用面的 columns 端點。

---

## 2. 業務概念 → 預設表速查

依功能區排列。「常被誤建成」欄是遷入與新建時最常見的自建表名，看到自己正要建這種表就回頭查。
表名一律寫**引用面表名**（Meta 標題放括號內，方便 `--grep`）。

### CRM 客戶關係

| 使用者會怎麼說 | 預設表（Meta 標題） | 常被誤建成 | 備註 |
|---------------|-------------------|-----------|------|
| 追蹤中的案件、標案、商機、pipeline、看板上的卡 | `crm_leads`（商機管理） | `tenders`、`opportunities`、`pipeline`、`cases` | 只有 `name` 必填；`stage_id`／`customer_id`／`user_id` 都可空，自動建立不會被卡。`type` ∈ lead／opportunity，`priority` 是字串 '0'–'3' |
| 案件的階段、看板欄位、狀態流 | `crm_stages`（銷售階段） | `statuses`、`stages` | 每個租戶自訂；不要在自建表放 `status` 字串重做一套看板 |
| 失單、流標、未得標原因 | `crm_lost_reasons`（遺失原因） | `lost_reasons` | 商機的 `lost_reason_id` 指向它 |
| 案件上的標籤、分類 | `crm_tags`（標籤管理） | `tags`、`categories` | 商機用 `tag_ids` JSON 陣列存 |
| 提醒、待辦、下次聯繫、截止日追蹤 | `crm_activities`（活動排程） | `reminders`、`todos`、`follow_ups` | `summary` 必填；`activity_type` ∈ email／call／meeting／todo；掛在 `lead_id` 上 |
| 往來機關、客戶、公司、個人、評審委員、合作對象 | `customers`（客戶管理；Meta key `crm_clients`） | `agencies`、`organizations`、`committees`、`partners` | `customer_type` 必填 ∈ company／individual；同時填 `is_company` |
| 機關窗口、聯絡人 | `customer_contacts`（不在 Meta） | `contacts` | `customer_id`、`name` 必填 |
| 客戶分群、等級、VIP | `customer_levels`（等級管理）、`customer_tags`（客戶標籤） | `levels`、`vip_flags` | |
| 業務團隊、負責小組 | `crm_teams`（銷售團隊） | `teams` | |
| 行銷來源、活動、媒介 | `utm_campaigns`／`utm_sources`／`utm_mediums` | `sources`、`channels` | |

### 專案管理

| 使用者會怎麼說 | 預設表（Meta 標題） | 常被誤建成 | 備註 |
|---------------|-------------------|-----------|------|
| 得標後的專案、合約執行、工程案 | `project_projects`（所有專案） | `projects`、`contracts`、`engagements` | `name` 必填 |
| 里程碑、交付節點、驗收點 | `project_milestones`（里程碑） | `milestones`、`deliverables`、`checkpoints` | `name`、`project_id` 必填 |
| 工作項、任務、待辦、使用者回饋要處理的事 | `project_tasks`（任務） | `tasks`、`tickets`、`feedback`、`issues` | `name` 必填；階段用 `project_task_types` |
| 進度報告、週報、結案報告、專案更新 | `project_updates`（專案更新） | `reports`、`status_updates`、`closing_reports` | `name` 必填；長文放 description |
| 專案階段、任務階段 | `project_project_stages`（專案階段；Meta key `project_stages`）、`project_task_types`（任務階段） | `phases` | |
| 專案標籤 | `project_tags`（專案標籤） | | |

### 銷售、採購、往來廠商

| 使用者會怎麼說 | 預設表（Meta 標題） | 常被誤建成 | 備註 |
|---------------|-------------------|-----------|------|
| 報價、訂單、成交 | `sale_orders`（銷售訂單）＋ `sale_order_lines` | `quotes`、`orders`、`deals` | `date_order` 必填；`state` 值域見 §4 |
| 報價範本 | `sale_order_templates`（報價範本） | `quote_templates` | |
| 產品、服務項目、品項、價目 | `product_templates`（產品列表；Meta key `sale_products`）＋ `product_categories` | `products`、`services`、`items`、`price_list` | `name` 必填；`type` ∈ consu／service／combo |
| 協力廠商、供應商、外包商 | `suppliers`（供應商管理；Meta key `purchase_suppliers`）＋ `supplier_contacts` | `vendors`、`subcontractors` | `name` 必填；`supplier_type` 有預設值 company |
| 採購單、請購、下單給廠商 | `purchase_orders`（採購訂單）＋ `purchase_order_lines`、`purchase_requisitions`（採購請求） | `purchases`、`po` | `date_order` 必填；`purchase_order_lines.order_id` 必填；`state` ∈ draft／sent／purchase／done／cancel |
| 廠商報價、供應商價格 | `product_supplierinfo`（供應商價格；Meta key `purchase_supplierinfo`） | `vendor_prices` | `supplier_id`、`price` 必填 |

### 會計財務、費用

| 使用者會怎麼說 | 預設表（Meta 標題） | 常被誤建成 | 備註 |
|---------------|-------------------|-----------|------|
| 發票、帳單、傳票、折讓、分錄 | `account_moves`（銷項發票／進項帳單／傳票管理／折讓…**同一張實體表**，Meta 依 `move_type` 拆成多個 key） | `invoices`、`bills` | 引用面只有一張 `account_moves`；明細在 `account_move_lines` |
| 收款、付款 | `account_payments`（客戶收款／供應商付款） | `payments`、`receipts` | `payment_type` 必填 ∈ inbound／outbound；`amount`、`date` 必填 |
| 員工報支的費用、差旅、代墊 | `hr_expenses`（不在 Meta）＋ `hr_expense_sheets`（費用報告） | `expenses`、`reimbursements` | ⚠️ `hr_expenses.employee_id` **必填**——報支人不是員工（外部使用者、機關）時整張表不可用 |
| 專案成本歸集、成本中心 | `analytic_accounts`（分析帳戶） | `cost_centers`、`budgets` | `name` 必填 |
| 專案費用明細（非員工報支） | **沒有可寫的預設表** | `project_expenses` | `analytic_lines`（分析明細）是**平台獨寫**的表，app 寫不了（§4）；`hr_expenses` 又要員工。這種情境自建表是正解——資料承載表寫明「已對照 `hr_expenses`／`analytic_lines`，前者要員工、後者唯讀」 |
| 付款條件、稅率、會計科目、幣別 | `account_payment_terms`、`account_taxes`、`account_accounts`（唯讀）、`currencies`（全域唯讀） | | 設定類，通常只讀不寫 |

### 人力資源

| 使用者會怎麼說 | 預設表（Meta 標題） | 常被誤建成 | 備註 |
|---------------|-------------------|-----------|------|
| 員工、同仁、部門 | `hr_employees`（員工列表）、`hr_departments`（部門） | `staff`、`members`、`teams` | 身分與登入沿用平台 `users`（規則 23），員工主檔才是 `hr_employees` |
| 請假、出勤、加班 | `hr_leaves`、`hr_leave_allocations`、`hr_attendances`、`hr_overtime_requests` | `leave_requests`、`attendance_logs` | `hr_leaves.state` 值域見 §4 |
| 工時、填報 | `hr_timesheets`（工時紀錄）、`hr_work_entries` | `time_logs` | `date` 必填 |
| 技能、證照 | `hr_skills`（技能管理）、`hr_employee_skills` | `certifications` | |
| 薪資 | `hr_payroll_*` | `payroll_settings`（demo 租戶實例） | 平台已有 `hr_payroll_settings`；薪資明細與合約表**不可引用**（黑名單） |

### 庫存、製造

| 使用者會怎麼說 | 預設表（Meta 標題） | 常被誤建成 | 備註 |
|---------------|-------------------|-----------|------|
| 出入庫、調撥、揀貨 | `stock_pickings`（調撥/揀貨單） | `shipments`、`transfers` | 明細 `stock_moves` **平台獨寫**——app 建的單要在平台模組介面補明細才能 validate（`platform-behaviors.md` §4.3） |
| 即時庫存、批號、倉庫 | `stock_quants`（唯讀）、`stock_lots`、`stock_warehouses` | `inventory` | |
| 盤點、規格轉換 | `inventory_check_batches`（盤點紀錄；Meta key `stock_checks`）、`inventory_converts`（Meta key `stock_converts`） | `stock_counts` | |
| 生產、工單、BOM | `mrp_productions`、`mrp_workorders`（唯讀）、`mrp_boms` | `work_orders` | |

### 訊息與通知

| 使用者會怎麼說 | 預設表 | 常被誤建成 | 備註 |
|---------------|-------|-----------|------|
| 對話、訊息、客服紀錄、LINE／Email 往來 | `msg_threads`、`msg_messages`、`msg_contacts`（不在 Meta） | `conversations`、`messages`、`email_logs`（demo 租戶實例） | `msg_messages` 必填 `thread_id`、`direction`、`sender_type`、`content`；綁通訊渠道的 app 才會自然落在這裡 |
| 系統通知 | `notifications`、`announcements` | `alerts` | 引用前查 columns 確認欄位夠用 |

---

## 3. Meta 面 key ↔ 引用面表名對照（只列不一致的）

核自平台 Meta 標注與 model 表名（2026-09-09）。查欄位、引用、Open Proxy 一律用右欄。

| Meta key | 引用面表名 | 備註 |
|----------|-----------|------|
| `crm_clients` | `customers` | 最常撞到的一組 |
| `crm_customer_levels`／`crm_customer_tags` | `customer_levels`／`customer_tags` | |
| `crm_utm_campaigns`／`crm_utm_sources`／`crm_utm_mediums` | `utm_campaigns`／`utm_sources`／`utm_mediums` | |
| `crm_partner_banks` | `partner_banks` | 租戶欄位是歷史欄位名 `company_id`（dev-guide §20.3） |
| `sale_products`／`sale_product_categories` | `product_templates`／`product_categories` | |
| `purchase_suppliers`／`purchase_supplierinfo` | `suppliers`／`product_supplierinfo` | |
| `stock_checks`／`stock_converts` | `inventory_check_batches`／`inventory_converts` | |
| `stock_orderpoints` | `stock_warehouse_orderpoints` | |
| `stock_packaging` | `stock_package_types`（以 columns 端點實查為準） | |
| `stock_freight_groups` | `freight_groups` | |
| `accounting_invoices`／`_bills`／`_vouchers`／`_credit_notes`／`_refunds`／`_journal_entries` | **全部是 `account_moves`** | Meta 依單據型別拆 key，實體表只有一張 |
| `accounting_payments_inbound`／`_outbound` | `account_payments` | 以 `payment_type` 區分 |
| `accounting_voucher_templates` | `account_move_templates` | |
| `accounting_fixed_assets`／`_inventory_valuations`／`_bank_statements` | `fixed_assets`／`inventory_valuations`／`account_bank_statements` | |
| `accounting_analytic_plans`／`_accounts`／`_lines` | `analytic_plans`／`analytic_accounts`／`analytic_lines` | `analytic_lines` 唯讀 |
| `accounting_accounts`／`_journals`／`_taxes`／`_payment_terms`／`_incoterms`／`_fiscal_years`／`_fiscal_positions` | 把 `accounting_` 換成 `account_` | `account_accounts` 全域唯讀 |
| `project_stages` | `project_project_stages` | |
| `users` | `users` | Meta 可讀、**引用面黑名單**（不可引用）；要關聯使用者見 `data-center.md` §9 |

**只在引用面、Meta 查不到的常用表**（Meta 404 是正常的）：`customer_contacts`、`supplier_contacts`、
`sale_order_lines`、`purchase_order_lines`、`account_move_lines`、`hr_expenses`、`hr_overtime_requests`、
`msg_*`、`notifications`、`announcements`、`stock_locations`、`stock_move_lines`。

**Meta 可讀但不可引用**（黑名單）：`users`、`hr_payroll_contracts`／`hr_payroll_slips`／`hr_salary_items`、
`utm_stages`／`utm_tags`、`roles`、`members`。

---

## 4. 常用表的必填欄與唯讀表

**必填欄**（核自 model：`nullable=False` 且無預設值，不含系統欄；2026-09-09）——寫入 payload 缺這些會 500／422：

| 表 | 必填欄 | 備註 |
|----|--------|------|
| `customers` | `name`、`customer_type` | `customer_type` ∈ company／individual；`is_company` 對應填 |
| `customer_contacts` | `customer_id`、`name` | |
| `suppliers` | `name` | `supplier_type` 有預設 company |
| `supplier_contacts` | `supplier_id`、`name` | |
| `crm_leads` | `name` | 其餘全可空 |
| `crm_activities` | `summary` | |
| `crm_stages`／`crm_tags`／`crm_lost_reasons` | `name` | |
| `project_projects`／`project_tasks`／`project_updates`／`project_tags` | `name` | |
| `project_milestones` | `name`、`project_id` | |
| `analytic_accounts` | `name` | |
| `hr_expenses` | `name`、`date`、**`employee_id`** | 沒有員工實體就不能用 |
| `hr_expense_sheets`／`hr_employees`／`hr_departments` | `name` | |
| `hr_timesheets` | `date` | |
| `sale_orders`／`purchase_orders` | `date_order` | |
| `sale_order_lines`／`purchase_order_lines` | `order_id` | |
| `product_templates` | `name` | |
| `product_supplierinfo` | `supplier_id`、`price` | |
| `account_payments` | `payment_type`、`amount`、`date` | |
| `msg_messages` | `thread_id`、`direction`、`sender_type`、`content` | |

CHECK 值域（`state`、`type`、`priority` 等）見 `custom-app-dev-guide.md` §20.2.1，或 `aigo_data.py meta table <key>`。
兩份都沒有的欄位，先查 Meta 再寫，不要對正式租戶試寫。

**唯讀表（app 寫入 403，規劃時當作「只能讀」）**：

| 類型 | 表 |
|------|----|
| 平台獨寫（由平台流程產生） | `stock_moves`、`stock_quants`、`mrp_workorders`、`analytic_lines`、`ir_sequences`、`currency_rates` |
| 全域參考資料（全租戶共用） | `account_accounts`、`countries`、`country_states`、`currencies`、`languages`、`uom_uom`、`uom_categories` |

---

## 5. 遷入常見誤判（第一版計畫 vs 對照後）

來自 2026-09-09 一個 46 張表的遷入案（issue #53）：第一版把 38–42 張判成自建表，對照後是 **13 張自建表＋11 張預設表引用**。
差距不是邊角，是三倍——每一列都是「沒用業務語言查」的結果。

| 原系統實體 | 第一版 | 對照後 | 誤判原因 |
|-----------|--------|--------|---------|
| 追蹤中的標案（pipeline、截止日、看板） | 自建表 | `crm_leads`＋`crm_stages`＋`crm_activities`＋`crm_tags`＋`crm_lost_reasons` | 表名叫 tenders，沒想到「案件追蹤」就是商機 |
| 機關、評審委員 | 自建表 ×2 | `customers`（company／individual）＋`customer_tags` | 以為 customers 只放「付錢的客戶」 |
| 得標後專案、里程碑、交付物、結案報告 | 自建表 ×4 | `project_projects`／`project_milestones`／`project_tasks`／`project_updates` | 沒查 `project_` 前綴下有四張表 |
| 使用者回饋 | 自建表 | `project_tasks` | 回饋是要處理的工作項 |
| 專案費用（報支人不是員工） | 自建表 | **仍是自建表，但要寫理由** | 對照 `hr_expenses`（要 `employee_id`）與 `analytic_lines`（平台獨寫）後排除——這是「查過沒有」的正例 |
| 同實體重複表（`tenders`／`tender_records`、`documents`／`tender_documents`、`proposal_*`／`report_*`） | 各一張 | 合併 | 原系統的歷史包袱不要原樣搬 |

另兩個常見型：**外部系統的 `users` 表**建成自建表（規則 23 禁止；走 `project_deconstruction_template.md` 認證映射）；
**與預設表同名的自建表**（demo 租戶有 `purchase_orders`、`messages`、`conversations`、`payroll_settings`）——建表當下就該被 §0 第三步擋下。

---

## 6. 維護方式

- **§2 與 §3 的來源**：Meta API（`aigo_data.py meta tables --source erp` 全列；標題與功能區就是 Meta 的 `title`／`section_path`）
  ＋ 引用面表名（`GET /api/v1/refs/available-tables` 或 columns 端點實查）。平台新增功能區時補列，
  不要憑印象加表——每一列都要能用 `meta table <key>` 或 columns 端點打到。
- **§4 的來源**：平台 model 的 `nullable=False`／CheckConstraint；引用面 columns 端點的 `nullable` 可實查驗證。
  issue 或實測給的必填欄，先對回 columns 端點再收錄。
- **§5**：每次遷入案結案後，把「第一版 vs 對照後」有落差的列補進來。
- 改本檔時同步檢查：`SKILL.md` 規則 18 與 Phase 1.5 第 3 項、`custom-app-dev-guide.md` §19／§20.1、
  `migration-workflow.md` §2.4、`resources/migration_mapping_template.md` 的資料承載表欄位是否仍一致。
