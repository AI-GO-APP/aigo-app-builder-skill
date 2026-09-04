# 回報前自審（Self-Grill Gate）

> **預設立場：平台必定正確；開發或使用失敗，預設是 Agent 自己的操作有誤。**
> 只有把「是我錯」的每個分支都用**證據**排除，才有資格說「這是平台問題」。
> 本檔是 `report_issue.py submit` 的前置閘門——沒走完，`submit` 會拒收（見 §5）。

機制借自 Matt Pocock 的 `grilling` skill（設計樹＋前沿＋輪次），但方向反過來：
原版是 AI 逼問使用者的計畫；這裡是 **AI 逼問自己的操作**。事實與排除全由 Agent 自己查，
使用者只剩最後一個決定——要不要送出。

---

## 1. 原則

| 原則 | 說明 |
|------|------|
| **一次只審一個症狀** | 多個症狀分開審。混在一起會互相掩蓋成因，也會把對話撐到「低效區域」 |
| **前沿順序** | 上游未排除不驗下游：token 沒確認前不驗 payload，payload 沒確認前不談重現 |
| **證據，不是判斷** | 每題要附**指令＋輸出節錄**。「應該沒問題」「我記得有做」＝未排除 |
| **不反覆重試** | 同一請求原樣重送超過 2 次沒有新資訊；換的是變因，不是次數 |
| **不確定就不報** | 前沿還有「待查」→ 把自審紀錄交給使用者決定，不替使用者送 |

失敗模式（對應原版「使用者連答四十次同意」）：**Agent 每題都填「已排除」，卻沒有真的跑指令。**
沒有證據欄的排除視同未排除。

---

## 2. 排除樹（六輪，依前沿順序）

每輪把當前前沿全部列出，格式：

```
❓ **Q<n>** - **<分支>**：<要驗什麼、怎麼驗>
➡️ 判定：已排除 / 未排除 / 待查
📎 證據：<指令＋輸出節錄>
```

### 第 0 輪：讀完再說

- **Q0.1 完整錯誤原文**：狀態碼、response body 全文、`request_id`、發生時間。
  外層狀態碼不等於成因——action 的 403 可能來自 action **內部**，看執行紀錄的 `error`。
- **Q0.2 症狀唯一化**：現在追的是一個症狀還是好幾個？多於一個 → 拆開，各自跑一次。

### 第 1 輪：版本與部署落差（最常被誤判為 bug）

- **Q1.1 skill 版本**：`python scripts/check_update.py` 有沒有提示落後？有「破壞性變更」警語時，
  症狀通常不指向真正原因（1.7.0 的租戶網址規則，症狀與密碼錯同形）。
- **Q1.2 prod 落差**：文件宣稱的端點 404／回應缺欄位 → 先當部署落差（prod 落後 main 約一週）。
  受影響清單見 `hosted-apps.md` 檔頭、`data-center.md` §9。隔幾天再試，不是 bug。
- **Q1.3 文件既有的 ⚠️ 註記**：對應章節是否已標「prod 尚未生效」「實測未驗證」？有 → 不是新發現。

### 第 2 輪：身分與環境

- **Q2.1 租戶網址**：`aigo_auth.py status` 印出的生效租戶是不是目標租戶？
  401「帳號或密碼錯誤」與打錯租戶**平台刻意同形**（`platform-behaviors.md` §6.1）。
- **Q2.2 token 狀態**：401＝過期、403＝權限。重新登入後症狀是否消失？
- **Q2.3 權限層級**：這步需要 `system.admin`、`builder.access` 還是 `datacenter.schema_write`？
  這顆帳號有沒有？一般員工帳號的 403 是否其實是 `builder.access` 破口（`data-center.md` §7.5）？
- **Q2.4 產品線與模式**：打的是 Custom App 還是 Hosted App 的端點？`internal`／`external`／
  `self_built` 的限制是否符合（internal 開不了匿名存取；`access_mode` 不可改）？
- **Q2.5 乾淨環境對照**：同一個瀏覽器 profile 連開多支 app 交叉比對會被快取污染，
  「沒動過的 app 也壞了」**不是證據**。可信的對照只有兩種——無痕視窗／新 profile 開同一支 app，
  或新建一支 hello-world app（`troubleshooting.md`「查不到怎麼辦」第 4 點）。對照乾淨才往下走。

