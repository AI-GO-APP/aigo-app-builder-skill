# 使用者授權架構與成員／角色管理

> **定位**：兩個入口共用本檔——
> ① `SKILL.md` Phase 1.5 計畫第 **1.7 項「授權架構選型」**的 SSOT（新建與遷入兩條路都走）；
> ② 資料操作線的一條 playbook：以**登入者本人**的 JWT 批次建邀請連結、增刪改查角色，
> 不建 app、不走 `/open/*`、不用 app 憑證。
> 端點、權限與後端硬閘核自 ai-go `main`（2026-09-08，v1.13.1 之後）：
> `backend/app/api/invitations.py`、`members.py`、`core/permissions.py`、`core/invite_links.py`、
> `infra/auth-proxy/internal/core/cookies.go`。

---

## 0. 立場（★ 判任何授權問題前先讀）

- **AI GO 的帳號體系是內外人員共用的**：員工、外部經銷商、合作夥伴、客戶……凡是要**登入**的人
  都是**租戶成員**，差別只在掛什麼**角色**。角色決定「能做什麼」（permissions），
  app 的角色白名單 `access_role_ids` 決定「看得到哪支 app」（§3）。
- 因此**「誰在登入」不再決定 app 模式**：只要有登入者，Custom App 一律 `starter-internal`、
  Hosted App 一律 `visibility=internal`。「員工後台＋客戶前台」不是拆成兩種模式的理由——
  同一支 internal app 用角色分流，或拆成兩支 internal app 各掛不同 `access_role_ids`。
- **不在 app 內另建使用者表、角色表、登入流程**（SKILL.md 規則 23）。遷入案的 `users` 表
  也不例外（§7）。
- 「角色群組」在平台裡**沒有獨立物件**——`Role` 只有 `category` 分類欄（如 `System`、`Sales`）。
  你要的「外部經銷商群組」就是一個角色，`category` 填 `External` 之類方便管理員辨識。
- Custom App 的 `external` 模式**不是**「給外部人用」的意思，它只對應一種需求：
  **Custom App 內要有不登入就能看的匿名頁**，而且拆不成 Hosted public 靜態站。
  沒有這個需求就不要提它；有這個需求先評估 Hosted public（`product-line-decision.md` §3 問題二），
  真的判進 external 才讀 `custom-app-dev-guide.md` §14／§15，並把「平台核可、無 SLA」列進計畫。

## 1. 授權架構選型（計畫第 1.7 項）

輸入：§1.0 需求盤點的「使用者群」清單、1.5 的 app 分配表。三問問完填表，缺一不算完成計畫。

| # | 問什麼 | 決定什麼 |
|---|---|---|
| 一 | **有哪些使用者群**？（員工的哪些部門、外部經銷商、客戶、稽核……） | 每群一個角色：沿用租戶既有角色，或**新開**（§5）。新開的角色列出 permissions，且必須是建角色者權限的**子集**（§2） |
| 二 | **每支 app 誰能開**？ | `access_role_ids`（§3）。空＝全租戶成員都能開；只給特定群就填角色 id。**兩條產品線都有這個欄位** |
| 三 | **人怎麼進來**？已是成員／要邀請／從既有系統搬遷 | 邀請走 §4（一人一連結、落點直達 app）；搬遷走 §7 |

**產出：授權架構表**（寫進計畫，與 app 分配表並列；用戶確認後照表建角色、設白名單、發邀請）：

```
| app（alias） | 模式 | access_role_ids（角色名） | 角色 → permissions（新開／沿用） | 進入方式／邀請落點 |
```

預設情況一列：`| <alias> | starter-internal | （空＝全租戶成員） | 沿用既有角色 | 已是成員 |`。

**填表時要攤開的陷阱**（每條都在計畫裡明寫，不留到上線）：

- **非員工帳號沒有員工列**：租戶「資料存取規則」（Auth gate，`custom-app-dev-guide.md` §27）的
  `restrict` 規則若用到 `$user.employee_id`／`$user.department_id`／`$user.manager_id`，
  對經銷商這類帳號**解不出→整列 deny→403 `policy_denied`**（enforce 後）。
  對外部人員的角色，規則只能用 `$user.id`／`$user.role_ids`，或另設 app 級規則放行；
  計畫裡要提醒租戶管理員這一點。
