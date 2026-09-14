# Changelog

版本號採 [Semantic Versioning](https://semver.org/lang/zh-TW/)。
**每次改動 Skill 內容（SKILL.md / CONTEXT.md / references / scripts）都要同步更新 `VERSION`**，
否則使用者端的更新檢查（`scripts/check_update.py`）不會提示。

## 1.41.0

### Custom App 線補上 `always_on` 決策閘：常駐的引導與選擇不再只有 Hosted 有

`always_on` 兩條線都有（Custom `PATCH /builder/apps/{id}/runtime-settings`、Hosted
`PUT /{id}/runtime-settings`），立場也一直是同一套「預設不開」，但**流程只掛在 Hosted 線**：
SKILL.md §1.5 只對判走 Hosted 的列要求常駐決策、需求盤點表 §四.1 標題寫死「只有判走 Hosted 的
app 才填」、里程碑交付只有 Hosted §3.4 讀回 `always_on`。Custom 線的唯一出口是 dev-guide §28
（要主動翻到）與 troubleshooting「第一發很慢」那列（要等使用者先抱怨）——而 Custom App 正是本
skill 的預設答案，缺口落在流量最大的那條線上。

補的形狀不照抄 Hosted：Custom 的 action 是 request/response，Hosted 三問裡「容器內排程」
（平台排程是入站請求、會喚醒 runner）與「長連線」都不存在，**只剩冷啟動一題**；而且 Custom
多了兩個 Hosted 沒有的前提——免費租戶 403 `ALWAYS_ON_REQUIRES_PAID_PLAN`（判「開」也設不上去）、
未發布 422（設定時點在首次 publish 之後）。

- `custom-app-dev-guide.md` 新增 **§28.1 `always_on` 決策閘（Custom 線）**：預設 `false`，
  **不必每支 app 主動問 owner**——只有命中即時互動訊號（櫃檯、掃碼、來電查詢、客戶在線上等回覆，
  或需求寫明「幾秒內要出結果」）才問「閒置後第一個人打開等 N 秒能不能接受」；「第一發慢」本身
  不是理由，純排程／批次／webhook app 一律關。判「開」要先確認付費方案與 publish 時點。
- **常駐現況的讀回點實查定案**（2026-09-11 測試租戶查 prod openapi＋實打）：Builder 線
  **只有 `PATCH`，沒有 `GET /runtime-settings`**（該路徑只在 Hosted 線），`GET /builder/apps/{id}`
  明細也不含 `always_on`；唯一讀回點是**列表** `GET /api/v1/builder/apps`（`CustomAppListItem` 帶
  `always_on` ＋ `has_messaging_trigger`）。⚠️ 列表的 `always_on` 是**存的設定值不是生效值**——
  綁通訊渠道的 app 讀到 `always_on=false` 但 `has_messaging_trigger=true`，實際是常駐，兩欄要一起讀。
  同一次實查該租戶 66 支 app `always_on` 全 `false`，佐證「Custom 線常態就是冷啟動」
- `new_app_requirements_template.md` §四.1 拆成 **§四.1-A（Hosted 三問）／§四.1-B（Custom 一問）**，
  標題改成「每支 app 都要有一個結論」；app 分配表改成**每一列**都附常駐結論（預設列直接帶
  `常駐＝關（預設）`），需求形狀結論那行同步
- `SKILL.md`：§1.5 加「兩條線都要有結論」一段並改寫分配表產出；**計畫閘門新增一條**——任何一列
  沒有常駐結論＝不算完成計畫；「驗證流程快速參照」的里程碑交付新增常駐狀態對帳
- `verification-details.md` §2 新增第 9 項「常駐狀態對帳」：寫「關」＝確認全程沒下過 `PATCH`、
  不必打端點；寫「開」才在 publish 後設定並確認 `effective_mode: "always_on"`
- `product-line-decision.md` §7、`project_deconstruction_template.md`（遷入案的 Custom app 幾乎
  一律維持關）、`hosted-apps.md` §3.0（加一句本節只管 Hosted）、`troubleshooting.md`「第一發很慢」
  列同步指向 §28.1

## 1.40.0

### 預設表欄位判定改站引用面：Meta 面的 `fields` 是策展白名單（issue #70）

`GET /data-center/meta/tables/{key}` 的 `fields` **不是欄位全集**——平台後端維護一份
「哪些欄位出現在 Workspace grid／表單」的標注清單，實體表有、清單未列的欄位一律不輸出
（核自 `erp_field_annotations.py` 檔頭與 `meta_registry._reflect_fields`）。清單是 2026-07
從舊前端快照機械遷移來的，**逐表落差隨機**：`hr_employees` Meta 20 欄 vs 引用面 42 欄，
缺的正是 `registered_address`／`contact_address` 那批；同樣的地址欄在 `crm_clients` 反而有標注。
集合關係恆為 **Meta 面 ⊆ 引用面**。

依 Meta 面判「平台沒有這個欄位 → 自建表」會系統性地把該走 Data Reference 的實體推去自建，
正是 `default-table-lookup.md` 要防的事。舊文件把打引用面的理由只寫成「key 不一定相同」，
又把 Meta 面描述成「有中文標題與欄位 label」，讀起來像完整清單。

- `default-table-lookup.md` §0：三步的第 2 步改成**兩個端點分工**（Meta 面找表讀語意／
  引用面 columns 判欄位有無），新增策展白名單的 ⚠️ 與 20 vs 42 對照表；
  §1 兩個命名面各補一句（Meta 面不能判欄位有無、引用面才是欄位權威）
- `SKILL.md` Phase 1.5 第 3 項與規則 18、`custom-app-dev-guide.md` §20.2／§20.4／§22.1、
  `migration-workflow.md` §2.4 同步這條硬規則
- `pre-report-self-grill.md` 新增 **Q3.7**：宣稱「平台缺表／缺欄位」前必須打過引用面 columns
  （原 Q3.7 資料操作線契約改號 Q3.8）

### 延伸欄位在 app 執行期取不到值：選型第一問改成「app 要不要讀它」（issue #71）

延伸欄位（EAV）**建得起來、寫得進去、用登入帳號讀得回來，但 app 跑起來完全取不到**。
2026-09-10 實測＋源碼核對，app 執行期四條通道全斷：`ctx` 白名單無延伸欄位方法；
action 內直打 `/data-center/ext-*` 回 **401**（端點吃 `get_current_user`，runner 無使用者身分
——**與 `builder.access` 高低無關**）；前端 SDK 無封裝、手打要 `builder.access`（一般員工 403，
且沒有「包 action」的解，因為 action 打不到）；external 線 `/ext/data-center/*` 沒有 `ext-*` 路由。
值只有資料中心 UI、持 `builder.access` 的人、遷入用的本地腳本讀寫得到。

舊文件把這寫成「app 執行期要用得自己打 REST」＋「大量讀寫時再考慮自建表」，
讀起來像多打一支 API 就好、只讀幾個欄位不受影響——實際是能力限制。

- `data-center.md` §10：決策表加「app 要讀寫 → `custom_data` 或自建表」列並前置
  「**選型第一問不是要不要型別，是 app 要不要讀它**」；「沒有封裝」那條 bullet 改成四條通道的事實表
- `data-center.md` §7.5：通道表補 ⚠️——action 內直打 `/data-center/*` REST 不是第四條路，恆 401 不是 403
- `SKILL.md` 規則 18、`CONTEXT.md` 延伸欄位段、`custom-app-dev-guide.md` §19 決策樹／選擇矩陣／
  §22.1、`migration-workflow.md` §2.4、`data-operations.md` 匯入 `tier-2` 那條同步
- `custom-app-dev-guide.md` §23.8 新增第 5 步：遷入前先確認 app 不需要讀這些值
- `resources/new_app_requirements_template.md` §五與 `resources/migration_mapping_template.md`
  的「軌」說明各加限制條件（延伸欄位只能填在 app 不讀時；欄位有無只認引用面）

### PATCH `ext-values` 少包一層 `values` 會靜默 no-op 回 200

`{"payslip_probe":"V2"}` → 200 帶**上一次**的值、沒寫入；該列本來沒值時回 `200 {}`，像成功。
`{"values":{...}}` 才寫得進去。未定義欄位的 422 `invalid_field` **只保護包了 `values` 的請求**，
扁平 body 連 `no_such_field` 都吞掉（成因：`values` 有預設空 dict＋未知鍵被忽略 →
解析成「零欄要寫」的合法請求）。

- `data-center.md` §10 端點速查後新增 body 形狀規則與四列對照組；
  `custom-app-dev-guide.md` §23.8 步驟 2 補 body 形狀與這個陷阱
- `pre-report-self-grill.md` Q3.1 擴充：**回 200 但值沒進去 → 先懷疑少包一層**

### 兩張都判「不回報平台」

Meta 面白名單與 EAV 的身分模型都是刻意設計，修完文件後 skill 不再依賴；
扁平 body 的寬鬆解析使用者側寫對 body 就完全避得開。
`issue-reporting.md`「什麼時候回報」新增**「不要回報刻意的能力邊界」**三列（含這兩項），
避免同一個症狀再被當平台事故送出。

## 1.39.3

### `requirements.txt` → 500 HeadObject 403：做了對照組，**不重現**，因此不回報平台

1.39.1 收了一列「只要 VFS 有 `actions/requirements.txt`，每支 action 就回 500
`HeadObject ... Forbidden`」，當時明寫「只在一個租戶看過、沒有對照組，不要據此斷定平台故障」。
2026-09-09 補做對照組實驗：另一個測試租戶、拋棄式 app、一支不 import 任何東西的探針 action，
唯一變因是 `requirements.txt` 的有無，跑五個相位——

| 相位 | VFS 有無 reqs | 結果 |
|---|---|---|
| A 基準線 | 無 | 3 發全 200 success |
| B 加上 reqs | 有 | 2 發 200，2 發 503（redeploy 空窗） |
| C 拿掉（不 publish） | 無 | 1 發 503、2 發 200 |
| D 拿掉並 publish | 無 | 3 發全 200 |
| E 放回 reqs | 有 | 3 發全 200 |
| F `import requests` 驗證 | 有 | 3 發 503 後轉 3 發 200，`requests.__version__` 回 `2.32.3` |

**22 發沒有任何一發出現 `HeadObject`**，且 F 相位證明 wheelhouse 真的有從 `requirements.txt`
建起來並掛上（套件版本解得出來）。⇒ 這**不是「有 `requirements.txt` 就會壞」的普遍行為**，
原觀察的成因未明、無法歸因平台，**依「先在最新 prod 驗證為真才回報」的原則不開回報單**。

順帶量到一個會被誤讀成故障的東西：**改依賴後發布有一段約 75 秒的 redeploy 空窗**
（連三發 503「app runner 暫時不可用」，每發卡滿 25 秒後才轉 200）。與本列症狀的分辨法：
503「app runner 暫時不可用」是空窗，500 帶 `HeadObject` 才是那個未明症狀。

`troubleshooting.md` 該列改寫：保留原症狀與分辨法，加上對照組結果、redeploy 空窗數字，
並把「不要據此斷定平台故障」講得更明確。

## 1.39.2

### 更正：發布 409 的 `code` 與 gap kind 混寫；補上 1.39.1 那批宣稱的測試租戶實打佐證

2026-09-09 在測試租戶把整條 egress 路徑走完（建服務 → 授權 → 停用 → 發布 → 全部刪掉），
1.39.1 寫進去的宣稱**全部驗證為真**，但發現一處自己寫錯的欄位標題：

- **`platform-behaviors.md` §13.5 的表把「執行期 error type」標成「409 的 code」**。
  實際上發布 409 的 `code` **恆為 `EGRESS_NOT_READY`**，成因只在 `gaps[].kind`；
  `egress_service_not_found`／`egress_service_inactive`／`egress_not_authorized`
  是**執行期**（`ctx.http.call` 當下）的 error type，兩邊靠 `GAP_KIND_TO_ERROR_TYPE`
  共用文案但不會出現在 409 body 裡。表頭改成「`gaps[].kind`（發布 409）｜執行期對應的
  error type」，並附上實打回來的 409 body 原文。`troubleshooting.md` 那列同步改。

同一輪補進去的實打佐證：

- 建外部服務**不給 `timeout_ms`** → 落庫 `timeout_ms: 10000`（證實 1.39.1 的更正：
  30000 是上限、10000 才是實際拿到的值）
- `PATCH {"timeout_ms": 60000}` → 422；`PATCH {"max_response_bytes": 10485760}` → 422
  「必須是 1～5242880 之間的正整數（bytes）」（證實 `max_response_bytes` 只調得下去）
- 授權後把服務停用 → `available-egress-services` **照樣回它**（`is_active: false`）
  且**仍留在 `authorized_egress_service_ids` 裡** → POST `/publish` 回 409、
  `gaps[].kind = service_inactive`。**「已授權 ∧ 已停用」確認為可達狀態**，
  1.39.1 補的那道判定是對的（平台自己的 `fix` 文案也寫「不要重建，slug 唯一」）
- `authorized_egress_service_ids` 的 dict 元素形狀在**第三個租戶**再次確認

誠實標註佐證強度：閘道四道上限裡，**「每分鐘 120 次」那道只有原始碼佐證、沒有實打**
（要打滿 120 次才觸發，未做），其餘三道皆 prod 實打——`platform-behaviors.md` §13
與 `custom-app-dev-guide.md` §25.4 都已標明。

## 1.39.1

### 修正：egress 預檢把每個 slug 都誤判成 gap、以及漏判「服務已停用」；補上閘道四道上限的零覆蓋

2026-09-09 在測試租戶實打 `GET /api/v1/builder/apps/{app_id}/available-egress-services`
（兩個不同租戶，回應形狀一致），並回平台原始碼交叉核對（v1.13.1～v1.14.1 皆同）：

**（一）`authorized_egress_service_ids` 的元素是 dict**
`[{"service_id": "<uuid>"}]`，與 `PUT authorized-egress-services` 的 body
`{"services": [{"service_id": …}]}` 同形，**不是 id 字串的 list**
（平台寫入端就是 `[{"service_id": sid} for sid in service_ids]`）。

1.39.0 的 `egress_preflight()` 對每個元素直接 `str(x)`，得到
`"{'service_id': '…'}"`，永遠對不上 `services[].id` → **`authorized` 恆為空集合、
每個 slug 都被點成 gap**，已授權的 `openai`／`openrouter` 照樣被擋，只能靠
`skip_preflight=True` 繞過。那一輪的 POST `/publish` 沒有觸發 `EGRESS_NOT_READY`
（該打的都已授權）——是 skill 這側自己算錯，平台閘門本身是在的。

**（二）反過來的誤判：預檢漏看 `is_active`**
發布閘門（`publish_guard.check_egress_readiness`）分**三種**互斥 gap：
`service_missing`／`service_inactive`／`unauthorized`。而 `available-egress-services`
的 `services` **含停用中的服務**（平台 `list_tenant_egress_services()` 預設
`active_only=False`，ADR 0011 刻意保留停用列以便重新啟用；該端點 docstring 過時）。
授權當下會擋停用中的服務，但**之後停用不會回收授權清單裡的 id**，所以
「已授權 ∧ 已停用」是可達狀態——只比對授權清單會印出 ✅，publish 卻回 409 `service_inactive`。
1.39.0 因為什麼都算 gap 而碰不到這格；修好（一）之後它就活了，故一併修。

**（三）egress 閘道的上限原本零覆蓋**，同一輪補齊，且**是四道不是三道**：
單次呼叫時間＝該服務的 `timeout_ms`（**預設 10000**、硬上限 **30000**；PATCH 60000／120000 回 422）、
送出的請求本體 **8 MiB**、回應 **5 MiB**（`max_response_bytes`，**只調得下去**）、
頻率 **每分鐘 120 次**（key＝單一 App × 單一 slug，超過回 429）。
逾時砍的是**整支 action**，`error` 原文與 runner ceiling 那道同形——同一支已發布 app 的純
`sleep(100)` 回 `success`／`duration_ms 100002`（manifest 的 120000 確實生效），
走 `ctx.http.call` 的四發卻全落在 30394～30405 ms。這是最容易被誤讀成
「manifest 沒生效／要 republish」的一格；且 **30000 是上限不是預設**，
沒明設 `timeout_ms` 的服務在約 10 秒就被切。

改動：

- `scripts/aigo_publish.py`：新增 `authorized_service_ids()`——`service_id`／`id`／
  `egress_service_id` 三種 key 都認，純字串元素也吃（空清單看不出形狀，留退路），
  壞元素略過；新增 `available_services()`，只認 `services` 這個 key（舊寫法「回應裡第一個 list」
  在缺 key 時會撈到授權清單當服務用，靜靜算錯）。`egress_preflight()` 改判 `is_active`
  （只有明確 `False` 才算停用，欄位缺席當啟用），回傳新增 `inactive_service`，
  `format_egress_preflight()` 三種成因分開講、✅ 那行註明「平台另檢查 secrets，這裡看不到」。
  新增離線自測 `python scripts/aigo_publish.py selftest`：不打網路、只用標準庫，涵蓋
  dict／字串／混用／空／壞資料五種元素形狀，以及全授權、零授權、半授權、租戶沒建服務、
  已授權但停用、`is_active` 欄位缺席、不給 available 降級等預檢情境。把 1.39.0 的舊
  id 解析法塞回去會失敗 6 項（其中 `gaps` 正是回報的 `['openai', 'openrouter']`）；
  把 `is_active` 判定拿掉會失敗 3 項
- `references/custom-app-dev-guide.md`：新增 §25.4「閘道的四道上限」（數值、可調性、
  撞到時的回應原文、串流不繞過、與 runner ceiling 的分辨法）；原 §25.4 順延為 §25.5；
  §7 執行逾時段補一則「走 `ctx.http.call` 另有一道更早的牆、括號裡的毫秒是閘道的值」
- `references/platform-behaviors.md`：新增 §13，記四道上限的實測數字與可調性、422 原文、
  `ctx.http.call(timeout=…)` 的 `TypeError`、`sleep(100)` 對照表、SSE 實測、
  三道不同層的體積限制對照，以及 §13.5「三種 gap kind × 可用清單會回停用列」
- `references/troubleshooting.md`：「Action 超時」列改成先分流；新增「走 `ctx.http.call`
  的 action 提早被切」列（含 `sleep(n)` 對照的分辨法）、413 請求體積列、429 限流列、
  「409 EGRESS_NOT_READY 但服務明明建好也授權了＝被停用」列；新增
  「有 `actions/requirements.txt` 就每支 action 回 500 HeadObject 403」列——
  **只記症狀與分辨法**（單一租戶、無對照組，不下平台故障的結論）
- `references/event-triggers.md`：§1.6／§2.6 的逾時模型原本只講「dispatcher 外層 ∪ runner
  ceiling 兩道取小」，補上第三道（egress 閘道）的指標——dev-guide §7 會把讀者指到這兩節，
  不補的話順著指標走的人看不到那道牆
- `SKILL.md`：`ctx.http.call` 段補四道上限、「提早被切不等於 manifest 沒生效」與「服務被停用也擋」

## 1.39.0

### 發布閘門與 503 三成因：起手式殘留的 `required_egress`、三個 publish 確認參數、遷入的狀態層落點

2026-09-09 盤點 issue #56–#62（含 #42／#43），在測試租戶用一支拋棄式 `starter-internal` App 逐項實打，
並回平台原始碼（`publish_guard.py`、`custom_app.py` publish 端點、`action.py` runner 失敗分支）核對。
實打為真且 skill 零覆蓋的四張（#57／#58／#59／#61）在本版處理；#56／#60／#62 已分別由
1.36.0／1.38.0／1.37.0 處理，殘句在本版補齊；#42／#43 屬產品決定，不在本版。

實打事實：

- `starter-internal` 1.6.0／`starter-external` 1.4.0 建出的 App 自帶 `_template.json`，宣告
  `required_egress: {"openai": …}`，示範 action `actions/summarize_leads.py` 也呼叫它；什麼都沒改直接發布
  409 `EGRESS_NOT_READY`
- 閘門掃的是「`actions/*.py` 字面 `ctx.http.call` slug ∪ `_template.json.required_egress`」聯集——
  刪掉 action 後光靠宣告仍擋；刪掉 `_template.json` 後不帶參數就能發布；README 與 `actions/manifest.json`
  殘留不影響（issue #61 原文說 README 會擋，不對）
- 閘門順序 400 `INVALID_ACTION_CODE` → 409 `ACTION_REMOVAL` → 409 `EGRESS_NOT_READY`；
  `confirm_removal`／`confirm_egress_gaps`／`auto_rollback` 三個 query 參數 prod 皆生效（`auto_rollback` 只驗成功路徑）
- 503「app runner 暫時不可用」＋`retry_after: 30` 三種成因同形：未發布（online 恆走 per-app runner，
  ksvc 不存在就連線失敗）、發布後冷啟動（立刻打 503，約兩分鐘後 162ms 跑通）、配額（帶 `quota_hint`）；
  原始碼沒有「未發布」分支

改動：

- `references/troubleshooting.md`：`ACTION_REMOVAL` 列改成帶 `?confirm_removal=true` 重發並寫閘門順序；
  新增 `EGRESS_NOT_READY` 列（兩個檔都要刪、刪法、何時帶 `confirm_egress_gaps`）；503 列拆三成因倒序——
  先問有沒有 publish，重試放最後
- `SKILL.md`：Phase 4.4 發布步驟補 `egress_preflight()`、三個參數的使用時機與「發布後立刻 503 是冷啟動」；
  問題回報段的 503 句同步三成因
- `references/custom-app-dev-guide.md` §8：三個參數表、閘門順序、`gaps[]` 形狀與掃描範圍；§26.2 補
  「起手式自帶 `_template.json` 宣告 openai、兩個檔都要刪、`sync_to_cloud()` 不會刪遠端檔」
- `references/platform-behaviors.md` §5.2：刪掉「未找到確認參數」，改為 `?confirm_removal=true`；
  新增 §5.3 `EGRESS_NOT_READY` 回應原文與規則
- `references/migration-workflow.md` §2.0 stack 盤點新增「狀態層」列（快照／排程產物／session 的三個落點：
  自建表／`/data`／每次重算）（#57）；§2.4 補「自建表實體名先定英文」前置提醒（#62 殘句）
- `references/hosted-apps.md` §7：加遷入時的反向指引，指回 §2.0 狀態層列（#57）
- `references/pre-report-self-grill.md` Q1.2：補「文件宣稱會注入的 header 沒出現」型與最小無框架程式
  印 header 的對照法（#56 殘句）
- `references/product-line-decision.md`：Hosted `visibility=internal` 格補「只是門禁、容器拿不到任何身分」（#56 殘句）
- `scripts/aigo_publish.py`：`publish_app()` 加 `confirm_removal`／`confirm_egress_gaps`／`auto_rollback`
  三個參數（預設皆不帶）；POST 前先跑 `egress_preflight()`（AST 掃字面 slug ＋ 讀 `_template.json` 宣告 ＋
  對照 `available-egress-services` 的授權清單），起手式殘留當場點名；409 回來把 `code` 翻成下一步，
  不自動帶 confirm；`auto_rollback` 的 422 明講已退版；`full_deploy()` 參數透傳
- `scripts/aigo_sync.py`：新增 `delete_remote_files()`（`DELETE /source/files` 帶 `expected_version`，
  刪後 GET 驗證）與 `STARTER_EGRESS_LEFTOVERS` 常數；`diff_vfs()` 的 `deleted` 清單只列不做，docstring 明講

## 1.38.0

### 更正：Custom App 執行期網址與存取端點——internal／external 兩線各自的正式／測試形狀與四條通道端點總表

1.36.0 以前整份 skill 對 external Custom App 的網址只有一格：`platform-behaviors.md` §6.2 寫
「`{subdomain}.apps.ai-go.app` → 導向獨立登入頁（供 external app 用）」，而且是錯的；
`/ext-runtime` 與 `version-test`（開發預覽）在 skill 裡出現次數是 0，`*.apps.ai-go.app` 在三處
被寫成三種東西（沙箱域／external 專用登入頁／webhook 基底）。2026-09-09 回平台原始碼
（`frontend/src/lib/appUrl.ts`、`externalRuntimeUrl.ts`、`middleware.ts`、`backend/app/main.py`
router 掛載與各 router 的 `Depends`）核對，並在 prod 以測試租戶的真實 app 逐形狀 GET 實打、
以四種憑證交叉打四條通道實打，結論：

- 網址兩線完全不同：internal `https://{tenant}.ai-go.app/runtime/{識別碼}`；external 有
  `subdomain` 走 `https://{subdomain}.apps.ai-go.app/ext-runtime`，沒有走
  `https://runtime.apps.ai-go.app/ext-runtime/{slug}`；測試版各多一段 `version-test`，
  external 的測試版還要 `?preview_token=`（`POST /ext/preview-token/{slug}` 鑄）
- 識別碼規則相反：internal 用 `url_name`（有值）否則 `slug`；external 路徑一律原始 `slug`
  （共用 host 上 `url_name` 只租戶內唯一，平台 security review 列 CRITICAL）
- `subdomain` 落庫真值是 `{租戶前綴}-{輸入}`（`check-subdomain` 實打回 `stored_subdomain`）；
  internal 與 external 都可以有子網域（測試租戶實查 3 支 internal 帶 `subdomain`）；
  裸根 `{subdomain}.apps.ai-go.app/` 是 rewrite 到 `/resolve-app`（網址不變）依 `access_mode` 渲染，
  不是導向登入頁
- `url_name` 只收小寫英數與連字號（`check-url-name` 實打中文回 `available: false`），
  1.36 以前 `member-admin.md` 寫「`url_name` 可含中文會被 422 擋」是錯的
- 端點四條通道各一組前綴、憑證不能互換（實打）：平台 JWT／app-scoped token 打 `/ext/*` 401、
  external 使用者 token 打 `/data-center`／`/proxy` 401、對 internal slug `register` 404；
  `/pub/*` 只有讀；`/open/*` 是 Hosted／self_built 的 API key 通道

改動：

- `references/platform-behaviors.md` §6.2：改寫成「Custom App 執行期網址：internal／external ×
  正式／測試」唯一權威表，附識別碼、`subdomain` 落庫值、`version-test` 門禁、`*.apps` 共用、
  規則 29 例外、常見錯法表、internal apps-origin 旗標的移動標靶註記；§6.1 表列改稱「執行期網域」
- `references/custom-app-dev-guide.md`：新增 §6.0「同一支 SDK，internal 與 external 打兩組端點」
  分流表（api／db／action／approval／user／Storage／compile）；新增 §29「存取通道端點總表」
  （internal／external／匿名／open 四條通道的憑證、前綴、權限閘，與自建表 CRUD 四路對照）；
  §2 補「規則 29 只管 base_url」指標；§14 補 `register` 的 `display_name` 必填、`/me/password`、
  `manage/{app_id}/users` 管理端點、終端使用者入口連結＝執行期網址；§26 補 `subdomain`／`url_name`
  契約與 `check-subdomain`／`check-url-name`
- `references/member-admin.md`：`/app-login/{slug}` 一律填自動 slug（理由改為 `url_name` 可能為
  null／發布前可改），移除「可含中文」的錯誤說法；補 external app 沒有這個落點
- `references/event-triggers.md` §1.3：`{domain}` 改回 `apps.ai-go.app`，`subdomain` 用落庫值，
  註明 `*.apps` 是執行期網域、internal 也可能有
- `SKILL.md`：規則 29 區塊與核心規則 29 補「app 執行期網址不受本條管」的例外；Phase 4.1 補
  「在瀏覽器看草稿」的網址；里程碑交付補「交付連結實開」；references 索引補 §6.2／§6.0／§29
- `references/verification-details.md`：新增第 8 項「交付連結實開」
- `references/troubleshooting.md`：新增「同一段 SDK 在 internal 通、external 401」與
  「給用戶的連結 404／空殼」兩列
- `references/data-center.md` §7、`references/hosted-apps.md` §1、`CONTEXT.md`：指到權威表
- `scripts/aigo_auth.py`：`*.apps.ai-go.app` 的擋下訊息改為「執行期網域（internal／external 共用）」

## 1.37.0

### 自建表命名硬閘：實體名一律英文、`biz_` 前綴，既有不合規表走重建式改名

自建表的**實體名**（physical name）是平台從 `display_name` 生成的、**建立後永不可變、沒有改名 API**。
生成規則是 NFKD 折疊後丟掉非 ASCII——**純中文顯示名折疊後是空字串**，於是落到保底前綴：
一張中文表拿到 `tbl`／`tbl_2`，欄位拿到 `col`／`col_2`／`col_3`，延伸欄位 `ext_N`。
所有 API、`filters`／`sort`、刪除確認值都用實體名，於是 code 永久長成
`queryTable('tbl_3', { filters: [{ field: 'col_7' }] })`。
資料中心 UI 建表框的 placeholder 就寫「例如：客訴紀錄」，用戶自建的表幾乎都是這個下場，
而本 skill 原本只寫了「顯示名字元集：任意（中文常見）」，建表規格表也只收顯示名——等於把 agent 帶進坑。

- **SKILL.md 新增規則 18.5「自建表命名規範：實體名一律英文」**（★ 強制）：
  表 `biz_<英文實體複數>`、欄位英文 snake_case、延伸欄位同規範、顯示名照樣中文。
  `biz_` 前綴的三個作用——與預設表的功能區前綴（`crm_`／`sale_`／`hr_`…）一眼分開、
  **完全避開保留名 409**（保留母體 = SQL 保留字 ∪ 預設表名 ∪ 平台地板表名 76 張，無一以 `biz_` 開頭）、
  不佔用平台自己在用的 `dc_`／`app_`
- **兩步命名法**（唯一能同時要到英文實體名與中文 UI 的做法）：`POST /tables` 的 `display_name`
  先填英文實體名 → 驗 `physical_name` → 再 `PATCH` 把表與各欄顯示名改成中文；**同一次交付內做完**
- **Phase 1.5 建表規格表加兩欄實體名**（`| 表實體名 | 表顯示名 | 欄位實體名 | 欄位顯示名 | …`），
  兩個實體名欄不得為空且一律英文；`migration_mapping_template.md` 的自建表區塊同步加欄，
  該表即「中文欄位名 → AI GO 英文實體名」的 SSOT
- **Phase 0 步驟 6 加「順手掃命名」**：只盤不動手。`data-center.md` §11.1 分四級——
  P0 保底名（必改）、P1 撞平台語意、**P2 只是少前綴但名字可讀（預設不動）**、P3 只有顯示名不對（直接 PATCH）。
  ⚠️ 不為了前綴一致去重建一張有資料的表：風險遠大於收益
- **`data-center.md` 新增 §11「重建式改名」**：平台沒有改名 API（`PATCH` 不收 `physical_name`，
  改欄 payload 是 `extra="forbid"`），所謂改名實際是「建新表→搬資料→改引用→驗收→刪舊表」五步不可逆。
  計畫書要五塊（對照表／引用掃描／relation 連鎖／配額/停機回滾），**用戶同意後才動**。
  三個實測坑：① 新表 = 新 UUID，指向舊表的 `relation` 欄位**也要重建**；② 重建期間新舊並存，
  表數暫時翻倍要先算配額；③ **image 欄位的 storage key 內嵌舊表實體名**，取 URL 端點會驗
  「key 裡的表是本租戶現存的表」——舊表一刪圖片全 404，key 不可直接複製，必須逐張重傳。
  只有部分欄位不合規時走「加新欄→搬值→刪舊欄」，不動表
- **`aigo_data_center.py`**：新增 `predict_physical_name()`（複刻平台演算法，送出前就能說「你會拿到什麼名字」）、
  `assert_naming()`（建表／加欄的硬閘，不合規直接不送）、`audit_table_naming()`／`format_naming_audit()`
  （既有表分級盤點）、`update_table()`（兩步命名法第二步；擋下 `physical_name` 並指向 §11）。
  `create_table()` 加 `labels=` 參數自動做完第二步，並在建完驗 `physical_name` 是否等於預期
  （不等就拋——此時沒資料，刪掉重建最便宜）。`format_create_spec()` 的降級指引改成
  「表名欄請照填 `<英文實體名>`，建好後我把顯示名改成中文」
- **`aigo_review.py`**：新增 `scan_table_references(vfs_state, names)`／`format_table_reference_scan()`
  ——全字比對（`tbl_2` 不會誤中 `tbl_20`）、另收**動態表名**（`queryTable(tableName)`、f-string 拼接）
  標為必須人工確認；掃全部檔案不只 `src/`
- `troubleshooting.md` 加三列（建出 `tbl`/`col_N`、想改實體名、重建後圖片全壞）；
  `CONTEXT.md`、dev-guide §23.4 同步
- ⚠️ **行為變更**：`create_table()`／`add_field()` 在送出前會因命名不合規而 `ValueError`——
  舊呼叫端若直接傳中文 `display_name` 會拋錯（錯誤訊息會印出它本來會拿到的實體名）。這是刻意的：
  放行的代價是一個永遠改不掉的 `tbl_2`。改法是把中文移到 `labels=`
- 離線驗證：`predict_physical_name` 與平台 `generate_physical_name` 逐案對照（中文／數字開頭／中英混／
  SQL 保留字／流水號／48 字截斷）全一致；`assert_naming` 擋放各 8/4 案；`audit_table_naming` 分級；
  `scan_table_references` 全字比對與動態表名偵測

## 1.36.0

### 更正：internal Hosted App 容器拿不到任何身分（實測推翻四個 X-Aigo header）

1.35.0 以前 `hosted-apps.md` §6 與 `member-admin.md` §6 寫「auth-proxy 驗過登入後會注入
`X-Aigo-User-Id`／`-Tenant-Id`／`-App-Id`／`-Population` 四個 header」。2026-09-09 在測試租戶
實打推翻：部署一支只把收到的 header 原樣印出來的 app（`internal` ＋ `access_role_ids=[]`），
以成員身分走完登入交遞後開啟，容器只看到 `Host`／`Forwarded`／`X-Forwarded-*`／`X-Request-Id`
這類轉送 header，**一個 `X-Aigo-*` 都沒有**，`Cookie` 也沒有。

也就是 internal 模式**門口擋得住、門內認不出人**——app 連「這是哪一位使用者」都不知道，
不只是「拿不到 roles」。容器內的 `AIGO_API_TOKEN` 是 app 身分不是使用者身分：打
`/api/v1/auth/me`、`/api/v1/members*` 一律 401；`/open/proxy` 打 `users`／`roles`／
`user_role_rel`／`members` 一律 403（平台身分表，引用面列不出來），對照組
`/open/data-center/tables` 200。已回報平台（2026-09-09）。

照舊文字寫的 app 會拿到一片空白，且症狀是「使用者永遠是同一個人」這種不會報錯的失敗，
所以四處全部改寫，並在 `troubleshooting.md` 補一列讓症狀查得到：

- `references/hosted-apps.md` §6：改寫成「容器收到的身分：一個都沒有」，附實打證據、
  `AIGO_API_TOKEN` 打身分端點的 401／403 對照，與三條替代做法（Custom internal app／
  Hosted `public` 當後端＋自驗簽章／按角色拆多支 app）
- `references/member-admin.md` §6：整節改寫並移除四個 header 的表；§0 的陷阱清單一併更正
- `SKILL.md` Phase 1.5 陷阱條與 references 索引：改為「拿不到任何身分」
- `references/troubleshooting.md`：新增「internal Hosted App 讀不到現在是誰在用」一列


## 1.35.0

### 回報內文的 BDD 骨架升級為硬閘：情境→操作→結果→預期，開藥方措辭拒收

原本的回報指引方向對（寫行為不寫解法），但骨架是「預期→實際→重現」——第一段就要人寫「依文件應該怎樣」，
把 agent 推向先講技術契約；「嘗試做什麼」沒有欄位承接；而且只是警告不是閘門，`--body` 完全自由格式，
也沒有任何機制擋「建議把 X 改成 Y」。這次只動骨架，不動流程：

- **`report_issue.py submit` 段落改為 `--given` 情境（想完成什麼、當時在什麼狀態，一句使用者目標層的話）→
  `--when` 操作 → `--then` 結果 → `--expected` 預期 → `--context` 環境**；舊旗標 `--actual`／`--steps`
  保留為 `--then`／`--when` 的別名。卡片內文依此順序組成
- **三道新檢查**：① 情境／操作／結果三段缺一**拒收**（`--body`／`--body-file` 內文須含這三個段落字樣），
  與 `--ruled-out`、`--user-confirmed` 同級；② 內文命中「建議把／應該改／修法／實作方式／根因是／root cause」
  等開藥方措辭**拒收**並印出那句（只掃 BDD 內文，不掃已排除清單——技術細節本來就該放那裡）；
  ③ 結果段超過 1200 字提醒「原文貼關鍵段落，指令與完整輸出留在已排除清單」（軟）
- `issue-reporting.md`「怎麼寫」改為七段骨架，新增「情境寫成技術契約」的壞範例；
  `pre-report-self-grill.md` §3 給使用者看的摘要改成同一順序，並要求情境與結果用非技術的話寫；
  SKILL.md「問題回報」第 4 步與規則 bullet、指令範例同步
- 離線驗證：缺 `--given` 拒收、內文含「建議把…改成」拒收、`--actual`／`--steps` 舊名可用、
  三段＋已排除＋確認齊備才走到連線（指向不可達位址，未建卡）

## 1.34.0

### issue #53：預設表語意對照升級為硬閘、新增「AI GO 預設表查表」、詞彙清理

起因：一個 46 張表的遷入案，第一版計畫把 38–42 張判成自建表，使用者追問後才對照出 13 張自建＋11 張預設表引用。
根因一半是 skill 把自建表寫成遷入的預設答案、第一問「要不要與平台功能連動」把舊系統推向「否」，
另一半是沒有任何閘門會在跳過預設表對照時擋下來。全部對回原始碼核實後修：

- **第一問改寫**（六處同構全改：SKILL.md 規則 18 表、dev-guide §19 決策樹／選擇矩陣／§22.1、
  `migration-workflow.md` §2.4、`hosted-apps.md` §7.1）：「平台有沒有同語意的實體？有 → 引用；查過仍無 → 自建」，
  新建與遷入同一句，舉證責任放在「為什麼不用預設表」
- **拿掉「遷入案例的主力」定調**（六處）：改為「語意落在 CRM、專案、銷售採購、HR、會計的表預設引用預設表，
  只有平台真的沒有對應實體才自建」；「自建表不是最後手段」一句保留但加「也不是遷入的預設答案」
- **資料承載表硬閘**：Phase 1.5 第 3 項新增產物 `| 實體 | 用業務語言說是什麼 | 已對照的預設表 | 採用／不採用理由 | 軌 |`，
  計畫閘門加兩條——沒有資料承載表不算完成計畫；任一自建表缺「已對照／不採用理由」不算完成計畫
  （與 Phase 0 步驟 6 自建表盤點同級）。`new_app_requirements_template.md` 新 §五、
  `migration_mapping_template.md` 每張表加「對照項」四列、§2.5 匯入閘門視缺對照為映射表未產出、
  `data-center.md` §2 建表流程加 2.5 步
- **新 `references/default-table-lookup.md`（AI GO 預設表查表）**：§0 三步查法、§1 表名前綴讀法與 Meta 面／引用面
  兩套命名、§2 業務語言→預設表速查（七個功能區、含「常被誤建成」欄）、§3 Meta key↔引用面表名對照
  （核自平台 Meta 標注與 model：`crm_clients`→`customers`、六個 `accounting_*` 全是 `account_moves`、
  `project_stages`→`project_project_stages` 等；Meta 404 ≠ 表不存在）、§4 常用表必填欄（核自 model
  `nullable=False` 無預設值）與唯讀表（平台獨寫 `stock_moves`／`analytic_lines`／`mrp_workorders`…、
  全域參考表）、§5 遷入常見誤判（issue #53 的前後對照）。**糾正 issue 一處**：`analytic_lines` 是平台獨寫表，
  「專案費用」不能對到它，報支人非員工時自建表是正解——這是「查過沒有」的正例
- **dev-guide §20.1 修正**：`available-tables` 的 `comment` 實務上為空（原始碼取 DB 表註解，業務表沒宣告），
  回應範例是理想樣貌，語意要從 Meta API 拿；§20.2.1 加必填欄與唯讀表的指標
- **詞彙清理**：repo 內唯一一處外部產品名（dev-guide §20.3「欄位別名」列）改為「歷史欄位名」；
  正文四處「ERP」（`platform-behaviors.md` §4.3 兩處與 §保留名一處、`troubleshooting.md` validate 列）改為
  「平台模組介面」「預設表撞名」；`CONTEXT.md` 稱謂對照新增「禁用詞」列，查表檔頭寫死撰寫規範
  （只用「功能區前綴」「Meta 面／引用面」「歷史欄位名」解釋命名，原始碼註解裡的外部系統名稱不得帶進文件或對話）
- 未做（另開）：`aigo_data.py suggest-refs` 工具提醒；平台側 `available-tables` 補 `comment` 走五步流程回報

## 1.33.0

### `always_on` 決策閘補齊結構化落點；問題回報改為「自動自審 → 主動詢問 → 同意才送」

**一、常駐（`always_on`）四處縫隙**（1.32.0 的 §3.0 只有文字規則、部署與計畫裡沒有格子）：

- **部署與驗證有格子了**：`hosted-apps.md` §3.2 明寫部署流程不碰 `always_on`（預設 `false`，判 `true` 才在
  `active` 後 PUT）、§3.3 註明常駐不在 CLI deploy 指令裡、開之前必過 §3.0；**§3.4 驗證表新增「常駐設定」列**——
  `GET runtime-settings` 讀回 `always_on` 必須等於 §3.0 決策、讀到 `true` 要拿得出理由與退場條件；
  驗證後決策表新增「讀回 `true` 但無決策紀錄」出口；「全部通過」列改成交付說明附 version marker ＋ 常駐狀態一句；
  §3.0 補上計畫／交付說明的落點；§7「需要常駐就開」舊句改為指回 §3.0；SKILL.md Phase 5 速查同步
- **需求模板與 app 分配表有欄位了**：`new_app_requirements_template.md` 新 **§四.1 Hosted 常駐決策**
  （三個業務問題＋換算＋結論格式，沒填＝關）、需求形狀結論加常駐行、app 分配表註明 Hosted 列附常駐結論；
  SKILL.md 1.5 產出同步；`project_deconstruction_template.md` Hosted 線註記：背景排程／WebSocket 兩列就是決策閘前兩題
- **Custom App 線立場對齊**：dev-guide §28「何時建議常駐」改寫——Builder App 只剩「冷啟動容忍秒數」一題，
  「第一發慢」本身不是理由、agent 不自行開、不把「要不要常駐」丟給 owner；`troubleshooting.md`「閒置後第一發慢」列
  不再直接給 `always_on: true` 當解法，先問容忍秒數

**二、問題回報的使用者流程**（設計原則不變：預設平台正確、六輪自審、不確定就不報；改的是「誰推進、誰決定」）：

- SKILL.md「問題回報」新增**固定五步**：① 觸發條件成立即**自動**自審（不等使用者要求、不先問要不要查）
  ② 六輪自審 ③ 判定——非平台問題只說結論不問送不送、前沿有待查問的是「要不要繼續追」、兩條件成立進 ④
  ④ **agent 主動給摘要並問使用者要不要提交**（不得替使用者決定）⑤ 同意才 `submit`；
  「錯誤處理」與 `troubleshooting.md`「查不到怎麼辦」第 3 步改為自動接入這條流程
- `pre-report-self-grill.md` 檔頭寫明自動啟動、§3 寫死問法（摘要格式＋問句）、§5 工具層強制加旗標；
  `issue-reporting.md` 加「使用者流程」五步表、BDD 第 6 項「送出確認」
- **`report_issue.py submit` 新增必帶 `--user-confirmed`**：代表第 ④ 步已做且使用者同意，缺少即拒收不建卡
  （與 `--ruled-out` 同一層，排在它之後、取憑證之前）；卡片末尾附「送出確認」段。旗標的真假 CLI 驗不了，
  靠對話裡留下的摘要與問句可稽核。離線驗證：缺 `--ruled-out` 先擋、缺 `--user-confirmed` 再擋、
  兩者齊備才走到連線（`URFIT_TICKET_API` 指向不可達位址，未建卡）

## 1.32.0

### issue #38 五條逐一 prod 驗證後修復；issue #40 `always_on` 決策閘落地

每條先對 2026-09-08 的 prod（openapi 實查、測試租戶實打、或 prod tag v1.13.1 原始碼）確認為真才改：

- **#38-1 `check_update.py` Python 3.9 啟動即 TypeError**（★ `uv run --python 3.9` 重現）：補
  `from __future__ import annotations`，3.9 與 3.14 皆通過 `--check-only`
- **#38-2 排程入口與權限鍵**（★ prod openapi 有 `/api/v1/builder/apps/{app_id}/crons` 全組＋`/crons/quota`，
  測試租戶實打 200）：`event-triggers.md` §2.1 改成兩入口對照表——**App 開發面**（Builder 該 App「排程」分頁；
  讀 `builder.access`、寫 `builder.app_cron_manage` **或** `settings.write`）為預設，租戶營運面
  `/dashboard/settings/app-crons`（只有 `system.admin`／`settings.write` 看得到）不再是開發者的入口；
  §2.2 流程與端點表改走 App 開發面並加 `quota` 端點；403 改「印平台原文、請管理員加
  `builder.app_cron_manage`」。修正 issue 內一句誤報：`settings.write`／`settings.read` **存在**於平台權限表
  （`permission_registry.py`），`/api/v1/app-crons` 確實要它——問題是開發者角色通常沒有，且測試租戶的
  「開發人員」「開發主管」系統角色也沒有 `builder.app_cron_manage`（只能唯讀）。
  `scripts/aigo_review.py` `fetch_app_crons()` 有 app_id 時改打 App 開發面端點；SKILL.md 規則 22／Phase 0 同步
- **#38-3 Data Reference 刪除路徑**（★ prod 實打：`DELETE /api/v1/refs/{ref_id}` 204、再刪 404「引用不存在」；
  `DELETE /refs/apps/{app_id}/{ref_id}` 404「Not Found」）：dev-guide §20.4 加第 6 步，含 `PATCH /refs/{ref_id}`
- **#38-4 `/api/v1/open/*` 限流**（核自 prod tag v1.13.1 `rate_limit.py`：`OPEN_API_RATE_LIMIT = 600`，桶鍵＝API Key、
  認證後才計；未實打 600 發）：`hosted-apps.md` §5、dev-guide §23.6 節奏、troubleshooting 新列
- **#38-5 Hosted 單請求 300 秒與 max-scale 2**（核自 prod tag v1.13.1 `orchestrate/runtime.go`：`timeoutSeconds: 300`、
  `DefaultMaxScale = "2"`；未實機打滿 300 秒）：`hosted-apps.md` §2 硬規則表新增兩列、§1 適合欄加註；
  `product-line-decision.md` §2 邊界表同步；troubleshooting 兩列
- **#40 `always_on` 決策閘**（★ prod openapi `HostedAppRuntimeSettingsUpdate.always_on` `default: false`）：
  `hosted-apps.md` **新 §3.0**——預設 `false`、三種才開（容器內自跑排程／長連線／冷啟動業務上不可接受）、
  「平台排程 ≠ 需要常駐」、問 owner 業務問題不問「要不要常駐」、開了寫退場條件；SKILL.md 1.5 Hosted 分支
  加必過此閘；troubleshooting 新列「沒人用卻一直有實例」


## 1.31.1

### 自建表匯入 parked 已回報平台

- `data-operations.md` §5 與 `troubleshooting.md`：自建表目標（`self_built_table`／`new_table`）在 prod 被 import-worker
  靜默 parked 一事，2026-09-08 已走 `pre-report-self-grill.md` 六輪自審（含平台 UI「確認定稿並開始匯入」對照，
  UI 同樣 parked）後以 `report_issue.py` 回報平台——文件加註「已回報，不必重複開單」，修好前照本地腳本繞法


## 1.31.0

### 授權架構選型成為計畫必含項：內外人員共用帳號體系、以角色區分；external 收成匿名頁例外；成員／角色 playbook（issue #48）

對 ai-go `main`（2026-09-08，v1.13.1 之後）逐條核對後的結構性調整。立場一句話：**AI GO 的帳號體系是
內外人員共用的**——員工、外部經銷商、客戶都是租戶成員，用**角色**分「能做什麼」、用 app 的
**`access_role_ids`** 分「看得到哪支 app」；「誰在登入」不再決定 app 模式，**有登入者一律 internal**。

- **新 `references/member-admin.md`**（吸收 issue #48）：§0 立場；§1 授權架構選型三問與**授權架構表**；
  §2 邀請／成員／角色／app 白名單端點與權限、後端子集規則；§3 `access_role_ids` 兩條產品線對照
  （Custom `PATCH /builder/apps/{id}/settings`、Hosted `PUT /hosted-apps/{id}/access-settings`；
  Hosted `internal`＋空＝全租戶成員；不在名單者 404「App 不存在」）；§4 批次邀請固定流程與四個邊界、
  `redirect_url` 白名單（含 `/app-login/`、`/hosted-app-handoff/`）；§5 角色 CRUD；
  §6 Hosted internal 容器收到的四個身分 header（`X-Aigo-User-Id`／`Tenant-Id`／`App-Id`／`Population`，
  **無 roles／permissions**，核自 `infra/auth-proxy`）；§7 既有系統使用者搬遷；§8 403 解讀；§9 不做的事
- **SKILL.md**：源頭意圖分流表加「成員／角色管理」一列；§1.0 問題一改問**使用者群**與匿名頁；
  1.5 改「登入者一律 internal」並加 Hosted 當 Custom 後端一條；**新增計畫第 1.7 項「授權架構選型」**
  （產出授權架構表，計畫閘門要求）；第 2 項拆分理由移除「員工後台＋客戶前台拆 internal/external」；
  第 3 項受眾改承接 1.7；計畫確認後多一步「建角色、設白名單、發邀請」；規則 23 補「外部人員也是
  租戶成員」；規則 31 前端 SDK 直呼收成一種常態；里程碑驗證加角色白名單實測；description 加授權架構
- **`product-line-decision.md`**：訊號表移除「使用者兩者都有→兩個 Custom App」；問題一改「有沒有登入者、
  誰是匿名的」，`starter-external` 只剩一個進入條件（匿名頁必須留在 Custom App 內）；四象限改「有登入者
  ／只有匿名」；§5 新增 **Hosted 當 Custom 後端 → `public`＋自驗簽章**（internal proxy 要 cookie，
  Server Action 打不進；帶憑證 CORS 平台不支援）；§6 補「使用者不跟著程式搬」
- **`hosted-apps.md`**：§6 補 `access_role_ids` 欄位語意、四個身分 header、handoff 落點；
  **新 §5.1** Hosted 當 Custom 後端的做法；§11 指標改指 member-admin
- **`migration-workflow.md`**：§1 全景表加「使用者群 → 角色」欄；§2.1 問題一改寫（原系統有客戶帳號
  不是 external 的理由）；§3 加使用者搬遷指標。**`project_deconstruction_template.md`** 使用者／認證表
  改成「人一律成為租戶成員」三列。**`new_app_requirements_template.md`** §一改盤使用者群、新增授權架構表
- **`custom-app-dev-guide.md`**：§1 模式說明、§14 加定位註記（只對例外 app 有意義、無邀請／預建／角色）、
  §14.1 指向 member-admin、§26.1 模板表改「internal 預設、external 例外」
- **`data-operations.md`**：§1 加成員／角色列；§5 匯入節改寫——`/api/v1/imports` 是**預設表**批次灌資料的首選：
  csv／xlsx／json、≤20 檔、單檔 50 MB、總量 200 MB、單來源 10 萬列；狀態機（**PUT mapping 定稿＝立刻派送**，
  execute 只是重派）、`table_required_columns` 必填預警、retarget 只能在候選集內、同檔重匯不去重；
  **自建表目標（`self_built_table`／`new_table`）在 prod 被 import-worker 靜默 parked**（旗標只給 API pod，
  worker 沒有）→ 自建表改走本地腳本；引導用戶「匯出檔案丟給 AI IDE」而不是給 DB 連線字串
- `data-center.md` §7 兩處、`CONTEXT.md` App 模式、`README.md` Phase 1.5、`verification-details.md`
  第 6／7 項、`troubleshooting.md` 新增三列（特定使用者 404、邀請／建角色 403 子集規則、外部人員
  `policy_denied`）同步立場
- **`scripts/aigo_data.py`** `permission_for` 補 invitations／members／roles／access-settings／settings 五組
  推估（離線測試通過）

### 2026-09-08 測試租戶實打（擁有者帳號；建的角色／app／hosted app／匯入資料全部清掉）

- **角色**：`GET /members/roles` 回 `{items}` 含 `user_count`／`access_whitelist_count`；建 201；同名 409
  「資料重複：相同的唯一值已存在。」；不存在的權限字串 **400**「不允許的權限：xxx」（不是 403）；
  刪角色回 `access_whitelist_cleaned`／`locked` 計數；`system.admin` 可改系統角色（200）
- **邀請**：`POST /invitations` 回 `{token, chat_invite_link, user_id: null}`，落點 `/app-login/{slug}` 直達；
  `redirect_url` 三種 422 字串（含 `?`／`#`、不在白名單、含中文）；缺 email 422「invitations require either
  user_id or email」；不存在的角色 400「角色不存在或不屬於此租戶：<id>」；同 email 重發舊張 `status: expired`、
  `expires_at`＝48h；`DELETE` 204、不存在 404「Invitation not found.」；**`POST /members` 不寄信時回 `id: null`**
  （受邀者註冊前沒有成員列）
- **白名單**：Custom `PATCH /builder/apps/{id}/settings` 200 讀回一致；非 UUID 400「access_role_ids 含無效的角色 ID
  （需為 UUID 格式）」；internal 開匿名 400「Internal App 不支援匿名存取」。Hosted `PUT /access-settings`
  `internal`＋角色 200；`public`＋角色 **422「public visibility 不可搭配 access_role_ids」**
- **匯入**：existing_table（suppliers）3 列 10 秒 `completed`；self_built_table 與 new_table **parked**（見上）；
  必填欄缺值整批 `failed`＋逐列 `error_detail`；副檔名不支援回 200 但 job `failed`；同檔重匯 6 列不去重；
  worker 冷啟動 40 秒～1.5 分鐘
- `aigo_data.py perm-check` 五組新路徑推估與實際權限一致

未實打（測試租戶只有擁有者帳號）：子集規則 403 本體、受限帳號開 app 的 404、`PUT /members/{id}`、
`resend-invite`、外部角色的 `policy_denied`、tier-2 欄位落延伸欄位——皆核自原始碼。


## 1.30.1

### PR #46 審查回修：hide 欄位狀態碼、CHANGELOG 結構、Hosted 兩處自相矛盾、測試租戶識別

對 1.30.0 逐條回對平台原始碼後的修正，全部是文件面，`scripts/` 未動：

- **hide 欄位進 `filters`／`order_by` 的狀態碼寫錯**（`custom-app-dev-guide.md` §27.2 兩處、
  `troubleshooting.md` 一列）：原文寫 403 `policy_invalid`；核自 `app_data_proxy.py`——`filters`／search
  指到 hide 欄位回 **400「未授權的篩選欄位」**（與欄位不存在同形），`order_by` 指到 hide 欄位被
  **靜默略過**退回預設排序；`policy_invalid` 只在規則自身引用越權欄位、或所有可投影欄位全被 hide 時出現
- **1.30.0 節結構**：「實打」小節誤插在清單中間，三顆 bullet 與一顆縮排子項被切到小節底下——歸位
- **`hosted-apps.md` §11**：restart／interpret 列補「v1.13.0 已補」，與 redeploy 列一致；**§3.4** 改為
  「正向半邊已實打、負向半邊未實打」，不再與 §3.2 矛盾
- **測試租戶識別**：1.30.0 新增的四處「demo 租戶」改回「測試租戶」（README 既有的網址範例未動）
- **順手修的三個日期**（各差一天，核自平台 git log）：Storage 路徑逃出 403 是 09-02（#1371）、
  413／401 兩條是 09-04（#1441）、深連結與「找不到此應用」三層是 09-03（#1424）
- **§15.1 同形 404 範圍收窄**：pub 面與 app 使用者 token 兩條路徑字串同為「App 不存在或尚未發布」；
  發終端使用者憑證的 auth 入口回「App 不存在」——同 404、字串不同，判斷用狀態碼

未動的兩條（待決）：`CUSTOM_DATA_SDK.updateRecord()` 仍送 PUT 到只收 PATCH 的 `/data/records/{id}`
（#1416 未修到，skill 也未提）；平台 09-08 已出 v1.13.1，prod 是否已切未查。


## 1.30.0

### 對齊平台 2026-09-01～09-07 main（v1.13.x）：Auth gate、匿名核可、timeout 上限、CodeBuild、per-app 資源

平台 monorepo 一週內 merge 了 114 個 commit，逐條篩出對 app 開發者可見的行為變更，
每條都核對過原始碼或 ADR／spec 才落文。**prod 現況以 v1.13.0（2026-09-07 10:35Z 部署成功）為準**：
tag 落在 main 倒數第二個 commit，本節所有端點與 schema 欄位皆以 prod 公開 `openapi.json` 實查在線；
只有靠環境旗標的兩條例外（`POLICY_GATE_MODE` prod off、`TENANT_DEDICATED_NODES` UAT／prod 皆
ops-only）與「程式在、行為未實打」的少數項目另行標明。

- **租戶資料存取規則（Auth gate v1）**——新 `custom-app-dev-guide.md` **§27**：租戶自訂
  「角色 × 表 × 動詞 → deny／`where_dsl` 列過濾／`hide_columns` 欄遮蔽」，由**平台**在資料函式層
  執法。app 會撞到的形狀：403 body 帶 `reason`（`policy_denied`｜`hidden_column_write`｜
  `policy_invalid`｜`runner_unavailable`｜`app_data_access_suspended`）＋`rule_id`；`restrict`
  命中時 200 但少列少欄、hide 欄位不得出現在 `filters`／`sort`／`order_by`；封鎖時 runtime host
  整頁「資料存取暫停」。**`POLICY_GATE_MODE` UAT＝on、prod＝off（2026-09-07）**。
  與 `platform-behaviors.md` §12 的 app 軸權限閘是兩條軸，**403 有沒有 `reason` 是分辨鍵**
  （SKILL.md 錯誤處理、self-grill Q2.3、troubleshooting 三列、CONTEXT.md 同步）。
  §27.3 另記 v0 的 `auth_gate` 自律模板：它不在請求路徑上，且依賴的 `ctx.user_role_ids`
  **runner 尚未接線**（分支未 merge）——今天退化成「無角色」，不要再擴 v0
- **匿名存取要平台核可**——`custom-app-dev-guide.md` **§15.1**：開 `allow_anonymous_access`
  ≠ 能對外服務；租戶端 `POST /apps/{id}/anonymous-access-request`（`builder.manage_access`）
  送申請，三態（未申請／已送出／已核可）對應 `anonymous_access_requested_at`／`approved_at`；
  **核可前匿名訪客與 app 使用者 token 都拿到與「App 不存在」同形的 404**，開發者租戶身分預覽不受
  影響——「我測都正常、用戶說 404」正是這個狀態。無 SLA，計畫要列成「等平台」的一步
  （SKILL.md Phase 1.5、`product-line-decision.md` §6、CONTEXT.md、self-grill Q2.4、troubleshooting）
- **Action 執行逾時真的生效了**：manifest `timeout_ms` 1000～**120000** 自 #1518（2026-09-07）起
  作為 runner ceiling（修正前恆 30 秒）。`custom-app-dev-guide.md` §7 新段；`event-triggers.md`
  §1.6／§2.6 改口——**cron 實務上限 120 秒不是 280**（dispatcher 300 秒只是外層）；troubleshooting
  「Action 超時」列改寫；ceiling 在 publish 時寫入，**v1.13.0 前發布的 app 要 republish 才換上新值**
- **Custom App 執行模式租戶自選（T43）**——新 `custom-app-dev-guide.md` **§28**：
  `PATCH /builder/apps/{id}/runtime-settings {"always_on"}`（`builder.publish`；免費 403
  `ALWAYS_ON_REQUIRES_PAID_PLAN`、未發布 422、綁通訊渠道一律常駐 `locked_reason`）；草稿固定冷啟動；
  Builder App 的 per-app CPU／記憶體上限**沒有租戶 UI**。troubleshooting 新列「閒置後第一發很慢」
- **§27.1 補**：拒絕紀錄查詢 `GET /apps/{id}/data-policy/decision-logs`／`GET /data-policy/decision-counts`、
  租戶級規則管理頁 `/dashboard/settings/data-policy`（T69）、`where_dsl` 引用 `id` 在 ERP read 隱含放行
  但 write 面仍 fail-closed（T72）、ADR 0029 定位（租戶自擔授權責任）
- **前端 `db.ts` 的 `update()` 動詞 PUT→PATCH**（#1416，2026-09-01）：舊模板送 PUT 恆回 405、
  更新從未生效。SKILL.md 規則 12 加註、troubleshooting 新列
- **503 帶 `quota_hint`**（#1437）：runner 不可達的 503 若租戶運算配額 ≥90% 會在 `detail` 後接配額
  說明並帶頂層 `quota_hint`——不是 code 問題，SKILL.md 錯誤處理與 troubleshooting 各加一列
- **Storage API 九個坑**——`custom-app-dev-guide.md` §12 新表（核自平台 `custom-app-storage.md`）：
  413 兩來源（單檔 100 MB／整包 109 MiB）、401 在讀 body 前就回、路徑逃出前綴一律 403
  （2026-09-01 起，含 `..`）、`list` 非遞迴且 folder 對帳規則、`GET /url` 404 是第二條對帳路徑、
  key ≤1024 bytes UTF-8、`url` 取不到是 `""` 不是 `null`
- **Hosted App**（`hosted-apps.md`）：
  - 建置引擎搬 **AWS CodeBuild**（ADR 0028；UAT 2026-09-05、prod v1.13.0 起）：§1 表、§2 建置包絡
    改「整台 8 GiB、OOM 只在整台用盡」並在建置記憶體陷阱補按 8 GiB 重算的提醒；建置期 env 失敗提示
    指向「環境變數」頁建置階段（§4）
  - 容器 capabilities **`drop ALL` ＋恆補 `NET_BIND_SERVICE`**（ADR 0017 2026-09-05 修訂）、
    gVisor 已拆除：§2 新列；`exec caddy: operation not permitted` 進 §10 與 troubleshooting
  - **§4.1 per-app 執行上限 `resources`**（T35／T47）：`PUT /runtime-settings` 全量語意
    **四欄→五欄**；四鍵 quantity 形狀、request 下限 50m／64Mi、limit 可留 null＝整台、
    422 `RESOURCE_LIMIT_EXCEEDS_MACHINE`（帶 `hint_instance_type`）、403
    `RESOURCES_REQUIRE_DEDICATED_NODES`；Builder App 無租戶 UI
  - **記錄分頁改版**（§8、§11）：`GET /{id}/runtime-starts`（7 天內容器執行段＋`reason`
    idle／rollout／crash／unknown，**idle 是推定**）、`GET …/runtime-starts/{pod_name}/logs`、
    `POST /{id}/logs/interpret-line`；三支收 Deploy Token
  - **租戶 app 數配額已移除**（T49，2026-09-07）：§10 的 429 `hosted_app_quota_exceeded` 只剩
    建置時限一種成因；新增「機器保留量已滿」列
  - **§5 Open Proxy 也在 Auth gate 執法範圍**（T66）：app 身分無 user，`restrict` 規則用到 `$user.*`
    即整列 deny——租戶開「依員工過濾」規則時 hosted app 直接 403；troubleshooting 新列
  - **§3.2 `active` 語意收緊**（#1464，prod v1.13.0 起）：結清改等新 revision 真的接手，起不來落 `failed`；
    §3.4 的 version marker 要求因尚未實打驗證不放寬
  - §6 記 #1421 修掉的「已登入使用者被匿名枚舉佇列擋成 503」；§8 補 App 佔用表 `restartCount`／
    `lastTerminatedReason`「有狀況」標記與五種原因的白話對照（T48）
  - 檔頭「部署落差」段改寫：prod＝v1.13.0，2026-09-01／02 的 404 清單標為已補齊的歷史紀錄，
    另列兩條靠旗標不靠版本的能力；troubleshooting「端點 404」列改為以 prod `openapi.json` 為判準
  - 檔頭部署落差段補 2026-09-07 main 三塊的判讀提示
- `platform-behaviors.md` §12：`api-grants` 端點 v1.13.0 起 prod 已有（2026-09-01 的 404 紀錄改為歷史）
- **平台行為補遺**（`platform-behaviors.md`）：§1.5 proxy 面新增 `not_in`（第 12 個運算子）；
  §6.2 新段——深連結 `?next=` 承載 search+hash（2026-09-02 起 HashRouter 頁面狀態可分享）與
  「找不到此應用」依身分三層；§12 末補人軸／app 軸兩條線的指引
- troubleshooting 另補：整頁「資料存取暫停」、restrict 少列少欄是預期、前端 422 通用提示
  （API `detail` 仍完整）、深連結落首頁＝部署落差、「找不到此應用」先問登入與租戶、
  Hosted 記錄頁 `idle` 不是「沒問題」

### 2026-09-08 prod 測試租戶實打（自清，建的 app 全刪）

以本版文字為腳本逐項對打，全部與文件一致，實測值回填到各節「實打」註記：

- Custom App：manifest `timeout_ms: 120000` 的 `sleep(45)` action 成功（`duration_ms 45001`）；
  發布前 `PATCH runtime-settings` 422 `RUNTIME_SETTINGS_REQUIRE_PUBLISHED`、發布後常駐開關 200；
  新建 app 的 `src/db.ts` 已是 `PATCH`；internal 開匿名 400；external 開旗標後公開端點 404 與不存在
  **逐位元組同形**、申請冪等、`requested_by` 不外露；規則 CRUD／enabled／mode／explain／decision-logs
  ／decision-counts 全 2xx（`policy_gate_mode: off`）；storage 六個行為（含路徑逃出 403、刪除冪等、
  刪後 404）；proxy `not_in` 200、`neq` 400
- Hosted App：`index.html` tarball → CodeBuild（`build_job_name` `codebuild:ap-northeast-1:…`）46 秒
  `active`、caddy 靜態站 200；`runtime-starts`／`runtime-logs` 有資料；`runtime-settings` GET 含
  `resources`，帶 `resources` 的 PUT 403 `RESOURCES_REQUIRE_DEDICATED_NODES`、五欄 PUT 200；
  `GET /tenant/compute/apps` 每列含 `restartCount`／`lastTerminatedReason`；刪除回 `teardown: completed`
- 新增兩條文件沒寫清的坑：storage `path` 必須是完整 key（相對路徑 403 不是 404）、
  `app-scoped-token` 打不了 `/ext/storage`（401）；`refs` 的 `columns` 空陣列＝之後查詢恆 400
- 未實打（負向案例）：CodeBuild OOM／無日誌矩陣、rollout 起不來落 `failed`、gate on 時的 403 body（prod off）
## 1.29.0

### 回報：開單前查既有卡（preflight，第一階段只記錄）

`report_issue.py submit` 送出前先呼叫回報系統的 `POST /api/tickets/preflight`，問
「同症狀是否已有卡、修好了沒」，印一行結果並帶 `preflight_id` 送出；成功後回報
`outcome=submitted`。這是 CSM Manager #45／#46 的 skill 側（本 repo #43）第一階段：

- **不改流程**：不論 decision 是 `fixed`／`tracking`／`none` 都照常送出。這一階段在累積
  「判得準不準」——伺服器端歸卡上線至今零命中實績，而誤命中的代價是 AI 對使用者說
  「修好了我直接繼續」然後重試失敗。命中率看得到再開第二階段（一句帶過、自動重試、續行）
- 帶 `preflight_id` 讓伺服器直接附掛處理中的卡（省一次 LLM 歸卡）、或把「已修復但重試
  失敗」當復發處理；伺服器不認（400／409）就退回不帶它再送一次
- best-effort：查卡任何失敗都靜靜略過，不影響回報；`URFIT_TICKET_PREFLIGHT=0` 可關
- SKILL.md 與 `references/issue-reporting.md` 明寫：**不要據那一行自行決定不報或告訴使用者
  已修好**

## 1.28.0

### 更新覆蓋規範改為強制同步：發現遠端較新即覆蓋本機所有安裝，不徵詢使用者

**行為變更（使用者端）**：`scripts/check_update.py` 從「發現新版→提示→由 AI 詢問是否更新」
改為「發現新版→直接把本機所有已註冊安裝強制同步到遠端 main」。本地修改、分岔的 commit、
多出來的檔案一律被遠端取代；不問、不等回覆。舊版腳本仍會先問一次——那是舊版的行為，
同意之後就進入本規範。

- **git 安裝**：`git fetch origin main`（origin 不可用時直接用官方 URL）→
  `git reset --hard FETCH_HEAD` → `git clean -fd`（不加 `-x`，gitignore 的 `.venv/`、`.aigo/`
  不動；`.claude/` 另外排除，裡面可能有 worktree）。git 指令失敗（沒裝 git）退回 zip 鏡像
- **複製式安裝（skills CLI）**：不再只印 `npx skills update` 指令——下載遠端 `main.zip`
  鏡像覆蓋，遠端有的全寫入，本地多出來的刪除（`.git`／`.venv`／`.aigo`／`.claude`／`.env`／
  `__pycache__`／`node_modules` 例外）。先在暫存目錄整包展開驗證，再動安裝目錄，不會半套
- **唯一不碰的是開發用副本**：本地版本高於遠端、或 git 副本不在 `main`／`master` 分支，
  視為正在改 skill 的工作區（維護者已 bump 未發布、功能分支、worktree），略過並標示
  「開發副本，略過」。這是保護未合併的工作，不是給使用者留本地修改的開關
- **節流語意改動**：原本抑制「同一組版本差 3 小時內重複提示」，現在改抑制「同一份安裝對
  同一個遠端版本 3 小時內同步失敗後重試」；同步成功後本地＝遠端自然不再觸發。
  狀態檔 `installs[path].last_result` 改為 `last_sync`（`remote`／`ok`／`at`）
- **旗標**：預設就是同步全部；新增 `--check-only`（只報告，維護者／CI 用）；
  `--apply`／`--apply-all` 仍接受但等同預設。新增環境變數 `AIGO_UPDATE_STATE_FILE`
  改狀態檔位置（測試用）
- **輸出**：只在「已同步」或「失敗」時出聲；失敗列出手動指令，含破壞性變更時加警語。
  stdout 導向管線時改 UTF-8、編不出的字元換 `?`——修掉 Windows cp950 主控台印 CHANGELOG
  裡的 `≤` 直接炸掉、且炸在同步完成之後的問題
- **SKILL.md Phase -1 改寫**：agent 的工作從「告知並詢問」改為「重新讀取 SKILL.md、告知
  版本落差與變更摘要」；明文禁止為了保住本地修改而跳過本階段或改用 `--check-only`。
  改 skill 內容走 repo 的 PR，本機副本只能是遠端 main 的鏡像
- **hook 範本** `timeout` 10 → 120：同步要 fetch 或下載 zip；沒新版時仍 3 秒內結束
- `pre-report-self-grill.md` Q1.1 對齊：仍落後只剩「失敗」與「開發副本」兩種可能

## 1.27.0

### 三條意圖線的閘門補齊：資料操作線的寫入閘門、Hosted 的部署後驗證、自審樹的本線分支

對三條意圖線（新建／遷入／資料操作）逐格核對 skill 自己的骨架——版本檢查、意圖判讀、
強制盤點、不可逆閘門、執行規則、驗證閘門、失敗入口、自審回報——找出三個閘門缺口與三處填空。
新建線與遷入線八格皆齊（遷入的資料面驗證在 `custom-app-dev-guide.md` §23.5，非缺口）；
缺的是**判成 Hosted 之後**與**資料操作線**這兩段：

- **`data-operations.md` 新增 §3.5 寫入閘門（★ 不可逆）**：開發線的不可逆決策（`access_mode`）
  擋在計畫閘門後，這條線的不可逆是**直接改寫唯一一份正式資料**——沒有沙箱、沒有草稿版、
  沒有發布快照可回退，遷入線匯錯還能重匯，這條線不能。四步缺一不動手：估影響面（同一組
  filter 先 GET 出筆數，算不出就不准跑批次）→ 取現值備份（`--out` 存本地 JSON；刪除後
  GET 404，本 skill 未知還原端點，備份是唯一退路）→ 先試一筆再分批 ≤100 逐批讀回 →
  把租戶／身分／端點／body／影響筆數／備份路徑一起給用戶確認。**DELETE 預設不做**，
  先問能不能用狀態欄代替
- **`data-operations.md` 新增 §7 出口**：本檔原本零連結指向 `troubleshooting.md`／
  `pre-report-self-grill.md`（全檔三個連結全指 dev-guide），撞牆時只能靠 SKILL.md 的全域段落
  兜底。補上出口並列出速查表中對本線有效的列
- **`pre-report-self-grill.md` 補 Q6.1b（★ 修一道結構性失效的閘）**：第 6 輪 Q6.1
  「去掉 app 程式碼、用純 API 重現」在資料操作線上**恆真**——這條線本來就是純 API，
  全樹最強的「app 側 vs 平台側」濾網在此自動通過，誤報成本高於另兩線。替代判準：
  ① 平台 UI 同帳號同操作對照（UI 也失敗才可能是平台側）② Q6.4 變因對照再多換一顆帳號。
  §3 送出條件 (a)「用純 API 穩定重現」有同一個破口，一併註明本線不適用、改以 UI 對照為準
- **`pre-report-self-grill.md` 補 Q3.7 資料操作線契約**：`perm-check` 是推估不是權威
  （✅ 仍可能 403）、Meta key ≠ proxy／refs 面表名（`crm_clients` vs `customers`）、
  分頁形狀分兩派（`skip`+`limit` vs `page`+`page_size`）、匯出白名單只有 6 張且自建表不在範圍
- **`hosted-apps.md` 新增 §3.4 部署後驗證閘門（＝Phase 4.2 的等價物）**：原本只有動手前的
  形狀硬規則（§2）與失敗診斷（§8／§10），部署後沒有任何條目化閘門，全檔唯一的驗證動作是
  §3.2 一句 version marker。新增「變更範圍 → 先等多久 → 必驗項目」矩陣（env／程式碼／
  首次部署／自訂網域）與驗證後決策表；`deployment: active` 不等於對外服務的是這一版
  （rollout 失敗對外仍是舊 revision，平台不顯示服務中版本），**任一項未通過不得對外交付**
- **`troubleshooting.md` 補 5 列資料操作線症狀**：模組 REST 分頁抓不齊、匯出 `/download`
  409、匯出送自建表 failed、`perm-check` ✅ 仍 403、Git Bash MSYS 路徑改寫；
  「查不到怎麼辦」加指向 `data-operations.md`
- **措辭修正**：SKILL.md 源頭意圖分流「兩條路」→「三條線」（1.18.0 寫於兩列時代，
  1.23.0 加第三列時未同步）；意圖分流表、驗證流程快速參照、參考文件表補上兩道新閘門的指標；
  `migration-workflow.md` §2.1 與 `product-line-decision.md` 的「不走 Phase 2–4」補上
  「驗證閘門改用 hosted-apps §3.4」
- **README 目錄補漏**：`hosted-apps.md` 與 `platform-behaviors.md` 原本完全不在目錄樹裡

## 1.26.0

### 新建 App 需求盤點：用戶的一句話是題目不是需求，先盤再判產品線

遷入線有 §2.0 stack 盤點→§2.1 兩問四象限→不可逆警示的完整鏈，新建線只有一行技術啟發式
（「需要常駐進程／WebSocket → Hosted」），沒有引導用戶說完整需求的步驟，`access_mode`
不可逆這件事也只在遷入分支有閘門；Phase 1 建 app 選模板的時點還在計畫之前。本版把新建鏈路
補到與遷入線對稱：

- **SKILL.md Phase 1.5 改名「需求盤點與實作計畫」，新增 §1.0 需求盤點**（新建情景的起手）：
  四問（誰在用→`access_mode`／做什麼→功能與資料實體／對外面向→公開 web 資產／機制需求→
  逐條核對 **Custom App 能力邊界表**：常駐進程、長任務上限、自選框架、自有網域與 SEO、
  前端框架限制、交易／JOIN／條件式 UPDATE、動態 schema、單檔 100 MB、Node 原生模組、直連 DB），
  每條標「Hosted」或「改設計」——標「兩條線都沒有」的資料層邊界換 Hosted 也解決不了；
  資訊不足就問不猜、答不出給選項；產出固定格式的「需求形狀結論」
- **新增 `references/product-line-decision.md`——兩條路共用的產品線與模式判斷 SSOT**（SKILL.md 第 1.5 項
  只留骨架與指標）：**預設立場「一個 Custom App」**與四種偏離訊號（功能群目的不同→多 Custom；使用者兩者都有→
  internal+external；公開 web 資產→Hosted；邊界命中→Hosted 或混合）、Custom App 能力邊界核對表、
  兩問四象限（先問誰在登入、再看形狀）、四象限落點、**混合方案分工原則**（共用資料落平台側、Hosted 走
  Open Proxy、不硬併、不得把 DB 立成 Hosted）、不可逆與硬前提（`access_mode` 建立後不可改→app 等計畫確認後
  才建；`internal` 不能開匿名要當場攤開）；產出 **app 分配表**（預設就是一列 Custom `starter-internal`）
- **第 2 項拆分觸發擴為三種**：功能群目的不同、使用者兩者都有、部分功能命中 Hosted 邊界；
  每個 app 各自過兩問。第 3 項受眾承接問題一不重問；第 4 項單頁／多頁在計畫定案，Phase 2 不另問
- **計畫閘門**：四問未齊或缺需求形狀結論／app 分配表不算完成計畫；確認後才是建 app 的唯一時點。
  Phase 1 步驟 3 與 dev-guide §26.1 同步「模板 slug 照 app 分配表，不臨場判」
- **`migration-workflow.md` §2.1 去重**：只保留遷入特有輸入（原系統誰在登入、§2.0 stack 形狀×面向
  對照表），問題一落點／四象限／不可逆警示指向 `product-line-decision.md`
- **新增 `resources/new_app_requirements_template.md`**：四問填表、邊界核對表、需求形狀結論、
  app 分配表——對稱遷入線的 `project_deconstruction_template.md`
- 源頭意圖分流表「開發新 App」列改寫；README 加 Phase 1.5 列、新 reference 與新模板

## 1.25.0

### 回報前自審閘門：預設平台必定正確，失敗預設是自己操作有誤

平台事故單發錯的代價很高（2026-09-03 曾因快取污染的假對照誤發兩張）。1.24.0 先補了「回報前先窮盡使用者側的可能」四步；本版把它擴成完整協定並在工具層強制：把
Matt Pocock `grilling` skill 的機制（設計樹＋前沿＋輪次＋每題附答）反向套用：
不是 AI 逼問使用者的計畫，而是 **AI 逼問自己的操作**，每個分支都要用證據排除「是我錯」。

- **新增 `references/pre-report-self-grill.md`**：六輪排除樹（讀完錯誤→版本與部署落差→
  身分與環境→請求契約→生命週期→文件核對→最小重現），依前沿順序上游未清不進下游；
  每題附「指令＋輸出節錄」，沒有證據視同未排除；終止需前沿為空＋（純 API 穩定重現且與
  文件明文矛盾｜5xx／硬阻斷）；不確定就不報，交使用者決定；送出前仍要使用者確認
- **`report_issue.py submit` 工具層強制**：新增 `--ruled-out`／`--ruled-out-file`
  （已排除清單，每行一項、至少 3 項），缺少即拒收並印出六輪摘要、不建卡；
  `--body-file` 內文須含「已排除」段。清單會以「## 已排除（回報前自審）」附在卡片裡供 triage
- SKILL.md「問題回報」節冠上預設立場與硬規則；`issue-reporting.md` 檔頭指標＋
  BDD 第 5 項「已排除清單」＋指令範例；`troubleshooting.md` 檔頭指向自審；README 目錄同步

## 1.24.0

### 發布前語意檢查：esbuild compile 不驗型別，TDZ 白畫面在發布前就攔下（issue #35）

`const` 在宣告前被使用（TS2448）這類語意錯誤 compile 全綠、發布後 runtime 白畫面，
console 只有 `Cannot access 'Ee' before initialization` 加 esm.sh scheduler 的堆疊——
症狀指向平台，真因在自家 bundle。平台的 Builder AI 有 `check_types` 但無 REST 端點，本版在本機補同一道閘：

- **新增 `scripts/aigo_typecheck.py`**：src 落臨時目錄＋esbuild loader 的資產宣告，`npx tsc --noEmit`
  （tsconfig 對齊平台 typecheck.py）；只阻擋會炸 runtime 的語意錯誤（TS2448／2454／2451／2300／2304／2552／語法），
  缺 @types 的噪音只列不擋；`--strict` 全擋；無 Node 略過並提示
- **SKILL.md Phase 4 加步驟 1.5**（前端有實質修改時必跑）與 compile 綠燈的語意說明；
  verification-details 加 ⓪ 語意檢查
- **troubleshooting**：白畫面＋TDZ 堆疊的判讀條目（定位法、修法）；「查不到怎麼辦」加第 4 點
  「懷疑平台全域故障前先做乾淨對照」（同 profile 多 app 交叉比對會被快取污染）
- **issue-reporting**：新增「回報前先窮盡使用者側的可能」四步（乾淨對照、回到自己的產物、
  確認平台既有路徑、乾淨環境可重現才回報）
- dev-guide §17 白屏列同步

## 1.23.0

### 資料操作模式：不開發 app，以使用者身分直接讀寫 AI GO 資料

用戶的目的是操作資料（查、改、批次、匯出）而不是做 app 時，原本只有自建表這一半能直接做，
預設表寫入一定要繞經 app proxy 加 Data Reference。本版把「登入使用者身分」的四條資料面
補齊並實測（2026-09-03 測試租戶，讀寫刪往返）：

- **新增 `references/data-operations.md`**：預設表走各模組 REST（`<module>.read/write/delete`，
  與平台 UI 同一套 RBAC）；自建表 records（`builder.access` 一刀切、無表級 ACL）；
  匯出白名單 6 張預設表（自建表不在範圍、`custom_table` 指舊 CustomObject）；
  Meta API 值域（Meta key ≠ proxy 表名，客戶是 `crm_clients`）；固定流程與不做的事
- **新增 `scripts/aigo_data.py`**：`me`（身分與 permissions）、`perm-check`（路徑前綴 → 權限推估，
  `system.admin` 直通）、`openapi paths|op|schema`（路由權威是免登入的 `/api/v1/openapi.json`，
  733 條路徑，不手抄；body schema 展開成欄位與必填）、`call`（通用呼叫，`--all` 依 openapi 分頁形狀
  自動翻頁：`skip/limit` 與 `page/page_size` 模組間不一致；寫入前印租戶與身分並先 perm-check）、
  `export`（建任務、輪詢、下載）、`meta tables|table`
- **SKILL.md 源頭意圖分流加第三種意圖「資料操作，不開發 app」**：不進 Phase 0 VFS review、
  不建 app、不走 proxy；偵測訊號與權限說明義務
- 拆掉兩條「prod 待驗證」註記：Meta API 的 options（dev-guide §20.2）、records 面 date 範圍查詢
  （platform-behaviors §1.5）——測試租戶實測皆可用

## 1.22.0

### 工作區 app 登錄表：一台裝置、一份 skill、N 租戶 N app，同一套機制

原本 `.aigo/config.json` 一個專案綁一個 Custom App，在遷入分流出的 1..n app、
Hosted＋Custom 混合案、跨 app 共用自建表、純資料 CRUD 這四種情境下都不成立。
本版改成三層模型：裝置（skill 一份＋`~/.aigo/.env`）→ 工作區（一個目錄＝一個租戶）
→ app 登錄表（0..n 筆，alias 當 key）。不分使用者類型，多一個租戶就多一個目錄、
多一個 app 就多一筆。

- **`config.json` schema 2**：`apps: {alias: {kind, id, slug, name, access_mode, app_domain,
  integration_id, path}}` ＋ `default_app`。舊格式讀入時自動升級成 `apps.default` 並鏡射回
  v1 鍵（既有呼叫端不用改）；`aigo_auth.py config migrate` 才改寫檔案並留 `.v1.bak`
- **`resolve_app()` 是取目標 app 的唯一入口**：`--app`／`AIGO_APP`（alias、UUID 或前綴）→
  `AIGO_APP_ID`（相容）→ `default_app` → 登錄表唯一一筆 → 多筆未指定**報錯列出 alias，不猜**。
  回 `AppRef`，`.describe()` 給寫入前要印的目標行；`assert_remote_matches()` 比對遠端 id／name
- **工作區往上找**：`find_workspace()` 從 cwd 往上找最近的 `.aigo/config.json`，
  Hosted 原始碼子目錄下也找得到；token.json、工作區 `.env` 都跟工作區走
- **CLI**：`setup-workspace <dir>`（拒絕 skill 安裝目錄）、`app add|list|default|remove`
  （add 打平台自動判定 custom／hosted 並回填 slug／name／access_mode／integration_id）、
  `run <alias> -- <cmd>`（把工作區 `.env` 的 `AIGO_DEPLOY_TOKEN__<ALIAS>` 匯出成 CLI 用的
  `AIGO_DEPLOY_TOKEN`，多租戶裝置上 CLI 的全域 profile 不再互相蓋）、`config migrate`
- **`status` 成為唯一診斷入口**：工作區、租戶與來源層、身分與來源檔、app 表（含預設標記與
  deploy-token 有無）、token、三種警告（工作區在 skill 目錄內、本機多份安裝、shell 覆寫租戶與 config 不同）
- `full_deploy()` 動手前印目標行；兩支測試跑器改走 `resolve_app`（`AIGO_APP_ID` 仍相容）；
  `check_update.py` 註冊表超過一份安裝時提醒合併
- 機器級 `.env` 範本改寫：`AIGO_TENANT` 標為可選，多租戶機器建議留空讓缺 config 的目錄明確報錯
- SKILL.md Phase 0／1／1.5／4 與 README 同步：三層模型表、佈局圖、選 app 順序、指令表

## 1.21.0

### Hosted App 遷入實戰回填：綁定介面、無日誌建置失敗、`/open` 雙平面、relation 限制、預設表值域

來源：2026-09-02 一個 Next.js 16 ＋ 56 表 Tier 3 系統整套遷入 Hosted App 的實測
（repo issue #25–#31），逐條對平台原始碼核對後收錄。平台側缺陷（500 而非 422、
OOM 無日誌、rollout 失敗不顯示服務中版本）另回報平台，本版只寫症狀與繞法。

- **hosted-apps §2**：「綁 0.0.0.0」看的是框架實際綁的介面——k8s 把 `HOSTNAME` 設成 pod 名，
  Next standalone 一類以 `HOSTNAME` 決定 bind 的框架要 `ENV HOSTNAME=0.0.0.0`；
  症狀是競態（ksvc ready 逾時但 runtime-logs 顯示 Ready、`Local:` 印 pod 名）；
  後遺症是 request 推算的 origin 變 `https://0.0.0.0:8080`，對外網址一律走 env。
  建置記憶體陷阱：限制 worker 數、heap 設包絡 60–65%，設太高反而無日誌 OOM
- **hosted-apps §3.2／§4**：env 變更「立即生效」改為「不重建但需數分鐘傳播（實測 1–6 分鐘）」；
  `apply_state` 只在 PUT 回、`applied` 不保證容器已換版；新增「遷入時要重新提供的 env 清單」
  （對外網址、session 密鑰、第三方憑證）；無日誌失敗先原樣重送；rollout 失敗期間對外是舊 revision
- **hosted-apps §5**：容器內兩個資料平面都要 `/open` 前綴（照 data-center §7 抄必 401）；
  預設表引用可用 API `POST /refs/apps/{整合 id}`（不是 hosted app id；session-only），
  403 訊息裡的「App」指隨附整合。§8 建置日誌全空的處置順序；§10／§11 補對照列與 prod 404 註記；
  檔頭部署落差追加 restart／redeploy／interpret 2026-09-02 仍 404
- **platform-behaviors 新增 §1.5**：自建表 records 與預設表 proxy 兩平面的過濾契約對照——
  `field` vs `column`、運算子集合（只有 proxy 有 `in`）、錯誤反應相反
  （records 422 列合法集合；proxy 對 `where` 等錯形狀 **200 回整表**）
- **data-center §3**：relation → 預設表只有部分表可解析且無法事先查（prod 8 張只有 `sale_orders` 過），
  規劃時一律當不支援、改 `text` 存 UUID；relation → 自建表無 cascade；`select.options` 純字串陣列；
  單欄 unique 409 是唯一的伺服器端 CAS、預設表沒有。§7 補 `/open` 平面、POST body 必包 `{data}`、
  `gte/lte` 依型別限縮
- **dev-guide §20.2**：columns 端點四個鍵看不到 CHECK 值域，寫錯直接 500；補 Meta API
  （`/data-center/meta/tables/{key}`，核自原始碼、prod 未驗證）與 **§20.2.1 常用預設表值域表**
  （核自原始碼 `CheckConstraint`）。§19 選擇矩陣、§23.7 降級表同步
- **dev-guide 新增 §23.9**：沒有交易／JOIN／條件式 UPDATE 時的改寫指引——`claim`＋409 模式表
  （複合鍵、upsert、樂觀鎖、租約鎖、計數器每格一列、webhook inbox 兩階段）與 JOIN 替代表
  （`in` 只在 proxy 面、反正規化是必需、不做跨請求快取）
- **migration-workflow §2.4**：外鍵映射三條——指向預設表一律 `text`、約束改寫在映射階段決定、
  值域先對表；**troubleshooting** 新增 13 列對照

## 1.20.1

### 移除 Hosted App 免費／付費與名額的前置描述——撞到上限再查表

分流與指引不再要求使用者先理解 Hosted App 的方案分級與配額：

- migration-workflow §2.1：整搬行與警示區的「付費檔限定＋每租戶 5 名額」移除
- hosted-apps §1 的「付費檔限定」bullet、CLI `--slug` 的「吃配額名額」、
  §7.1 禁令段的「占用名額」附帶理由——移除
- **§10 錯誤碼對照表保留不動**（403 `hosted_app_requires_paid_plan`、
  429 `hosted_app_quota_exceeded`）：撞到時查表得到完整解釋與處置，
  這正是「撞到上限再說」的承接點

## 1.20.0

### 遷入分流第三軸：「公開 web 資產 vs 應用介面」——官網不再被錯導向 Custom App

官網、電商 storefront 這類公開站在舊分流會落到「純前端 → Custom App」，
被裝進 `/runtime` 網址＋HashRouter＋`/pub`——無自有網域、SEO 做不了，
技術上能動、產品上是錯的。本版補上面向判斷：

- **§2.0 前端盤點加「面向」判讀**：應用介面（登入後使用的工具）vs
  公開 web 資產（訊號：自有網域、SEO／社群分享卡、內容行銷頁、匿名是主要動線）
- **§2.1 問題二純前端行拆兩支**：應用介面 → Custom App；
  公開 web 資產 → **Hosted App**（zbpack 任意棧含靜態站、§9 綁自訂網域）
- **「自有網域／SEO 凌駕形狀判斷」**：需要自有網域的公開站不論後端形狀
  一律偏 Hosted——並補回 1.18.0 改版時從問題二遺失的「自訂網域」訊號
- **混合情景明文拆法**：官網 Hosted＋系統 Custom，共用資料落平台側
  （自建表／Open Proxy），不硬併成一個 app
- **dev-guide §15 補 `/pub` 定位**：只適合 external app 的少數公開頁
  （表單、查詢、分享檢視），不承載整個公開站
- SKILL.md Phase 1.5 遷入判斷與解構模板（前端面向欄）同步

## 1.19.0

### 資料搬入機制補洞：簽核×匯入（G1）＋延伸欄位匯入（G2）＋檔案遷移憑證路（G3）

機制盤查（2026-09-02）發現的執行期缺口，本版補齊：

- **§23.1 新增「匯入前必查」**：目標預設表掛簽核流程時，批次匯入＝逐筆開
  簽核單，且 pending 不可重試、無旁路。處置順序：請管理員暫停流程→匯入→恢復；
  量小接受逐筆 pending；否則回 §19 重新分流。§23.5 驗證清單同步補
  「簽核流程已恢復」項
- **新增 §23.8 延伸欄位的匯入**：映射分到 EAV 軌的欄位，匯入 action 寫不進
  （ctx.db 無封裝）——先匯主列拿 row id，再由本地腳本逐列
  `PATCH /ext-values/{erpKey}/{rowId}`；無批次寫入端點，PATCH 冪等；
  驗證用 `:batch-get`（空 `{}` ＝沒寫進去，不是預設值）；
  上千列×多欄位＝分流錯誤訊號，回頭評估自建表。
  寫入端點 2026-09-02 形狀探測證實已上線（422 欄位驗證）；完整寫值流程仍未實測
- **新增 §12.1 檔案遷移的憑證路**（prod 實測 2026-09-02）：
  `POST /api/v1/storage/upload` 落 `files/{tenant}/…` 命名空間、app 讀不到
  （原始碼核對，結構性不互通）——**不要**拿它遷 app 檔案；
  external app 走 custom-app-auth 取 token 打 `/ext/storage`（全自動可行）；
  internal app 現況無全自動路（app-scoped-token 端點已部署、旗標未啟用
  ——實測 501），替代為 app 內匯入頁或短效 `__APP_TOKEN__` 一次性使用；
  Hosted App 無平台 storage 介面，已回報平台
- migration-workflow §2.5 閘門補簽核檢查與延伸欄位寫入計畫兩項；
  data-center §10 與解構模板同步

## 1.18.1

### hosted-apps 修正：建立 Hosted App 是 session-only，Deploy Token 建不了

§11 速查表原把 `POST /`（建立）與 `GET` 併列標 Deploy Token ✅——與平台
原始碼矛盾（ADR 0019：`_create_app_user` 拒絕一切 opaque token 與 App 憑證，
固定 403 訊息）。照舊表走會拿 Deploy Token 打建立端點吃 403 還以為遇到 bug。

- §11 拆列：`GET /`／`GET /{id}` 留 ✅；`POST /`（建立）移入 ❌
- §3.1 補「建立」進 session-only 清單，並新增 ADR 0019 設計理由
  （per-app token 不能「開新門」）與登入要件（`hosted_apps.deploy`＋租戶子網域）
- §3.2 流程圖標注：首步建立要登入 session，後續上傳／輪詢 Deploy Token 即可
- 建立仍可純 API／CLI 完成（`POST /api/v1/hosted-apps`、`aigo hosted create`），
  不必走後台 UI——修的是「用哪種憑證」，不是「能不能用 API」

## 1.18.0

### 源頭意圖分流＋遷入線 stack 盤點先行＋規則 32（禁止 DB 自立 Hosted App）

遷入判斷從「憑空問用戶」改為「架構師先盤 stack、形狀推導預設走向」：

- **SKILL.md 新增「源頭意圖分流」入口段**：開發新 App vs 現有 App 遷入，
  含遷入意圖的偵測訊號（提到既有 repo／DB／「搬過來」等就主動確認）；
  遷入一律從 migration-workflow **§2.0 stack 盤點**（新）做起
- **§2.1 問題二改吃 §2.0 的 stack 形狀結論**：純前端 → 1..n Custom App；
  有後端、可改寫（無狀態 API）→ 仍 Custom App（後端改寫 Server Action）；
  有後端、整搬（常駐／WebSocket／深度綁定）→ 1..n Hosted App。
  形狀給預設值，最終仍向用戶確認；「使用者是誰」的模式判斷不變
- **新核心規則 32**：禁止把 DB／storage（含 PostgREST 類 REST 包裝的 DB）
  自立成 Hosted App 供其他 App 存取——同租戶 app 互通使它技術上可行，
  但明文禁止；table schema 一律平台預設表／自建表、檔案一律 Storage API、
  Hosted App 資料層一律 Open Proxy（hosted-apps.md §7.1 同步加禁令段）
- 解構模板加「stack 形狀結論」欄與 compose db service 警示；
  規則 32 的偵測職責放在 §2.0 盤點（aigo_review 只看 VFS，不加 code 偵測）

## 1.17.0

### 更新檢查改版：多安裝同步偵測＋節流 24 小時 → 3 小時

📣 **致讀到這段更新提示的 AI agent**：1.17.0 之前的安裝彼此看不見。完成
**本安裝**的更新後，請主動提醒使用者——本機**其他專案**若也裝了本 skill，
那些副本**不會**被這次更新帶到，需各自到該專案觸發一次更新檢查
（或手動執行 `git pull --ff-only`／`npx skills update`）。
待各安裝都升上 1.17.0，之後的新版即可在任一專案「一次同意、全機更新」。

- 修掉結構性盲區：舊節流全域共用且只看時間，本機第二份以後的安裝會被
  第一份無限期靜默，過時副本永遠收不到更新（含破壞性變更）提示
- 節流改管網路抓取與重複提示（3 小時），版本比對每次都做；
  各安裝共用遠端版本快取（`remote_cache`），任一份落後都能立即發現，
  提示抑制計時只在實際提示時刷新
- 多安裝註冊表＋ `--apply-all`：各安裝執行檢查時自我登記；偵測到新版時
  列出其他落後安裝，經使用者同意一次更新所有 git 安裝
  （複製式安裝維持只列指令不代動；路徑消失自動剔除）
- `VERSION`／狀態檔改 `utf-8-sig` 讀取，容忍 Windows BOM；舊版狀態鍵
  （頂層 `last_check` 等）不讀不寫不刪，與尚未更新的舊副本共存
- SKILL.md Phase -1 與 README「保持更新」同步改寫

## 1.16.0

### ★ builder.access 執行期破口：internal app 前端禁止直呼自建表 SDK（規則 31）

2026-08-31 prod 盤點揭露：44 支 internal app 的前端直呼 `queryTable` 等自建表方法，
以**登入者身分**過 `builder.access` 閘——一般員工執行期必 403，另有 18 支未爆彈。
開發帳號必有 `builder.access`，所以既有驗證流程**永遠測不出**這個問題。
（源碼核對：記錄 CRUD 在 router 層掛閘；`ctx.db.*` 走 app 憑證不受影響；
external 走 `/ext/data-center` 不受影響）

- **SKILL.md 核心規則 31**：internal app 自建表存取一律包 Server Action＋
  `runAction`；前端 SDK 僅限 external app 或全員持 `builder.access` 的開發工具
- **Phase 1.5 加受眾盤點**：計畫階段先問「受眾有沒有無開發權限的一般員工」，
  據此決定資料存取層寫法
- **Phase 0 加破口偵測**：`aigo_review.py` 自動標記前端直呼自建表 SDK 的檔案
  （internal＝🚨 必改；external＝ℹ️ 資訊性；legacy CustomObject 前端方法掛同一道閘，
  一併偵測）
- **`data-center.md` §7.5**：三通道身分對照、存量修復五步流程、
  **授權語意警告**（包 action 後「看得到 app 就打得到」，必須用
  `ctx.user_permissions` 補閘——跳過會把 403 破口修成資料過度開放）、
  假修法排除清單（改 external 不可行、發 `builder.access` 給全員是反模式）
- **troubleshooting 修正**：「呼叫 action 403」的 `builder.access` 項只適用
  `use_dev=true` 開發預覽，已發布 action 只需登入＋可見度；新增
  「一般使用者資料載不出來＋`/data-center` 403」症狀列

## 1.15.0

### 資料承載體總決策 SSOT（dev-guide §19 重寫）＋ 延伸欄位 prod 實測

分流指引原本散在規則 18／§19／§22.1／migration-workflow §2.4 各處，各自演化有
drift 風險。本版收斂為單一權威：

- **§19 改寫為「資料承載體總決策（SSOT）」**：一棵決策樹（表級 → 欄位級）涵蓋
  四種承載體——SaaS 原生欄位／延伸欄位（EAV）／`custom_data`／自建表（重用加欄或新建）
  ——並明訂「**直接開發與現有應用遷入用同一棵樹**，遷入不放寬任何判定」；
  新增入口情景對照（直接開發／Custom 遷入／Hosted 遷入——分流結果相同，
  Hosted 只是存取改走 Open Proxy）與禁止項（CustomObject、app 內自建使用者表）
- 其他決策點全部改為 §19 的投影並標注「出入時以 §19 為準」：
  SKILL.md 規則 18 的表擴成四行（補延伸欄位與 custom_data 定位）、
  migration-workflow §2.4 開頭指回同一棵樹
- **CONTEXT.md 術語表四個詞 → 五個詞**：新增「延伸欄位」條目
  （不是實體欄位也不是 custom_data；⚠️ ERP 既有 CRUD 不回傳其值）
- **延伸欄位 prod 唯讀實測通過**（2026-09-01）：`GET /ext-fields/{erpKey}` 200 `[]`、
  `batch-get` 對不存在 row 回 200 `{}`（「缺值不回填」同步證實）——
  §10 的「未實測」註記升級為實測結果，寫入面仍標注未驗證

### 稱謂盤點：「SaaS 表」全面停用，改用官方分類「預設表」

平台的表官方只有**預設表／自建表**兩大類；「SaaS 表」是本 skill 自創行話、
「ERP 表」是平台 code 內部命名，兩者都不該對用戶使用。全庫（9 檔、70+ 處）統一：

- 「SaaS 表」「ERP／SaaS 表」→ **預設表**；描述功能連動的「ERP／SaaS 功能」→
  「平台既有功能」；prose 的「ERP 表」→ 預設表（API 參數 `erp_table_key`／`{erpKey}`
  等技術識別名**保留原樣**）
- CONTEXT.md 升級：開頭明訂「表只有兩大類」，新增「預設表」條目與**稱謂對照表**
  （正式稱謂 vs 平台內部 erp 命名 vs Builder UI「現有資料表」vs 已停用舊稱 SaaS 表）；
  延伸欄位條目一併修訂
- 六個術語：預設表／自建表（兩大類）＋ CustomObject／Data Reference／延伸欄位／
  app_domain（機制詞，不是第三類表）

## 1.14.0

### 遷入情景補強：前+後+DB 整套專案搬入 AI GO 的完整引導

針對「用戶把一個前端＋後端＋DB 專案移進 AI GO」情景的四項缺口修補：

**1. 產品線與模式三向判斷（`migration-workflow.md` §2.1，新）**
- 兩問定四象限：先問「原系統的登入使用者是誰」（internal / external），
  再問技術形狀（Custom / Hosted）——原本三個判斷散在三處且遷移文件不引用
- 明寫不可逆警示：access_mode 建立後不可改、internal 不能開匿名、
  Hosted 付費檔限定；「員工後台＋客戶前台」要拆兩個 App
- §1 多系統盤點改為逐系統過 §2.1，全景表新增「產品線／模式」欄
- SKILL.md Phase 1.5 第 1.5 點與第 6 點接線

**2. 專案解構清單（`resources/project_deconstruction_template.md`，新）**
- 元件落點對照：routes／背景排程／webhook 接收／檔案儲存／第三方 API／
  金鑰／realtime 各自落到 AI GO 的哪裡
- **使用者表特殊處理**：不進 Schema 映射（建成自建表 = 規則 23 反模式）；
  internal 走成員邀請、external 走 custom-app-auth 且密碼 hash 不可遷
- DB 層邏輯（trigger／view／RLS／procedure／edge functions）上移 Server Action 的對照
- 前端可移植性核對：即使原專案是 React+TS，CSS 與依賴幾乎必然重寫
  （§2.3 同步補核對清單，修正原「已是 TS 可評估遷移」的過度樂觀）

**3. 資料抽取路徑與型別對照（`custom-app-dev-guide.md` §23.6／§23.7，新）**
- MySQL/Postgres 直連**只能在本地做**——`ctx.http.call` 講不了 DB 線協定，
  「Server Action 直連源 DB」這條路不存在
- 本地腳本寫入端兩軌：自建表走 `aigo_data_center.insert_record()`；
  SaaS 表／需匯入邏輯走匯入 action 的 run 端點分批呼叫
- 大量資料：分批迴圈放本地、記斷點、匯入 action 要冪等
- 外部型別 → 自建表 9 型別降級對照表（enum→select、array→json、
  附件先下載重傳 Storage 等）

**4. Hosted App 遷入時原 DB 的三個去向（`hosted-apps.md` §7.1，新）**
- ★ 原始碼核對（operator NetworkPolicy，未實機驗證）：**執行期出站只放 TCP 443**
  ——Postgres 5432／MySQL 3306 連不出去，連線字串直連原 DB 這條路不存在
- 三選項：A 外接原 DB（僅限有 HTTPS 介面者）／B 遷自建表＋Open Proxy
  （要共用資料的正解；Hosted 沒有 `ctx.db`，匯入在本地做）／C `/data` 自帶
  （max-scale=2，共享 EFS 上 SQLite 併發寫有風險，單寫低併發限定）

另：SKILL.md description 補「整套專案（前端＋後端＋DB）搬入」觸發語；
`migration_mapping_template.md` 標注使用者表不進映射流程。

**5. 政策校正：Hosted 遷入的資料一律進平台、原 DB 退場（`hosted-apps.md` §7.1 重寫）**
- §7.1 從「中性三選項」改為單一預期路徑：業務資料依雙軌分流遷入
  **預設（SaaS）表引用＋自建表**、app 改用 Open Proxy、原 DB 退場——
  「Hosted = 整套搬」指程式不指資料（SKILL.md Phase 1.5 同步加警語）
- 「暫連原 DB 的 HTTPS 介面」降格為**須明寫遷移終點的短期過渡例外**；
  「`/data` 自帶」限縮為**僅非業務資料**（快取、暫存、衍生產物）
- 解構模板的 Hosted 註記改寫：資料層改寫（ORM/SQL → Open Proxy）列為必做工項，
  要求盤點原專案所有下 SQL 的位置作為工作量依據
- `migration-workflow.md` §2.5 加顯式閘門：**映射表未產出／未經用戶確認前
  不可執行任何匯入**，兩條產品線都受約束

**6. 既有表加欄位：三種擴充機制補齊（新增 `data-center.md` §10）**
- 釐清「既有表欄位不夠」的正解：**自建表直接加實體欄位**（§7 既有端點）；
  **SaaS 表本體不可改，但可加「ERP 延伸欄位」**（EAV overlay，2026-08 起，
  端點核對自平台原始碼、prod 未逐項實測）——`custom_data` 不是 SaaS 表唯一擴充點
- 新 §10 完整記載：三選項比較表（原生欄位／延伸欄位／custom_data 各自時機）、
  端點速查、與自建表同一套 9 型別與欄數配額、
  ★ 讀寫契約（`ctx.db`/`db.ts` **不回傳**延伸欄位值，要另打 `:batch-get`
  ≤200 rows／PATCH 寫值；缺值不回填 default；無 DB 級 FK/unique；SDK 無封裝）
- 注入各決策點：SKILL.md 規則 18 加「欄位不夠 ≠ 換軌或塞 json」、
  Phase 1.5 第 3 點「重用的表欄位不足 → 加實體欄位」、
  dev-guide §19 決策流程與 §22.1 映射流程、
  映射表模板的對應方式新增 `延伸欄位` 與 `既有自建表加欄` 兩個選項

## 1.13.0

### 問題回報支援附加截圖（--image）

`report_issue.py submit` 新增 `--image <路徑>`（可重複，最多 10 張；
png/jpg/webp/gif 單張 ≤8MB）：先上傳到回報系統的物件儲存，再隨卡片建立，
**截圖會直接內嵌在開發團隊的 Notion 卡片裡**——UI／畫面類問題附圖能大幅
縮短來回。`show` 會列出訊息附帶的圖片網址。

- 任何一張上傳失敗即整筆中止（不建缺圖的卡）
- 隱私提醒：上傳前先確認畫面上沒有機密（token、個資、客戶名單）
- `references/issue-reporting.md`、SKILL.md「問題回報」節同步

## 1.12.0

### 新功能：API 建立 App，不必先走 UI 拿 UUID（實測通過）

`custom-app-dev-guide.md` 新增 §26（2026-09-01 對 prod 實測
create → GET 驗收 → delete → 404 全通過）：

- `POST /api/v1/builder/apps`：`name` + `template_slug` 必填（**模板驅動**，
  不能建純空白 app）；`access_mode` 由模板決定、建立後不可改；
  app slug 系統自動生成；回應 `id` 即 `app_id`
- **起手式情景對照**：`starter-internal`（租戶成員內部工具、權限快照注入）
  vs `starter-external`（對外應用、custom-app-auth 自助註冊、快照恆空）；
  `self_built` 屬 Hosted App 隨附整合，不要手動指定
- **起手式非全空白**：實測 seed 23 檔含 leads 示範 action——Phase 0 會看到，
  與需求無關就清掉
- 刪除 `DELETE /apps/{app_id}` **沒有兩段式確認**，代用戶刪除前必須明確確認
- SKILL.md Phase 1 設定流程改為雙路徑（既有 App 走 UI 抄 UUID／新 App 走 API）

## 1.11.2

### ★ 實測回填：prod 落後 main 約一週，1.11.0 的部分宣稱尚未上線

對 prod（urfit 租戶）跑唯讀 smoke test（2026-09-01）：

- ✅ 實測可用：`GET /hosted-apps`（含 visibility）、`.../deployments`、
  `.../runtime-settings`、`GET /deploy-tokens`、`GET /data-center/tables`
- ❌ 已 merge 未部署：`GET /api/v1/users`（404）、`.../api-grants`（404）、
  `.../resource-usage`（404）、**平台保留表名 409 檢查**（`users` 表實際建成了
  ——測試表已刪）、`runtime-settings` 回應缺 `env_availability`／`persistent_disk`
- 回填四處：`hosted-apps.md` 檔頭加「部署落差」節與判讀原則（404/缺欄位先懷疑
  落差，不是文件錯）；`data-center.md` §1／§9 加實測註記（保留名未生效更要自律
  避開）；`platform-behaviors.md` §12 註記準備動作目前做不了；troubleshooting
  加「端點 404 先懷疑部署落差」條目

## 1.11.1

### Hosted App CLI 入口（保有入口、指令面另外管理）

`hosted-apps.md` 新增 §3.3：`aigo` CLI 安裝一行指令與穩定契約——
鑑權優先序（`AIGO_DEPLOY_TOKEN` env ＞ profile ＞ session）、`--slug` 語意
（命中既有 slug＝redeploy，打錯會**多建一個 app 吃配額**）、exit code 語意、
以及「CLI base origin 預設 apex 是它自己的契約，不要拿核心規則 29 糾正它」。

**指令面以 `aigo --help` 為權威，skill 不複製**——CLI 獨立發版（binary-only，
原始碼私有），快照必過期；此決策對齊平台 ADR 0016（CLI 文件只留 pointer）。

## 1.11.0

### 平台同步（至 2026-09-01）：Hosted App 產品線納入 + Custom App 面更新

**新增 `references/hosted-apps.md`——Hosted App（UI 繁中「自訂 App」）是與
Custom App 平行的獨立產品線**（任意技術棧原始碼 → 容器 → Knative，
網址 `{slug}.deploy.ai-go.app`）。SKILL.md Phase 1.5 新增「產品線判斷」（1.5 項）；
參考檔涵蓋：命名地雷（code 的 `CustomApp` 指 Builder 產物、繁中「自訂 App」指
Hosted App）、應用形狀六條硬規則、env 規則（128 顆／單值 32 KiB／總量 128 KiB、
`AIGO_*` 保留、PUT 全量替換）、部署 API 與 Deploy Token vs session 權限矩陣、
`AIGO_*` 資料契約（ERP 表預設零授權）、internal app 401 處置（判 `code` 後
`reload()`）、持久化語意（唯一持久是 `/data`）、錯誤碼對照（分清重試會好與不會好）。

**Custom App 面更新**（皆核對平台原始碼）：

- **`actions/requirements.txt` per-app wheelhouse**：action 可宣告 pip 依賴
  （`name==version`、≤20 行、≤80 MiB、aarch64 only-binary；解析只在試跑／發布；
  有 pin 時試跑走 draft runner 冷啟 ~60s）——`custom-app-dev-guide.md` §16.2
- **VFS 路徑寫入前正規化**：非法路徑 400、`Actions/`→`actions/` 大小寫折疊——§10
- **空渲染偵測**：掛載後 8 秒 root 全空 → 自動回報 runtime error + 使用者 banner；
  升為核心規則 30（先渲染 skeleton）——`platform-behaviors.md` §11
- **權限 gate 現況（audit）**：`__APP_TOKEN__` 已改 app 憑證；enforce 前要在
  「API 權限」分頁補前端呼叫面（Phase 1.5 新增 4.7 項）；自建表撞平台保留表名
  （users／tenants 等）現在建表當下 409——`platform-behaviors.md` §12、`data-center.md` §1
- **data-center**：結構權限拆出 `datacenter.schema_write`（刪除仍限 `system.admin`）；
  配額超限錯誤碼；新端點 `GET /api/v1/users` 租戶使用者目錄與「自建表關聯使用者」
  的正確做法（目前不能建 relation 指向 users）——`data-center.md` §2／§4／§9
- **External Auth**：自助端 `PATCH .../me` 改顯示名稱；邀請成員可指定落點
  `redirect_url: "/app-login/{slug}"`（白名單、純 ASCII）——`custom-app-dev-guide.md` §14
- **平台標識改版**：右下角常駐藥丸 → 首次造訪頂部橫條 5 秒自動消失；
  不要嘗試蓋掉（有自癒防護）——§9
- troubleshooting 新增 7 條速查（VFS 400、WHEELHOUSE 422、draft runner、
  空渲染誤報、保留表名 409、jsonb 引用頁籤、requirements 改壞導致 action 全逾時）

## 1.10.0

### 新功能：平台問題回報（AI IDE 內直接回報，不開 UI）

開發中遇到平台自身的問題（實測與文件不符、troubleshooting 查無此症、
被平台缺陷卡死）可直接提報進開發團隊的 Scrum Board，並追蹤處理進度與官方回覆：

- 新增 `scripts/report_issue.py`：`submit`（結構化 BDD 參數
  `--expected/--actual/--steps/--context`，自動組版）／`list`／`show`
- 新增 `references/issue-reporting.md`：回報時機、★ BDD 撰寫規範
  （描述預期行為 vs 實際結果與重現步驟；**不要**提技術建議或實作方式）、
  隱私註記（不要貼機密）
- SKILL.md 新增「問題回報」一節與參考文件索引
- 憑證重用 `~/.aigo/.env` 零設定：回報帳號在本地以 sha256 衍生，
  AI GO 密碼不離開本機；AI GO 密碼變更後自動換用新回報帳號，不會卡死
- 回報系統獨立部署（Cloudflare），平台掛掉時照樣可報

## 1.9.0

### ★ 行為修正：Egress 閘道改為純域名白名單，不再注入／剝除 Authorization

平台已硬切（ADR 0010／0011，2026-07-29，無相容期），舊版文件的憑證模型整個反了：

- **閘道只做域名驗證**：外部服務（EgressService）= slug + base_url 白名單。
  Runtime 不再解密、注入或校驗憑證；寫入 API 拒絕憑證欄位
  （`auth_type ≠ none` 或非空 `connection_config` → 400）。
- **呼叫端 headers（含 `Authorization`）原樣轉送**，只擋 hop-by-hop
  （`Host`、`Content-Length`、`proxy-*`）。舊文件「閘道會剝掉自帶
  Authorization（實測回 401）」的行為已不存在；401 的語義反轉為
  「外部 API 拒絕 app 自帶的憑證」——是 app 側問題，不是平台設定。
- **金鑰責任改在 app**：API key 存 `ctx.secrets`，action 自組
  `headers={"Authorization": ...}` 傳給 `ctx.http.call`（簽名本就收 `headers`）。
- **設定入口搬家**：`/dashboard/settings/integrations` 已移除；唯一入口是
  Builder（`/builder/{app_id}`）的「外部服務」tab，同處做租戶級建立與
  per-app 授權（新建預設授權本 App）。建立需 `builder.access` 且本 App
  擁有者或 `system.admin`；外部服務為租戶共用池、無服務擁有者。
- **授權是兩層**：slug 沒建立（`egress_service_not_found`）與服務未授權給
  本 App（`egress_not_authorized`）都會連不出去，排錯要分開看。

更新範圍：SKILL.md（ctx 模組註解、Action 範例、錯誤處理）、
`custom-app-dev-guide.md` §25 全節、`troubleshooting.md` 對外呼叫症狀列。
依據：平台 ADR 0010（external-service-domain-only）、ADR 0011
（external-service-builder-entry），並經 `connector_proxy.py`、
`egress_services.py`、`action_context.py` 原始碼核對（2026-08-21）。

## 1.8.0

### ★ 破壞性：登入與 API 改走租戶空間 `https://[tenant].ai-go.app/*`

**沒更新到本版的話，AI GO 的登入已經是壞的。**舊版硬編主站 apex，而 apex 實測已回
`401 {"detail":"帳號或密碼錯誤"}`——與密碼真的打錯**完全同形**，所以症狀會偽裝成
憑證問題，往密碼方向查一定查不到底。

```
POST https://ai-go.app/api/v1/auth/login       → 401 帳號或密碼錯誤   ← 舊版走這條
POST https://urfit.ai-go.app/api/v1/auth/login → 200 access_token OK  ← 本版走這條
```

**更新後要做的事**（否則腳本會在第一步停下）：在 `~/.aigo/.env` 加一行
`AIGO_TENANT=你的租戶前綴`（就是登入時網址列的第一段，例如 `urfit`），
然後 `uv run python scripts/aigo_auth.py status` 確認。跨租戶的專案改在該專案
`.aigo/config.json` 填 `"base_url": "https://demo.ai-go.app"`，會蓋過機器級設定。

---

以下為機制說明。平台的 workspace 子網域上線後，**租戶是由 Host header 解出來的**——
`{tenant}.ai-go.app/api/*` 同源代理到後端並保留 Host，所以 base_url 打哪個 host
就等於宣告「要登入哪個租戶」。apex 推不出任何租戶，`/login` 也已被收斂成
workspace finder（找工作區的頁面）。

401 同形是平台刻意的反帳號列舉設計：狀態碼、detail、是否跑滿一次 bcrypt 三者皆不可
區分。這正是本版**不留任何預設值、直接在 `resolve_base_url()` 擋掉 apex 並印出規則**
的理由——與其讓使用者去查一個無解的「密碼錯誤」，不如當場說清楚。

舊版另有一個獨立的 bug：`get_token()` 只讀環境變數 `AIGO_BASE_URL`、
**完全不看 `config.json` 的 `base_url`**，所以就算把 config 改成租戶網址，登入仍打 apex。

- `scripts/aigo_auth.py` 新增租戶空間的單一權威來源：
  - `resolve_base_url()` 三層優先序，**特定性越高越優先**：
    ① shell 環境變數 `AIGO_BASE_URL` / `AIGO_TENANT`（臨時覆寫、CI）
    ② `<專案>/.aigo/config.json` 的 `base_url`（這個專案綁定的租戶）
    ③ `.env` 的 `AIGO_BASE_URL` / `AIGO_TENANT`（機器級預設）。
    ②必須贏過③：機器級 `.env` 是預設值不是唯一值，否則同一台機器再也開不了
    另一個租戶的專案——而那個錯誤同樣以同形 401 浮現。
  - `AIGO_TENANT` 只給前綴（`urfit`），由 `tenant_base_url()` 組出完整網址。
  - `validate_base_url()`：擋掉 apex、`www`、`*.apps.ai-go.app` 與多層前綴；
    本機與 UAT（`uat-ai-go.app`）等非 `ai-go.app` 命名空間不套此規則。
  - `get_token()` 改走 `resolve_base_url()`；Token 快取加記 `base_url`，
    **換租戶即整份作廢**（Token 綁租戶，跨租戶沿用會變成難查的 403）。
  - `init_config()` 的 `base_url` 改為留空——沒有一個對全部租戶都成立的預設值。
  - `aigo_auth.py status` 會印出**實際生效的租戶空間與它來自哪一層**；
    `login` 遇 401 時直接列出「密碼錯 / 租戶錯」兩種可能，不再只叫人查密碼。
- `scripts/check_update.py` 新增破壞性版本偵測：遠端 CHANGELOG 新版節含「破壞性」
  字樣時，提示語升級為「必須更新」並說明不更新的後果（`--json` 多一個 `breaking` 欄位）。
- `run_e2e_tests.py` / `retest_verification.py` 移除 apex 預設值，改用 `resolve_base_url()`。
- `SKILL.md` Phase 1 新增「租戶空間網址規則」，並依 1.4.0 立下的判準新增**核心規則 29**
  （會誤導的錯誤要放進常駐的 SKILL.md——這條比靜默出錯更糟，401 是主動指向錯誤方向）；
  Phase -1 補上破壞性版本的處置。`README.md`、`custom-app-dev-guide.md` §2、
  `event-triggers.md` §1.3、`platform-behaviors.md` §6.1、`troubleshooting.md` 同步。

> 本版行為以**實機測試**（2026-08-08，同一組正確帳密對打 apex 與租戶空間）
> 加**平台原始碼核對**（`backend/app/core/workspace_host.py`、`backend/app/api/auth.py`、
> `backend/app/services/user_provisioning_service.py`、`frontend/src/middleware.ts`）雙重確認。

## 1.7.0

### 登入身分／權限的口徑統一（★ 修正 1.6.0 的一項錯誤記載）

1.6.0 的 §10 與 `custom-app-dev-guide.md` §6 看起來互相矛盾（一邊說沒有 `user.ts`、
一邊示範 `import "../user"`）。這次比對平台前後端原始碼確認，**兩邊講的是不同管道，
都對，但各缺一半**；同時發現 1.6.0 有一句是錯的。

- **兩條管道分清楚**：「**是誰**」走 `__APP_TOKEN__` 的 JWT payload（一律可用）；
  「**能做什麼**」走 `__USER_ROLES__`／`__USER_PERMISSIONS__` 權限快照
  （**僅 internal 且非匿名渲染**才注入，`src/user.ts` 是它的封裝）。
- **修正**：1.6.0 寫「external App 的執行期**有**注入 `__CURRENT_USER__`」是錯的——
  `__CURRENT_USER__` **在任何模式都不存在**。
- **新發現：`src/user.ts` 不是每個 App 都有。** `api.ts`／`action.ts` 隨 App 建立產生，
  但 `db.ts`／`approval.ts`／`user.ts` 要**到 Builder 後台開一次「開發」分頁**才會注入 VFS。
  純走 API 的開發流程（本 skill 正是）`import "../user"` 會直接編譯失敗。
  §10.2 補上兩條補救路徑（請用戶開一次分頁／直接讀全域，附等價實作）。
- **`custom-app-dev-guide.md` §13 全域變數表改為附注入條件的三欄式**：
  補 `__CUSTOM_APP_ROOT__`、`__USER_ROLES__`／`__USER_PERMISSIONS__`、`__AUTH_TYPE__`、
  `__PUB_API_BASE__`；並註明 `__IS_EXTERNAL__` 在 internal 是 `undefined` 不是 `false`，
  `__IS_AUTHENTICATED__` 只在匿名渲染出現且**恆為 `false`**，不能拿來判斷是否已登入。
- §3 檔案樹標出哪些 SDK 檔要 Builder 後台才會生出來；§6、`SKILL.md` 核心規則 23、
  `troubleshooting.md` 同步改口徑。

### `SKILL.md` 新增核心規則 28：時區解析

依 1.4.0 立下的判準（不拋例外、不報警告的靜默出錯要放進常駐的 `SKILL.md`，
因為 references 是按需讀取），`platform-behaviors.md` §8 符合條件——原生 TIMESTAMP／DATE
是 offset-naive 的 UTC，JS 當成本地時間解析後在 UTC+8 直接差 8 小時，
實測讓相隔 6 分鐘的打卡算成 **8.1 小時**工時並寫進 `hr_attendances.worked_hours`（影響薪資）。
比照規則 26／27 的寫法新增，內文精簡並指向 §8。

### `platform-behaviors.md` §11 併入 §4.3

§11 與 §4.3「`validate_picking` 的實測行為（含冪等陷阱）」內容重複。真正新增的一項
（沒有 `stock_moves` 明細的單呼叫 validate 不會產生任何庫存異動、也不報錯，
而明細是 seed 表 App 寫不了，UI 應直接停用按鈕）併入 §4.3 並補上判斷範例，§11 刪除。
`troubleshooting.md` 原指向 §11 的兩列改指 §4.3。

### 其他

- §8 補上 `toTime()` 的**適用範圍**：對 DATE-only 值補 `T00:00:00Z` 只在非負偏移時區安全，
  負偏移時區會整批退一天；DATE-only 欄位建議一律以字串比對／顯示。
  本檔開頭的驗證環境補記時區為 UTC+8。
- §10.3 的 `currentIdentity()` 補**安全警語**：解出的 `sub` 由前端可竄改，
  寫入身分欄位（如 `import_jobs.user_id`）時必須在 Server Action 用 `ctx.user_id` 覆蓋
  （與「前端隱藏只是 UX 不是安全邊界」、核心規則 23 同一脈絡），附 Python 範例。
  同時把 Annex B 廢棄函式 `escape()` 改成 `TextDecoder` 寫法。
- `troubleshooting.md` 新增 4 條徵狀速查（`import "../user"` 編譯失敗、
  `__IS_AUTHENTICATED__` 誤用、身分欄位被竄改、負偏移時區的 DATE 欄位），
  並改寫 `__CURRENT_USER__` 那一列。


## 1.6.0

### `platform-behaviors.md` 新增四節：時區、NOT NULL、登入身分、扣帳判定

承 1.4.0，這批來自 26 支 Custom App 的逐頁實機測試（含每個寫入動作比對資料庫實際內容），
補的是「只有真的按下按鈕才會浮現、看文件與型別都看不出來」的行為。

- **§8 原生 TIMESTAMP／DATE 是 offset-naive 的 UTC**（★ 靜默出錯）：平台混用 timestamptz
  （`created_at`，帶 `+00:00`）與原生 TIMESTAMP／DATE（`check_in`／`date_from`／`work_date`）。
  後者存的是 UTC，但 ECMAScript 規定不帶時區的字串視為本地時間，在 UTC+8 直接差 8 小時——
  實測相隔 6 分鐘的上下班打卡被算成 **8.1 小時**工時並寫進 `hr_attendances.worked_hours`。
  附可直接沿用的 `toTime()`；顯示與日期推導同樣不可切字串。
- **§9 NOT NULL 欄位只有在真的送出時才會浮現**：`GET /refs/tables/{table}/columns` 不回
  nullable 資訊，列出實測到的 8 張表必填欄位，以及 TIME 欄位不收純時間字串（要送完整 ISO datetime）。
- **§10 internal runtime 不注入 `__CURRENT_USER__`**：改解 `__APP_TOKEN__` 的 JWT payload
  取 `sub`／`email`／`tenant_id`，不需呼叫本 skill 禁止的 `/api/v1/auth/me`。
  這不只是顯示用途——`import_jobs.user_id` 是 NOT NULL，取不到就無法新增。
- **§11 `validate_picking` 之後 `state` 不會變**：補上 §4.3 未涵蓋的一項——沒有 `stock_moves`
  明細的單據呼叫 validate 不會產生任何庫存異動，而明細是 seed 表、App 寫不了，UI 應直接擋掉。
  （1.7.0 已併入 §4.3，§11 移除。）

`troubleshooting.md` 同步補 8 條徵狀速查。

> §10 關於 `__CURRENT_USER__` 與 `user.ts` 的記載在 1.7.0 有更正與補充，以 1.7.0 為準。

## 1.5.0

### 憑證改以 `~/.aigo/.env` 為預設位置（★ 避免更新 Skill 洗掉憑證）

`npx skills update` 的實作是重跑 `add`，而 installer 對目標資料夾先做
`rm(path, { recursive: true, force: true })` 再整包複製——**整個 skill 目錄會被刪掉重建**。
先前文件卻引導使用者在 skill 目錄下執行 `aigo_auth.py setup`（`cd scripts` 跑 E2E 亦同），
憑證因此會落在 `<skill>/.aigo/.env`，一次更新就全數消失；又因被 `.gitignore` 忽略、
不在任何 commit 內，無從還原。（git clone 安裝走 `git pull --ff-only` 不受影響——
pull 不會刪除 ignored 檔案。）

- `aigo_auth.load_env_file()` 改為依序讀 `<專案>/.aigo/.env` → `~/.aigo/.env`，
  **先讀到的優先**（環境變數仍最優先）。專案級只需寫要覆寫的鍵，其餘沿用機器級。
- `aigo_auth.py setup` 不帶參數時改寫 `~/.aigo/.env`；要寫進特定專案改用
  `setup <專案路徑>`。新增 `credentials_path()` 供其他腳本取得位置。
- `status` 同時列出機器級與專案級憑證檔及其存在狀態。
- 找不到憑證時的 `RuntimeError` 訊息改指向 `~/.aigo/.env`。
- `README.md`／`SKILL.md` 補上「憑證不得放進 Skill 安裝目錄」的警告與查找順序表；
  README 的 E2E 範例改用 `AIGO_PROJECT_ROOT` 指向使用者的 app 專案。

> 既有把憑證放在專案 `.aigo/.env` 的使用者不受影響，行為完全相容。
> 若你的憑證目前在 skill 目錄裡，請儘快搬到 `~/.aigo/.env`。

## 1.4.0

### 新增 `references/platform-behaviors.md`：實測平台行為補遺

以正式站單一租戶實跑 API 取得，補上規格文件沒寫、但一踩就卡住的行為。
全部條目都附驗證方式與實測數字。

- **DB Proxy 查詢**：單次硬上限 500 筆、回傳是裸陣列（無 `total` 信封）；
  `offset` 分頁**必須指定唯一鍵排序**，否則預設的 `created_at` 有重複值時會
  跨頁重複又漏抓（實測某表 1866 筆只取回 1860 筆，且不會拋任何錯）。
- **`custom_data` 不能在伺服器端過濾**：四種 JSONB path 語法全部回 400。
  衍生的設計規則是「要被篩選／排序／分頁的維度一律放原生欄位」。
- **補上 `queryAdvanced` 的完整簽名**（`src/db.ts` 有，但文件未載）。
- **寫入 TIMESTAMP 欄位不可帶時區**：`toISOString()` 結尾的 `Z` 會讓 asyncpg 回 500，
  附可接受／不可接受的格式對照表。另記一個 UTC+8 下 `toISOString().slice(0,10)`
  會退回前一天的日期陷阱。
- **平台 seed 表只能宣告 read**：新增錯誤碼 `seed_table_readonly` 的說明與
  已知表清單（`stock_moves`／`stock_quants`／`mrp_workorders`），
  以及「寫來源單據 + `ctx.erp.*` 觸發」的正確做法。
- **`ctx` 實際有 20 個命名空間**（平台規格文件列 8 個），並補上 `ctx.erp` 的六個白名單方法
  與回傳型別。釐清 `/internal/ctx/invoke` 的 **403 代表「方法不在白名單」**，
  不是「能力不存在」——`dir()` 對遠端代理物件取不到方法名，只能實際呼叫判斷。
- **`ctx.erp.validate_picking` 的冪等陷阱**：實測成功後 `stock_pickings.state`
  **不會**轉為 `done`（只寫 `date_done`），真正反映完成的是 `stock_moves.state`。
  以單據 state 做冪等判定會導致守門永遠不生效。
- **Builder API 兩個必填／衝突**：`DELETE /source/files` 需 `expected_version`；
  發布若會移除既有 action 會回 409 `ACTION_REMOVAL`。
- **Internal App 執行期網址**為 `{tenant}.ai-go.app/runtime/{slug}`，
  並註明 App 渲染在 Shadow DOM 內（自動化測試會踩到）。
- **Server Action 必須 publish 後才可呼叫**，只 sync 會回 404。

`troubleshooting.md` 同步新增 8 條錯誤速查，皆指向本檔對應章節。

### `db.json` 不再是 Data Reference 的判定依據（★ 修正既有指引）

實測 `src/db.json` 在 VFS 內恆為 `{}`，即使 Data Reference 全部註冊成功——
它是執行期注入檔。原先 SKILL.md Phase 0 有一條 ★ 重要步驟要「解析 db.json 列出
SaaS 表、欄位、權限、`app_domain` 分布」，照做只會拿到空清單。

- `SKILL.md` Phase 0 步驟 5、Phase 1.5 盤點步驟改走
  `GET /api/v1/refs/apps/{app_id}`，並明說 db.json 不可作為判定依據。
- `custom-app-dev-guide.md` §19 兩軌差異表、§19 決策流程、§22.x 加入引用流程、
  `CONTEXT.md` 同步改口徑。

### 靜默出錯的兩條升為核心規則

`platform-behaviors.md` 是按需讀取的，但 `offset` 分頁與 `validate_picking` 冪等
這兩條**不拋例外、不報警告**，agent 不會因為看到錯誤而去翻文件。故規則本體
放進常駐的 `SKILL.md`（核心規則 26、27）。

### 其他

- `custom-app-dev-guide.md` §7 ctx 清單補 `ctx.erp` 並指向 `platform-behaviors.md` §4.2。
- §18 app_domain 補上「前端過濾 + 500 筆上限」的複合風險警語。

## 1.3.0

### 租戶邊界：補上「表沒有 `tenant_id` 不等於沒保護」

- **起因**：開發者實測回報「`announcement_reads` / `import_mappings` / `ir_sequences` /
  `msg_messages` / `account_accounts` 沒有 `tenant_id`，是 bug 嗎？」——查證結論是
  **五張全部刻意設計、租戶隔離正常**，但本 Skill 先前完全沒有描述租戶邊界形態，
  §20.2 的回應範例又剛好拿了自帶 `tenant_id` 的 `customers` 當例子，等於默認
  「每張表都有 `tenant_id`」。Agent 依此推論會走上兩條錯路：誤判該表不安全而改用別的表，
  或自己補 `WHERE tenant_id = ...`（那些表根本沒這欄位，直接失敗）。
- **新增 `custom-app-dev-guide.md` §20.3「租戶邊界：不要用『有沒有 `tenant_id`』判斷」**：
  列出 DB Proxy 的四種邊界形態（自帶 `tenant_id` ／ 欄位別名 `company_id` ／ 父表歸屬
  `EXISTS` 子查詢 ／ 全域表刻意不過濾）與各自的代表表，並給兩條實作守則
  （不自補 `WHERE tenant_id`、不因缺欄位就改用別的表）。原 §20.3 典型使用流程順延為 §20.4。
- **`SKILL.md` 新增核心規則 25「表沒有 `tenant_id` 不等於沒保護」**（★ 強制）：
  reference 是按需讀取的，但真正會誤判的時點是 Phase 1.5 查欄位結構的當下，
  agent 未必開過指南——故規則本體放進常駐的 SKILL.md，並在 Phase 1.5「資料架構設計」
  盤點步驟就地補一句警語。
- **§20.2 補註**：明示回應範例是「自帶 `tenant_id`」形態，不是每張表都有。
- **§17 常見問題速查**：新增一列，讓 agent 不必讀完 §20 就能命中答案。
- 平台側同步：AI GO repo `docs/integrations/custom-app-agent.md` §7.2 補上第四種形態
  （全域表）與同一條警語。

## 1.2.0

### 對外 API 呼叫改回 `ctx.http.call` 閘道（反轉 1.1.0 的指引）

- **1.1.0「直接 `import httpx`」的指引已被實測推翻**：AI GO runner pod 是
  **default-deny egress**（`httpx`/`requests`/`urllib.request` 在沙箱 denylist，
  出口網路只放行平台閘道與 DNS），raw httpx 直連**必定 timeout**。
  實測（2026-07-28，Developer 平台沙箱）：raw `httpx.get(...)` 20 秒 timeout；
  `ctx.http.call` 3/3 成功。raw httpx 寫法的 action 測不過沙箱，
  而送審門檻要求每支 enabled action 至少一次 success——等於卡死。
- 對外呼叫一律 **`ctx.http.call("<egress-slug>", "<path>", method=..., body=...)`**：
  base_url 與憑證來自租戶在後台 `/dashboard/settings/integrations` 以**同名 slug**
  註冊的 **EgressService**。回傳 dict（`status` + `data`），要自己檢查 status。
- **憑證不可自帶 `Authorization` header**：閘道會剝掉自帶的授權標頭
  （AI GO `connector_proxy._sanitize_headers` 與 Developer 平台 `dev_ctx._STRIPPED`
  兩邊都剝），實測回 **401**。金鑰歸 EgressService，action 不碰，
  也不需要為它開 `ctx.secrets` key（`ctx.secrets.get()` 留給 webhook 驗簽等
  非對外憑證用途）。
- 同步改寫：
  - `SKILL.md`：Phase 0 步驟 8（盤點 egress slug、raw httpx 標記必改）、
    Phase 1.5 項目 4.6（盤點表改 `slug + base_url`、金鑰不開 secret key）、
    Phase 3「呼叫外部 API」範例、ctx API 清單補 `ctx.http.call`、
    「錯誤處理：Action 對外呼叫失敗」（timeout／401 對症分流）
  - `custom-app-dev-guide.md` §25：全面改寫（呼叫寫法、EgressService 註冊、
    症狀對照表、規劃階段盤點）；§7 ctx API 清單補回 `ctx.http.call`；§17 速查列同步
  - `troubleshooting.md`：「Action 打第三方 API 連不出去」「Action 超時」兩列
- 寫法對齊 aigo-template-transfer-skill v0.4.0（鐵律 6、pollution-signals、
  `raw_http_outbound` 掃描規則）。

## 1.1.1

- 後台頁面一律改用**相對路徑**指引（`/dashboard/settings/integrations`、`/dashboard`），
  不再寫死主機名稱——子網域日後可能變動。
  與 `event-triggers.md` 既有的 `/dashboard/settings/app-crons` 寫法一致。
- §25.2 補上這條慣例，避免後續文件又寫回完整 URL。

## 1.1.0

### 對外 API 呼叫與 Egress 白名單

- **移除 `ctx.http.call` 的所有記述**（SKILL.md、`custom-app-dev-guide.md` §7）。
  原本把它列為呼叫外部 API 的方式，會把 agent 帶往錯誤路徑。
- Server-Side Action 呼叫第三方 API 一律**直接 `import httpx`**，
  金鑰走 `ctx.secrets.get()`，並強制設 `timeout=`。
- 新增 `custom-app-dev-guide.md` **§25 對外 API 呼叫與 Egress 白名單**：
  呼叫寫法、白名單設定位置（後台 → Settings → Integrations）、
  權限不足時的處置、被擋掉時的診斷準則。
- Egress 白名單納入流程各階段：
  - Phase 0 新增步驟 8「盤點對外呼叫與 Egress」
  - Phase 1.5 新增計畫項目 4.6「對外 API 呼叫盤點」——規劃階段就要列出網域並提醒申請
  - SKILL.md「錯誤處理」新增「Action 對外呼叫失敗」小節
  - `troubleshooting.md` 新增對應速查列
- 核心準則：對外呼叫失敗時**先讀 API 回傳的 error message**；
  指向 Egress 或權限就停止改 code，引導用戶設定白名單
  （看不到設定頁 = 權限不足，請租戶管理員代設）。

### 憑證與 Token

- 新增 `aigo_auth.get_token()` 作為所有 API 呼叫的統一入口：
  依序嘗試「未過期 Token 快取 → `refresh_token` 換發 → `.aigo/.env` 帳密登入」。
- Token 快取於 `.aigo/token.json`，剩餘不足 5 分鐘提前換新
  （平台 Token 效期 1 小時，避免長流程中途 401）。
- 憑證改放 `.aigo/.env`（`.gitignore` 已涵蓋 `.aigo/`），**每台機器設定一次**即可，
  不必每次開發前設環境變數；環境變數仍為合法來源。
- `aigo_auth.py` 新增 CLI：`setup` / `login` / `status` / `logout`
  （`status` 不顯示秘密值）。
- Phase 0 明訂 agent **不得向用戶索取、代為輸入或寫入密碼**；
  憑證檔一律由使用者本人填寫。
- `run_e2e_tests.py`、`retest_verification.py` 改讀 `.aigo/.env`。

## 1.0.0

- 首次標記版本號。
- 新增 Skill 自我更新檢查機制：`VERSION`、`scripts/check_update.py`、
  SKILL.md「Phase -1：Skill 自我更新檢查」、Claude Code / Codex SessionStart hook 範本。
