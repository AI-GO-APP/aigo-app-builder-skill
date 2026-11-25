# AI Hub：平台內建 AI 與 AI Credit（能力邊界、模型、四個呼叫面、計費與錯誤處置）

> app 要「呼叫 AI」（摘要、分類、抽欄位、讀 PDF／圖片、聊天）時讀本檔。AI Hub 是平台代管的模型閘道（後端是
> OpenRouter）：不用自己申請 OpenAI／Anthropic 金鑰、不用建外部服務，費用從**租戶的 AI Credit** 扣。
> 逐一模型的清單與實打結果在附表 **`ai-hub-models.md`**。
>
> **怎麼驗證的**：2026-11-24／25 在測試租戶（付費、專屬運算池）prod 全面實打——173 個模型逐一呼叫、四個呼叫面、
> 串流、檔案、`ctx.ai`、錯誤路徑、吞吐，600 多次 HTTP 呼叫（另有 Action 內、Hosted 容器內與 SDK 實跑的呼叫），
> 總花費約 USD 0.125（約 58 Credit）。再對照平台 `origin/main`（最新 tag v1.22.1）：`backend/app/api/ai_hub.py`、
> `backend/app/services/{ai_hub_service,ai_hub_exec_spec,credit_service,quota_service}.py`、
> `backend/app/core/{action_context,rate_limit,scope_map,scope_scan}.py`、`infra/aihub-executor/`、
> `docs/architecture/{ai-hub-execution,usage-and-quota}.md`、`docs/integrations/custom-app-agent.md` §7.2a／§8.4。
> 內文標「（實打）」的是 prod 實測過，標「（原始碼）」的只核過原始碼；**沒能實打的項目列在 §13**。

## 目錄

- §1 什麼時候用 AI Hub、什麼時候不用
- §2 開放條件：四個前提，缺一就不能用（★ 規劃時先查）
- §3 能力邊界總表：做得到／做不到（★ 規劃時先看）
- §4 模型目錄：有哪些模型、怎麼挑、旗標可不可信
- §5 四個呼叫面：怎麼呼叫、授權、實打狀態
- §6 請求契約：欄位、互斥、上限、平台不檢查的地方
- §7 檔案輸入：怎麼拿 `file_id`、格式、大小、兩種 PDF 引擎
- §8 前端 `AI_SDK`：取得方式、非串流、串流、錯誤物件
- §9 Action `ctx.ai`：同步文字、帶檔案的工作（目前不可用）、逾時與錯誤形狀
- §10 錯誤碼與處置（有沒有扣錢、能不能重送）
- §11 吞吐與時間上限：頻率限制、併發、逾時
- §12 AI Credit：怎麼算、誰在扣、怎麼查
- §13 實打紀錄與未驗證項目
- §14 規劃與交付檢查清單

---

## 1. 什麼時候用 AI Hub、什麼時候不用

| 情境 | 走法 |
|---|---|
| app 要呼叫 LLM（文字、結構化 JSON、讀 PDF／圖片） | **AI Hub**（本檔）——預設選它 |
| 要的能力 AI Hub 沒有（生圖、語音、embedding、聯網搜尋、function calling、調 `temperature`，§3） | 自帶金鑰：`ctx.http.call` 打供應商 API，金鑰放 `ctx.secrets`（`custom-app-dev-guide.md` §25）；費用走客戶自己的供應商帳單，**不扣 AI Credit** |
| 租戶不符 §2 的開放條件（免費或共用運算），或客戶指定要用自己的供應商帳號 | 同上，自帶金鑰 |
| 只要「從企業知識中心找相關段落」 | `ctx.knowledge.search`——純向量檢索、**不經 LLM、不扣 AI Credit**；要生成回答再把結果餵給 AI Hub |
| 智能客服自動回覆（LINE 等通訊渠道） | `ctx.messaging.trigger_ai_reply`，是另一套系統，不在本檔範圍 |

⚠️ **不要在 action 裡用 `ctx.http.call` 打平台自己的 `/api/v1/ai-hub/*`**——那是瀏覽器面，要使用者或 app 憑證；
Action 一律用 `ctx.ai`。

## 2. 開放條件：四個前提，缺一就不能用（★ 規劃時先查）

| # | 前提 | 不滿足時 | 怎麼事先查 |
|---|---|---|---|
| 1 | **付費租戶，且開了專屬運算池**（`complete` 跑在租戶專屬 executor） | 403 `dedicated_compute_required`；免費租戶、付費但用共用池都是這個，**沒有退路**（平台池不代跑）。這個檢查排在平台自訂碼的 422（`model_not_allowed`、`model_no_image_input`、`conflicting_*`、`invalid_messages` 等）之前，不符資格的租戶送這類請求會先拿到 403；但格式層的 pydantic 422（未知欄位、`max_tokens` 不是正整數等，`detail` 是陣列）仍比 403 先回（原始碼） | `GET /api/v1/tenant/compute`（要 `builder.access`）：回 `dedicated: true` 才行；免費租戶直接 403。回應**沒有** Action 檔案工作（§9）就緒與否的欄位 |
| 2 | 專屬池的 executor 已就緒 | 503 `tenant_compute_not_ready`＋`Retry-After: 5`（零支出，可重送）；剛開池、搬遷中、縮零後第一發、或 30 秒內排不到 executor 都可能遇到 | 無查詢端點，照 §10 重送 |
| 3 | 租戶有可用的 AI 金鑰（平台代配） | 503 `ai_not_provisioned`（推論前擋下，不扣錢） | 無查詢端點；遇到就請租戶管理員找平台 |
| 4 | **授權**：呼叫面各自的權限／scope（§5） | 403（使用者權限不足，`detail` 是字串、沒有 `code`）或 403 `app_scope_denied` | 使用者權限看角色設定；app scope 看 `GET /api/v1/apps/{app_id}/scopes` |

另有額度：AI Credit 用完回 429（§10、§12）。**`GET /ai-hub/models` 不檢查第 1–3 項**——列得出模型
**不代表** `complete` 打得通，判斷能不能用一律看 `/tenant/compute`。

## 3. 能力邊界總表（★ 規劃時先看）

| 能力 | 做得到嗎 | 細節 |
|---|---|---|
| 文字對話（chat completions） | ✓（實打） | 輸出**只有文字**；`messages` 1–100 則，`role` 實際能用的只有 `system`／`user`／`assistant`（§6） |
| 結構化 JSON 輸出 | ✓（實打） | `response_format` strict JSON schema；12 個旗標為真的模型（8 家）全部回出合 schema 的 JSON。**平台不檢查模型支不支援**，挑模型要自己看旗標（§4） |
| 讀圖片 | ✓（實打） | PNG／JPEG／WebP／GIF，**只能用平台檔案 `file_id`**（不收 URL、base64、`image_url` 訊息段）；模型要 `supports_image_input`（§7） |
| 讀 PDF | ✓（實打） | 預設引擎平台先抽文字（任何模型都能讀，但單檔實際上限約 5 MiB）；`engine: "native"` 原檔交給模型（要 `supports_file_input`）（§7） |
| 一次多檔 | ✓（實打） | `file_ids` 最多 20 個、總量 ≤ 40 MiB，依序附在最後一則 user 訊息 |
| 串流（SSE） | ✓（internal、Hosted 實打；ext 面同一套程式、未實打） | `ctx.ai` 不行。**預設模型與部分推理模型不會逐字吐**，整段在最後一次到（§8） |
| 備援模型（`models`） | ✓（實打） | 上游**最多收 3 個**（平台驗證寫 8，4 個以上上游拒收（400）、平台回 422 `ai_upstream_rejected_request`）（§6） |
| 讀/寫 app 私有檔（`ctx.storage`）給 AI | 只有 Action 能送，而 Action 的檔案工作**目前跑不起來**（§9）；Hosted 用 `/open/storage` 的檔可以（實打） | internal 前端讀不到 app 擁有的檔（一律 404，連擁有者都一樣，實打） |
| 調參數：`temperature`、`top_p`、`seed`、`stop`、`n`、`logprobs`、`frequency_penalty`… | ✗（實打） | 未知欄位一律 422 `extra_forbidden` |
| Function calling／tools、`tool` 角色 | ✗（實打） | `tools`／`tool_choice` 422；`role: "tool"` 驗證會過但送不出 `tool_call_id`，上游必拒 |
| 指定託管商（provider routing）、推理強度（`reasoning`）、OpenRouter `plugins`／`transforms` | ✗（實打） | 都是 422；託管商由上游依請求內容自動路由，同一模型可能換家 |
| 生圖、語音、embedding、聯網搜尋、moderation | ✗（原始碼＋實打目錄） | 目錄只上架「輸入含文字、輸出只有文字」的模型，173 個裡沒有這類模型 |
| 查價格、查剩餘額度 | ✗ | `/models` 不含價格；app 執行期沒有額度查詢端點（§12） |
| 單次時間 | 同步／串流 600 秒（原始碼） | Action 內受 `timeout_ms` 限制（上限 120 秒，§9）；併發與頻率見 §11 |