- **Hosted internal app 內做不到依角色分功能**：proxy **不給容器任何身分**（§6，2026-09-09 實打），
  連使用者 id 都沒有。角色分流只能在門口（`access_role_ids`）做；
  要在畫面內依角色開關功能 → 該部分做成 Custom internal app（`__USER_PERMISSIONS__` 快照）。
- **判斷授權用 permission 標籤，不用角色名**（角色可被改名，SKILL.md 規則 23）。
- **經銷商角色的 permissions 從空集合起步**：Custom internal app 的資料存取走 Server Action
  （app 憑證，SKILL.md 規則 31），成員本身不需要模組權限就能用 app；只有 app 前端要直呼
  模組 REST 或平台功能頁時才逐項加。權限給多了，這個人在平台主站也拿得到——
  `system.*`、`hr.*`、`accounting.*` 這類不要給外部人員。
- **邀請一人一連結、48 小時過期、受邀者要驗證信箱**（§4 邊界）——批次邀請經銷商時要規劃
  誰轉交連結、過期怎麼重發。

## 2. 端點與權限對照

| 動作 | 端點 | 需要的權限 |
|---|---|---|
| 建邀請（回連結） | `POST /api/v1/invitations`，body `{email, name, role_ids[], redirect_url?, send_email?}` → 回 `token`、`chat_invite_link` | `system.invitations` |
| 列／作廢邀請 | `GET /api/v1/invitations`、`DELETE /api/v1/invitations/{token}` | `system.invitations` |
| 邀請成員（另一入口） | `POST /api/v1/members`（body 含 `role_ids`、`redirect_url`、`send_email`）→ 回 `chat_invite_link`；`POST /members/{id}/resend-invite` 重寄 | `hr.member_manage` |
| 列角色 | `GET /api/v1/members/roles` | `system.roles_manage` |
| 建角色 | `POST /api/v1/members/roles`，body `{name, comment?, category?, permissions[]}` | `system.roles_manage` |
| 改角色（含權限字串） | `PUT /api/v1/members/roles/{role_id}` | `system.roles_manage` |
| 刪角色 | `DELETE /api/v1/members/roles/{role_id}` | `system.roles_manage` |
| 改成員角色 | `PUT /api/v1/members/{id}`，body `role_ids[]` | `hr.member_manage` |
| Custom App 角色白名單 | `PATCH /api/v1/builder/apps/{app_id}/settings`，body `{access_role_ids: [...]}` | `builder.manage_access` |
| Hosted App 可見度與白名單 | `PUT /api/v1/hosted-apps/{id}/access-settings`，body `{visibility, access_role_ids}` | `hosted_apps.deploy`，再收窄到 app 的 `created_by`／admin |

**憑證**：這些端點都掛 `require_permission(...)`，**只有真人 JWT 打得到**——
`aigo_auth.get_token()` 取的就是登入者本人的平台 JWT。隨附整合 API Key 只走 `/open/*`、
Deploy Token 只認 `/hosted-apps*`、Custom App 的 service token 掛在無角色的 service account 上
（403）、app-scoped 瀏覽器憑證的路由表不含 members／invitations／roles。

**後端硬閘**（AI 不用自己判，但要能解讀 403，§8）：

- 建角色：新角色的 `permissions` 必須是**呼叫者權限的子集**（`assert_can_define_role_permissions`）。
- 邀請／指派時帶 `role_ids`：每個角色的 `permissions ⊆ 呼叫者權限`，且角色屬本租戶
  （`assert_can_grant_roles`）。持 `hr.member_manage` 的人**不能**把「系統管理員」派給任何人。
- `system.admin` 短路第 2 道，不短路租戶邊界。

## 3. app 角色白名單 `access_role_ids`（兩條產品線）

