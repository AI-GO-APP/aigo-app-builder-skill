# 需求盤點與實作計畫（Phase 1.5 的完整版）

> `SKILL.md` Phase 1.5 只留強制性、四問標題、四張表清單與閘門條列；本檔是逐項展開。
> 新建情景的起手是 §1.0 四問；遷入情景的對稱起手在 `migration-workflow.md` §2.0。

## 目錄

- §1.0 需求盤點：四問與產出的需求形狀結論
- 計畫內容必須包含：第 1 項需求分析 → 第 1.5 項產品線與模式 → 第 1.7 項授權架構 → 第 3 項資料承載表 → 第 4.x 項外部整合
- 計畫閘門：五條，缺一不得進 Phase 2

---

### 1.0 需求盤點（★ 新建情景的起手，對稱遷入線的 §2.0）

遷入線靠 `migration-workflow.md` §2.0 把系統的 stack 形狀盤出來再分流；新建線沒有 repo
可盤，**輸入只能來自用戶，所以要主動問**。用戶開場的一句話（「幫我做個報修系統」）
**是題目，不是需求**——拿題目直接寫計畫、再拿計畫過閘門，等於讓用戶替你補作業。

- **資訊不足就問，不猜**；用戶答不出來就給選項（下表右欄），不要替他選
- 一輪把四問問完（不要一題一題擠牙膏），但**四問缺一不進 1.5**
- 已在對話中明確講過的不重問；遷入情景這四問由 §2.0 盤點推導，不另問
- **常見情況幾句話就答完**（內部成員用、沒有對外、沒命中邊界 → 一個 Custom App）——
  問是為了確認沒有例外，不是把簡單需求問成專案訪談

| # | 問什麼 | 為什麼非問不可 | 用戶答不出時給的選項 |
|---|---|---|---|
| 一 | **誰在用**——列出**使用者群**（哪些部門的員工、外部經銷商、客戶、夥伴…），以及有沒有**不登入就要能看**的頁 | 使用者群餵第 1.7 項授權架構（每群一個角色、每支 app 一份角色白名單）；**凡有登入者一律 internal**，內外人員都是租戶成員，不因「有外部人」改模式；只有匿名頁才影響產品線（問題三） | 「只有員工」／「員工＋外部經銷商（或客戶）」／「還有不登入就要看的頁」 |
| 二 | **做什麼**——功能清單、每個功能的使用場景與使用者流程、涉及哪些資料實體 | 計畫第 1 項全部來自這裡；資料實體清單餵第 3 項的雙軌分流 | 請用戶用「誰、在什麼時候、要完成什麼」各講一句 |
| 三 | **對外面向**——需不需要自有網域、SEO、讓匿名訪客瀏覽整站？ | 公開 web 資產 → Hosted App；Custom App 的 `/runtime`＋HashRouter 做不了 SEO 與自有網域，`/pub` 只適合少數公開頁 | 「純內部、登入後才能用」／「有幾頁不登入也要看」／「整個站要對外、要自己的網址」 |
| 四 | **機制需求**——逐條核對 `references/product-line-decision.md` §2 的 **Custom App 能力邊界表** | 命中的每一條是 Hosted 訊號或要改設計；**留到寫 code 才發現＝整段白做** | 把邊界表拿給用戶逐條勾 |

另外順帶盤（不決定產品線，計畫第 4.5–4.7 項要用）：第三方 API、外部 webhook、定時工作、檔案上傳。

**產出：需求形狀結論**（照 `resources/new_app_requirements_template.md` 填，帶進 1.5）：

```
使用者群：<群名清單>（有登入者 → internal；匿名頁 → 見面向）
面向：應用介面 / 公開 web 資產 / 混合（→ 拆）
邊界命中：<條目，每條標「Hosted」或「改設計」>；或「無」
功能群：<群名 → 功能清單>（2 群以上不同目的 → 第 2 項拆分）
資料實體：<清單>
外部整合：API <slug 清單> / webhook <來源> / 排程 <頻率> / 檔案 <有無>
```

