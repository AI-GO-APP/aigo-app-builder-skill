# UAT 環境（每支要上正式的 app 都要有「UAT 結論」；dev-rules.md 規則 33）

> 2026-09-21 立。起因：既有 AI GO 專案普遍沒有 UAT——Custom App 部署腳本寫死正式站、Hosted App 沒有第二顆，
> 「測試」不是在正式 app 灌 demo 資料就是換個租戶。本檔從第一個遷入案的做法抽出通則，
> 但**那一個案子的拓撲不是所有專案的拓撲**——先照 §1 鏡像自己的系統，再挑 §3 適用的步驟。

## 目錄

- 0. 一句話（含 0.1 `version-test` 不是 UAT）
- 1. 先鏡像拓撲
- 2. 資料庫：一定分開
- 3. 建置步驟（含 3.5 使用者：只補測試者）
- 4. 驗證
- 5. 維運

---

## 0. 一句話

UAT 是**與正式邏輯隔離、資料隔離**的第二套系統，鏡像正式的拓撲，用 `-uat` 命名，
獨立資料庫與憑證，排程／通知／webhook **預設停用**，逐項驗過才開。
「在正式 app 灌 demo 資料」「換一個租戶測」都**不算** UAT（前者污染正式資料，後者測不到租戶自己的設定）。

**規則 33 要的是「結論」，不是無條件蓋一套**：每支 app 在計畫階段寫一句 `UAT＝有；拓撲 X` 或
`UAT＝無；理由 Y；風險 Z`（例：純展示頁、沒有正式資料、關掉就沒事）。沒寫＝沒過閘。
判準是**有沒有正式資料會被測試污染、有沒有對外副作用**；兩者都沒有的 app 可以寫「無」。

### 0.1 `version-test` 不是 UAT

Custom App 的草稿版（`{租戶}.ai-go.app/runtime/version-test/{識別碼}`，`platform-behaviors.md` §6.2）驗的是
**畫面**：同一份 VFS、**同一個資料落點**，寫入會進正式的表。只有「Custom-only 且資料落點能用旗標切到另一組表」
的 app，才可以拿 `version-test`＋分離落點當 UAT；其餘要照 §1 另建。

## 1. 先鏡像拓撲（不是「clone 一顆 Hosted」）

把正式系統的每個組件列出來，逐個決定 UAT 對應物：

| 正式組件 | UAT 對應 | 命名 |
|---|---|---|
| Custom App（入口／前端／action） | 再建一顆同模板的 Custom App | `url_name` 加 `-uat`（例 `<name>-uat` → `{租戶}.ai-go.app/runtime/<name>-uat`）；**建立時就要帶**，發布後凍結（§3 步驟 4） |
| Hosted App | 再一顆 Hosted App | slug 加 `-uat`（例 `<slug>-uat.deploy.ai-go.app`）；slug 是**申請**不是保證，clone 回應要回讀 |
| 平台自建表 | 同租戶內**另一組表**（表名前綴或 `_uat` 後綴），或走 §2 的外接庫 UAT 專案 | — |
| 外接 PostgreSQL（dev-rules.md 規則 32 例外） | 租戶的 `<tenant>-uat` 專案（一租戶一顆 UAT，服務以 schema 分） | `<tenant>-uat` |
| 外部服務（egress slug） | 指向正式後端的 slug 要另建一支指向 UAT | `<slug>-uat` |
| 平台排程 | UAT **先不建**；要驗排程時另建並指向 UAT 的 action | — |
| Webhook 接收、通知、LINE、Email | 指向測試用目的地或關閉 | — |
| 檔案（Storage） | 同租戶 Storage 另開資料夾前綴 | `uat/` |
| **使用者** | **同一個租戶、同一批成員**——沒有「UAT 租戶」。差別只在 app 的角色白名單（§3 步驟 4、`member-admin.md` §7） | UAT 專用角色 |

只有 Custom App 的專案：對應物就只有第一列（加自建表那列）。多服務的專案：每個服務各一列。

## 2. 資料庫：一定分開