| | Custom App | Hosted App |
|---|---|---|
| 設定端點 | `PATCH /builder/apps/{id}/settings {access_role_ids}` | `PUT /hosted-apps/{id}/access-settings {visibility, access_role_ids}` |
| 空陣列的語意 | 所有人可用（internal 下＝全租戶成員） | **`internal`＋空＝全租戶已登入成員**；`public` 下必須為空（DB CHECK） |
| owner 免檢 | app 的 `user_id` | app 的 `created_by` |
| 不在名單的人看到 | **404「App 不存在」**（fail-closed，與查無此 app 同形，不用 403 洩漏存在性）；資料面、action、compile、cron 端點同一守門 | proxy 依 `is_hosted_app_visible_with` 判定，不可見同樣不放行 |

- `access_role_ids` 是**可見度**，不是資料授權：進得了 app 的人能打到 app 所有 action，
  action 內仍要用 `ctx.user_permissions` 分流（SKILL.md 規則 23／31）；資料層的人軸交給
  Auth gate（dev-guide §27）。
- 角色 id 從 `GET /members/roles` 取；寫入前把「角色名 → id」對照印給用戶確認。
- 開發者自己有 `builder.access` 也**不再無條件繞過**白名單（action／compile 端點已收緊）——
  測試時把自己的角色放進名單，或用 owner 帳號。
- 2026-09-08 測試租戶實打：兩條線設定後 GET 立即讀回一致；錯的角色 id 兩線同一句 400「角色不存在或不屬於此租戶：<id>」；
  Custom 送非 UUID 400「access_role_ids 含無效的角色 ID（需為 UUID 格式）」；Hosted `public`＋角色 422
  「public visibility 不可搭配 access_role_ids」。受限帳號側的 404 未實打（§8）。

## 4. 邀請：批次建連結的固定流程

```
1. aigo_auth.py status                                    ← 工作區＝租戶；登錄表可為空
2. aigo_data.py me                                        ← 確認有 system.invitations（或 hr.member_manage）
3. aigo_data.py call GET /api/v1/members/roles            ← 角色名 → id；要新開角色先走 §5
4. 讀名單（csv／json：email, name, 角色名）→ 印出「N 人、角色、落點」給用戶確認（§3.5 寫入閘門）
5. 先試一筆 POST /api/v1/invitations，讀回 chat_invite_link 驗證落點正確
6. 迴圈其餘，每筆記錄 email, name, roles, chat_invite_link, expires_at；失敗列單獨列出
7. 輸出表交給用戶轉交（send_email=false 時平台不寄信）
```

**四個邊界**（平台行為，不是 skill 限制）：

1. **一人一連結，沒有匿名多人共用連結**：`InvitationCreate` 要求 `email` 或 `user_id` 至少一個；
   註冊端比對 email，不符回 400「Email 與邀請不符」。
2. **48 小時過期**；同租戶同 email 重發會作廢先前 pending 的那張。
3. **帶外連結的受邀者仍要走信箱驗證**：只有平台代寄（`send_email: true` 且投遞成功）那條路免驗證；
   你拿回來轉交的連結，受邀者註冊時仍要驗證收件信箱。
4. **端點沒有限流**，迴圈數百次不會被擋；但 `data-operations.md` §3.5 寫入閘門對所有 POST
   都適用——批次仍要「估影響面 → 試一筆 → 確認」。

**`redirect_url` 落點白名單**（fail-closed 422；核自 `core/invite_links.py`）：
`/app-login/`、`/runtime/`、`/customApp/`、`/builder/`、`/dashboard/`、`/onboarding`、`/hosted-app-handoff/`。

- `/app-login/{slug}`：**直達 internal Custom App 的登入頁**，中間不繞 `/register`；
  slug 是 app 的 `url_name`／自動 slug，純 ASCII `[A-Za-z0-9/._~-]`，不可含 `?`／`#`，≤256 字
- `/hosted-app-handoff/{slug}`：直達 Hosted internal app
- 其餘前綴走 `/register?token=…&redirect=…`；**不指定落點的受邀者會落在 `/dashboard`**——
  對只有 app 角色的外部人員那是他沒權限的地方，**邀請外部人員一律指定落點**