### 第 3 輪：請求契約

- **Q3.1 payload 包裝**：records 寫入有沒有包 `{"data": {...}}`？（422 `not_null_violation` 但欄位明明有給）
- **Q3.2 實體名 vs 顯示名**：所有 API 用實體名；`/impact` 確認值也是實體名。
- **Q3.3 查詢契約**：只有 `filters:[{column,op,value}]` 生效，`where`／`filter` 靜默忽略；
  records 平面只有 `eq/contains/gte/lte`；`custom_data` 不能伺服器端過濾（`platform-behaviors.md` §1.5）。
- **Q3.4 型別格式**：TIMESTAMP 要 offset-naive；TIME 要完整 ISO；`select` 的 `options` 是純字串陣列；
  CHECK 值域查 `custom-app-dev-guide.md` §20.2 或 Meta API。
- **Q3.5 路徑**：VFS 路徑 POSIX 相對、無 `\`、無 `..`；`DELETE /source/files` 帶 `expected_version`；
  容器內打 data-center 要 `/open` 前綴。
- **Q3.6 平台有沒有既有路徑**：想要的能力可能已存在於別的入口（型別檢查在 Builder AI 的
  `check_types`、值域在 Meta API、路由權威在 `/api/v1/openapi.json`）。
  「API 沒提供」要先查 `references/` 與 openapi 再說。

- **Q3.7 資料操作線的契約**（不開發 app、以使用者身分直打模組 REST 時才問）：
  ① `aigo_data.py perm-check` 是**推估不是權威**——它說 ✅ 仍可能 403（少數端點有細權限如
  `hr.leave_manage`、`accounting.post`），「perm-check 過了所以權限沒問題」不是排除。
  ② **表名分面**：Meta API 的 key 不一定等於 proxy／refs 面的表名（客戶是 `crm_clients`，
  proxy 面叫 `customers`）——先 `meta tables --grep` 確認打的是哪一面的名字。
  ③ **分頁形狀不一致**：`client`／`sale`／`hr`／`stock`／`purchase` 用 `skip`＋`limit`，
  `crm` 用 `page`＋`page_size`；「筆數少了」先確認翻頁參數用對，不是平台漏資料。
  ④ **匯出範圍**：白名單只有 6 張預設表，**資料中心自建表不在匯出範圍**（送 id 或
  physical_name 都會 failed）——那是設計不是缺陷（`data-operations.md` §5）。

### 第 4 輪：生命週期與狀態機

- **Q4.1 發布快照**：sync／compile 都不會讓 action 上線，有 publish 嗎？改 manifest 後有 republish 嗎？
- **Q4.2 簽核攔截**：回傳有無 `approval_status: "pending"`／「需要簽核審批」？
  有 → 既非成功也非失敗，不是 bug，也不可重試（`custom-app-dev-guide.md` §24）。
- **Q4.3 鎖與衝突**：409 是 `vfs_version` 衝突還是配額？423 是有待審發布？
- **Q4.4 非同步延遲**：排程 `nextcall` 計算中、draft runner 冷啟約 60 秒、Hosted App env 傳播 1–6 分鐘、
  rollout 失敗時對外仍是舊 revision。等過了再判斷。
- **Q4.5 平台刻意設計**：`__CURRENT_USER__` 任何模式都不存在、`__IS_AUTHENTICATED__` 恆 false、
  seed 表唯讀、`ctx.erp` 白名單 403、runner default-deny egress、空渲染偵測 8 秒——
  這些是行為不是缺陷。
- **Q4.6 自己的產物**：白畫面先開 console。`ReferenceError` 帶 minified 名稱＝自家 bundle 的
  use-before-declaration；compile 走 esbuild **只轉譯不驗型別**，`compile_errors: []` 不是「程式正確」的證據。
  先跑 `uv run --project scripts python scripts/aigo_typecheck.py <專案目錄>`（SKILL.md Phase 4 步驟 1.5）。

### 第 5 輪：文件核對

- **Q5.1 `troubleshooting.md`**：逐列比對症狀。有列 → 照表處理後再看。
- **Q5.2 對應 reference 章節**：讀完整段，不是只讀被引用的那一句。文件寫的行為是否其實就是現在看到的？
- **Q5.3 `CONTEXT.md` 術語**：是否把 CustomObject 當自建表、Data Reference 當新表、延伸欄位當 `custom_data`？
- **Q5.4 文件沒寫 ≠ 平台錯**：文件缺口是 **skill 文件的問題**，回報到 skill repo，不是報平台。

### 第 6 輪：最小重現（走到這裡才有資格說「平台問題」）

- **Q6.1 去除 app 程式碼**：不經前端、不經 action，用登入 session 直接打同一端點、同一 payload
  （`aigo_data.py call` 或 curl），是否重現？不能重現 → app 側問題，停。
- **Q6.1b 資料操作線的替代判準**（★ 本線 Q6.1 恆真，不可拿它當證據）：這條線本來就是純 API，
  「去掉 app 程式碼仍重現」不排除任何東西——全樹最強的那道「app 側 vs 平台側」濾網在此自動通過。
  改用兩個對照：① **平台 UI 對照**——同一顆帳號在平台介面做同一件事（同一張表、同一筆、同一個值），
  UI 也失敗才可能是平台側；UI 正常 → 是我們的請求構造有誤，回第 3 輪（含 Q3.7）。
  ② **變因對照**——Q6.4 照做，並多換一項：**換一顆權限相同的帳號**（排掉這顆帳號的權限殘缺）。
  兩個對照都做完才有資格進 §3 的送出條件。
- **Q6.2 穩定性**：連續 ≥2 次、間隔數分鐘，是否確定性重現？偶發型（Hosted App 建置 failed 且日誌全空）先原樣重送一次。
- **Q6.3 最小 payload**：縮到最小仍重現，鎖定是哪個欄位／參數。
- **Q6.4 對照組**：換一張表／換一個 app／換一個值，症狀是否跟著變？用來確認觸發條件，不是猜。

---

## 3. 終止與送出條件（兩個都要成立）

1. **前沿為空**：六輪每題都是「已排除」且有證據。任何一題「待查」或「未排除」都不能送。
2. **硬條件擇一**：
   - (a) 用純 API 呼叫（不含 app 程式碼）穩定重現，且行為與 `references/` 的**明文條款**矛盾
     （★ **資料操作線不適用**——本線全程純 API，這一條恆真；改以 Q6.1b 的平台 UI 對照
     同樣失敗，且行為與明文條款矛盾為準）；或
   - (b) 端點 5xx／資料異常／流程硬阻斷，且第 1、2、4 輪全部排除。

不成立時的出口：

| 判定 | 出口 |
|------|------|
| 不確定 | **不報**。把自審紀錄交給使用者，由使用者決定 |
| app 側 | 回 `troubleshooting.md`／修 app |
| 文件缺口 | skill repo issue |
| 部署落差 | 記錄症狀，隔幾天再試 |

兩個條件都成立後，**仍要使用者確認才送出**（對應 grilling 的「使用者確認共識後才行動」）。

---

## 4. 自審紀錄：已排除清單（隨回報一併附上）

自審結束後，把每題的判定與證據濃縮成「已排除清單」，透過 `--ruled-out` 隨回報送出：

```
版本：skill 1.25.0 最新；端點未列入 data-center §9 prod 落差
身分：aigo_auth.py status → 租戶 <slug>；重新登入後仍 422；帳號具 builder.access
契約：payload 已包 {"data"}；欄位用實體名；options 為純字串陣列
生命週期：無 approval_status；非 409/423
文件：troubleshooting 無此症；data-center §3 明文允許此型別
重現：aigo_data.py call 直打 3 次必現；最小 payload 只含 name 一欄；改 text 型別即正常
```

這段讓開發團隊能在 30 秒內 triage，也讓回報者自己在寫的時候發現漏洞。
**寫不出這段，就代表還沒排除完。**

---

## 5. 工具層強制

`report_issue.py submit` 要求 `--ruled-out "<已排除清單>"`（或 `--ruled-out-file`）；
用 `--body-file` 時內文必須含「已排除」段落。缺少即拒收並印出六輪摘要，不會建卡。

這不是形式：文字規則會被跳過，CLI 拒絕不會。
