# AI GO Harness 重構設計：依 harness 分類切結構，為 MCP 化鋪路

- 狀態：草稿（待審）
- 日期：2026-09-17（2026-09-21 更新：PR #82 已合併，§2.1、§2.2、§5 隨之修訂）

## 0. 這份文件在談什麼

AI GO 的 agent harness 目前以 **GitHub repo** 為發布單位：`AI-GO-APP` organization 底下，每個 skill 各自是一個獨立的 repo，使用者用 git clone 把整個 repo 裝進自己機器的 skill 目錄。

本文件處理其中三個**非 FDE 專用**（下稱 general）的 repo：

| 本文簡稱 | GitHub repo | 做什麼 | 誰在用 |
|---|---|---|---|
| **builder** | `AI-GO-APP/aigo-app-builder-skill`（本文件所在的 repo） | 開發 AI GO Custom App：前端、Server-Side Action、部署與驗證 | FDE、租戶 |
| **transfer** | `AI-GO-APP/aigo-template-transfer-skill` | 把上線中的 Custom App 轉成可上架的市集模板 | FDE |
| **checker** | `AI-GO-APP/skill-safely-vibecoding-checker` | 對 AI 協作開發的專案做安全稽核 | FDE、外部使用者 |

**本文件的範圍**：builder 與 transfer 兩個 repo 合併重構；checker 僅對齊切法，維持獨立 repo。

**不在範圍**：`AI-GO-APP/agentoss-module-builder-skill`（服務 Agent OSS 平台，不是 AI GO），以及 FDE 專案 repo 內附帶的 skill。

---

## 1. 應該長怎樣（業界共識）

### 1.1 分類的判準是「何時進入 context」

Claude Code 官方文件、Martin Fowler 與 HumanLayer 三方對 harness 的切法一致：分類的依據不是內容長短或主題，而是**這段內容在什麼時機被載入模型的 context**。

| 分類 | 載入時機 | 放什麼 |
|---|---|---|
| Rules | 每次 session 開始時，或模型讀到指定路徑的檔案時 | 寫 code 時永遠成立的限制 |
| Skills | 按需——模型判斷與當前任務相關，或使用者以 `/名稱` 叫用 | 參考知識、需要模型推理的多步驟流程 |
| Workflows | 使用者主動觸發 | 有外部副作用的流程 |
| Guards（hooks） | 生命週期事件發生時，必定執行 | 可由程式判定對錯的護欄 |
| Agents（subagents） | 主 agent 派工時，在獨立 context 執行 | 需要大量讀檔的盤點、獨立的驗證者 |
| Tools | 模型呼叫時 | 對外部系統的實際操作 |

### 1.2 三條業界證據

**(a) 寫成文字的規則只是請求，寫成程式的檢查才是強制。**

Claude Code 官方文件明載：在 CLAUDE.md 或 skill 裡寫「不准改 `.env`」是一個請求，不是保證；用 `PreToolUse` hook 擋下才是強制。官方的結論是：如果一條規則必須每次都成立，就該做成 hook，而不是提示詞裡的一句指示。

Fowler 對 agent 控制手段的分類呼應同一點：他把控制手段分成「確定性（computational）」與「推理（inferential）」兩類——linter、型別檢查與測試屬於前者，「快、確定，結果可靠」；AGENTS.md 與 skills 屬於後者，效果不保證。因此，**凡是能改寫成確定性檢查的規則，就不該只留在文字裡**。

**(b) 塞給模型的指示越多，模型的表現越差。**

HumanLayer 引述 ETH Zurich 的研究：當 context 檔案過大或由工具自動生成時，agent 多花了 14–22% 的推理 token 去處理這些指示，而任務表現並沒有提升。HumanLayer 自己的結論是「指示越少越好」，該團隊的 CLAUDE.md 不到 60 行。

Claude Code 官方文件建議 CLAUDE.md 控制在 200 行以內，超過就該改用路徑限定的 rules，或移到按需載入的 skill。Skill 本身則採「漸進揭露」：`SKILL.md` 只說明有哪些補充檔案、什麼情況下該去讀，細節放在 `references/` 底下。

**(c) 有外部副作用的流程，不該讓模型自行決定何時執行。**