- 重寄（`resend-invite`）省略 `redirect_url` 會沿用上一張的落點
- **`POST /members` 與 `POST /invitations` 在 `send_email:false` 下是同一件事**（★ 實打）：都只建邀請、回
  `token`＋`chat_invite_link`，`POST /members` 回應的 `id`／`user_id` 是 `null`——受邀者註冊完成前**沒有成員列**，
  之後要改角色（`PUT /members/{id}`）或重寄（`resend-invite`）都要先從 `GET /members` 找到他的 id
- 批次名單的 slug 一律用 app 的**自動 slug**（`GET /builder/apps/{id}` 的 `slug`，12 位十六進位），
  不用 `url_name`——後者可含中文，會被 422 擋

## 5. 角色 CRUD 流程

```
1. GET /api/v1/members/roles              ← 現況：名稱、category、permissions、is_system_role
2. aigo_data.py me                        ← 呼叫者的 permissions＝可鑄造的權限全集（子集規則）
3. 擬定：name、category、permissions[]   ← 外部人員角色從 [] 起步（§1 陷阱）
4. 把「現況 → 改動後」的 diff 印給用戶確認（§3.5）
5. POST／PUT；讀回 GET 驗證
```

- `is_system_role=true` 的角色不可刪；同租戶角色名唯一（409）。
- 改既有角色的 `permissions` 會**立即影響所有掛該角色的人**——改前看 `GET /members/roles` 回的
  `user_count`（★ 實打有此欄）；`access_whitelist_count` 是有多少支 app 把它放進白名單。
- 刪角色會**連帶從各 app 的 `access_role_ids` 清掉**，回應帶 `access_whitelist_cleaned`／`access_whitelist_locked`
  計數（★ 實打）——刪外部角色前先確認沒有 app 只靠它放行，否則那些 app 會退回「全租戶成員可開」。
- `system.admin` 帳號**可以**改系統角色（`is_system_role=true`）的 permissions（★ 實打 200）——腳本不要碰它們，
  §3.5 閘門在這裡尤其重要。
- 權限字串以 `aigo_data.py me` 印出的清單為準，不手抄；拿不到的字串（不在呼叫者權限內）
  建角色會 403（§8）。

## 6. Hosted internal app 收到的身分：沒有

**門口擋得住，門內認不出人。** auth-proxy 驗過登入後把請求轉給容器，但**不傳遞任何身分**——
2026-09-09 測試租戶實打（`internal` ＋ `access_role_ids=[]`，容器把收到的 header 原樣印出）：

- 容器只看到 `Host`／`Accept`／`Forwarded`／`X-Forwarded-*`／`X-Request-Id` 這類轉送 header，
  **一個 `X-Aigo-*` 都沒有**；平台 cookie 也在進容器前被剝掉，所以 `Cookie` 同樣沒有
- ⇒ app **連「這是哪一位使用者」都不知道**，更沒有 email／roles／permissions。
  「app 內要『誰』可以、要『能做什麼』做不到」這個舊說法要整條退回：**兩個都做不到**
- 容器內的 `AIGO_API_TOKEN` 是 **app 身分不是使用者身分**：打 `/api/v1/auth/me`、`/api/v1/members*`
  一律 401；`/open/proxy` 打 `users`／`roles`／`user_role_rel`／`members` 一律 403（平台身分表，
  引用面列不出來）。拿使用者 id 去查角色這條路**不存在**（也拿不到 id）
- **已回報平台（2026-09-09）**，不必重複開單

⚠️ 1.35.0 以前本節列的四個注入 header（`X-Aigo-User-Id`／`-Tenant-Id`／`-App-Id`／`-Population`）
是**錯的**——那屬於平台另一條尚未接線的資料面設計。

