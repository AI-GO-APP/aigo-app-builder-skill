# AI Hub 模型目錄快照與逐一實打結果（2026-11-24）

> `ai-hub.md` §4 的附表：**租戶能叫哪些模型、每個模型實際叫得通嗎、能力旗標可不可信**。
>
> 快照來源：測試租戶 prod 的 `GET /api/v1/ai-hub/models`（173 個模型）。每個模型實打一次
> `POST /api/v1/ai-hub/complete`（提示 `Reply with the single word OK.`、`max_tokens` 16、4 路併發），
> 首輪失敗的隔 15 秒再試兩次；能力旗標另挑 32 個代表模型實際送圖片、PDF、JSON schema（§4）。
> 全部 173 次加重試共花 USD 0.0756。
>
> ⚠️ **這是某一天的快照，不是承諾**：目錄每小時同步，模型會增減、預設模型會換、會有已下架但還列著的模型（§3）。
> 程式一律執行期現查 `/models`、依能力旗標挑模型，**不要從本表抄 id 寫死**。本表用途是規劃時估「有沒有合用的模型」與成本級距。

## 目錄

- §1 怎麼讀這張表
- §2 總覽：各供應商數量、能力旗標、實測結果
- §3 列在目錄裡但叫不到的模型
- §4 能力實測矩陣（讀圖／原生 PDF／JSON schema）
- §5 逐一模型表（依供應商）

---

## 1. 怎麼讀這張表

| 欄 | 意思 |
|---|---|
| 圖／檔／JSON | `/models` 的 `supports_image_input`／`supports_file_input`／`supports_structured_output`（平台照抄 OpenRouter）。「檔」只管 `engine: "native"` 的 PDF；預設引擎的 PDF 是平台先抽文字，任何模型都能讀 |
| context | `context_length`（tokens） |
| 實測 | `✓`＝回了答案；`✓空`＝HTTP 200 但內容是空的、`finish_reason: "length"`（推理型模型把 `max_tokens` 花在推理上；usage 回報的 tokens 數不一，有 4 個 OpenAI 模型甚至回報 0 個 completion tokens），`max_tokens` 要給到數百以上，見 `ai-hub.md` §6；`✗`＝每次都失敗；`⚠`＝當天被上游限流、未能判定 |
| 探針 USD | 這一次呼叫的 `usage.cost`（約 13 tokens 的提示、`max_tokens` 16）。**只用來比較相對貴賤**，不是報價——平台不對租戶公開單價，實際花費隨輸入輸出長度線性放大，換算 Credit 見 `ai-hub.md` §12 |

## 2. 總覽

| 供應商 | 模型數 | 讀圖 | 原生 PDF | JSON schema | 實測可叫 | 其中推理型（16 tokens 回空） |
|---|---|---|---|---|---|---|
| OpenAI | 46 | 41 | 37 | 46 | 46 | 8 |
| Anthropic | 15 | 15 | 15 | 15 | 15 | 2 |
| Google | 23 | 22 | 17 | 23 | 23 | 8 |
| xAI | 7 | 7 | 7 | 7 | 6 | 0 |
| DeepSeek | 14 | 3 | 0 | 14 | 14 | 4 |
| Meta Llama | 7 | 2 | 0 | 5 | 5 | 0 |
| Mistral | 21 | 12 | 11 | 20 | 19 | 1 |
| Qwen | 40 | 24 | 0 | 39 | 40 | 21 |
| **合計** | **173** | 126 | 87 | 169 | **168** | 44 |

- 只有這 8 家：平台自動上架規則限定供應商白名單、只收「輸入含文字、輸出只有文字」、id 不帶 `:` 變體（沒有 `:free`／`:online`）、輸出單價每百萬 tokens ≤ USD 60 的模型（`ai-hub.md` §4）。**沒有生圖、語音、embedding、聯網搜尋模型**
- 實測延遲（166 個首輪成功）：中位數 1.27 秒、P90 3.07 秒、最慢 13.07 秒；4 路併發沒有遇到 503
- 回應的 `model`（上游實際用的）只有 1 個和請求不同（見 §5 備註）；`provider`（實際託管商）由上游路由決定、呼叫端不能指定，同一模型在不同請求可能換託管商

## 3. 列在目錄裡但叫不到的模型

**列在 `/models` 不代表叫得通**——平台要等模型從 OpenRouter 目錄消失滿 7 天才停用它（原始碼）；在那之前，或上游目錄還列著、但已經沒有供應商在服務時，就會出現下面這種叫不到的模型。