Claude Code 官方文件建議：會產生副作用的 skill 應設定 `disable-model-invocation`，讓它只能由使用者手動叫用。

### 1.3 因此，理想的結構要滿足四件事

- 每類內容只有一個歸屬，不重複、不混放
- 可由程式判定的規則要寫成程式，不能只寫成文字
- 主入口檔只負責分流，細節按需載入
- builder 與 transfer 共用的基礎設施只維護一份（SSOT）

---

## 2. 實際長怎樣

### 2.1 現況

這三個 repo 的內容都是「一個 repo 等於一個 skill 目錄」：根目錄直接放 `SKILL.md`，旁邊是 `references/`、`scripts/` 等子目錄。所有 harness 內容都擠在各自的 `SKILL.md` 與 `scripts/` 裡。

| Repo（簡稱） | 最後維護 | SKILL.md | 其他 |
|---|---|---|---|
| builder 1.44.0 | 2026-09-21 | 471 行 | 13 支 scripts 約 5000 行，且沒有任何測試 |
| transfer 0.9.0 | 2026-09-01 | 484 行 | 14 個測試檔 |
| checker | 2026-07-25 | 162 行 | 無 scripts |

**builder 的 SKILL.md 長度問題已於 2026-09-21 由 PR #82（版本 1.44.0）解決**：主檔從 1092 行瘦身到 471 行，四段內容搬進新建的 `references/dev-rules.md`、`planning.md`、`environment.md`、`review-workflow.md`，該 PR 並附上 `scripts/check_docs.py`（檢查主檔長度、引用斷鏈、reference 目錄、搬家後的內容遺漏）與三個 eval 情境。

**這件事解決的是「長度」，不是「分類」。** 搬進 reference 的內容仍然是 skill 的一部分，規則、護欄、流程依舊混在同一個 skill 目錄裡——下一節逐項說明。那個 PR 因此不與本設計衝突，反而先替本設計完成了步驟 2 的一部分搬移工作。

### 2.2 哪些內容放錯了分類

builder（以下位置為 1.44.0 瘦身後的現況）：

| 現況位置 | 應屬 | 為什麼 |
|---|---|---|
| `references/dev-rules.md`（259 行，原 Phase 3 規則 18–32）、`references/environment.md` 的租戶空間網址與憑證規則、SKILL.md Phase 3 留下的規則 1–17 速查表 | Rules | 這些是開發者寫 app code 時永遠要成立的限制，不是某個流程的步驟。它們現在雖然搬出主檔，但仍只在 skill 被觸發時才載入，模型直接改 code 時看不到 |
| 規則 9（SDK 檔不可修改）、規則 14（VFS 上限 200 檔、單檔 1MB）、禁用詞交付前 grep、憑證不得出現在指令列 | Guards | 這四條都能由程式直接判定對錯，寫成文字只是請求 |
| SKILL.md Phase -1 的 skill 自我更新、Phase 4「每次改完 code 都必須部署並驗證」 | Guards／自動化 | 「每次都要做」正是生命週期事件觸發的定義 |
| `references/review-workflow.md` 的現況盤點九步（既有 code、租戶自建表、既有排程、對外呼叫）、`references/pre-report-self-grill.md` 的六輪自審 | Agents | 盤點要讀大量檔案但只需回傳結論；自審交給獨立的驗證者比自己檢查自己更可信 |
| SKILL.md Phase 4.4 發布、Phase 5 的問題回報 submit | Workflows | 這兩者會影響外部系統，不該由模型自行決定何時執行 |
| `scripts/` 底下 13 支腳本（含 1338 行的 `aigo_auth.py`） | Tools | 這些已經是一套 SDK，不是給模型讀的指示 |

補充：1.44.0 新增的 `scripts/check_docs.py` 與 `evals/` 屬於 repo 自身的品質工具，檢查的是文件結構與 agent 行為，不是本節要分類的 harness 內容；重構後應歸在 `tests/` 底下。

transfer 的 SKILL.md：

- **做對的地方**：鐵律 3「階段不可跳」已由腳本的狀態機強制執行，鐵律 2 的人工閘也已由腳本的互動確認擋住——這正是 §1.2 (a) 說的「把規則改寫成確定性檢查」
- 鐵律 1（不得直接編輯 `work/<slug>/template/` 下的檔案）與鐵律 7（憑證紀律）仍然只是文字，應改寫成 Guards
- 鐵律 6（對外呼叫走 egress 閘道，約 20 行）是平台知識而非鐵律，且與 builder 的規則 29 講同一件事，兩邊各存一份
- Phase S9 送審會把模板送進審核流程，應歸 Workflows

