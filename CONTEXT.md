# CONTEXT — AI GO Custom App 開發術語

本檔是**術語表**，不是規格書。實作細節在 `references/` 底下。

---

## 資料承載體：六個詞，別混用

> 分流決策的 SSOT 在 `references/custom-app-dev-guide.md` §19；本節只管「詞是什麼」。

**平台的表只有兩大類：預設表與自建表。** 其餘四個詞（CustomObject、Data Reference、
延伸欄位、app_domain）是機制或標籤，不是第三類表。

### 預設表（platform default tables）

AI GO **預先定義**的中小企業通用資料表（專案、客戶、銷售、會計…），兩大類之一。
表本體 schema 由平台管理，**租戶與 app 都不可改**；app 要用它，走 Data Reference 引用。

**稱謂對照（★ 只有「預設表」是對用戶的正式稱謂）**：

| 場合 | 叫法 |
|------|------|
| 對用戶溝通、本 skill 全部文件 | **預設表** |
| 平台原始碼與 API 參數 | `erp` 字樣（`erp_table_key`、`{erpKey}`、ERP 表）——內部命名，沿用即可，別拿來對用戶說 |
| Builder 引用面板 UI | 「現有模組引用」「現有資料表」 |
| 本 skill 舊版文件 | 「SaaS 表」——**已停用**，看到即為過時文件 |

### 自建表（custom table）

綁 **tenant** 的**真實 Postgres 表**。同一租戶下所有 custom app、以及租戶自己的資料中心 UI
看到的是同一批表、同一份資料——**跨 app 天然共用**。

- 每張表與每個欄位有兩個名字：**顯示名**（可改，中文常見）與**實體名**（建立後永不可變，純 ASCII）。
  所有 API 一律用實體名指涉。
- 系統欄位 `id` / `created_at` / `updated_at` 自動帶，不可刪、不計配額。
- **改結構需 `system.admin`**；讀結構與記錄 CRUD 只需 `builder.access`。

因為是租戶級共用，「建表前先盤點有沒有可重用的既有表」是紀律而非建議——
同一張「客戶」表不該因為兩個 app 各建一次而分裂成兩份資料。

### CustomObject（前代，已退場）

綁 **app** 的舊模型，資料存在 JSONB 裡、**沒有真實資料表**。每個 app 各自擁有一組互不相通的表。

**它不等於自建表。** 目前狀態：builder 工具面已退場、後台「資料」tab 已隱藏；
SDK 雙軌並存所以存量 app 不會壞；舊模型與端點尚未移除。

**新功能一律只接自建表，不要再往 CustomObject 加東西。**

辨識方式：VFS 裡 `src/data.json` 有內容、code 用 `listRecords` / `submitRecord` /
`ctx.db.query_object` → 那是 legacy。

### Data Reference

把**既有的預設表**授權給某個 app 引用，授權後由 Runtime 在執行期注入 schema。
盤點引用狀態一律用 `GET /api/v1/refs/apps/{app_id}`——VFS 裡的 `src/db.json` 實測恆為 `{}`。

**它不是新建的表**——是對平台既有表的引用授權。
加入引用可在 Builder 後台操作，也可用 API：`POST /api/v1/refs/apps/{app_id}`
（只需 `builder.access`，body 為 `{table_name, columns[], permissions[]}`）。

### 延伸欄位（ERP ext field）

幫 **預設表**加的**租戶級正式欄位**（2026-08 起）。表本體 schema 不可改，
延伸欄位是 **EAV overlay**：定義與值存在獨立表，與自建表同一套 9 型別與欄數配額。

**它不是實體欄位，也不是 `custom_data`。** 三者的分工：原生欄位永遠優先；
延伸欄位給「要型別、全租戶可見可管理」的正式欄位；`custom_data` 給 app 私有標記與鬆散擴充。

⚠️ 最大陷阱：**預設表既有 CRUD（`ctx.db`／`db.ts`）不回傳延伸欄位的值**——
讀寫走獨立的 `ext-fields`／`ext-values` 端點（`references/data-center.md` §10）。

### app_domain

寫進預設表 `custom_data` JSONB 的**來源標籤**，讓多個 app 共用同一張預設表時能區分資料來源。

**只屬於 Data Reference 那一軌。** 自建表沒有 `custom_data` 欄位，而且「跨 app 共用」正是
自建表的設計目的——拿 `app_domain` 去標記自建表資料是反模式。

---

## 事件觸發：兩個來源，同一條管線

### Webhook

外部系統打進來的事件。在 `actions/manifest.json` 用 `"webhook": true` 宣告，
每個宣告的 action 各得一條獨立對外端點。

### App 排程（App Cron）

平台時鐘按表觸發。排程是**後台 DB 的一列**，不在 VFS 裡，與 app 的發布生命週期脫鉤。

### 兩者的共同語義

它們走**同一個 dispatcher、同一套投遞保證**：**at-least-once**。
事件保證至少執行一次，代價是**可能重複執行**。

因此 **webhook action 與 cron action 都必須冪等**。這不是最佳實務，是硬需求。

---

## App 模式

- **access_mode**：`internal`（組織內部）／`external`（對外客戶）／
  `self_built`（第三方自建應用，走 API Key 存取 Proxy）
- **匿名存取**：功能旗標（`allow_anonymous_access` + `is_public_readable`），走 `/pub/*` 端點。
  **不是 access_mode 的一種**，而且**只有 `external` / `self_built` 可以啟用**——
  `internal` app 開匿名存取回 400。