## 4. 模型目錄：有哪些模型、怎麼挑、旗標可不可信

**2026-11-24 快照：173 個模型、8 家供應商**（OpenAI 46、Qwen 40、Google 23、Mistral 21、Anthropic 15、
DeepSeek 14、xAI 7、Meta Llama 7）；讀圖 126 個、原生 PDF 87 個、JSON schema 169 個；
**實打 168 個叫得通**、4 個每次都失敗、1 個當天被上游限流未能判定。逐一清單、每個模型的探針成本與能力實測矩陣見
**`ai-hub-models.md`**。

**目錄怎麼來的**（原始碼）：

- 每小時（:41）從 OpenRouter 同步；**自動上架**只收：供應商在白名單（上面 8 家）、id 不帶 `:` 變體
  （沒有 `:free`／`:online`）、輸入含文字且輸出只有文字、不是分類器、價格有效、**輸出單價每百萬 tokens ≤ USD 60**。
  其他模型要平台營運手動上架
- 模型從 OpenRouter 目錄消失滿 **7 天**才停用；所以**列在 `/models` 不代表叫得通**——實打有 4 個列著卻叫不通
  （隔天再查四個都已被上游下架，`ai-hub-models.md` §3），會回 422 `ai_upstream_rejected_request`
- 每個程序快取目錄 60 秒
- **預設模型**：營運指定的那一筆，否則平台內建預設（當天 `openai/gpt-6-luna`，`is_default: true`）。預設模型會換，
  而且它是**推理型**（§6 `max_tokens`）

**`GET …/models` 的回應**（實打）：HTTP body 是 `{"models": [...]}`（前端 `AI_SDK.listModels()` 與 `ctx.ai.list_models()`
會拆成陣列），每筆 8 個欄位：`id`、`display_name`、`provider`、`context_length`、`supports_image_input`、
`supports_file_input`、`supports_structured_output`、`is_default`；**不含價格**（平台不對租戶公開單價）。
排序固定：openai、anthropic、google、x-ai、deepseek、meta-llama、mistralai、qwen，再依名稱。

**能力旗標可不可信**（實打，`ai-hub-models.md` §4）：

| 旗標 | 平台有沒有擋 | 可信度 |
|---|---|---|
| `supports_image_input` | 有：送圖給旗標為假的模型 → 422 `model_no_image_input`（零成本，`models` 每個候選都檢查） | 可信（旗標為真就收圖）：實測 21 個旗標為真的模型，20 個讀對 128 px 圖；gpt-4.1-nano 在 128 px 以下會誤讀、512 px 才對，圖要夠大（§7） |
| `supports_file_input` | 有：只擋 `engine: "native"` 的 PDF → 422 `model_no_file_input` | 可信 |
| `supports_structured_output` | **沒有**：旗標為假照樣 200、照樣扣錢，模型可能回散文 | 旗標本身大致正確，但平台不保證輸出是 JSON |

**怎麼挑模型**：

1. 程式一律執行期現查 `/models`，**用旗標篩、不寫死 id**；要讓使用者挑就用它填選單
2. 要結構化輸出 → 篩 `supports_structured_output`，而且 `JSON.parse` 一律包 try/catch
3. 要讀圖 → 篩 `supports_image_input`；圖要夠大（§7）；**每張圖計的 tokens 差上百倍**（gpt-4o-mini 一張 128 px 圖約
   8500 tokens，同圖在 haiku／gpt-5-nano 約 20–30）
4. 要低延遲、串流要逐字出現 → 避開推理型與預設模型（§8）；推理型的 `max_tokens` 要給到數百以上
5. 成本級距看 `ai-hub-models.md` 的「探針 USD」欄：同一短提示最便宜與最貴差約 7.7 萬倍（mistral-nemo 約 USD 2.1e-07 對 gpt-6-astra-pro 約 USD 0.016）；OpenAI `*-pro` 與部分 grok
   會在上游自帶 1,200–2,700 個隱藏 prompt tokens、照計費，短請求也很貴
6. 上游可能下架或限流 → 用 `models` 給 2–3 個備援，或收到 `ai_upstream_rejected_request`（`upstream_status` 404）時換下一個

## 5. 四個呼叫面

| 呼叫面 | 怎麼呼叫 | 端點前綴 | 串流 | 帶檔案 | 授權 | 實打狀態 |
|---|---|---|---|---|---|---|
| **internal app 前端** | `AI_SDK`（§8；**新建的 app 預設沒有，也補不進 `src/api.ts`**） | `/api/v1/ai-hub` | ✓ | ✓ 同步回結果 | **使用者**要有 `ai.hub.invoke` 權限，再疊 app 憑證的 API 群 `ai.hub.write`（`platform-behaviors.md` §12） | ✓ 擁有者 JWT 實打過 models／complete／串流／檔案；app 憑證實打過 models／complete／串流（帶檔案只驗了 404） |
| **external app 前端** | 同一支 `AI_SDK`，依 `__IS_EXTERNAL__` 改打 ext | `/api/v1/ext/ai-hub` | ✓ | ✓ 本 app 的檔＋雲端硬碟 External／指定本 app 的檔（§7） | **app scope** `ai.hub.invoke`（讀 `published_scopes`），不驗使用者權限；只收 external 使用者的登入憑證 | ✗ 只驗了 401 與 405——要 external 使用者帳號才打得進去，**擁有者的預覽憑證也打不進**（§13） |
| **Server Action** | `ctx.ai.*`（§9） | （runner 內部） | ✗ | 回 `job_id` 非同步——**目前跑不起來** | app scope `ai.hub.invoke`；internal 發布時自動宣告＋核可，external 只宣告、要擁有者核可 | ✓ 文字同步；✗ 檔案工作在測試租戶三支 app 共 11 次全部 `ai_job_not_started` |
| **Hosted App** | 自己 `fetch`，`Authorization: Bearer $AIGO_API_TOKEN` | `/api/v1/open/ai-hub` | ✓ | ✓ 同步回結果（`file_id` 來自 `/open/storage`） | 隨附整合的 scope `ai.hub.invoke`（`hosted-apps.md` §5.2） | ✓ 容器內全部實打過（models／complete／串流／JSON／檔案／錯誤） |

三個 HTTP 面共用端點：`POST /complete`、`GET /models`、`GET /jobs/{job_id}/result`；
`DELETE /jobs/{job_id}/result` **只有 internal 面有**（ext、open 回 405 `Allow: GET`，實打）。
Hosted 的 `AIGO_API_TOKEN` 打瀏覽器面 `/api/v1/ai-hub` 會 401（實打）——Hosted 一律走 `/open`。

**internal 前端的兩層授權**：

- **使用者權限 `ai.hub.invoke`**：預設角色**都沒有**它（原始碼：沒有任何預設角色種入它），等於只有
  `system.admin`（擁有者）能用，其他人要先到角色設定開「平台 AI（AI Hub）呼叫」。它和 `ai.access`（AI 助手 Cowork）
  是兩回事。缺權限回 403、`detail` 是字串 `權限不足，缺少: ai.hub.invoke`、沒有 `code`（原始碼）
- **app 憑證**：app 執行期拿的是 `POST /api/v1/app-scoped-token/{app_id}?env=online` 發的短效憑證（實打：
  有效 900 秒、要 app 已發布，否則 404 `App 尚未發布`；scope ＝ app 宣告 ∩ 使用者權限 ∩ 瀏覽器面 scope；
  app 憑證不能自己續發，回 403 `credential_minting_forbidden`）。**prod 現況閘門沒有在擋**：scope 是空的 app 憑證
  照樣能 models／complete／串流（實打），enforce 那天才會 403