checker 的分類本身乾淨，只需把 `templates/` 目錄改名為 `assets/`，與其他兩者一致。

### 2.3 builder 與 transfer 共用的基礎設施已經分歧

| 檔案 | 分歧狀況 |
|---|---|
| `check_update.py` | builder 與 transfer 各有一份，互相 diff 有 735 行差異：builder 會強制同步到遠端最新版，transfer 只印出提示 |
| `resources/hooks/*` | 兩份內容近乎相同，但 hook timeout 一個設 120 秒、一個設 10 秒 |
| `aigo_client.py` | transfer 的這支腳本在註解中自稱「憑證與租戶空間紀律對齊 builder 1.8.0+ 的 `aigo_auth.py`」，而 builder 現已是 1.43.0 |

### 2.4 為什麼會變成這樣

混類不是因為寫的人隨便，而是發布方式造成的：這三個 repo 要 clone 到 FDE 或租戶的機器上，而客戶端（Claude Code、Codex）只會把「一個 skill 目錄」當成一個可安裝的單位——rules 要放進使用者的專案才會載入、hooks 要寫進使用者的 settings 才會執行，兩者都不會跟著 skill 目錄走。所以規則與護欄只能退而求其次，全部塞進 `SKILL.md`。**要解決混類，得先換掉發布方式。**

---

## 3. 建議

### 3.1 目錄結構

builder 與 transfer 兩個 repo 合併成一個 repo（下稱 `aigo-harness`，正式名稱待定，見 §6），內部依 §1.1 的六類切開：

```
aigo-harness/              ← 合併 builder 與 transfer 後的單一 repo
├── rules/                  ← 寫 code 時永遠成立的限制（frontmatter 以 paths 限定適用範圍）
│   ├── frontend.md         ← builder 規則 1–13、16、17、30、31
│   ├── actions.md          ← builder 規則 10、20–22、26–28 與 Server-Side Action 撰寫
│   ├── data.md             ← builder 規則 18、19、24、25、32
│   ├── platform-api.md     ← 租戶空間網址、builder 規則 29、egress（併入 transfer 鐵律 6）
│   └── credentials.md      ← builder 憑證規則併入 transfer 鐵律 7
├── skills/                 ← 按需載入（維持 Agent Skills 標準格式）
│   ├── builder/            ← SKILL.md 只做分流（500 行以內）；平台知識放 references/
│   ├── migrate/            ← 遷入流程，自 builder 的 Phase 1.25／2.0 拆出
│   └── template-transfer/  ← transfer 的 S0～S8
├── workflows/              ← 使用者主動觸發、有外部副作用
│   ├── publish.md          ← builder Phase 4.4
│   ├── report-issue.md     ← builder Phase 5 問題回報
│   └── template-submit.md  ← transfer S9 送審
├── guards/                 ← 確定性檢查，純函式、不做 I/O
│   ├── sdk_files.py        ← builder 規則 9
│   ├── vfs_limits.py       ← builder 規則 14
│   ├── forbidden_terms.py  ← CONTEXT.md 的禁用詞
│   └── template_gates.py   ← transfer 的狀態機與內容雜湊閘
├── agents/                 ← subagent 定義（只給唯讀工具）
│   ├── app-inventory.md    ← builder Phase 0 的現況盤點
│   └── report-verifier.md  ← 問題回報前的六輪自審
├── tools/                  ← 原 scripts/；未來即 MCP tool 的實作
│   ├── core/               ← auth、client、config，builder 與 transfer 合用一份
│   ├── builder/
│   └── transfer/
├── assets/                 ← 範本、掃描規則、保留表名（原 resources/ 與 config/）
├── tests/                  ← guards 與 tools 的測試；builder 側需從零補齊
└── CONTEXT.md              ← 術語表（沿用現有內容）
```