### 計畫內容必須包含

1. **需求分析**（新建：由 §1.0 問題二的答案整理；遷入：由 §2.0／§2.2 盤點整理）
   - 用戶要實現的功能清單
   - 每個功能的目標使用場景
   - 預期的使用者流程

1.5. **產品線與模式判斷**（Custom App vs Hosted App；登入者一律 internal；★ 結果不可逆）
   - **SSOT 在 `references/product-line-decision.md`**，兩條路共用——判斷前讀它
   - **預設立場：一個 Custom App `starter-internal`**。新建 app 絕大多數就是這個答案；只有命中訊號才偏離：
     功能群目的不同 → 多個 Custom App；
     公開 web 資產（自有網域／SEO／整站匿名）→ Hosted App；邊界表命中「Hosted」→ Hosted 或**混合**
     （業務介面 Custom ＋ 命中的部分獨立 Hosted，共用資料落平台側、Hosted 走 Open Proxy）
   - **使用者有內有外不改模式、不拆模式**：員工與外部經銷商／客戶都是租戶成員，差別在角色與
     app 角色白名單（第 1.7 項）；要拆也是拆成兩支 internal app 各掛不同 `access_role_ids`
   - **兩問定位，先問有沒有登入者、再看形狀**：問題一「有登入者嗎、誰是匿名的」——有登入者 → internal，
     只有匿名 → Hosted public，兩者都有 → 拆（新建取 §1.0 問題一；遷入問原系統）；
     問題二「形狀」定 Custom／Hosted／混合
     （新建取 §1.0 的面向＋邊界命中；遷入取 §2.0 的 stack 形狀，對照表在 `migration-workflow.md` §2.1）
   - **不可逆與硬前提**：`access_mode` 由模板決定、建立後不可改 → **app 等本計畫確認後才建**；
     `internal` 不能開匿名（400）→「內部工具想給訪客看一頁」要在此刻攤開：拆成 Hosted public 靜態頁，
     拆不成才落到 `starter-external` 這個例外，且匿名**還要平台核可、無 SLA**（dev-guide §15.1）
     → 排程時列成「等平台」的一步；拿不準 Custom vs Hosted 給 `hosted-apps.md` §1 差異表選，
     拿不準有沒有匿名頁回頭問，**不可用預設值帶過**
   - **Hosted 當 Custom 的後端**（常駐進程接在 Custom 介面後面）→ Hosted 設 `public` ＋ 自驗簽章，
     `internal` 的 proxy 會把 Server Action 的呼叫導去登入（`product-line-decision.md` §5）
   - 判走 Hosted App 的 app → `references/hosted-apps.md`，不走本 skill 的 Phase 2–4；
     「Hosted = 整套搬」指程式不指資料，業務資料一律落平台的表（`hosted-apps.md` §7.1）；
     **部署前必過 `hosted-apps.md` §3.0 的 `always_on` 決策閘**（下一項）
   - **常駐（`always_on`）兩條線都要有結論，預設都是 `false`**——Hosted 過 `hosted-apps.md` §3.0 三問；
     **Custom App 過 `custom-app-dev-guide.md` §28.1，而且答案幾乎一律是「關」**：action 是 request/response，
     沒有「容器內排程」與「長連線」兩題，只剩冷啟動等待，**不必主動問 owner**——除非命中即時互動訊號
     （現場等待：櫃檯、掃碼、來電查詢、客戶在線上等回覆，或需求寫明「幾秒內要出結果」）才問那一題；
     「第一發慢」本身不是理由，純排程／批次／webhook app 一律關
   - **產出：app 分配表**（每個 app 一列，寫進計畫、確認後照表建 app）
     `| alias | 產品線 | 模式（模板 slug / visibility） | 負責的功能群 | 拆分理由 |`
     ——預設情況就是一列 `| <alias> | Custom | starter-internal | 全部 | —；常駐＝關（預設） |`
     ——**每一列**都在拆分理由欄後附常駐決策：`常駐＝關（預設）`，或 `常駐＝開；理由 X；退場條件 Y`
     （問答填在需求盤點表 §四.1：Hosted 填 §四.1-A、Custom 填 §四.1-B；Hosted 另有 §3.4 部署後讀回核對）