**`ai.hub.invoke` 是高風險 scope**：external app 與 Hosted App 核可它時，平台要求核可人當場輸入**自己的密碼**
（`reauth_password`；沒帶回 401——external 實打、Hosted 原始碼；SSO 無密碼帳號 403，要先設密碼，原始碼）。
**agent 不代填密碼**——請擁有者到 Builder 的 Scope 分頁（external）或 Hosted 詳情頁「平台 AI 與檔案」自己開。
external app 核可後**要再發布一次**才生效：ext 面與上線 runner 只讀 `published_scopes`，核可只寫 `granted`，
發布時才凍結成 `published`；重發時 granted 又會收斂成「舊 granted ∩ 掃描結果」，所以要有 action 用 `ctx.ai` 才留得住。
Hosted 隨附整合核可當下就自動發布，不用重發（原始碼）。
Hosted 現況：隨附整合 scope 全空時 `/open/ai-hub` 照樣 200（實打）——閘門也沒在擋，但仍要照規範開。

⚠️ **發布時的自動宣告只掃 `actions/*.py`**（實打）：

- **internal**：action 有 `ctx.ai` → 發布後 `requested`／`granted`／`published` 都有 `ai.hub.invoke`（自動核可）。
  只在前端用 `AI_SDK`、沒有 action → 三者都是空的，app 憑證也就不帶它；現況照樣能用，**enforce 那天前端 AI 呼叫會 403**。
  做法同 `planning.md` 第 4.7 項：在 Builder「API 權限」分頁把 AI Hub 群開起來，或放一支用 `ctx.ai` 的 action
- **external**：發布只把 `ai.hub.invoke` 放進 `requested`，`granted`／`published` 維持空的（不自動核可）；
  前端專用（沒有 action 用 `ctx.ai`）的 `ai.hub.invoke` 就算手動宣告＋核可，下次發布也會被收斂掉（原始碼：
  發布時 requested 以掃描結果覆寫、granted 取舊 granted ∩ 掃描結果）。external app 要用 AI，**把 AI 呼叫放進 Action**——掃得到、
  也才能在伺服端擋濫用（external 使用者不是租戶成員，前端直打等於任何註冊者都能花租戶的錢）。
  ⚠️ 但 Action 的檔案工作目前不可用（§9），要讀檔的 external 需求先回報用戶
- `GET /builder/apps/{id}` **沒有** scope 欄位（回應模型不含），要看 requested／granted／published 一律打 `GET /api/v1/apps/{app_id}/scopes`（實打）

## 6. 請求契約

三個 HTTP 面共用 `AiHubCompleteRequest`，**未知欄位一律 422**（`extra="forbid"`）。實打逐一確認會 422 的：
`temperature`、`top_p`、`tools`、`tool_choice`、`seed`、`stop`、`n`、`user`、`reasoning`、`plugins`、`provider`、
`transforms`、`stream_options`、`max_completion_tokens`、`frequency_penalty`、`logprobs`……

| 欄位（前端 SDK 用 camelCase） | 說明（皆實打） |
|---|---|
| `messages` | 1–100 則。`role` 驗證收 `system`／`user`／`assistant`／`tool`，但 **`tool` 實際不能用**：`tool_call_id` 會被丟掉、也不能帶 `tools`，上游一律拒收（400）→ 422 `ai_upstream_rejected_request`、不扣錢（連完整的 `assistant.tool_calls`＋`tool` 串也一樣）。平台 `AI_SDK` 的 TypeScript 型別也列了 `'tool'`，型別檢查會過，別被誤導（原始碼）；`developer`／`function` 直接 422。`content` 只收字串或 `[{type:"text", text}]`——`image_url`、`file` 段、段落多帶 key、非字串 text 一律 422 `invalid_messages`；空字串或空陣列被上游 422。訊息上多帶的 key（如 `name`、`tool_call_id`）在 HTTP 面**被默默丟掉**；`ctx.ai` 則每則只能有 `role`、`content`，多帶就回 `{"status":"error","reason":"invalid_messages"}`（原始碼）。只有 system、只有 assistant 的對話都能跑 |
| `model` ／ `models` | 二擇一（同時給 422 `conflicting_model_selection`；這個碼與下面的 `invalid_model_selection` 在 HTTP 面依原始碼、`ctx.ai` 實打）。都不給（或空白字串）＝平台預設。不在目錄 422 `model_not_allowed`（`models` 任一個不在也是）。**`models` 實際只能 1–3 個**：平台驗證收到 8 個，但 4 個以上上游拒收、平台回 422 `ai_upstream_rejected_request`（`upstream_status` 400、訊息 `'models' array must have 3 items or fewer.`、不扣錢；已回報平台（2026-11-25），不必重複開單）；9 個以上、空陣列、空白 id 是 pydantic 422；重複 422 `invalid_model_selection`。行為：用第一個叫得通的，第一個已下架會自動落到下一個；計費與回應的 `model` 都是實際用的那個 |
| `max_tokens`（`maxTokens`） | 正整數（`0`、負數、`"16"`、`1.5`、`true` 都是 pydantic 422，HTTP 面拿不到 `invalid_max_tokens` 這個碼）。**含推理 tokens**：推理型模型給 16 會回 200、內容空、`finish_reason: "length"`、照扣錢——173 個裡有 44 個這樣（抽 6 個改給 200 都有回答，其餘沒重試）；做結構化輸出、看圖、讀 PDF 的推理模型要 1000 以上（實打 300 仍空，1000–1500 才有內容）。**不是硬上限**：太小的上限會被上游往上拉、照實際產出計費（gpt-4.1-nano／Azure 給 3、5 都產出並計 16 個；回答本來就短時照實際計），部分 `*-pro` 與 grok 會回超過上限的 tokens（實打 `max_tokens` 16 回 1030）並照計費。超大值（到 2³¹）也照收。**省略時平台不補預設**（原始碼；實打省略時沒被截斷），上游的額度預檢這時用固定上限估成本（平台 UAT 對 gpt-6 量到 65,536，本次未實打），額度低時反而更容易被 429 `request_exceeds_remaining_quota`（原始碼推論，§12）——**一律給** |
| `response_format`（`responseFormat`） | `{name, strict, schema}`；平台轉成上游的 `{type:"json_schema", json_schema:{…}}`。OpenAI 原生形狀（自己包 `type`）會 422；`strict` 寬鬆布林（`"yes"`、`"true"` 都當真）；schema 有非有限數字 422 `invalid_response_format`，其他格式錯多半是 pydantic 422。結果是 `choices[0].message.content` 裡的 **JSON 字串**，要自己 `JSON.parse`。**平台不檢查模型的 `supports_structured_output`**（§4）。可以和串流、圖片一起用 |
| `file_id` ／ `file_ids`（`fileId`／`fileIds`） | 二擇一（同時給 422 `conflicting_file_selection`）；`file_ids` 1–20 個不可重複（重複 422 `invalid_file_selection`，21 個以上 413，空陣列 pydantic 422）。帶檔案時 `messages` 一定要有 `user` 訊息（否則 422 `missing_user_message`）。細節見 §7 |
| `engine` | PDF 解析器：省略＝`cloudflare-ai`（平台抽文字），`native`＝原檔交給模型。**沒帶檔案時不檢查**——任何 64 字以內的字串都照收、被忽略（`mistral-ocr` 與超過 64 字是 pydantic 422）；帶檔案時其他值 422 `invalid_pdf_engine` |
| `stream` | `true` 回 `text/event-stream`（只有 HTTP 面；`ctx.ai` 不支援）；非布林 pydantic 422 |

**pydantic 422** 的 body 是 `{"detail": [{type, loc, msg}]}` 陣列、**沒有 `code`**（§8 錯誤物件要處理 `code` 為
`undefined`）；有 `code` 的 422 才是 `{"detail": {"code": …}}`。

**超過 context 的長輸入**：context ≤ 8k 的模型**不會報錯**，輸入被默默截短、只計剩下的 tokens（實打：4k 模型送約
6.5k → 只計 653；8k 模型送約 12.5k → 計 1670；截哪一段未確認）。這是上游 OpenRouter 對 context ≤ 8k 端點預設開的 context compression（OpenRouter 文件；32k 模型超長時上游的錯誤訊息也指向這個 plugin，實打），**呼叫端關不掉**——`plugins`／`transforms` 一律 422（實打）；2026-11-24 目錄裡 ≤ 8k 的只有 `openai/gpt-3.5-turbo-0613`（4095）、`openai/gpt-4`（8191）、`google/gemma-2-27b-it`（8192）。32k 的模型則回 422
`ai_upstream_rejected_request`（實打一個 32k 模型，更大 context 的未測）。長文件要先看 `context_length`，不要指望報錯。