checker 不併進來，維持成獨立的 `AI-GO-APP/skill-safely-vibecoding-checker` repo，只在內部照同樣的切法整理。它在 `AGENTS.md` 明訂「產品資訊只能出現在 `references/aigo-platform.md` 定義的範圍內」，這條產品中立的界線是它作為稽核工具的可信度基礎，因此不併入上述結構。

### 3.2 關鍵決策與取捨

| 決策 | 理由 | 取捨 |
|---|---|---|
| `guards/` 與 `tools/` 分開 | guard 負責判斷、tool 負責動作；tool 在執行前呼叫 guard，就能把檢查擋在伺服器端 | 多一層呼叫 |
| `workflows/` 自 `skills/` 拆出 | 這些流程有外部副作用，只能由使用者觸發 | 目錄多一類 |
| `rules/` 依 paths 拆成多檔 | 模型只在讀到對應路徑的檔案時才載入該檔，省 context（理由見 §1.2 b） | 規則散在多檔，需要一份索引 |
| 不做 Claude Code plugin | 既然預定以 MCP 發布，plugin 這條路會綁定單一客戶端；而且官方文件明載 plugin 根目錄的 CLAUDE.md 不會被載入，plugin 無法夾帶 rules | 過渡期仍得用 git clone 安裝 |

---

## 4. 對應到 MCP

MCP 是「客戶端程式 ↔ MCP server」之間的固定協定。模型只負責決定要呼叫哪個 tool、參數填什麼，實際的請求由客戶端程式送出。一個 MCP server 除了提供 tools，還能提供 resources（可讀取的文件）、prompts（預先寫好的流程），以及連線時直接注入模型 context 的 instructions。

| 本設計的分類 | 在 MCP 裡怎麼送 | 備註 |
|---|---|---|
| `tools` | MCP tool | `core/auth` 改為伺服器端 OAuth，使用者的密碼不再經過 agent |
| `guards` | 由 tool 在執行前先呼叫，不合規就直接拒絕 | 所有操作都走 tool，因此比裝在客戶端的 hook 更可靠，也不受客戶端種類影響 |
| `skills` | 做成 resource，由客戶端按需讀取 | **標準尚未定案，見 §4.1** |
| `workflows` | prompt，每個流程一個 | 有支援的客戶端會把 prompt 顯示成 slash command |
| `rules` | 三路並用：① server instructions 送最精簡的硬規則 ② scaffold tool 把 `rules/` 寫進 app 專案的 `.claude/rules/` 與 `AGENTS.md` ③ tool 回傳結果時附上相關條文 | MCP 沒有辦法強迫客戶端常駐載入某份內容 |
| `agents` | 以 resource 提供定義，由客戶端自行安裝 | MCP 沒有對應機制，是整套設計裡最弱的一環 |

### 4.1 用 MCP 發送 skill 的標準還沒定案

MCP 原本只有 tools、resources、prompts 三種機制，沒有「skill」這一類。2026 年 4 月成立的 Skills over MCP 工作組（由 Anthropic 與 Nordstrom 的維護者共同主持，Google、GitHub、AWS 等公司參與）正在決定怎麼補上這一塊，目前有兩個提案（SEP 是該工作組的提案編號，性質等同 RFC）：

| 提案 | 做法 | 優點 | 缺點 |
|---|---|---|---|
| **第 69 號**：沿用現有機制 | 把 skill 當成 resource 發送：server 提供一份索引檔，客戶端再按需去讀索引指到的各個檔案 | 不必修改協定；已在 Codex、Gemini CLI、Goose 等現有客戶端實測可用 | 各家客戶端處理「按需讀取」的方式不一致 |
| **第 86 號**：新增一種機制 | 讓 skill 成為與 tool、prompt 並列的第四種機制，可以列出、可以啟用；skill 需要的 tool 要等它被啟用後才出現 | 沒被啟用的 skill 不會把幾十個 tool 定義提前塞進模型 context | 要修改協定，時程較長 |

兩案目前都還在討論，**沒有結論**；工作組內部連這個機制該不該叫「skill」都還有爭議（怕與既有的 Agent Skills 規格混淆）。微軟 Agent Framework 的 .NET 實作已經採用第 69 號那種做法，但其文件明講「本 API 為實驗性，未來版本可能變更」。

**因此本設計的決定是**：`skills/` 一律維持 Agent Skills 標準格式（`SKILL.md` 搭配 `references/`）。這個格式本身與 MCP 無關，就算兩案最後都被推翻，這些檔案仍可透過 git clone 或 plugin 安裝，不會白做。