**要在畫面內依角色開關功能**：① 該部分做成 Custom internal app（runtime 有 `__USER_ROLES__`／
`__USER_PERMISSIONS__` 快照）；② Custom App 當前端 ＋ Hosted 設 `public` 當後端、由 app 自驗簽章
（`hosted-apps.md` §5.1）；③ 按角色拆成多支 internal Hosted App，各掛不同 `access_role_ids`（§3）。
401 處置與 cookie 剝除見 `hosted-apps.md` §6。

## 7. 既有系統的使用者搬遷

原系統的 `users`／`accounts` 表**不進**資料表映射（`migration-workflow.md` §2.4）。人一律成為租戶成員：

| 原系統的登入者 | 去向 | 怎麼做 |
|---|---|---|
| 員工 | 租戶成員＋既有角色 | 已是成員的不用動；不是的走 §4 邀請，落點直達 app |
| 外部經銷商／客戶／夥伴 | 租戶成員＋一個新開的外部角色（`category` 標 External） | §5 建角色 → §4 批次邀請（名單從原 users 表匯出 email／name）→ 落點指定 app |
| Hosted **public** 站的匿名訪客 | 不是使用者，不遷 | 若原站有會員登入，優先評估改 Hosted internal＋角色；確需 app 自理才連原認證一起搬（`hosted-apps.md` §7.1） |

- **密碼 hash 不遷**：受邀者走邀請連結設定新密碼；溝通流程要先寫進計畫。
- 使用者表上跟著人走的業務欄位（偏好、等級、標籤…）拆出來存自建表，以**平台 user id** 當 key。
- 原系統的「群組／角色」表 → 對映成平台角色（§5），不要建成自建表。

## 8. 回應怎麼讀（2026-09-08 測試租戶擁有者帳號實打；★ 標記＝實測字串）

**成功回應的形狀**（拿來寫驗證，不要猜）：

| 端點 | 實測 |
|---|---|
| `GET /members/roles` | ★ `{items: [{id, name, comment, permissions[], is_system_role, sequence, category, user_count, access_whitelist_count}]}`——`user_count` 是掛此角色的人數，改權限前看這格 |
| `POST /members/roles` | ★ 201，回角色物件（無 `user_count`） |
| `POST /invitations` | ★ 200 `{token, chat_invite_link, user_id: null}`；落點 `/app-login/{slug}` 時連結形狀 `https://<租戶>.ai-go.app/app-login/{slug}?token=…`，不帶落點時 `…/register?token=…` |
| `GET /invitations` | ★ `{items: [{email, name, role_ids[], status, expires_at, invited_by_id, token, chat_invite_link}]}`；同 email 重發後**舊那張 `status` 變 `expired`**（不是 `revoked`）；`expires_at` ＝ 建立時間＋48h |
| `DELETE /invitations/{token}` | ★ 204 無 body |
| `POST /members`（`send_email:false`） | ★ 200，但 **`id` 與 `user_id` 都是 `null`**——受邀者註冊前沒有成員列，`PUT /members/{id}` 改角色要等他註冊完成；回應同樣帶 `token` 與 `chat_invite_link`（落點照 `redirect_url`） |
| `PATCH /builder/apps/{id}/settings` | ★ 200 回整個 app 物件（含 `vfs_state`，很大——驗證只看 `access_role_ids`） |
| `PUT /hosted-apps/{id}/access-settings` | ★ 200 回 hosted app 物件，`visibility`／`access_role_ids` 立即生效；`POST /hosted-apps` 不帶 `visibility` 時預設 `public` |
| `DELETE /members/roles/{id}` | ★ 200 `{detail: "已刪除", access_whitelist_cleaned, access_whitelist_locked}`——平台會把該角色從各 app 的 `access_role_ids` 清掉並回計數 |

**錯誤回應對照**：