**回應**（實打）：上游 chat completion 原樣（只遮掉機密）——`id`、`model`（**實際用的**）、`provider`（實際託管商）、
`choices`、`usage`（`prompt_tokens`、`completion_tokens`、推理 tokens、`cost` 美元、`cost_details`、`is_byok`）、
`service_tier`。回應標頭只透出 `content-type`、`x-generation-id`（＝ body 的 `id`）、`retry-after`、`x-request-id`，
帳務待補時多一個 `X-AIHub-Accounting: pending`。非串流回應上限 8 MiB，超過變 502 `ai_inference_indeterminate`（原始碼）。

## 7. 檔案輸入

**`file_id` 從哪來**——每個呼叫面只認自己那條上傳路徑的檔：

| 呼叫面 | 上傳端點 | 讀得到的檔 |
|---|---|---|
| internal 前端 | `POST /api/v1/files/upload`（multipart：`file`、`parent_id`、`add_to_knowledge`；要 `files.access`；30 次／分鐘，超過 429＋`Retry-After: 60`）回的 `id`（實打，擁有者 JWT） | 登入使用者有權限的雲端硬碟檔。**app 擁有的檔（`ctx.storage`／app-storage）一律 404**，app 自己的憑證、擁有者都一樣（實打）。`POST /api/v1/storage/upload` 不建檔案節點、沒有 id，**不能**餵 AI Hub |
| external 前端 | `/ext/storage/upload`（原始碼） | 本 app 上傳的檔，加上雲端硬碟裡存取設定為 External 或指定給本 app 的檔（原始碼）；其他一律 404 |
| Action | `ctx.storage.upload(...)` 回的 `file_id`，或使用者權限讀得到的雲端硬碟檔 | 本 app 的檔；排程／webhook 觸發時只讀得到「無角色成員」看得到的檔 |
| Hosted | `POST /open/storage/upload` 回的 FileRef（實打） | 同 external：本 app 上傳的檔＋雲端硬碟 External／指定本 app 的檔（後者原始碼）；其他一律 404 |

查無、不是 uuid（含空字串）、資料夾 id、已刪除、沒權限（含 app 擁有的檔）全部同形 404 `{"code":"not_found"}`、
零成本（實打）；未 `ready` 的檔也是同一個 404（原始碼）——不能用 404 分辨「格式錯」與「沒權限」。

**格式與大小**（實打）：

- 只吃 **PNG、JPEG、WebP、GIF、PDF**。其他類型（如 `text/plain`）在平台端 422 `unsupported_ai_input`；
  宣告的 MIME 與實際位元組不符、壞圖、超過 1 億像素在 executor 端 422 `unsupported_file_type`——兩者都不扣錢。
  上傳時的 `mime_type` 是客戶端宣告的，執行時會再驗實際內容
- 單檔 ≤ 20 MiB、總量 ≤ 40 MiB、最多 20 個，超過 413 `ai_input_too_large`（推論前擋下）
- **預設 PDF 引擎（`cloudflare-ai`）單檔實際約 5 MiB 就被上游拒**（5,138,710 B（約 4.9 MiB）過、5,453,283 B
  （約 5.2 MiB）起回 422 `ai_upstream_rejected_request`、訊息是檔案超過解析器上限；確切界線在兩者之間）——遠低於 20 MiB。大 PDF 改用 `engine: "native"`
  （實打 19.5 MiB 可過，模型要 `supports_file_input`），或先拆檔
- 檔案附在**最後一則** user 訊息，多檔依序；圖片、PDF 可混送

**兩種 PDF 引擎怎麼選**：

| | 預設 `cloudflare-ai` | `native` |
|---|---|---|
| 模型要求 | 任何模型（純文字模型也行） | `supports_file_input`，否則 422 `model_no_file_input` |
| 單檔實際上限 | 約 5 MiB | 20 MiB |
| 成本 | 只有抽出文字的 tokens，通常便宜（grok-4.20：USD 0.00022） | 依供應商差很大（同檔 grok-4.20：USD 0.0063；Anthropic 約 12 倍 prompt tokens） |
| 適合 | 文字型 PDF | 掃描檔、版面或圖表要看懂、大檔 |

**圖片品質**（實打）：小模型看小圖會誤判——`gpt-4.1-nano` 看 64 px 圖顏色全錯、128 px 左右顛倒、512 px 才對；
`gpt-5-nano` 64 px 左右顛倒；haiku、gemini 64 px 也對。要判讀細節或位置的圖送**至少約 512 px**。
`prompt_tokens` 沒增加**不代表**模型沒看到圖。

## 8. 前端 `AI_SDK`

**取得方式**（⚠️ 實打）：平台文件寫 `AI_SDK` 在 `src/api.ts`、用 `import { AI_SDK } from "./api"` 取用，但**新建的 app
的 `src/api.ts` 只有資料中心 SDK、沒有 `AI_SDK`**（starter-internal、starter-external 都一樣，範本預覽也一樣）。照文件寫那行
import 會編譯失敗：`No matching export in "src/api.ts" for import "AI_SDK"`。而且這個檔**補不進去**：
- `src/api.ts` 是保護檔，從原始碼 API 寫入（連只加一行註解）都回 403 `PROTECTED_FILE_WRITE_REJECTED`，本機同步也不上傳它
- Builder「開發」分頁注入的 SDK **只留在編輯器、不會存進草稿**，編譯讀的是草稿（平台文件明寫，原始碼相符）——
  所以「請擁有者開一次開發分頁」**沒有用**。實打的是 API 建的 app；Builder 網頁建的 app 依原始碼應該一樣，未實打

做法（實打可行）：把 `AI_SDK` 那段（含它用到的 `__API_BASE__`／`__APP_TOKEN__`／`__IS_EXTERNAL__` 讀法與錯誤處理）
放進**自己的非保護檔**，例如 `src/aiHub.ts`，再從那裡 import——實打編譯成功、bundle 內有 `ai-hub` 呼叫。
要點：讀 `window.__API_BASE__`（預設 `/api/v1`）、`window.__APP_TOKEN__`（帶成 `Authorization: Bearer`）、
`window.__IS_EXTERNAL__`（決定打 `/ai-hub` 或 `/ext/ai-hub`）。**不要動 `src/api.ts`**。這是平台側的缺口，已回報平台（2026-11-25），不必重複開單。不想自己維護 SDK 副本的 internal app，也可以把文字類 AI 呼叫放進 Action 用 `ctx.ai.complete`（同步、實打可用，§9）

```typescript
import { AI_SDK } from "../aiHub";   // 自己放的非保護檔 src/aiHub.ts（上面的做法）；從 "../api" 匯入會編譯失敗

// 結構化輸出：先挑支援的模型，不寫死 id
const models = await AI_SDK.listModels();          // 已拆成陣列
const model = (models.find(m => m.is_default && m.supports_structured_output)
            ?? models.find(m => m.supports_structured_output))?.id;

const res = await AI_SDK.complete({
  messages: [{ role: "user", content: "整理這份請款單的總金額" }],
  fileId,                       // 平台檔案 id；沒有檔案就不要帶（'' 會照送並回 404）
  model, maxTokens: 2000,       // 推理型模型 max_tokens 要夠大
  responseFormat: { name: "invoice", strict: true, schema: {
    type: "object", properties: { total: { type: "number" } },
    required: ["total"], additionalProperties: false } },
});
let data;
try { data = JSON.parse(res.choices[0].message.content ?? ""); }
catch { /* 模型沒回 JSON（平台不保證），當失敗處理 */ }
```

- camelCase 對應（實打）：`maxTokens`→`max_tokens`、`responseFormat`→`response_format`、`fileId`／`fileIds`→
  `file_id`／`file_ids`，`model`／`models`／`engine`／`stream` 原樣；`undefined` 的選項不送，`signal` 不序列化