### 4.2 改用 MCP 之後可以移除的東西

- **skill 自我更新機制**（builder 與 transfer 的 Phase -1、兩份 `check_update.py`、SessionStart hook 範例）：remote server 上永遠是最新版，客戶端沒有本地副本需要更新
- **transfer 的工作目錄守衛**（鐵律 1）：`work/<slug>/` 會變成伺服器端的狀態，agent 根本碰不到那個目錄，不需要再用規則去擋

### 4.3 內容去向：哪些東西會到使用者手上

| 去向 | 內容 | 使用者可見性 |
|---|---|---|
| 只留在伺服器 | tools、guards、憑證、transfer 的工作狀態 | 使用者只看得到 tool 的輸入與輸出 |
| 按需進入模型 context | skills、workflows、server instructions、tool 回傳時附帶的條文 | 使用者的機器上不存檔，但內容看得到，也可以要求模型整段貼出來 |
| 落地成使用者機器上的檔案 | 專案裡的 `.claude/rules/`、`AGENTS.md`、agents 定義 | 以檔案形式存在，需要靠版本比對提醒使用者同步 |

原則：需要保護的判斷邏輯要放進 guards 與 tools；給模型讀的文字一律當作使用者看得到來撰寫。

---

## 5. 遷移步驟

1. ~~等 `AI-GO-APP/aigo-app-builder-skill` 的 PR #82 合併~~——**已於 2026-09-21 合併（merge commit `d7b729a4`，版本 1.44.0）**，本次重構可以開始
2. 依 §3.1 在合併後的 repo 內建立空目錄骨架，把 builder 與 transfer 的 `references/`、`resources/`、`config/` 原樣搬過去，此步不改任何內容
3. 從 builder 抽出 rules：`references/dev-rules.md` 全份、`references/environment.md` 的租戶網址與憑證規則、SKILL.md Phase 3 的規則 1–17 速查表，依 §3.1 拆成五個 rules 檔；`check_docs.py` 的引用檢查需同步改指新位置
4. 實作 guards：每支先寫測試再寫實作；builder 與 transfer 的 SKILL.md 中對應的條文改為指向該 guard
5. 合併 `tools/core/`：以 builder 的 `aigo_auth.py` 為基準，補上 transfer `aigo_client.py` 的差異，並補測試
6. 把 §2.2 標為 Workflows 與 Agents 的段落各自抽成獨立檔案
7. 每完成一個步驟，用 1.44.0 附帶的 `evals/` 三個情境驗證 agent 行為沒有變差——該 PR 已建立「改 skill 要跑 eval」的慣例，本重構沿用
8. MCP server 的 transport、認證與部署另立一份設計文件，不在本文件範圍

## 6. 待決事項

- [ ] 合併後的 repo 怎麼生：在 `AI-GO-APP` 新開一個 `aigo-harness` repo 並把兩邊搬進去，或直接在 `aigo-app-builder-skill` 內重組後改名（後者保得住 137 個 commit 的歷史與既有 issue）
- [ ] transfer repo 合併後如何處置：封存，或保留並在 README 指向新 repo
- [ ] 過渡期要不要同時維持「一個 repo 等於一個 skill 目錄」的舊安裝方式，若要，維持多久
- [ ] Claude Code 與 Codex 目前對「用 MCP 發送 skill」的支援程度（尚未查證）
- [ ] transfer 的 `template-contract.md` 與 builder 的 `platform-behaviors.md`、`data-center.md` 內容重疊多少（尚未逐段比對）

## 參考

- [Extend Claude Code — features overview](https://code.claude.com/docs/en/features-overview)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [How Claude remembers your project — CLAUDE.md 與 rules](https://code.claude.com/docs/en/memory)
- [Harness engineering for coding agent users — Martin Fowler](https://martinfowler.com/articles/harness-engineering.html)
- [Skill Issue: Harness Engineering for Coding Agents — HumanLayer](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents)
- [Skills Over MCP Working Group notes](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2628)
- [Discover Agent Skills from MCP servers — Microsoft](https://devblogs.microsoft.com/agent-framework/discover-agent-skills-from-mcp-servers-in-net/)