- 平台自建表：UAT 用另一組表或 UAT 專案。**不要**讓 UAT app 讀寫正式表——「同一份程式、換一個環境變數指不同庫」
  的設計是 UAT 的前提，遷入案在計畫階段就要有這個旗標。
- 外接 PostgreSQL：租戶已有正式專案時，UAT 是**同組織下另一顆** `<tenant>-uat`，不是同一顆的另一個 schema——
  同顆會共用 compute 與備份範圍，UAT 灌資料會拖慢正式。
- UAT 資料：用正式 dump 的**去識別化**副本，或合成資料。含真人個資的正式 dump 直接灌 UAT
  要租戶 owner 同意並限制誰能登入（§3 步驟 4 的 UAT 角色就是那道限制）。

## 3. 建置步驟（Hosted + Custom 入口的形狀；其他形狀挑用得到的）

每一步都要冪等（重跑不重複建、不輪替金鑰），最後有 §4 的驗證。端點都在 `/api/v1` 下。

1. **外接庫**（若適用）：開 `<tenant>-uat`，密碼寫進本機 `.aigo/<something>-uat.env`（600，不進 git）。
2. **Hosted App**：`POST /hosted-apps/{正式id}/clone`，body `{"name": …, "slug": "<slug>-uat"}`；回應的 `slug` 要回讀。
   ⚠️ **clone 會整包複製正式的 env、`always_on`、持久碟、資源規格、`visibility`、`access_role_ids`，而且 Knative
   會立刻起一個 pod**——在你覆寫之前，那個 pod 是拿**正式設定**在跑（實測窗口約 6 秒）。所以：
   - clone 前確認正式 `always_on=false`（不然 clone 出來就常駐）；
   - clone 後**立刻**做步驟 3 的 env 覆寫，中間不做別的事；
   - 緊接著 `PUT /hosted-apps/{id}/access-settings` `{"visibility": "internal", "access_role_ids": [<UAT 角色>]}`
     ——正式若是 `public`，clone 出來的 UAT 第一天就是全網可達（`member-admin.md` §3）；
   - 到平台補上「clone 帶 env 覆寫」之前，這個窗口只能縮短不能消除——寫進計畫。
3. **env 覆寫**：`PUT /hosted-apps/{id}/runtime-settings` 是**全量替換**（`hosted-apps.md` §4），所以用**白名單重建**，
   不是「改幾個已知的鍵」：逐鍵決定沿用／換值／清空。最少要動的：資料庫連線（指 UAT 庫）、session secret／
   cron key／換票金鑰（全部新值，正式與 UAT 不共用）、所有回指自己的網址改成 UAT 網址、入口網址改成 UAT 入口、
   空庫開站門禁只放建置者、通知／推播／第三方金鑰清空；`always_on=false`、`persistent_disk=false`（除非 UAT 真的要驗持久碟）。
4. **入口 Custom App**：`POST /builder/apps`（同模板，body 帶 `url_name: "<name>-uat"`）。
   ⚠️ `url_name` **發布後永久凍結**，`-uat` 必須在建立時就帶上；正式 app 的 `url_name` 可能是 `null`（中文名產不出），
   這時自己指定一個全新的 `<something>-uat`，不要從正式的名字推導（`custom-app-dev-guide.md` §26）。
   然後 `PATCH /builder/apps/{id}/settings` `{"access_role_ids": [<UAT 專用角色>]}`——**不要沿用正式的
   `access_role_ids`**：同一個租戶，沿用等於把 UAT 磁貼發給全體正式使用者。UAT 角色先用 `member-admin.md` §5 建
   （例名 `<app>-UAT測試`），只發給測試者。
5. **外部服務**：`GET /builder/apps/{id}/available-egress-services` 看正式入口用哪些 slug；指向正式後端的 slug 另建
   `POST /builder/apps/{id}/egress-services` `{"name": …, "slug": "<slug>-uat", "base_url": "<UAT Hosted>", "auth_type": "none"}`；
   再 `PUT /builder/apps/{id}/authorized-egress-services` **body `{"services": [{"service_id": "<uuid>"}]}`**
   （送 id 字串陣列會 422，CHANGELOG 1.39.1）。**不做這步，發布會 409 `EGRESS_NOT_READY`**。
   Builder UI 的「外部服務」tab 是同一件事的介面（`custom-app-dev-guide.md` §25.2）。