- 回傳是上游 chat completion 原樣；內容可能是 `null`（推理吃光 `max_tokens`），取值要防呆
- **錯誤物件**（實打 422／404／401；429、503 與 `err.retryAfter` 以真 SDK 程式碼模擬＋原始碼）：一律 `throw Error`

  | 欄位 | 什麼時候有 |
  |---|---|
  | `err.status` | 一定有（HTTP 狀態；串流中途失敗是 200） |
  | `err.code` | `detail` 是物件且有 `code` 時才有。**pydantic 422（陣列）、401、頻率限制 429 都是 `undefined`** |
  | `err.message` | `detail.message` → `detail.code` → 字串 `detail` → `AI Hub Error (<status>)` |
  | `err.retryAfter` | 有 `Retry-After` 標頭時（503、429 都可能；模擬＋原始碼），單位秒 |
  | `err.upstream`／`err.upstream_status` | 上游拒絕或不可用時；`upstream_status` 是上游自己的狀態（400、404、429…） |

  判斷順序：`err.name === "AbortError"`（使用者取消，不是錯誤）→ `err.code`（照 §10）→ `code` 為 `undefined` 時看
  `err.status`（401＝登入過期、422＝請求格式錯、429＝太頻繁）。⚠️ **`err.upstream` 不要顯示給使用者**——
  裡面可能有平台的上游帳戶識別碼與供應商資訊（實打：模型已下架的 404 會帶），只記到日誌
- **重送**：`complete()` 任何狀態都**不會**自動重送；`listModels()` 碰到 429／503／網路錯誤會自動重送，連第一次在內最多試
  3 次（每次等待依 `Retry-After`，單次上限 10 秒），額度用完不重試（實打＋以真 SDK 程式碼模擬）
- 帳務待補：結果上有不可列舉的 `accountingPending: true`（`JSON.stringify` 帶不出來）——內容是好的、平台事後補帳，
  **不要重送**（只在模擬看過，實打沒遇到）
- ⚠️ **external app 在 Builder 預覽／測試網址裡呼叫 `AI_SDK` 會失敗**：擁有者預覽只處理編譯與渲染，執行期不會把預覽憑證注入 app（`__APP_TOKEN__` 留空、ext 呼叫以匿名送出，平台文件）；就算手動帶上預覽憑證，`/ext/ai-hub/models`、`/ext/ai-hub/complete` 也回 401「無效或已過期的 Token」（實打；`/ext/storage`、`/ext/data-center` 一樣）。external 的 AI 功能要用 external 使用者帳號登入正式網址測（`custom-app-dev-guide.md` §29）

**串流**（長輸出、要先顯示部分內容時）：

```typescript
const controller = new AbortController();
try {
  const events = await AI_SDK.complete({ messages, model, maxTokens: 8000, stream: true, signal: controller.signal });
  for await (const ev of events) {
    if (ev.data === "[DONE]") break;
    if (ev.event === "comment") continue;            // 上游保活 ": OPENROUTER PROCESSING" 與帳務待補通知
    const delta = ev.json?.choices?.[0]?.delta?.content;
    if (delta) append(delta);
    const usage = ev.json?.usage;                    // 最後一個 JSON chunk 帶 usage.cost
  }
} catch (err) {
  if (err.name !== "AbortError") showError(err);     // 4xx／5xx 在拿到 iterator 前就拋
}
// 使用者按停止：controller.abort()
```

- 格式（實打）：成功的串流只有 `data:` 行（沒有 `event:`、`id:`），最後一行 `data: [DONE]`；`[DONE]` 前一個 chunk
  帶 `usage`（含 `cost`），`finish_reason` 會出現兩次。上游的 `: OPENROUTER PROCESSING` 保活註解會照傳，SDK 給成
  `{event:"comment"}`。標頭和第一批資料一起到，第一個 token 之前前端拿不到任何狀態（一般模型約 0.7–1.1 秒）
- ⚠️ **預設模型 `openai/gpt-6-luna` 與 `openai/gpt-5-nano` 不會逐字串流**：整個答案在最後一次到（實打：預設模型兩次都只有 1 個內容 frame，對照 gpt-4.1-nano 34 個）。
  成因是加密推理欄位結尾像 JWT 開頭（`.eyJ…`），平台的機密遮罩把它當成可能的憑證、壓住後面所有 frame 直到 `[DONE]`（原始碼＋串流特徵推論；平台 executor README 的串流遮罩規則涵蓋這類情況）。要逐字顯示的畫面，挑
  沒有加密推理欄位的模型（實打 `gpt-5.4-nano`、`gemini-2.5-flash-lite`、haiku 都逐字出）
- 送出前的錯誤（實打 422；403、503 依原始碼同理）是一般 JSON 回應，`await complete()` 就拋、拿不到 iterator
- 串流已回 200 後的失敗：`err.status` 是 200，看 `err.code`——平台送的 `event: error`：`ai_stream_interrupted`、
  `upstream_incomplete_stream`、`upstream_stream_error`（上游 chunk 帶 error，`err.upstream` 是那個 chunk）、
  `invalid_sse_json`、`checkpoint_unavailable`、`sse_event_too_large`、`incomplete_sse_frame`、
  `sse_redaction_window_exceeded`；SDK 自己判的：`ai_stream_incomplete`（沒有 `[DONE]` 就斷）、
  `ai_stream_unavailable`（回應不是 SSE）、`ai_stream_event_too_large`（單一事件超過 1 MiB）、`ai_stream_error`
  （原始碼＋以真 SDK 程式碼模擬）
- `abort()`：下一步丟 `signal.reason`（`DOMException`，`name` 是 `AbortError`、`code` 是數字 20——**不要把 truthy 的
  `err.code` 當平台碼**）。中途取消的請求**事後會補扣**（不一定當下就扣）：平台用上游的 generation 紀錄每 10 分鐘對帳一次
  （實打：取消後約 15–40 分鐘入帳；最多對帳 5 次、間隔逐次加倍並跟著每 10 分鐘的巡檢跑，大約一個多小時內就停、之後轉平台核對，原始碼）——**不要把取消當成免費**，用量看板也會晚一點才反映

畫面要照規則 30 做四態（`dev-rules.md`）：送出中鎖按鈕（避免連點重複花錢）、失敗訊息依 §10 分「稍後再試」
與「調整內容」兩種、額度用完講清楚是「本期 AI 額度已用完」而不是籠統的錯誤。

## 9. Action `ctx.ai`

| 方法 | 用途與回傳 |
|---|---|
| `ctx.ai.complete(messages, *, file_id=None, engine=None, response_format=None, model=None, models=None, max_tokens=None, file_ids=None, stream=False)` | **`messages` 之後全部只能用關鍵字**（位置參數或多帶 `temperature` 這類參數直接拋 `TypeError`，實打）。**不帶檔案**：同步回上游 JSON（實打）。**帶檔案**：立即回 `{"job_id": "…"}`（約 0.15–0.75 秒）——但 job **目前跑不起來**（下方）。`stream=True` 回 `{"status":"error","reason":"stream_not_supported"}` |
| `ctx.ai.list_models()` | 模型清單，**直接是陣列**（不是 `{models:…}`，實打） |
| `ctx.ai.get_job(job_id)` | `{job_id, status, result_text, file_id, result_available, result_truncated, error_message}`；`result_text` 只到 64 KiB。**查無的 uuid 拋 `httpx.HTTPStatusError`（404），不是 uuid 拋 `ValueError`**（實打） |
| `ctx.ai.get_job_result(job_id)` | 完整結果 JSON（≤ 8 MiB）：`{"status":"ok","result":…}`；失敗 `reason` ∈ `not_found`／`ai_result_too_large`／`ai_result_invalid`／`result_storage_unavailable`（可重試）。**job 沒完成（pending、failed）一律 `not_found`**（實打） |
| `ctx.ai.delete_job_result(job_id)` | 刪結果；**只有已完成的 job 重複刪才冪等**，沒完成的第一次刪就回 `not_found`（實打；已完成那段是原始碼）。job 有發起者、且呼叫端帶使用者身分時兩者必須是同一人；呼叫端沒有使用者身分（如排程觸發）或 job 沒有發起者時，同 app 都能刪（原始碼） |

```python
def execute(ctx):
    try:
        r = ctx.ai.complete(
            [{"role": "user", "content": f"把這段客訴分類成 退貨／維修／詢價：{ctx.params['text']}"}],
            max_tokens=200,                      # 推理型模型要夠大
        )
    except Exception as e:                       # CtxError、httpx.HTTPStatusError、TypeError 都可能
        ctx.response.json({"ok": False, "reason": getattr(e, "error_type", None) or type(e).__name__})
        return
    if isinstance(r, dict) and r.get("status") == "error":     # ★ 一律先檢查 status
        ctx.response.json({"ok": False, "reason": r["reason"]})
        return
    ctx.response.json({"ok": True, "label": r["choices"][0]["message"]["content"]})
```