1.7. **授權架構選型**（★ 強制；SSOT 在 `references/member-admin.md` §1，兩條路共用）
   - **立場**：AI GO 帳號體系是內外人員共用的——凡要登入的人都是租戶成員，用**角色**分「能做什麼」、
     用 app 的 **`access_role_ids`** 分「看得到哪支 app」。不在 app 內另建使用者表、角色表、登入流程
   - **三問**：① 使用者群有哪些 → 每群一個角色（沿用或新開，新開的 permissions 必須是建立者權限的子集）；
     ② 每支 app 誰能開 → `access_role_ids`（空＝全租戶成員；Custom 與 Hosted 都有此欄）；
     ③ 人怎麼進來 → 已是成員／邀請（一人一連結、落點直達 app）／既有系統搬遷（`member-admin.md` §7）
   - **要攤開的陷阱**：非員工帳號沒有員工列，租戶資料存取規則用到 `$user.employee_id` 類欄位會對他們
     整列 deny；Hosted internal app 內**拿不到任何身分**（連使用者 id 都沒有，2026-09-09 實打），
     角色分流只能在門口做，要在畫面內分流就得換 Custom internal app；
     外部人員角色的 permissions 從空集合起步，`system.*`／`hr.*`／`accounting.*` 不給
   - **產出：授權架構表**（與 app 分配表並列寫進計畫；確認後照表建角色、設白名單、發邀請）
     `| app（alias） | 模式 | access_role_ids（角色名） | 角色 → permissions（新開／沿用） | 進入方式／邀請落點 |`
     ——預設情況就是一列 `| <alias> | starter-internal | （空＝全租戶成員） | 沿用既有角色 | 已是成員 |`

2. **場景拆分與 App 邊界建議**
   - 出現任一情況就**必須建議拆成多個 app**：
     - (a) 需求涵蓋 2 群以上不同功能與目的——「客戶管理」和「財務報表」→ 2 個 Custom App
     - (b) 登入後的系統＋不登入就要看的頁——匿名部分 → Hosted public、登入部分 → internal
     - (c) 部分功能命中 Hosted 邊界——Custom + Hosted 混合，分工見 `product-line-decision.md` §5
   - **使用者有內有外不是拆分理由**：同一支 internal app 用角色分流；真要分開也是兩支 internal app
     各掛不同 `access_role_ids`（第 1.7 項），不是拆成兩種模式
   - 拆出來的每個 app **各自過 1.5 的兩問、各自定模式與授權架構**，不是複製同一個答案
   - 每個 Custom App 的 `app_domain` 標籤建議值
   - **拆出來的每個 app（Custom 或 Hosted）都要進工作區登錄表**：建好後
     `aigo_auth.py app add <alias> --id <uuid>`，alias 用 app 分配表的短名；
     之後對話與指令一律用 alias 指稱，UUID 不在對話裡傳遞