| 模型 | 結果 | 呼叫端怎麼辨認 |
|---|---|---|
| `meta-llama/llama-3.2-3b-instruct` | ⚠ 三次都 502（上游供應商 429 限流），當天未能判定 | `ai_upstream_unavailable`（502），稍後可能恢復 |
| `x-ai/grok-build-0.1` | ✗ 422 上游回 404：OpenRouter 已下架，目錄還沒跟上 | `ai_upstream_rejected_request` 且 `upstream_status` 404 |
| `meta-llama/llama-3.2-1b-instruct` | ✗ 422 上游回 404：OpenRouter 已下架，目錄還沒跟上 | `ai_upstream_rejected_request` 且 `upstream_status` 404 |
| `mistralai/mistral-medium-3` | ✗ 422 上游回 400：Mistral 不認 OpenRouter 轉送的模型名 | `ai_upstream_rejected_request` 且 `upstream_status` 400 |
| `mistralai/mistral-medium-3.1` | ✗ 422 上游回 400：Mistral 不認 OpenRouter 轉送的模型名 | `ai_upstream_rejected_request` 且 `upstream_status` 400 |

隔天（2026-11-25）再查：兩個 mistral-medium 也被 OpenRouter 下架，四個都是 `upstream_status` 404，而且四個都還列在 `/models`——同一個模型的失敗原因會隨上游變，呼叫端不要寫死狀態碼判斷。

處置：收到 `ai_upstream_rejected_request` 且 `upstream_status` 是 404，就把該模型從候選裡剔除、改挑下一個；要穩定就用 `models` 備援清單（最多 3 個，`ai-hub.md` §6）。

## 4. 能力實測矩陣

每組（供應商 × 讀圖 × 原生 PDF × JSON schema 旗標）挑 1–2 個最便宜的模型實際送檔（2026-11-24，共 141 次、USD 0.015）：
128×128 左紅右藍 PNG、單頁寫著一組代碼的 PDF、strict JSON schema。

| 能力 | 旗標可信嗎 | 實測 |
|---|---|---|
| 讀圖（`supports_image_input`） | **可信**（旗標為真就收圖）——實測 21 個旗標為真的模型（8 家都有），20 個讀對 128 px 圖；gpt-4.1-nano 小圖誤讀、512 px 才對（見下方圖片大小表）；旗標為假的一律 422 `model_no_image_input`，未推論、零成本 | 讀對的 20 個：anthropic haiku-4.5／haiku-5.5、deepseek v4.1-flash-1017／v4-flash-vision-exp、google gemma-3-4b／12b、gemini-2.5-flash-lite、gemini-3.1-flash-lite、meta llama-4-scout／maverick、mistral pixtral-large-2502／mistral-small-3.2／ministral-3b／mistral-large-2512、openai gpt-5.1-codex-mini／gpt-5-nano／gpt-4o-mini、qwen3.7-flash／qwen3-vl-30b、x-ai grok-4.20 |
| 原生 PDF（`supports_file_input`＋`engine: "native"`） | **可信**——旗標為假一律 422 `model_no_file_input`（零成本，訊息建議改用 `cloudflare-ai`） | 讀對：claude-haiku-5.5、gemini-2.5-flash-lite、voxtral-small、codestral-2508、mistral-medium-3-5、gpt-4.1-nano、gpt-5-nano、grok-4.20；mistral-large-2512 上游三次 502 未能判定 |
| 預設引擎 PDF（省略 `engine`） | 不看旗標 | 純文字模型也讀得到：deepseek-v4-flash、gemma-2-27b、llama-3.1-8b、mistral-nemo、gpt-oss-20b、qwen3-coder-30b 全讀對 |
| JSON schema（`supports_structured_output`） | **平台不檢查**——旗標為假照樣 200、照樣扣錢 | 12 個旗標為真的模型（8 家）全部回出可 `JSON.parse`、完全合 schema 的 JSON；旗標為假的 3 個：llama-3.1-70b 回散文、pixtral-large-2502 回拒答句、qwen3-235b-thinking 在 `max_tokens` 1500 時反而回了合法 JSON |

**圖片大小會影響小模型的判讀**（與串流與否、託管商無關）：

| 模型 | 64 px | 128 px | 512 px |
|---|---|---|---|
| `openai/gpt-4.1-nano`（全走 Azure） | 6/6 顏色錯 | 純色 6/6 對；左右分色 6/6 錯或左右顛倒 | 3/3 對 |
| `openai/gpt-5-nano` | 2/2 左右顛倒 | 對 | — |
| `anthropic/claude-haiku-5.5`、`google/gemini-2.5-flash-lite` | 對 | 對 | — |