6. **Secrets**：`POST /actions/apps/{uat入口id}/secrets` `{"key_name": …, "value": …}` 注入與 UAT Hosted **同值**的換票金鑰
   與 cron key（已存在就 `PUT /actions/secrets/{secret_id}`）。兩邊不同值＝換票一律 401。
7. **Open Proxy 引用**：clone 建的是**新的**隨附整合，預設表引用**不會**帶過去；UAT Hosted 若走 Open Proxy 讀預設表，
   要對 UAT 的整合重做 `POST /refs/apps/{整合id}`（`hosted-apps.md` §5），否則 403。走外接庫、不讀平台表的可暫時略過。
8. **前端 VFS**：打包時把寫死的正式 Hosted 網址與 egress slug 換成 UAT 的（用環境變數注入打包腳本，
   **原始碼不動**，預設值時輸出逐位元組不變）；同步到 UAT 入口、編譯、發布。
9. **排程**：不建。要驗排程時另建一支指向 UAT 入口 action 的平台排程，驗完停用。

### 3.5 使用者：只補測試者，不邀整批人

身分綁在 AI GO——租戶成員＋app 角色是第一道門，app 自己的名單是第二道，兩道門怎麼走依產品線不同，
正本在 `member-admin.md` §7。UAT 只做三件事：

- 先確認**指定的測試者**已經是租戶成員、掛了步驟 4 的 UAT 角色；沒有就只為他們補（發角色不寄信；邀請會寄信）。
- **不要為了 UAT 邀整批人**：租戶只有一個，UAT 與正式入口共用成員——邀進來就是正式上線，那是客戶（租戶管理員）的事。
- app 自己那道門（例：外接庫裡的人員名單）在 UAT 庫裡也要有測試者，且信箱要跟他的 AI GO 帳號一致。

## 4. 驗證（少一項不算搭好）

| 項目 | 怎麼驗 | 通過 |
|---|---|---|
| 後端活著 | `GET <uat hosted>/login`（或首頁）200；沒帶身分打 API 401 | 兩個狀態碼對 |
| 接的是 UAT 庫 | 後端的自檢端點回報的主機／ref 是 UAT 的 | ref 對、非正式 |
| 正式沒被碰 | 正式的排程留痕表在 clone 窗口內沒有來自 UAT pod 的列；正式 env、`visibility`、`access_role_ids` 未變 | 零筆、未變 |
| 磁貼只有測試者看得到 | 用非測試者帳號開 UAT 入口 → 平台「無法存取此應用」 | 被擋 |
| 入口可進 | `{租戶}.ai-go.app/runtime/<name>-uat` 200，測試者登入後換票成功 | 進得去 |
| 403 對照 | 用 UAT app 身分讀一張有 `$user.*` 規則的預設表：`POLICY_GATE_MODE` **翻旗後**預期 403；仍 off 時回 200 **不算失敗**（`hosted-apps.md` §5）——UAT 正是翻旗前先看到這條的地方 | 符合當下旗標 |
| 金鑰隔離 | 拿正式的 cron key 打 UAT 端點 → 403 | 舊值失效 |
| 排程／通知未動 | UAT 沒有平台排程；通知目的地為空或測試值 | 確認 |

## 5. 維運

- **owner 與到期日**：UAT 一開就寫誰負責、預計用到何時、月費多少（Hosted 走租戶方案；外接庫另計）。
- **金鑰輪替**：Hosted 與入口 App 的換票金鑰、cron key 是**成對**的，輪替要兩邊一起，驗證舊值失效。
- **資料重灌**：UAT 庫可以整顆清掉重灌；清之前確認沒人在用。
- **退場**：專案結束時刪 UAT Hosted（會連 PVC 一起刪）、UAT 入口、`<slug>-uat` 外部服務、UAT 角色、UAT 庫。