3. **資料架構設計**（★ 必須遵循雙軌分流策略，見 Phase 3 規則 18）
   - **受眾承接 1.7 授權架構表，不重問**（★ 決定資料存取層的寫法，見規則 31）：
     受眾中有沒有**無 `builder.access` 的一般成員**（一般員工、外部人員都算）？
     - 有（絕大多數情況）→ 自建表存取**全部包 Server Action**，前端不直呼 `queryTable` 等方法
     - 受眾全員持有 `builder.access` 的開發工具型 app → 前端 SDK 可直呼
   - **盤點兩邊**（順序不可省，★ 兩邊都是硬閘）：
     - `GET /api/v1/data-center/tables` — 租戶既有自建表（Phase 0 已做，此處覆核）
     - **預設表語意對照**——每個實體先用業務語言查 `references/default-table-lookup.md` §2，
       再 `aigo_data.py meta tables --source erp --grep <關鍵字>` 看中文標題；
       `GET /api/v1/refs/available-tables` 只是表名清單（`comment` 實務上為空），不能當語意來源
     - 對候選預設表呼叫 `GET /api/v1/refs/tables/{name}/columns` 查欄位結構
       （Meta key 與引用面表名不同時依查表 §3 換名再打）
       ★ **兩個端點分工是硬的：Meta 面找表讀語意、引用面 columns 判欄位有無。**
       Meta 面的 `fields` 是 Workspace 用的策展白名單，比實體表少欄是常態
       （`hr_employees`：Meta 20 欄 vs 引用面 42 欄）——**「Meta 沒列 → 平台沒有」是錯的推論**，
       這樣判會把該走 Data Reference 的實體推去自建（查表 §0 的 ⚠️、issue #70）
       ⚠️ **查到的表沒有 `tenant_id` 是正常的**，不代表不安全，也不要自補過濾——見規則 25
   - 列出所有需要的資料表（來源：§1.0 的資料實體清單），逐表判定走哪一軌（判定標準見規則 18）
   - **產出：資料承載表**（每個實體一列，寫進計畫；模板在 `new_app_requirements_template.md` §五、
     遷入線在 `migration_mapping_template.md` 每張表的對照項）
     `| 實體 | 用業務語言說是什麼 | 已對照的預設表（Meta 標題） | 採用／不採用理由 | 軌 |`
     ——走自建表的列，「已對照」與「不採用理由」兩欄**不得為空**；「沒想到有」不是理由，「查過沒有」才是
   - **重用優先於新建**：既有自建表語意相同就重用，不要新建；
     **重用的表欄位不足 → 直接加實體欄位**（`data-center.md` §7 加欄），
     不要因缺欄就另建新表或把結構化欄位塞進 json 欄
   - 走 Data Reference 的表：說明如何用 `custom_data` JSONB 擴充、`app_domain` 標籤值
   - 走自建表且需要新建的：產出**建表規格表**
     `| 表實體名 | 表顯示名 | 欄位實體名 | 欄位顯示名 | 型別 | 必填 | 唯一 | relation 目標 |`
     ——**兩個實體名欄不得為空且一律英文**（表 `biz_<英文複數>`、欄位 snake_case）；
     中文只能出現在顯示名那兩欄。理由與兩步命名法見規則 18.5
   - 若決定使用的預設表尚未被引用（以 `GET /api/v1/refs/apps/{app_id}` 為準，不是 db.json），
     引導用戶到 Builder 後台加入 Data Reference
   - 需求命中「交易／JOIN／條件式 UPDATE」邊界的實體，在這裡寫出改設計後的寫法
     （dev-guide §23.9），不要留到 Phase 3 才想

4. **頁面架構**
   - 路由結構（單頁 / 多頁）——**在這裡定案**，Phase 2 不再另問
   - 主要頁面和功能
   - Server Action 需求

4.5. **事件觸發需求**（若適用）
   - **Webhook**：列出要對外開放的端點
     `| hook 名稱（= action 名） | 事件來源 | 冪等 key 來源 | 驗簽方式 |`
   - **App 排程**：列出排程需求
     `| 排程名稱 | 觸發哪個 action | 頻率 | 時區 | 固定 params |`
     - **同時確認 tier 放不放得下**——最小間隔與條數上限依付費檔分層，
       超限是 400 不是靜默截斷。數值見 `references/event-triggers.md` §2.4
   - 兩者都要在計畫中明寫「此 action 的冪等策略」——見規則 20
   - 詳見 `references/event-triggers.md`