→ 要判讀細節或位置的圖，送 **至少約 512 px**；小模型不要拿縮圖。

**每張圖計的 prompt tokens 差上百倍**（同一張 128 px 圖）：gpt-5-nano／gpt-5.1-codex-mini／haiku／mistral 約 +20–30、llama-4 約 +150、deepseek 約 +185、gemma／gemini-2.5 約 +260、gemini-3.1-flash-lite 約 +1100、**gpt-4o-mini 約 +8500**（一張圖約 USD 0.0013）。原生 PDF（整個請求的 prompt tokens，不是增量）：OpenAI／Mistral 36–49（比預設引擎抽出文字的約 100–160 還少）、Anthropic 約 1600、grok-4.20 約 2400（grok-4.20 原生 USD 0.0063 對預設引擎 USD 0.00022）。**prompt tokens 沒增加不代表模型沒看到檔**（OpenAI／Anthropic／Mistral 路由都有這現象）。

## 5. 逐一模型表

### OpenAI（46）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `openai/gpt-chat-latest` | ✓ | ✓ | ✓ | 400000 | ✓ | 0.00021 |  |
| `openai/gpt-3.5-turbo-0613` |  |  | ✓ | 4095 | ✓ | 1.6e-05 |  |
| `openai/gpt-3.5-turbo-16k` |  |  | ✓ | 16385 | ✓ | 4.6e-05 |  |
| `openai/gpt-4` |  |  | ✓ | 8191 | ✓ | 0.00048 |  |
| `openai/gpt-4.1-nano` | ✓ | ✓ | ✓ | 1047576 | ✓ | 2.2e-06 | 能力實測：讀圖 小圖誤讀（見 §4）、原生 PDF ✓、JSON schema ✓ |
| `openai/gpt-4o` | ✓ | ✓ | ✓ | 128000 | ✓ | 4.5e-05 |  |
| `openai/gpt-4o-2024-05-13` | ✓ | ✓ | ✓ | 128000 | ✓ | 8.5e-05 |  |
| `openai/gpt-4o-2024-08-06` | ✓ | ✓ | ✓ | 128000 | ✓ | 4.5e-05 |  |
| `openai/gpt-4o-2024-11-20` | ✓ | ✓ | ✓ | 128000 | ✓ | 4.5e-05 |  |
| `openai/gpt-4o-mini` | ✓ | ✓ | ✓ | 128000 | ✓ | 2.7e-06 | 能力實測：讀圖 ✓ |
| `openai/gpt-4o-mini-2024-07-18` | ✓ | ✓ | ✓ | 128000 | ✓ | 2.7e-06 |  |
| `openai/gpt-5` | ✓ | ✓ | ✓ | 400000 | ✓空 | 1.6e-05 |  |
| `openai/gpt-5-nano` | ✓ | ✓ | ✓ | 400000 | ✓空 | 6.5e-07 | 能力實測：讀圖 ✓、原生 PDF ✓ |
| `openai/gpt-5.1` | ✓ | ✓ | ✓ | 400000 | ✓ | 0.00013 |  |
| `openai/gpt-5.1-codex` | ✓ |  | ✓ | 400000 | ✓ | 0.00018 |  |
| `openai/gpt-5.1-codex-max` | ✓ |  | ✓ | 400000 | ✓空 | 1.6e-05 |  |
| `openai/gpt-5.1-codex-mini` | ✓ |  | ✓ | 400000 | ✓ | 3.1e-05 | 能力實測：讀圖 ✓、原生 PDF 422（零成本） |
| `openai/gpt-5.2` | ✓ | ✓ | ✓ | 400000 | ✓ | 9.3e-05 |  |
| `openai/gpt-5.2-codex` | ✓ |  | ✓ | 400000 | ✓ | 0.00025 |  |
| `openai/gpt-5.3-codex` | ✓ | ✓ | ✓ | 400000 | ✓ | 9.3e-05 |  |
| `openai/gpt-5.4-mini` | ✓ | ✓ | ✓ | 400000 | ✓ | 3.2e-05 |  |
| `openai/gpt-5.4-nano` | ✓ | ✓ | ✓ | 400000 | ✓ | 8.8e-06 |  |
| `openai/gpt-5.5` | ✓ | ✓ | ✓ | 1050000 | ✓空 | 0.00055 |  |
| `openai/gpt-5.6-luna` | ✓ | ✓ | ✓ | 1050000 | ✓ | 8.6e-06 |  |
| `openai/gpt-5.6-luna-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.00038 | 約 13 tokens 的提示被計 1530 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 61 個 completion tokens（照計費） |
| `openai/gpt-5.6-sol` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.00015 |  |
| `openai/gpt-5.6-sol-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0067 | 約 13 tokens 的提示被計 1530 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 30 個 completion tokens（照計費） |
| `openai/gpt-5.6-terra` | ✓ | ✓ | ✓ | 1050000 | ✓ | 8.6e-05 |  |
| `openai/gpt-5.6-terra-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0037 | 約 13 tokens 的提示被計 1530 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 55 個 completion tokens（照計費） |
| `openai/gpt-6-astra` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.00038 |  |
| `openai/gpt-6-astra-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.016 | 約 13 tokens 的提示被計 1479 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 25 個 completion tokens（照計費） |
| `openai/gpt-6-luna` | ✓ | ✓ | ✓ | 1050000 | ✓ | 3.8e-06 | ★ 當天的平台預設模型；本輪回了 OK，但串流與帶圖的實打在 `max_tokens` 16 時內容空——屬推理型，`max_tokens` 要給到數百 |
| `openai/gpt-6-luna-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.00017 | 約 13 tokens 的提示被計 1491 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 39 個 completion tokens（照計費） |
| `openai/gpt-6-sol` | ✓ | ✓ | ✓ | 1050000 | ✓ | 7.6e-05 |  |
| `openai/gpt-6-sol-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0032 | 約 13 tokens 的提示被計 1402 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 37 個 completion tokens（照計費） |
| `openai/gpt-6.1-sol` | ✓ | ✓ | ✓ | 1050000 | ✓ | 7.6e-05 |  |
| `openai/gpt-6.1-sol-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0032 | 約 13 tokens 的提示被計 1459 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 25 個 completion tokens（照計費） |
| `openai/gpt-6.1-terra` | ✓ | ✓ | ✓ | 1050000 | ✓空 | 9.3e-05 |  |
| `openai/gpt-6.1-terra-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0018 | 約 13 tokens 的提示被計 1402 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 75 個 completion tokens（照計費） |
| `openai/gpt-6.2-astra` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0003 |  |
| `openai/gpt-6.2-astra-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.014 | 約 13 tokens 的提示被計 1646 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 25 個 completion tokens（照計費） |
| `openai/gpt-6.2-sol` | ✓ | ✓ | ✓ | 1050000 | ✓ | 7.6e-05 |  |
| `openai/gpt-6.2-sol-pro` | ✓ | ✓ | ✓ | 1050000 | ✓ | 0.0035 | 約 13 tokens 的提示被計 1646 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 25 個 completion tokens（照計費） |
| `openai/gpt-oss-120b` |  |  | ✓ | 131072 | ✓空 | 1.2e-05 |  |
| `openai/gpt-oss-20b` |  |  | ✓ | 131072 | ✓空 | 7.6e-06 | 能力實測：讀圖 422（零成本）、預設引擎 PDF ✓、JSON schema ✓ |
| `openai/o3` | ✓ | ✓ | ✓ | 200000 | ✓空 | 2.6e-05 |  |

### Anthropic（15）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `anthropic/claude-fable-5` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00066 |  |
| `anthropic/claude-fable-5.1` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00038 |  |
| `anthropic/claude-fable-5.2` | ✓ | ✓ | ✓ | 1000000 | ✓空 | 0.00078 |  |
| `anthropic/claude-haiku-4.5` | ✓ | ✓ | ✓ | 200000 | ✓ | 3.4e-05 | 能力實測：讀圖 ✓ |
| `anthropic/claude-haiku-5.5` | ✓ | ✓ | ✓ | 1000000 | ✓ | 3.8e-06 | 能力實測：讀圖 ✓、原生 PDF ✓、預設引擎 PDF ✓、JSON schema ✓ |
| `anthropic/claude-opus-4.5` | ✓ | ✓ | ✓ | 200000 | ✓ | 0.00017 |  |
| `anthropic/claude-opus-4.6` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00017 |  |
| `anthropic/claude-opus-4.7` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00026 |  |
| `anthropic/claude-opus-4.8` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00018 |  |
| `anthropic/claude-opus-5` | ✓ | ✓ | ✓ | 1000000 | ✓空 | 0.00048 |  |
| `anthropic/claude-opus-5.5` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00015 |  |
| `anthropic/claude-sonnet-4.5` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.0001 |  |
| `anthropic/claude-sonnet-4.6` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.0001 |  |
| `anthropic/claude-sonnet-5` | ✓ | ✓ | ✓ | 1000000 | ✓ | 7.2e-05 |  |
| `anthropic/claude-sonnet-5.5` | ✓ | ✓ | ✓ | 1000000 | ✓ | 7.6e-05 |  |

### Google（23）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `google/gemini-2.5-flash` | ✓ | ✓ | ✓ | 1048576 | ✓ | 4.9e-06 |  |
| `google/gemini-2.5-flash-lite` | ✓ | ✓ | ✓ | 1048576 | ✓ | 1.2e-06 | 能力實測：讀圖 ✓、原生 PDF ✓、JSON schema ✓ |
| `google/gemini-2.5-pro-preview` | ✓ | ✓ | ✓ | 1048576 | ✓ | 0.00014 | 回應 `model` 是 `google/gemini-2.5-pro` |
| `google/gemini-3-flash-preview` | ✓ | ✓ | ✓ | 1048576 | ✓ | 6.5e-06 |  |
| `google/gemini-3.1-flash-lite` | ✓ | ✓ | ✓ | 1048576 | ✓ | 3.2e-06 | 能力實測：讀圖 ✓ |
| `google/gemini-3.1-flash-lite-preview` | ✓ | ✓ | ✓ | 1048576 | ✓ | 3.5e-06 |  |
| `google/gemini-3.1-pro-preview` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 0.00017 |  |
| `google/gemini-3.1-pro-preview-customtools` | ✓ | ✓ | ✓ | 1048576 | ✓ | 0.00016 |  |
| `google/gemini-3.5-flash` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 0.00012 |  |
| `google/gemini-3.5-flash-lite` | ✓ | ✓ | ✓ | 1048576 | ✓ | 4.6e-06 |  |
| `google/gemini-3.6-flash` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 5.4e-05 |  |
| `google/gemini-3.7-flash` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 5.4e-05 |  |
| `google/gemini-3.8-flash` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 5e-05 |  |
| `google/gemini-4-argon` | ✓ | ✓ | ✓ | 1048576 | ✓ | 0.00013 |  |
| `google/gemini-4-carbon` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 0.00024 |  |
| `google/gemini-4-hydrogen` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 0.00018 |  |
| `google/gemini-4-neon` | ✓ | ✓ | ✓ | 1048576 | ✓空 | 0.00036 |  |
| `google/gemma-2-27b-it` |  |  | ✓ | 8192 | ✓ | 1.4e-05 | 能力實測：讀圖 422（零成本）、預設引擎 PDF ✓ |
| `google/gemma-3-12b-it` | ✓ |  | ✓ | 131072 | ✓ | 1.7e-06 | 能力實測：讀圖 ✓ |
| `google/gemma-3-27b-it` | ✓ |  | ✓ | 131072 | ✓ | 2.9e-06 |  |
| `google/gemma-3-4b-it` | ✓ |  | ✓ | 131072 | ✓ | 8.4e-07 | 能力實測：讀圖 ✓、原生 PDF 422（零成本）、JSON schema ✓ |
| `google/gemma-4-26b-a4b-it` | ✓ |  | ✓ | 262144 | ✓ | 3.4e-06 |  |
| `google/gemma-4-31b-it` | ✓ |  | ✓ | 262144 | ✓ | 3.6e-06 |  |

### xAI（7）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `x-ai/grok-4.20` | ✓ | ✓ | ✓ | 2000000 | ✓ | 0.00011 | 能力實測：讀圖 ✓、原生 PDF ✓、預設引擎 PDF ✓、JSON schema ✓ |
| `x-ai/grok-4.20-multi-agent` | ✓ | ✓ | ✓ | 2000000 | ✓ | 0.0032 | 約 13 tokens 的提示被計 2667 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 1030 個 completion tokens（照計費） |
| `x-ai/grok-4.3` | ✓ | ✓ | ✓ | 1000000 | ✓ | 0.00042 | `max_tokens` 16 卻回 122 個 completion tokens（照計費） |
| `x-ai/grok-4.5` | ✓ | ✓ | ✓ | 500000 | ✓ | 0.00034 | `max_tokens` 16 卻回 22 個 completion tokens（照計費） |
| `x-ai/grok-4.6` | ✓ | ✓ | ✓ | 500000 | ✓ | 0.00052 | `max_tokens` 16 卻回 47 個 completion tokens（照計費） |
| `x-ai/grok-4.7` | ✓ | ✓ | ✓ | 500000 | ✓ | 0.0033 | 約 13 tokens 的提示被計 1249 個 prompt tokens（上游自帶隱藏提示，照計費）；`max_tokens` 16 卻回 418 個 completion tokens（照計費） |
| `x-ai/grok-build-0.1` | ✓ | ✓ | ✓ | 256000 | ✗ |  | 422 上游回 404：OpenRouter 已下架，目錄還沒跟上 |

### DeepSeek（14）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `deepseek/deepseek-chat` |  |  | ✓ | 163840 | ✓ |  | 首輪 502（上游供應商 429 限流），重試成功 |
| `deepseek/deepseek-chat-v3-0324` |  |  | ✓ | 163840 | ✓ | 3.5e-06 |  |
| `deepseek/deepseek-chat-v3.1` |  |  | ✓ | 163840 | ✓ | 8.5e-06 |  |
| `deepseek/deepseek-v3.1-terminus` |  |  | ✓ | 163840 | ✓ | 5.8e-06 |  |
| `deepseek/deepseek-v3.2` |  |  | ✓ | 163840 | ✓ | 3.6e-06 |  |
| `deepseek/deepseek-v3.2-exp` |  |  | ✓ | 163840 | ✓ | 3.4e-06 |  |
| `deepseek/deepseek-v4-flash` |  |  | ✓ | 1048576 | ✓ | 1.7e-06 | 能力實測：讀圖 422（零成本）、預設引擎 PDF ✓、JSON schema ✓ |
| `deepseek/deepseek-v4-flash-0731` |  |  | ✓ | 1048576 | ✓ | 7.7e-06 |  |
| `deepseek/deepseek-v4-flash-vision-exp` | ✓ |  | ✓ | 1048576 | ✓空 | 2.2e-05 | 能力實測：讀圖 ✓ |
| `deepseek/deepseek-v4-pro` |  |  | ✓ | 1048576 | ✓空 | 3e-05 |  |
| `deepseek/deepseek-v4-pro-0813` |  |  | ✓ | 1048576 | ✓ | 1e-05 |  |
| `deepseek/deepseek-v4.1-flash` | ✓ |  | ✓ | 1048576 | ✓空 | 1.7e-05 |  |
| `deepseek/deepseek-v4.1-flash-1017` | ✓ |  | ✓ | 1048576 | ✓ | 9.4e-06 | 能力實測：讀圖 ✓、原生 PDF 422（零成本） |
| `deepseek/deepseek-r1-0528` |  |  | ✓ | 163840 | ✓空 | 4e-05 |  |

### Meta Llama（7）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `meta-llama/llama-3.1-70b-instruct` |  |  |  | 131072 | ✓ | 1.8e-05 | 能力實測：JSON schema 回散文 |
| `meta-llama/llama-3.1-8b-instruct` |  |  | ✓ | 131072 | ✓ | 2.3e-06 | 能力實測：讀圖 422（零成本）、預設引擎 PDF ✓、JSON schema ✓ |
| `meta-llama/llama-3.2-1b-instruct` |  |  |  | 60000 | ✗ |  | 422 上游回 404：OpenRouter 已下架，目錄還沒跟上 |
| `meta-llama/llama-3.2-3b-instruct` |  |  | ✓ | 131072 | ⚠ |  | 三次都 502（上游供應商 429 限流），當天未能判定 |
| `meta-llama/llama-3.3-70b-instruct` |  |  | ✓ | 131072 | ✓ | 3.2e-05 |  |
| `meta-llama/llama-4-maverick` | ✓ |  | ✓ | 524288 | ✓ | 8e-06 | 能力實測：讀圖 ✓ |
| `meta-llama/llama-4-scout` | ✓ |  | ✓ | 327680 | ✓ | 3.5e-06 | 能力實測：讀圖 ✓、原生 PDF 422（零成本）、JSON schema ✓ |

### Mistral（21）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `mistralai/codestral-2508` |  | ✓ | ✓ | 256000 | ✓ | 5.7e-06 | 能力實測：原生 PDF ✓ |
| `mistralai/devstral-2512` |  | ✓ | ✓ | 262144 | ✓ | 1.3e-05 |  |
| `mistralai/ministral-14b-2512` | ✓ |  | ✓ | 262144 | ✓ | 2.6e-06 |  |
| `mistralai/ministral-3b-2512` | ✓ |  | ✓ | 131072 | ✓ | 1.2e-06 | 能力實測：讀圖 ✓、JSON schema ✓ |
| `mistralai/ministral-8b-2512` | ✓ |  | ✓ | 262144 | ✓ | 2e-06 |  |
| `mistralai/mistral-large` |  | ✓ | ✓ | 128000 | ✓空 | 0.00014 |  |
| `mistralai/mistral-large-2407` |  | ✓ | ✓ | 131072 | ✓ | 0.00014 |  |
| `mistralai/mistral-large-2512` | ✓ | ✓ | ✓ | 262144 | ✓ | 8.8e-06 | 能力實測：讀圖 ✓、原生 PDF 上游 502，未能判定、預設引擎 PDF ✓ |
| `mistralai/mistral-large-4-0` | ✓ |  | ✓ | 1048576 | ✓ | 4.5e-05 |  |
| `mistralai/mistral-medium-3` | ✓ | ✓ | ✓ | 131072 | ✗ |  | 422 上游回 400：Mistral 不認 OpenRouter 轉送的模型名；11-25 再查改為 404 已下架（§3） |
| `mistralai/mistral-medium-3.1` | ✓ | ✓ | ✓ | 131072 | ✗ |  | 422 上游回 400：Mistral 不認 OpenRouter 轉送的模型名；11-25 再查改為 404 已下架（§3） |
| `mistralai/mistral-medium-3-5` | ✓ | ✓ | ✓ | 262144 | ✓ | 5.3e-05 | 能力實測：原生 PDF ✓ |
| `mistralai/mistral-nemo` |  |  | ✓ | 131072 | ✓ | 2.1e-07 | 能力實測：讀圖 422（零成本）、預設引擎 PDF ✓、JSON schema ✓ |
| `mistralai/mistral-small-24b-instruct-2501` |  |  | ✓ | 32768 | ✓ | 8.7e-06 |  |
| `mistralai/mistral-small-3.1-24b-instruct` | ✓ |  | ✓ | 128000 | ✓ | 4.6e-06 |  |
| `mistralai/mistral-small-3.2-24b-instruct` | ✓ |  | ✓ | 256000 | ✓ | 1.2e-06 | 能力實測：讀圖 ✓、原生 PDF 422（零成本） |
| `mistralai/mistral-small-2603` | ✓ |  | ✓ | 262144 | ✓ | 4.5e-06 |  |
| `mistralai/mixtral-8x22b-instruct` |  | ✓ | ✓ | 65536 | ✓ | 5.6e-05 |  |
| `mistralai/pixtral-large-2502` | ✓ |  |  | 128000 | ✓ | 4e-05 | 能力實測：讀圖 ✓、JSON schema 回散文 |
| `mistralai/mistral-saba` |  | ✓ | ✓ | 32768 | ✓ | 5.6e-06 |  |
| `mistralai/voxtral-small-24b-2507` |  | ✓ | ✓ | 32768 | ✓ | 1.8e-06 | 能力實測：讀圖 422（零成本）、原生 PDF ✓ |

### Qwen（40）

| 模型 id | 圖 | 檔 | JSON | context | 實測 | 探針 USD | 備註 |
|---|---|---|---|---|---|---|---|
| `qwen/qwen-plus` |  |  | ✓ | 1000000 | ✓ | 4.7e-06 |  |
| `qwen/qwen-2.5-72b-instruct` |  |  | ✓ | 32768 | ✓ | 5.8e-06 |  |
| `qwen/qwen-2.5-coder-32b-instruct` |  |  | ✓ | 32768 | ✓ | 2.6e-05 |  |
| `qwen/qwen2.5-vl-72b-instruct` | ✓ |  | ✓ | 128000 | ✓ | 1.9e-05 |  |
| `qwen/qwen3-14b` |  |  | ✓ | 40960 | ✓空 | 5.1e-06 |  |
| `qwen/qwen3-235b-a22b-2507` |  |  | ✓ | 262144 | ✓ | 3.7e-06 |  |
| `qwen/qwen3-235b-a22b-thinking-2507` |  |  |  | 128000 | ✓空 | 6.4e-05 | 能力實測：JSON schema max_tokens 300 回空、1500 回合法 JSON |
| `qwen/qwen3-30b-a3b` |  |  | ✓ | 40960 | ✓空 | 9.9e-06 |  |
| `qwen/qwen3-30b-a3b-instruct-2507` |  |  | ✓ | 262144 | ✓ | 2.1e-06 |  |
| `qwen/qwen3-32b` |  |  | ✓ | 131072 | ✓ | 7.8e-06 |  |
| `qwen/qwen3-coder-30b-a3b-instruct` |  |  | ✓ | 262144 | ✓ | 1.3e-06 | 能力實測：讀圖 422（零成本）、預設引擎 PDF ✓、JSON schema ✓ |
| `qwen/qwen3-coder` |  |  | ✓ | 262144 | ✓ | 6.5e-06 |  |
| `qwen/qwen3-coder-flash` |  |  | ✓ | 1000000 | ✓ | 3.9e-06 |  |
| `qwen/qwen3-coder-next` |  |  | ✓ | 262144 | ✓ | 3.4e-06 |  |
| `qwen/qwen3-next-80b-a3b-instruct` |  |  | ✓ | 262144 | ✓ | 3.5e-06 |  |
| `qwen/qwen3-vl-235b-a22b-instruct` | ✓ |  | ✓ | 262144 | ✓ | 7e-06 |  |
| `qwen/qwen3-vl-30b-a3b-instruct` | ✓ |  | ✓ | 262144 | ✓ | 3.5e-06 | 能力實測：讀圖 ✓、原生 PDF 422（零成本） |
| `qwen/qwen3-vl-8b-instruct` | ✓ |  | ✓ | 262144 | ✓ |  | 首輪 502（上游供應商 429 限流），重試成功 |
| `qwen/qwen3.5-397b-a17b` | ✓ |  | ✓ | 262144 | ✓空 | 5.6e-05 |  |
| `qwen/qwen3.5-plus-02-15` | ✓ |  | ✓ | 1000000 | ✓空 | 3.2e-05 | `max_tokens` 16 卻回 18 個 completion tokens（照計費） |
| `qwen/qwen3.5-plus-20260420` | ✓ |  | ✓ | 1000000 | ✓空 | 3.7e-05 | `max_tokens` 16 卻回 18 個 completion tokens（照計費） |
| `qwen/qwen3.5-122b-a10b` | ✓ |  | ✓ | 262144 | ✓ | 3.4e-05 |  |
| `qwen/qwen3.5-27b` | ✓ |  | ✓ | 262144 | ✓空 | 3.1e-05 |  |
| `qwen/qwen3.5-35b-a3b` | ✓ |  | ✓ | 262144 | ✓空 | 1.3e-05 |  |
| `qwen/qwen3.5-9b` | ✓ |  | ✓ | 262144 | ✓空 | 6.9e-06 |  |
| `qwen/qwen3.5-flash-02-23` | ✓ |  | ✓ | 1000000 | ✓ | 5.3e-06 |  |
| `qwen/qwen3.6-27b` | ✓ |  | ✓ | 262144 | ✓空 | 5.7e-05 |  |
| `qwen/qwen3.6-35b-a3b` | ✓ |  | ✓ | 262144 | ✓空 | 1.6e-05 |  |
| `qwen/qwen3.6-flash` | ✓ |  | ✓ | 1000000 | ✓空 | 2.3e-05 | `max_tokens` 16 卻回 18 個 completion tokens（照計費） |
| `qwen/qwen3.6-plus` | ✓ |  | ✓ | 1000000 | ✓空 | 4.1e-05 | `max_tokens` 16 卻回 18 個 completion tokens（照計費） |
| `qwen/qwen3.7-flash` | ✓ |  | ✓ | 1000000 | ✓空 | 2.6e-06 | 能力實測：讀圖 ✓ |
| `qwen/qwen3.7-max` |  |  | ✓ | 1000000 | ✓空 | 9.6e-05 |  |
| `qwen/qwen3.7-plus` | ✓ |  | ✓ | 1000000 | ✓空 | 2.6e-05 |  |
| `qwen/qwen3.8-2.4t-a95b` |  |  | ✓ | 1048576 | ✓空 | 0.00023 |  |
| `qwen/qwen3.8-27b` | ✓ |  | ✓ | 1024000 | ✓空 | 3.5e-05 |  |
| `qwen/qwen3.8-flash` | ✓ |  | ✓ | 1000000 | ✓空 | 1.8e-05 |  |
| `qwen/qwen3.8-max-0902` | ✓ |  | ✓ | 1000000 | ✓空 | 0.00023 |  |
| `qwen/qwen3.8-max-prime` | ✓ |  | ✓ | 1000000 | ✓空 | 0.00046 |  |
| `qwen/qwen3.8-omni-flash` | ✓ |  | ✓ | 1000000 | ✓ | 1.3e-05 |  |
| `qwen/qwen4-max` | ✓ |  | ✓ | 1000000 | ✓ | 9.7e-05 |  |