- **錯誤有多種形狀**（實打＋原始碼）：
  - `{"status":"error","reason":…}` dict——文字呼叫的所有公開錯誤（含 `quota_exceeded`、
    `request_exceeds_remaining_quota`、`model_not_allowed`、`invalid_max_tokens`、`invalid_messages`、
    `invalid_model_selection`、`conflicting_model_selection`、`ai_busy`、`ai_inference_indeterminate`），以及帶檔案的前置檢查
    （`missing_user_message`、`stream_not_supported`、`invalid_pdf_engine`、`model_no_image_input`、`invalid_file_selection`、
    `unsupported_ai_input`、`not_found`、`ai_job_enqueue_failed`……）
  - `CtxError`（`RuntimeError` 子類）——**只有帶檔案的路徑**額度不足時 `e.error_type == "QuotaExceededError"`
  - `httpx.HTTPStatusError`——`get_job` 查無（404）、scope 被拒或呼叫不存在的方法（403）。**不是 `RuntimeError` 子類**，
    只接 `RuntimeError` 會漏
  - `TypeError`（參數寫錯）、`ValueError`（`get_job` 給非 uuid；`response_format` 含 NaN／Infinity 時在 runner 端直接拋，不會回 `invalid_response_format` dict，實打一次）
- **`ctx.ai` 文字路徑不驗 `response_format` 形狀**：一樣要給 `{name, strict, schema}`（平台再包成 `{type:"json_schema", json_schema:…}`）。給錯形狀不報錯、照樣推論扣錢、內容不保證是 JSON（實打 `{"foo":1}` 與 `{"type":"json_object"}`；同樣的 body 打 HTTP 面是 pydantic 422）；照 OpenAI 原生寫法自己包 `{type:"json_schema", json_schema:{…}}` 會被再包一層，同樣不報錯（原始碼）。`engine` 沒帶檔案時被忽略（實打）
- **時間預算＝這支 action 的 `timeout_ms`**（上限 120 秒、預設 30 秒；`actions/manifest.json` 設，`custom-app-dev-guide.md`
  §7）。實打：發布後 `timeout_ms` 120000 的 action，一次 34 秒的推論成功；`timeout_ms` 30000 的同一支在約 32 秒回
  `status: "timeout"`（推論可能已扣錢）。平台這端至少等 60 秒，所以通常是 action 先逾時，而不是回
  `ai_inference_indeterminate`——**兩者都可能已扣錢，不要自動重送**
- ⚠️ **開發期試跑（dev runner）一律 30 秒封頂**，manifest 寫 120000 也一樣（實打）——長推論只能發布後測
- **`ai_busy`**：只管同步文字呼叫，**以每個後端 pod 計**：同一 pod 內同租戶最多 8 個、該 pod 所有租戶合計最多 64 個
  同時進行（prod 有 8–10 個 pod，所以不是一個全租戶或全平台固定的數字），
  滿了立刻回 dict、不排隊、未推論未扣錢（原始碼）；可能是別的租戶把 pod 塞滿。稍後重試
- **帶檔案的工作——2026-11-24／25 在付費專屬池的測試租戶上三支 app 共 11 次全部失敗**（PNG、PDF、雲端硬碟 PDF、多檔、原生 PDF）：
  `get_job` 一直是 `pending`，等到平台下一次巡檢才變 `failed`（送出後 0–10 分鐘不等；相隔幾分鐘送出的三筆在同一次巡檢一起變，實打）、`error_message: "ai_job_not_started"`；從沒進到 `processing`，
  未推論、未扣錢。原因在平台端（執行 job 的容器沒能領到工作；原始碼推論），`/tenant/compute` 看不出來，租戶這邊無解。只在一個付費專屬池租戶上驗過，其他租戶是否相同未知；已回報平台（2026-11-25），不必重複開單。
  巡檢每 10 分鐘一次（原始碼），失敗要等它才看得到，輪詢再快也沒用。因此：
  - **需要讀檔的功能先不要放進 Action**：internal 改用前端 `AI_SDK` 帶 `fileId`（同步、實打可用，但只讀得到雲端硬碟檔，
    §7）；Hosted 用 `/open`；external 目前沒有已驗證的讀檔路徑——規劃時告訴用戶
  - 若仍要寫 job 流程：存 `job_id`、由前端輪詢一支 `get_job` action 或排程收結果，`ai_job_not_started` 當可重送
    （未扣錢）處理並設上限；`status="failed"` 時 `error_message` 是封閉集合的碼（平台 `custom-app-agent.md` §8.4），
    集合外的值當未知失敗；結果用完用 `delete_job_result` 清
  - 瀏覽器端 `GET`／`DELETE /api/v1/ai-hub/jobs/{id}/result` 都要 **app 身分**（app 憑證），擁有者的平台 JWT 不論 job 狀態一律 404（實打）——用擁有者 JWT 測到的 404 不代表 job 沒完成；
    成功時 307 到 60 秒短效網址（原始碼，因 job 跑不起來未實打）
- `ai_ocr_jobs`、`ai_ocr_job_sources`、`ai_hub_invocations` 是黑名單表，`ctx.db`／proxy 讀寫不到，一律用 `ctx.ai.get_job`

## 10. 錯誤碼與處置

**扣錢的規則**（原始碼）：上游有回 `usage` 或 generation id 就照實扣，**即使上游狀態是 4xx／5xx**；只有上游沒回這兩樣的
拒絕才零成本。實打：404／413／422 的驗證與能力錯誤、上游拒收（`ai_upstream_rejected_request`）都沒扣錢；403（缺權限、
`dedicated_compute_required`、`app_scope_denied`）與 429（額度、頻率限制）沒能實打觸發，不扣錢依原始碼（都在推論前擋下）。

| 碼 | HTTP（ctx） | 扣錢了嗎 | 處置 |
|---|---|---|---|
| （無 `code`，`detail` 是字串） | 401 | 否 | 憑證無效或過期（`Invalid authentication token`／`Not authenticated`／ext 面是中文字串）→ 重新登入 |
| （無 `code`，`detail` 是字串） | 403 | 否 | 使用者缺 `ai.hub.invoke`（§5） |
| `dedicated_compute_required` | 403 | 否 | 租戶不符資格（§2 第 1 項），重送無效——改走自帶金鑰或請租戶升級 |
| `app_scope_denied` | 403 | 否 | body 的 `required_scope` 就是要開的 scope（§5）；現況閘門沒在擋，enforce 後才會出現 |
| `not_found` | 404 | 否 | 檔案或 job 不可見（§7、§9） |
| （pydantic，`detail` 是陣列） | 422 | 否 | 欄位型別或範圍錯、多帶欄位（§6），修正請求；`AI_SDK` 的 `err.code` 是 `undefined` |
| `model_not_allowed`／`model_no_image_input`／`model_no_file_input` | 422 | 否 | 模型不在目錄或不支援該輸入，從 `/models` 依旗標重挑 |
| `invalid_messages`／`missing_user_message`／`conflicting_model_selection`／`conflicting_file_selection`／`invalid_model_selection`／`invalid_file_selection`／`invalid_max_tokens`（ctx）／`invalid_response_format`／`invalid_pdf_engine` | 422 | 否 | 修正請求 |
| `unsupported_ai_input`／`unsupported_file_type` | 422 | 否 | 前者：檔案類型不是圖片／PDF；後者：內容與宣告不符、壞檔、超過 1 億像素（§7） |
| `ai_input_too_large` | 413 | 否 | 超過 20 檔／單檔 20 MiB／總量 40 MiB／spec 4 MiB（中文約 6 位元組一字） |
| `ai_upstream_rejected_request` | 422 | 否（實打） | **上游拒收這次請求**（上游 4xx，402／403／429 以外）。實打成因：模型已下架（`upstream_status` 404）、上游不認模型名、`models` 超過 3 個、輸入超過 context（實打 32k 的模型回這個碼；8k 以下的模型反而默默截斷，§6）、`tool` 角色、預設引擎 PDF 超過約 5 MiB（後面幾種都是 400）。原樣重送不會過：404 就換模型，其他照訊息修正 |
| `quota_exceeded` | 429 | 否 | **本期 AI Credit 用完**（或上游金鑰本月額度已滿），同一期內不會過；告訴使用者、請管理員加值或等下期 |
| `request_exceeds_remaining_quota` | 429 | 否 | 額度還有、但**上游**估這次會超過剩餘額度（§12）。訊息分三種：「輸出上限太大，請調小 max_tokens」→ 調小 `max_tokens` 或換便宜模型；「輸入太長，請縮短輸入或清除對話歷史」；只有前半句（未辨識）。原樣重送不會過 |
| （無 `code`，`detail` 是字串） | 429＋`Retry-After: 60` | 否 | **頻率限制**（§11）：`請求頻率超過限制`（每人／每 IP／每 app）、`租戶請求頻率超過限制`、Hosted 的 `請求過於頻繁，每分鐘上限 N 次`；等 `Retry-After` 秒（原始碼） |
| `ai_busy` | （ctx dict） | 否 | 稍後重試（§9） |
| `stream_not_supported` | （ctx dict） | 否 | `ctx.ai` 不能串流 |
| `ai_upstream_unavailable` | 502 | 通常否（回應沒有 `usage`） | 上游或平台帳戶層暫時不可用：**上游供應商限流（`upstream_status` 429）**、上游 5xx 或逾時（實打原生 PDF 約 305 秒後才回）、內容審查（上游 403）、平台帳戶額度。限流那種隔幾秒到一分鐘重送常會好（實打）——**重送要有上限與退避**；長時間不好就換模型 |
| `byok_unsupported` | 502 | 否 | 平台設定問題（原始碼），請租戶管理員找平台 |
| **`ai_inference_indeterminate`** | **502**（不帶 `Retry-After`） | **可能已扣** | **不要自動重送**——推論可能已跑完（含回應超過 8 MiB）；給使用者「結果不明，要重新送出嗎」 |
| `tenant_compute_not_ready` | 503＋`Retry-After: 5` | 否 | 照 `Retry-After` 秒數重送；連續失敗再告訴使用者「AI 服務啟動中」 |
| `ai_not_provisioned` | 503 | 否 | 重送無效，請租戶管理員找平台 |
| 串流中途的 `event: error` | 200 | 視情況 | §8 的串流錯誤碼；內容不完整，**不要自動重送**（可能已扣） |
| `ai_job_not_started` | （`get_job` 的 `error_message`） | 否 | Action 檔案工作沒開跑（§9），可重送但目前大概率再失敗 |