4.6. **對外 API 呼叫盤點**（★ 若有打第三方 API 就不可省）
   - 列出**所有要連出去的外部服務**
     `| egress slug | base_url（網域） | 用途 | 哪個 action 會用 |`
   - **在計畫階段就提醒用戶去建立外部服務**：Builder（`/builder/{app_id}`）的
     「外部服務」tab，以**同名 slug** 建立（base_url 域名白名單）並授權本 App
     （新建預設授權本 App）
     - 建立需本 App 擁有者或 `system.admin`；權限不足要請租戶管理員代設
   - 外部服務沒建立或沒授權，寫完的 code 一律連不出去——**等部署才發現等於整段白做**
   - 金鑰歸 app 自管：為每個 API 金鑰開 `ctx.secrets` 欄位，action 自組
     `Authorization` header——閘道只驗域名，不代管憑證（ADR 0010）
   - 詳見 `references/custom-app-dev-guide.md` §25

4.7. **平台 API 權限面盤點**（權限 gate 目前 audit，enforce 後前端呼叫會 403）
   - 列出**前端（瀏覽器 SDK）會直接呼叫的平台 API 群**——app 的宣告範圍是從
     `actions/*.py` 靜態推導的，**不含前端呼叫面**
   - 提醒用戶在 Builder（`/builder/{app_id}`）「API 權限」分頁把這些群開啟
     （寫入需 `builder.manage_access`）
   - 詳見 `references/platform-behaviors.md` §12

5. **app_domain 標籤設計**
   - 確定此 App 的 `app_domain` 值（snake_case，如 `patent_os`、`crm_leads`）
   - 說明標籤用途：所有寫入預設表的資料都會帶上此標籤

6. **現有系統遷移評估**（若適用）

   > 用戶有現存系統（Supabase / Google Sheet / MySQL / 既有程式碼）要遷入
   > → 先讀 `references/migration-workflow.md` §2，依序做：stack 盤點（§2.0）、
   > 產品線與模式判斷的遷入輸入（§2.1）、專案解構盤點（§2.2，前+後+DB 完整專案時，
   > 含使用者表與 DB 層邏輯的特殊處理）、語言架構評估、Schema 映射與資料遷移計畫。
   > 純新建 App 跳過本項。

### 計畫閘門

- **新建情景：§1.0 四問未齊、或計畫裡沒有「需求形狀結論」「app 分配表」「授權架構表」「資料承載表」→ 不算完成計畫，
  不得送閘門**——先回 §1.0／1.7／第 3 項補；遷入情景同樣要有這四張表
- **app 分配表任何一列沒有常駐結論 → 不算完成計畫**——兩條線預設都是 `false`；
  Custom App 沒命中即時互動訊號就直接寫 `常駐＝關（預設）`（§28.1，不必問 owner），
  寫「開」的列必須同時有「理由 X；退場條件 Y」，還要先確認租戶是付費方案（免費 403 設不上去）
- **資料承載表裡任何一張自建表缺「已對照的預設表／不採用理由」→ 不算完成計畫**——
  這道閘與 Phase 0 步驟 6 的自建表盤點同級（issue #53：少了它，46 張表的遷入案第一版判了 40 張自建表，對照後只剩 13 張）
- **必須等待用戶明確回覆「同意」或提供修改意見後，才可進入 Phase 2**
- 若用戶修改需求，需更新計畫後再次確認
- 計畫確認後：
  - 依 app 分配表建 app（Phase 1 步驟 3，模板 slug 照表）並 `aigo_auth.py app add` 登錄——
    **這是建 app 的唯一時點**
  - 將 `app_domain` 值記錄到 `.aigo/config.json`
  - 依授權架構表建角色、設 `access_role_ids`、發邀請（`member-admin.md` §3–§5；每一步都過
    `data-operations.md` §3.5 寫入閘門）——白名單沒設，不在名單的人開 app 是 404「App 不存在」
  - 判走 Hosted App 的 app → 轉 `references/hosted-apps.md`；本 skill 的 Phase 2–4 只跑 Custom App