| 症狀 | 意思 | 處置 |
|---|---|---|
| `POST /members/roles` 400 ★「不允許的權限：xxx」 | 權限字串不存在（**不是**子集規則；子集規則才 403） | 字串以 `aigo_data.py me` 或既有角色的 `permissions` 為準，不手抄 |
| `POST /members/roles` 409 ★「資料重複：相同的唯一值已存在。」 | 同租戶角色名重複 | 先 `GET /members/roles` 查，重用既有角色 |
| `POST /members/roles`／帶 `role_ids` 的邀請 403 | 目標角色的 permissions 不是呼叫者權限的子集，或想鑄造的權限超出自己所有（後端子集規則） | 印出兩邊 permissions 差集給用戶看；請更高權限者操作，**不要**改用別的角色硬塞 |
| 邀請／白名單帶角色 id 400 ★「角色不存在或不屬於此租戶：<id>」 | `role_ids`／`access_role_ids` 裡的 id 錯（三個端點同一句：`POST /invitations`、`PATCH /builder/apps/{id}/settings`、`PUT /hosted-apps/{id}/access-settings`） | 角色 id 一律從 `GET /members/roles` 取，不從別的租戶或舊筆記抄 |
| `PATCH /builder/apps/{id}/settings` 400 ★「access_role_ids 含無效的角色 ID（需為 UUID 格式）」 | 送了角色名或非 UUID | 名 → id 先對照 |
| `POST /invitations` 422 ★「邀請落點不可含 ? 或 #（連結尾端要接 token，會互相衝突）」／★「邀請落點不在允許清單內：/app-login/、/runtime/、/customApp/、/builder/、/dashboard/、/onboarding、/hosted-app-handoff/」／★「邀請落點只允許英數字與 / - _ . ~」 | `redirect_url` 形狀不合（fail-closed） | 照 §4 白名單組落點；slug 用 app 的自動 slug（純 ASCII），不要用含中文的 `url_name` |
| `POST /invitations` 422 ★「invitations require either user_id or email」 | 沒給 `email` 也沒給 `user_id` | 一人一筆，email 必填 |
| `DELETE /invitations/{token}` 404 ★「Invitation not found.」 | token 不存在或已被新邀請作廢清掉 | 用 `GET /invitations` 現查 |
| `DELETE /members/roles/{id}` 404 ★「角色不存在」 | id 錯或已刪 | — |
| `PATCH /builder/apps/{id}/settings {allow_anonymous_access: true}` 400 ★「Internal App 不支援匿名存取」 | internal 開匿名 | 匿名頁拆 Hosted public（`product-line-decision.md` §6），不是換模式 |
| `PUT /hosted-apps/{id}/access-settings` 422 ★「public visibility 不可搭配 access_role_ids」 | `public` 帶了非空白名單 | 要限角色就 `internal`；`public` 時 `access_role_ids` 送 `[]` |
| `POST /invitations` 403 | 呼叫者沒有 `system.invitations` | 換 `POST /members`（需 `hr.member_manage`）或請管理員授權 |
| 用 Deploy Token／`AIGO_API_TOKEN`／app token 打任何本檔端點 401／403 | 憑證體系不對（§2） | 換登入者 JWT，不是 bug |
| 使用者開 app 拿 404「App 不存在」 | 角色不在 `access_role_ids` 內、或 app 未發布 | 先查白名單再查發布狀態；不是路由問題（受限帳號側的 404 形狀**未實打**，核自 `core/permissions.py`） |
| 403 body 帶 `reason`／`rule_id` | 租戶資料存取規則擋的（人軸） | `custom-app-dev-guide.md` §27；外部人員角色特別注意 `$user.employee_id` 類規則 |

未實打（測試租戶只有擁有者帳號）：子集規則的 403 本體、受限帳號開 app 的 404、`PUT /members/{id}` 改角色、
`resend-invite`（要有已存在的成員列）。這幾條的行為核自 `core/permissions.py`（`assert_can_grant_roles`／
`ensure_app_visible`）與 `api/members.py`。

## 9. 這條線不做的事

- 不為了邀人或改角色建 app、建整合；不走 `/open/*`、`/ext/*`。
- 不猜權限字串；子集規則 403 就停，請更高權限者操作。
- 不用 `system.admin` 帳號替一般使用者做他自己沒權限的事而不告知。
- 不在 app 內另建帳號、角色、登入流程；不把原系統 users 表建成自建表。
- 不主動提 Custom App external 模式；只有 §0 的匿名頁條件成立才展開。