⚠️ 422／502 的 `detail.upstream` 是上游原始錯誤，平台只遮憑證格式、其他欄位原樣透出（原始碼），所以**可能**含平台的上游帳戶識別碼、供應商名稱與連結（實打：模型已下架的 404 會帶帳戶識別碼；供應商端 400 與部分 502／504 不帶）——**只記日誌，不要顯示給使用者**。

## 11. 吞吐與時間上限

**頻率限制**（原始碼；成功回應帶 `X-RateLimit-Limit: 600` 與 `X-RateLimit-Remaining` 已實打）：

| 呼叫面 | 上限 | 計數單位 | 超過時 |
|---|---|---|---|
| internal 前端（平台使用者 JWT） | 600 次／60 秒滑動視窗 | **每個使用者**，與 `/data`、`/proxy`、`/actions`、`/ext`、`/data-center` 等**共用同一桶** | 429，`detail` 字串、`Retry-After: 60` |
| internal 前端（app 憑證） | 600 次／60 秒 | **每個來源 IP**——prod 的 app 憑證是 EdDSA 簽章，限流只驗 HS256，驗不過就退回 per-IP 桶、也不疊租戶總量（原始碼）；同一出口 IP（同公司 NAT）後面所有 app 的憑證流量共用，**連沒帶憑證或憑證無效而 401 的請求也扣同一桶**（實打：兩支不同 app 的憑證、無憑證、亂帶 Bearer 的請求交錯扣同一個計數器，與擁有者 JWT 分開）——憑證過期還一直重試的程式會把同一 IP 後面的 app 一起拖到 429。平台程式註解與測試的原意是 app 憑證每個 app 一桶並疊租戶總量（HS256 時），prod 改用 EdDSA 後才落到 per-IP（原始碼），日後可能改回，規劃不要依賴這個行為 | 同上 |
| external 前端 | 600 次／60 秒 | **每個 app**——同 app 所有使用者共用（原始碼，未實打） | 同上 |
| 平台使用者 JWT、external 憑證再疊租戶總量 | 3000 次／60 秒 | 每個租戶 | 429 `租戶請求頻率超過限制` |
| `/open/*`（API key） | Hosted App 容器的 `AIGO_API_TOKEN`（隨附整合憑證）1200 次／分鐘；其他一般 API key 600 次／分鐘 | 每把憑證（輪替重疊期兩把各自計） | 429 `請求過於頻繁，每分鐘上限 N 次`、`Retry-After: 60` |
| `/open/*` 認證失敗 | 60 次／分鐘 | 每個來源 IP | 429 |

**實際推論併發**（原始碼＋實打）：每個租戶一個 executor 服務，每個 pod 同時 4 個、最多 2 個 pod——**全租戶所有 app、
所有呼叫面加起來最多 8 個同時推論**；但常駐只有 1 個 pod，第 2 個要等擴容。超過的請求在平台排隊、不會被拒；
排隊超過 30 秒沒領到才回 503 `tenant_compute_not_ready`。實打 12 個同時送（兩輪）：全部 200、沒有 429／503，
但一次只消化約 4–5 個，其餘分批排隊（第二輪約 1.1、2.3、3.4 秒三批；8 個同時送也是 4 個約 1.2 秒、另 4 個約 4.3 秒；
單發約 1.1 秒）。
→ 規劃批次量時，**有效吞吐約 4–8 ÷ 單次延遲**（突發以 4 估：1 秒一次約每分鐘 240 次；持續滿載擴到 2 個 pod 才接近
480；長輸出更少），而且會擠到同租戶其他 app。

**時間上限**（原始碼，Action 部分實打）：

| 項目 | 上限 |
|---|---|
| 同步與串流推論 | 600 秒（串流也在 600 秒切斷） |
| 排隊等 executor | 30 秒，超過 503 `tenant_compute_not_ready` |
| Action 內的 `ctx.ai` | action 的 `timeout_ms`（上限 120 秒；開發期試跑 30 秒） |
| Action 檔案工作 | 900 秒（目前跑不起來，§9） |
| 非串流回應大小 | 8 MiB；串流單一事件 1 MiB |

## 12. AI Credit：怎麼算、誰在扣、怎麼查

- **一個租戶一個池**：AI Hub、Cowork、Builder 的 AI、Hosted 日誌解讀……租戶內**所有** AI 用量扣同一份
  AI Credit。一支 app 把額度花光，全租戶的 AI 功能一起 429——app 有批次或大量呼叫時要在規劃時講明。
  app 憑證的呼叫也扣同一池（實打）
- **換算**：Credit ＝ 上游實付美元（`usage.cost`）× 1.5（平台加成）× 匯率（TWD／USD）× 10，四捨五入到小數 6 位。
  也就是**每 1 Credit 對應新台幣 0.1 元的售價**。匯率由平台營運手動設定、依生效時間套用，沒有自動更新
  （原始碼）。**2026-11-24 實測倍數是 465（匯率 31.0）**：`usage.cost` × 465 與 Credit 增量逐筆吻合。
  例：一次呼叫上游實付 USD 0.01 → 4.65 Credit。倍數會隨營運調整匯率而變
- **扣的時點**：上游回 `usage.cost` 後立刻入帳（實打：呼叫完馬上查月用量就看得到）；推論前被擋的都不扣（§10）。
  串流被中途取消的，事後對帳才可能補扣（§8）
- **額度怎麼擋**——三道，都在推論前（原始碼）：
  1. **平台閘門**：只比「本期已用 + 1 是否超過上限」，**不估這次要花多少**。沒有訂閱的租戶每 UTC 月 **100 Credit**；
     有訂閱的只有「平台開了強制、超額被明確關掉、預付為 0」時才擋 → 429 `quota_exceeded`
  2. **上游預檢**（OpenRouter 對租戶金鑰）：分開估「`max_tokens` × 輸出單價」與「輸入 tokens × 輸入單價」，任一個超過金鑰
     剩餘額度 → 429 `request_exceeds_remaining_quota`。省略 `max_tokens` 時上游用固定上限估（平台團隊在 UAT 對 gpt-6 量到 65,536，見平台 `usage-and-quota.md`；
     本次未實打，其他模型未知），
     **額度低時更容易被擋**；超大的 `max_tokens` 上游似乎會先壓到模型上限（實打 10,000,000 照過，推論）
  3. **上游金鑰月額度已滿** → 429 `quota_exceeded`。這是軟上限：用量約晚 10 秒反映，同時打進來的幾發會超出一點並照扣
- **查額度**：`GET /api/v1/usage/ai-credits/monthly`（要 `system.audit_log`，管理員才查得到；實打）

  | 欄位 | 意思 |
  |---|---|
  | `period.start`／`end` | 本期起訖（跟訂閱期走；沒訂閱用 UTC 月曆月） |
  | `credits` | 本期已用（即時） |
  | `included_credits`／`included_remaining` | 方案內含／內含剩餘 |
  | `prepaid_balance` | 預付餘額 |
  | `overage_credits` | 已進入超額計費的量 |
  | `limit_credits` | **本期用到這個值就會被擋**；`null`＝不設上限 |
  | `limit_overage_credits` | `limit_credits` 中期末以超額計費的部分 |
  | `key_limit_credits` | 上游金鑰本 UTC 月的硬上限換算成 Credit（營運參考用） |

  日明細：`GET /api/v1/usage/ai-credits/daily?days=1..365`（同權限）回 `{period, daily:[{date, credits, llm_calls,
  by_source}]}`——**是每晚結算的彙總，當天的用量要隔天才出現**（實打：當天大量呼叫後仍是 0），依來源分、**不依 app 分**
- ⚠️ **app 執行期不要靠查額度**：ext／open／`ctx` 沒有額度查詢端點；internal 前端用 app 憑證今天打得到 monthly
  （實打，因為閘門沒在擋、且擁有者本身有 `system.audit_log`），enforce 後就不行。app 只能照 §10 接 429；
  要給使用者看用量，請管理員到平台用量頁看
- **用量歸屬**：每次呼叫記一筆 `llm_call`、metadata 帶呼叫端 `app_id`（原始碼），但**租戶看不到依 app 的明細**——
  任何用量端點都沒有 app 維度（實打）。要分 app 估成本，只能在規劃時自己估

## 13. 實打紀錄與未驗證項目

2026-11-24／25，測試租戶（付費、專屬運算池）prod，擁有者帳號；探針資源一律 `probe-ai-*` 命名，能經 API 刪的事後都已刪除
並核對 404。平台設計上留下的殘餘：Hosted 探針的隨附整合（scope 全空、憑證已撤，API 刪不掉）、軟刪除的 Hosted 列、
已刪 Custom App 的靜態 VFS 檔（API 無法列出或刪除，未確認）。

| 範圍 | 結果 |
|---|---|
| 173 個模型逐一呼叫（`ai-hub-models.md`） | 168 個可叫；4 個每次失敗（11-24：2 個已下架、2 個上游不認模型名；11-25 再查四個都已被上游下架、仍列在 `/models`）；1 個上游限流未能判定；延遲中位數 1.27 秒 |
| 能力矩陣：32 個代表模型送圖、PDF、JSON schema | 讀圖、原生 PDF 旗標可信；JSON schema 旗標平台不擋 |
| 同步請求契約（100 多種組合） | §6 的欄位規則、pydantic 422、`models` 上限 3、長輸入行為 |
| 串流 22 次＋錯誤路徑 | §8 格式；預設模型不逐字出；中途取消事後補扣（約 15–40 分鐘） |
| internal 檔案 75 次（46 個檔） | §7 全部；預設 PDF 引擎約 5 MiB 上限 |
| app 憑證：兩支 internal app 發布後實打 | 憑證可用、閘門沒在擋、app 擁有的檔 404、starter 範本沒有 `AI_SDK` |
| 真 SDK 程式碼在 Node 實跑 17 次＋模擬 | §8 錯誤物件、重送行為、abort |
| `ctx.ai`：一支 internal app 8 支探針 action 試跑與發布後各跑，另一支 app 重現檔案工作 | 文字同步可用；錯誤形狀；dev runner 30 秒封頂；檔案工作三支 app 共 11 次（7＋1＋3，跨兩天）全部 `ai_job_not_started` |
| Hosted 容器內 `/open/ai-hub` | 全部實打可用（含串流、JSON、同步讀檔） |
| 吞吐：12 個同時呼叫 | 全部 200、排隊不拒絕 |
| AI Credit | 倍數 465 逐筆吻合；monthly 即時、daily 隔天 |

**沒能實打的**（只有原始碼或模擬）：

- **external 面的成功路徑**（models／complete／串流／檔案、scope 閘門 403）：只收 external 使用者帳號的憑證，
  探針規則不建帳號；擁有者的預覽憑證也被 401。要驗證需建一個測試用 external 使用者
- **Action 檔案工作的成功路徑**：`get_job` 完成、`get_job_result` 成功、瀏覽器 307 短效網址、刪除 204（job 都跑不起來）
- 非擁有者角色缺 `ai.hub.invoke` 的 403（擁有者的 `system.admin` 會直接放行；不建帳號）
- 各種 429（額度、上游預檢、頻率限制）、503、`ai_inference_indeterminate`、`ai_busy`、帳務待補——健康的付費租戶上
  觸發不了或不該觸發，形狀來自原始碼，SDK 端以真程式碼模擬過
- 串流已回 200 後平台送的 `event: error`（只用合成資料餵真 SDK 程式碼）；中途取消後的補扣時間（實打約 15–40 分鐘入帳，
  最多對帳 5 次、約一小時多就停是原始碼）；external 憑證的頻率限制以 app 為桶（原始碼）
- 閘門 enforce 後的行為（prod 目前 off 或 audit，外部分不出是哪一個）
- 沒有訂閱的租戶的 100 Credit 試用（測試租戶有付費訂閱）
- Builder 網頁建的 app 有沒有 `AI_SDK`（只核原始碼與平台文件：開發分頁注入的 SDK 不進草稿）
- 能力矩陣只測每組 1–2 個便宜模型，約 140 個模型只做了文字呼叫

## 14. 規劃與交付檢查清單

**規劃（`planning.md` 第 4.8 項）**——需求裡有任何 AI 功能就要過：

1. `GET /tenant/compute` 查 `dedicated`：`false` 或 403 → 不能用 AI Hub，計畫改寫成自帶金鑰
   （`planning.md` 第 4.6 項外部服務盤點），並告訴用戶兩者差別（誰付錢、誰管金鑰）
2. 對照 §3 能力邊界：要生圖、語音、embedding、聯網、function calling、調 `temperature` → AI Hub 做不到，改自帶金鑰
3. 定呼叫面：internal 前端 `AI_SDK`（新建 app 的 `src/api.ts` 沒有它、也補不進去，要把 SDK 放進自己的非保護檔，§8）／Action `ctx.ai`／Hosted；external 優先 Action（§5）。
   **要讀檔的功能：Action 檔案工作目前不可用（§9）**，internal 改前端、Hosted 用 `/open`，external 先回報用戶
4. 授權：internal 前端用 → 授權架構表（第 1.7 項）裡要用 AI 的角色**都要開 `ai.hub.invoke`**（預設角色都沒有）；
   external／Hosted → 列「請擁有者自己開 `ai.hub.invoke`（要輸入密碼）」為一個步驟
5. 用量估算：每次呼叫大約多少 tokens、一天幾次，挑候選模型對照 `ai-hub-models.md` 的成本級距與 §12 的換算估 Credit；
   有批次或排程大量呼叫時寫明會吃全租戶額度、受全租戶併發限制（突發約 4 個、滿載最多 8 個，§11）
6. 模型：不寫死 id，寫「選擇條件」（要結構化輸出／讀圖／讀 PDF／要逐字串流）與 2–3 個備援

**交付前自查**：

- [ ] 每個呼叫都設了 `max_tokens`，推理型模型給得夠大；內容為 `null` 有防呆
- [ ] 模型清單是現查的、依旗標挑；JSON 輸出 `JSON.parse` 包 try/catch
- [ ] 沒有自動重送 `ai_inference_indeterminate` 與串流中途失敗；`tenant_compute_not_ready`、`ai_upstream_unavailable`
      的重送有上限與退避
- [ ] 錯誤判斷先看 `AbortError`、再看 `err.code`，`code` 為 `undefined` 時看 `err.status`；`err.upstream` 不顯示給使用者
- [ ] 兩種額度 429 與頻率限制 429 分開顯示給使用者
- [ ] 送出中鎖按鈕，避免連點重複扣錢
- [ ] Action 的 `timeout_ms` 夠推論用（發布後測，試跑 30 秒封頂），回傳先檢查 `status`，例外用 `except Exception` 接
- [ ] 圖片夠大（細節判讀約 512 px 以上）；大 PDF 用 `native` 或拆檔
- [ ] 要逐字串流的畫面沒有用預設模型
