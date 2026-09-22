# AI GO Harness 重構設計：依 harness 分類切結構，為 MCP 化鋪路

- 狀態：草稿（待審）
- 日期：2026-09-17（2026-09-21 更新：PR #82 已合併，§2.1、§2.2、§5 隨之修訂；同日依 #86 review 修訂 §0、§1.3、§2.4、§2.6、§3、§4、§5、§6——發布契約先行、可攜核心＋轉接層、checker 不併；2026-09-22 依 #89 的 Codex review 再修：更新權責、確認閘改兩階段、CONTEXT.md 進 skill 目錄、規則副本過期處理、發布閘門）

## 0. 這份文件在談什麼

AI GO 的 agent harness 目前以 **GitHub repo** 為發布單位：`AI-GO-APP` organization 底下，每個 skill 各自是一個獨立的 repo，使用者用 git clone 把整個 repo 裝進自己機器的 skill 目錄。

本文件盤點其中三個**非 FDE 專用**（下稱 general）的 repo：

| 本文簡稱 | GitHub repo | 做什麼 | 誰在用 |
|---|---|---|---|
| **builder** | `AI-GO-APP/aigo-app-builder-skill`（本文件所在的 repo） | 開發 AI GO Custom App：前端、Server-Side Action、部署與驗證 | FDE、租戶 |
| **transfer** | `AI-GO-APP/aigo-template-transfer-skill` | 把上線中的 Custom App 轉成可上架的市集模板 | FDE |
| **checker** | `AI-GO-APP/skill-safely-vibecoding-checker` | 對 AI 協作開發的專案做安全稽核 | AI GO 的 vibe coder、FDE |

**本文件的範圍**：builder 與 transfer 合併重構——兩者共用憑證、API client、更新檢查，而且已經分歧（§2.3）。checker **不併**，維持獨立 repo、獨立版本：它沒有 scripts、與另外兩者沒有共用程式碼，併進來反而要新寫一支檢查才守得住它的產品中立（§3.4）。本文件對 checker 的幾項建議（§2.2、§2.5、§3.4）在它自己的 repo 內進行。

**不在範圍**：`AI-GO-APP/agentoss-module-builder-skill`（服務 Agent OSS 平台，不是 AI GO），以及 FDE 專案 repo 內附帶的 skill。

本文件也會提出**對 AI GO 平台本體的一項修改建議**（§7）：目前寫死在 skill 文件裡的平台限制值，應改由平台提供 API 查詢。

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

**「檢查」會落在兩個不同的分類，不要混為一談：**

| | Guards | 推理型檢查（歸 Skills＋Agents） |
|---|---|---|
| 怎麼判定 | 程式直接判定 | 要讀 code、理解商業邏輯才能判斷 |
| 結果 | 固定，同樣輸入永遠同樣答案 | 會變，同一份 code 不同次可能判出不同嚴重度 |
| 何時執行 | 事件觸發，每次必定執行 | 使用者要求時才跑 |
| 本專案的例子 | 「VFS 檔案數有沒有超過上限」 | checker 的「這個 API 有沒有租戶隔離漏洞」 |

判準看 Fowler 的確定性／推理二分（§1.2 a）：guard 是確定性的，checker 是推理的。**需要控制誤判率的，就是推理型檢查**——checker 每份 reference 結尾都要求寫「常見誤判，不要報」，正是這個性質的證明。

### 1.2 三條業界證據

**(a) 寫成文字的規則只是請求，寫成程式的檢查才是強制。**

Claude Code 官方文件明載：在 CLAUDE.md 或 skill 裡寫「不准改 `.env`」是一個請求，不是保證；用 `PreToolUse` hook 擋下才是強制。官方的結論是：如果一條規則必須每次都成立，就該做成 hook，而不是提示詞裡的一句指示。

Fowler 對 agent 控制手段的分類呼應同一點：他把控制手段分成「確定性（computational）」與「推理（inferential）」兩類——linter、型別檢查與測試屬於前者，「快、確定，結果可靠」；AGENTS.md 與 skills 屬於後者，效果不保證。因此，**凡是能改寫成確定性檢查的規則，就不該只留在文字裡**。

**(b) 塞給模型的指示越多，模型的表現越差。**

HumanLayer 引述 ETH Zurich 的研究：當 context 檔案過大或由工具自動生成時，agent 多花了 14–22% 的推理 token 去處理這些指示，而任務表現並沒有提升。HumanLayer 自己的結論是「指示越少越好」，該團隊的 CLAUDE.md 不到 60 行。

Claude Code 官方文件建議 CLAUDE.md 控制在 200 行以內，超過就該改用路徑限定的 rules，或移到按需載入的 skill。Skill 本身則採「漸進揭露」：`SKILL.md` 只說明有哪些補充檔案、什麼情況下該去讀，細節放在 `references/` 底下。

**(c) 有外部副作用的流程，不該讓模型自行決定何時執行。**

Claude Code 官方文件建議：會產生副作用的 skill 應設定 `disable-model-invocation`，讓它只能由使用者手動叫用。

### 1.3 因此，理想的結構要滿足五件事

- 每類內容只有一個歸屬，不重複、不混放
- 可由程式判定的規則要寫成程式，不能只寫成文字
- 主入口檔只負責分流，細節按需載入
- 共用的基礎設施只維護一份（SSOT）：憑證、API client、更新檢查、hooks 範例由 builder 與 transfer 共用
- **每個 skill 目錄自給自足**：`SKILL.md` 用到的 references、scripts、assets 都在該 skill 目錄之內。Agent Skills 規格、`skills` CLI、MCP 的 Skills extension（§4.1）三者都以「一個 skill 目錄」為搬運單位，相對路徑一律對 skill 根目錄解析——放在 skill 目錄之外的東西，到不了使用者手上（實測見 §2.6）

---

## 2. 實際長怎樣

### 2.1 現況

這三個 repo 的內容都是「一個 repo 等於一個 skill 目錄」：根目錄直接放 `SKILL.md`，旁邊是 `references/`、`scripts/` 等子目錄。所有 harness 內容都擠在各自的 `SKILL.md` 與 `scripts/` 裡。

| Repo（簡稱） | 最後維護 | SKILL.md | 其他 |
|---|---|---|---|
| builder 1.46.2 | 2026-09-21 | 475 行 | `scripts/` 下 17 支 Python 約 7500 行；沒有單元測試（僅 `aigo_publish.py` 的 inline self-test，與需要憑證實打平台的 `run_e2e_tests.py`） |
| transfer 0.9.0 | 2026-09-01 | 484 行 | 14 個測試檔 |
| checker | 2026-07-25 | 162 行 | 無 scripts |

**builder 的 SKILL.md 長度問題已於 2026-09-21 由 PR #82（版本 1.44.0）解決**：主檔從 1092 行瘦身到 471 行，四段內容搬進新建的 `references/dev-rules.md`、`planning.md`、`environment.md`、`review-workflow.md`，該 PR 並附上 `scripts/check_docs.py`（檢查主檔長度、引用斷鏈、reference 目錄、搬家後的內容遺漏）與三個 eval 情境。

**這件事解決的是「長度」，不是「分類」。** 搬進 reference 的內容仍然是 skill 的一部分，規則、護欄、流程依舊混在同一個 skill 目錄裡——下一節逐項說明。那個 PR 因此不與本設計衝突，反而先替本設計完成了 §5 步驟 4 的一部分搬移工作。

### 2.2 哪些內容放錯了分類

builder（以下位置為 1.44.0 瘦身後的現況）：

| 現況位置 | 應屬 | 為什麼 |
|---|---|---|
| `references/dev-rules.md`（259 行，原 Phase 3 規則 18–32）、`references/environment.md` 的租戶空間網址與憑證規則、SKILL.md Phase 3 留下的規則 1–17 速查表 | Rules | 這些是開發者寫 app code 時永遠要成立的限制，不是某個流程的步驟。它們現在雖然搬出主檔，但仍只在 skill 被觸發時才載入，模型直接改 code 時看不到 |
| 規則 9（SDK 檔不可修改）、規則 14（VFS 上限；文件與腳本曾各抄一份 200、實為 500，已由 #85／#88 修正，見 §7）、禁用詞交付前 grep、憑證不得出現在指令列 | Guards | 這四條都能由程式直接判定對錯。前兩條其實**已經有一半是程式**：`aigo_sync.py` 的 `read_local_files` 會跳過 SDK 保護檔、檢查檔數與單檔大小——但只守「從本機讀進來」這一條路，直接改遠端 VFS 的路徑（`sync_to_cloud` 的呼叫端自組 files）繞得過去。要做的是把既有判斷抽成純函式，並在**每個寫入遠端的邊界**都呼叫，不是從零寫 |
| SKILL.md Phase -1 的 skill 自我更新、Phase 4「每次改完 code 都必須部署並驗證」 | Guards／自動化 | 「每次都要做」正是生命週期事件觸發的定義 |
| `references/review-workflow.md` 的現況盤點九步（既有 code、租戶自建表、既有排程、對外呼叫）、`references/pre-report-self-grill.md` 的六輪自審 | Agents | 盤點要讀大量檔案但只需回傳結論；自審交給獨立的驗證者比自己檢查自己更可信 |
| SKILL.md Phase 4.4 發布、Phase 5 的問題回報 submit | Workflows | 這兩者會影響外部系統，不該由模型自行決定何時執行（這是語意分類；實體落點是腳本的「準備／執行」兩階段核准，見 §3.2） |
| `scripts/` 底下 17 支 Python（含 1338 行的 `aigo_auth.py`） | Tools | 這些已經是一套 SDK，不是給模型讀的指示 |

補充：1.44.0 新增的 `scripts/check_docs.py` 與 `evals/` 屬於 repo 自身的品質工具，檢查的是文件結構與 agent 行為，不是本節要分類的 harness 內容；重構後 `check_docs.py` 歸 `tests/`；`evals/` 是跑在真實對話上的行為情境，維持獨立目錄。

transfer 的 SKILL.md：

- **做對的地方**：鐵律 3「階段不可跳」已由腳本的狀態機強制執行，鐵律 2 的人工閘也已由腳本的互動確認擋住——這正是 §1.2 (a) 說的「把規則改寫成確定性檢查」
- 鐵律 1（不得直接編輯 `work/<slug>/template/` 下的檔案）與鐵律 7（憑證紀律）仍然只是文字，應改寫成 Guards
- 鐵律 6（對外呼叫走 egress 閘道，約 20 行）是平台知識而非鐵律，且與 builder 的規則 29 講同一件事，兩邊各存一份
- Phase S9 送審會把模板送進審核流程，應歸 Workflows

checker：

- 它整體是**推理型檢查**，歸 Skills＋Agents，不是 Guards（見 §1.1 的對照表）
- 8 個稽核維度目前是循序讀取，應改為各派一個唯讀 subagent 平行稽核
- 硬規則 3「不修改程式碼」可由工具權限直接限制成唯讀，不必只靠文字
- `templates/report.md` 改名為 `assets/report.md`，對齊 Agent Skills 的慣用目錄名（該 repo 內部的整理，不是本重構的前提）
- **抽象層級不一致**（新發現，見 §2.5）

### 2.3 builder 與 transfer 共用的基礎設施已經分歧

| 檔案 | 分歧狀況 |
|---|---|
| `check_update.py` | builder 與 transfer 各有一份，互相 diff 有 735 行差異：builder 會強制同步到遠端最新版，transfer 只印出提示 |
| `resources/hooks/*` | 兩份內容近乎相同，但 hook timeout 一個設 120 秒、一個設 10 秒 |
| `aigo_client.py` | transfer 的這支腳本在註解中自稱「憑證與租戶空間紀律對齊 builder 1.8.0+ 的 `aigo_auth.py`」，而 builder 現已是 1.44.0 |

### 2.4 為什麼會變成這樣

混類不是因為寫的人隨便，而是發布方式造成的：這三個 repo 要 clone 到 FDE 或租戶的機器上，而客戶端（Claude Code、Codex）只會把「一個 skill 目錄」當成一個可安裝的單位——rules 要放進使用者的專案才會載入、hooks 要寫進使用者的 settings 才會執行，兩者都不會跟著 skill 目錄走。所以規則與護欄只能退而求其次，全部塞進 `SKILL.md`。**要解決混類，得先換掉發布方式**——因此 §5 把 guards 與回歸網排在前面、發布契約定案之後才搬目錄，而不是反過來；現行發布方式加在目錄結構上的硬限制見 §2.6。

### 2.5 checker 的 stack 檔破壞了它自己的抽象層級

checker 的 `references/` 底下同時放了兩種層級的檔案：

| 檔案 | 層級 | 內容 |
|---|---|---|
| `01-tenant-isolation.md` 等 8 個維度檔 | 抽象，對所有技術棧成立 | 「租戶識別的唯一可接受來源是伺服器端 session／JWT claim」「查詢過濾要有全域機制，不能靠每支查詢自己記得加 where」 |
| `stacks/supabase.md`、`nextjs.md`、`postgres-prisma.md` | 具體實作 | `service_role` key 的誤用、查 `pg_policies` 的 SQL |

三個問題：

1. **層級混放**：維度檔講「要檢查什麼」，stack 檔講「在這個技術棧怎麼檢查」，但兩者平行放在同一層目錄，沒有主從關係
2. **覆蓋不完整且沒有邊界宣告**：只有三個 stack。遇到 Django、Rails、Firebase 的專案，文件沒說怎麼辦。抽象維度理應涵蓋得了，但 stack 檔的存在會讓 agent 誤以為「不在清單裡就不用查」
3. **重複**：`01-tenant-isolation.md` 講租戶識別，`stacks/supabase.md` 又用 RLS 把租戶隔離講一次，同一條原則兩處維護

**建議**：把主從關係倒過來。8 個維度檔是唯一的檢查清單（SSOT）；stack 檔降級為「查核提示」，只放該技術棧特有的陷阱與查法（例如「Supabase 用這兩段 SQL 查 RLS 狀態」），並明確寫出「未列出的技術棧一樣要做完 8 個維度，只是要自己找對應的查法」。

### 2.6 現行發布方式對目錄結構的兩條硬限制

任何新結構都要先過這兩關，否則 merge 當下就會弄壞既有安裝。

**(a) `npx skills add` 只安裝「含 `SKILL.md` 的那個資料夾」。** 這是 README 主推的安裝方式。2026-09-21 以一個假 repo 實測（`skills/builder/SKILL.md` 加上與 `skills/` 同層的 `tools/`、`rules/`、`guards/`）：

```
installed tree:
/.claude/skills/builder/SKILL.md
/.claude/skills/builder/references/a.md
```

同層的 `tools/`、`rules/`、`guards/` **沒有**被安裝。也就是說，把 scripts 搬到 skill 目錄之外，`SKILL.md` 指到的腳本會全部斷鏈。

**(b) `scripts/check_update.py` 會把每一份已登記的安裝強制同步到遠端 main**（3 小時節流）。它分兩種安裝型態（`_install_method`，`:247`）：有 `.git` 的做 `git fetch` → `git reset --hard`（`:292–313`）；沒有的（`npx skills add` 複製式安裝）下載**整個 repo 的 main.zip** 鏡像覆蓋（`_force_sync_zip`，`:379`）。若在本 repo 的 main 直接重組，merge 後數小時內所有既有安裝的根目錄 `SKILL.md` 消失；`resources/hooks/` 範本裡寫死的 `scripts/check_update.py` 路徑也一併失效，連自我修復的機會都沒有。而且第二種型態在新結構下更危險：它會把 repo **根目錄**的內容蓋進一個 skill 資料夾。

**結論**：重構在**新 repo** 進行，由使用者選擇遷移；本 repo 在過渡期維持現有結構、照常收修正（§5 步驟 7、§6）。

---

## 3. 建議

### 3.1 目錄結構：可攜核心＋發布轉接層

§1.1 的六分類是**語意上**的分類，不必一對一變成頂層目錄。實體結構要同時滿足 §2.6 的兩條限制，所以分成兩層：

- **可攜核心**（`skills/`）：Agent Skills 標準格式、每個 skill 目錄自給自足。任何客戶端、任何安裝方式（`npx skills add`、git clone、plugin、MCP Skills extension）拿到的都是同一份
- **發布轉接層**（repo 根目錄的 plugin 元件、scaffold 產出的 `AGENTS.md`、日後的 MCP server）：把「核心做不到的載入時機」補上——常駐規則、生命週期 hook、subagent。轉接層只引用核心的正本，不另存一份內容

builder 與 transfer 合併成一個新 repo（下稱 `aigo-harness`，正式名稱待定，見 §6）：

```
aigo-harness/                       ← 新 repo；repo 根目錄同時是一個合法的 Claude Code plugin
├── .claude-plugin/plugin.json      ← 轉接層：讓整個 repo 可當 plugin 安裝
├── skills/                         ← 可攜核心（每個目錄自給自足）
│   ├── aigo-builder/
│   │   ├── SKILL.md                ← 只做分流（500 行以內）
│   │   ├── CONTEXT.md              ← 術語表（SKILL.md 第一段就要求先讀它，所以必須在 skill 目錄內）
│   │   ├── references/             ← 平台知識
│   │   │   └── rules/              ← Rules 的正本：frontend／actions／data／platform-api／credentials
│   │   ├── scripts/                ← Tools ＋ Guards（builder 專用；`_core/` 為共用程式的同步副本）
│   │   └── assets/                 ← 範本、掃描規則、保留表名（原 resources/ 與 config/）
│   ├── aigo-migrate/               ← 遷入流程，自 builder 的 Phase 1.25／2.0 拆出（自帶用到的 references 副本）
│   └── aigo-template-transfer/     ← transfer 的 S0～S9；用到的平台規則（原鐵律 6）以**生成副本**放在自己的 references/
├── core/                           ← 共用程式的正本：auth、client、config、check_update、guards
│                                     同步進各 skill 的 scripts/_core/；CI 檢查副本與正本逐位元組一致
├── shared-refs/                    ← 跨 skill 共用的規則文字正本（platform-api、credentials）；同樣以生成副本進各 skill 的 references/
├── agents/                         ← 轉接層：subagent 定義（app-inventory、report-verifier）
├── hooks/hooks.json                ← 轉接層：SessionStart（更新檢查＋注入精簡硬規則索引）、PreToolUse（guards）
├── tests/                          ← core、guards、各 skill scripts 的測試；安裝 smoke test
└── evals/                          ← 行為情境（沿用 1.44.0 建立的慣例，§5 步驟 2 擴充）
```

**自給自足的判準**：每個 `skills/<name>/` **單獨**裝到一台乾淨機器上，`SKILL.md` 指到的每一個檔都要存在——這是 §5 步驟 2 的安裝 smoke test 要逐一 skill 驗的。跨 skill 共用的東西（程式在 `core/`、規則文字在 `shared-refs/`）一律以**生成副本**進各 skill 目錄，CI 守副本與正本一致；不靠安裝時的網路、不靠相對路徑往上跳。

六分類各自落在哪裡：

| 分類 | 正本 | 誰來載入 |
|---|---|---|
| Skills | `skills/*/SKILL.md`＋`references/` | 所有客戶端（按需） |
| Tools | `skills/*/scripts/`（共用部分來自 `core/`） | 模型呼叫時 |
| Guards | `core/guards/`（純函式、不做 I/O） | ① sync／publish 腳本在動作前呼叫——**所有客戶端都成立**，比照現有的 `egress_preflight`（`aigo_publish.py:252`）② plugin 的 PreToolUse hook ③ CI ④ 日後的 MCP tool |
| Rules | `skills/aigo-builder/references/rules/*.md` | ① skill 觸發時按需讀（所有客戶端）② plugin 的 SessionStart hook 注入一份精簡索引（30 行以內；**每一行都是一條可執行的硬規則**，例如「不得修改 `src/db.ts`」——只列檔名沒有行為效果）③ scaffold 寫進 app 專案的 `.claude/rules/`（帶 `paths`）與 `AGENTS.md`，附版本戳與內容雜湊；④ 新增一個 `upgrade-project` 操作（scripts 內的指令，所有客戶端都能跑）：比對雜湊、重產過期副本、**保留使用者自己加進 `AGENTS.md` 的段落**。②③④ 的行為效果要有 eval 情境驗證（直接改 code 不經 skill 觸發、續接的舊 session 兩種），不是寫了就算 |
| Agents | `agents/*.md` | plugin（Claude Code）；其他客戶端退回 skill 內的文字指示「可派 subagent 時，交給獨立 context 執行」 |
| Workflows | **不獨立成一類**——見 §3.2 | 有外部副作用的操作走「準備／執行」兩階段（§3.2），不靠 slash command 也不靠互動式 `input()` |

### 3.2 關鍵決策與取捨

| 決策 | 理由 | 取捨 |
|---|---|---|
| 可攜核心＋轉接層，而不是六個頂層目錄 | §2.6 (a)：skill 目錄之外的東西到不了使用者手上。核心自給自足，才能同時支援 `skills` CLI、git clone、plugin、MCP 四種搬運方式 | 共用程式要同步進各 skill 目錄（見下一列） |
| 共用程式以 `core/` 為正本、同步副本進各 skill 的 `scripts/_core/`，CI 守一致 | 不依賴安裝時的網路與套件來源；每個 skill 目錄拿到的就是完整、可執行的一份（「離線」要說清楚：第一次 `uv run` 仍要抓 `pyproject.toml` 宣告的第三方套件如 `httpx`，只是不必再抓我們自己的程式）。CI 除了逐位元組比對，還要**在副本位置實際 import 並跑一次**——只比對存在的檔抓不到「正本多了一個檔、副本沒同步到」 | repo 內有重複檔案。替代方案（`scripts/pyproject.toml` 以 git 依賴釘 revision 安裝 `core`，或打成版本化 wheel 隨 skill 附上）列入 §6；起步先用副本 |
| **plugin 與 MCP 都做，兩者都是轉接層，不是二選一** | plugin 今天就能送 skills、agents、hooks、MCP server 定義；plugin 根目錄的 `CLAUDE.md` 確實不會載入，但 SessionStart hook 的 stdout／`additionalContext` 會進 context（官方 hooks 文件明載，plugin hook 與 settings hook 行為相同），規則因此送得進去。反過來 MCP 同樣送不了常駐規則與 subagent（§4）。repo 根目錄本來就幾乎是 plugin 的形狀，多一個 manifest 的成本很低 | plugin 只服務 Claude Code；其他客戶端靠可攜核心＋`AGENTS.md`，拿不到 hook 與 subagent |
| Guards 的第一落點是 **tool 內呼叫**，hook 其次 | tool 內呼叫對所有客戶端成立，也是日後 MCP 伺服器端把關的同一段程式；hook 只有部分客戶端有 | 多一層呼叫 |
| Workflows 不獨立成一類；有外部副作用的操作走**「準備／執行」兩階段**，不靠互動式確認 | `disable-model-invocation` 是 Claude Code 專屬欄位（§3.3），換客戶端保護就消失。而**腳本裡的互動式確認也不成立**：agent 透過非互動 shell 跑腳本時 stdin 是關的，`input()` 直接 `EOFError`（2026-09-22 實測）；就算 agent 餵得進去，那也是 agent 自己按的，證明不了真人同意。可攜的做法是：`prepare` 階段（非互動）印出**確切的目標與變更**（哪個 app、哪個版本、會動到哪些檔／哪些欄）並產生一個綁定這次操作內容的核准 token；`execute` 階段必須帶這個 token，且 token 只由**可信的核准管道**核發——Claude Code 上是 slash command 內由使用者確認、其他客戶端是使用者自己在終端機跑一句、MCP 上是 server 端的核准流程。拿不到管道就拒絕執行，**不接受 agent 自己傳的 `--yes` 旗標**。transfer 現有的互動確認閘要改成這個形狀 | 每支有副作用的腳本（publish、問題回報 submit、模板送審、scaffold 的 upgrade-project 覆寫）都要實作兩階段並測試；使用者多一個動作 |
| Rules 的正本留在 skill 目錄內，常駐載入交給轉接層 | 正本只有一份、跟著 skill 走、由更新機制同步；落地到使用者專案的副本只是快取，帶版本戳與內容雜湊 | 落地副本會過期，而且**只在 scaffold 與 SessionStart 比對是不夠的**——沒有 hook 的客戶端上的既有專案永遠不會被提醒。所以 §3.1 表的 ④ `upgrade-project` 是必要的，而且 builder 的每個可攜入口（`aigo_sync`／`aigo_publish` 起跑時）都要順手比對一次雜湊、過期就印警告 |
| **更新權責：一個 skill 在一台機器上只有一份有效安裝，誰裝的誰更新** | 現在的 `check_update.py` 對 git 安裝做 reset、對複製安裝下載整包 repo ZIP 鏡像（§2.6 (b)），兩者都假設「一個 repo＝一個 skill 目錄」，在新結構下會把 repo 根目錄蓋進 skill 資料夾。新結構要分三種來源：`npx skills add`（由 skills CLI 更新，我們的 updater 只**告知**）、git clone（updater 可 reset，但 reset 的是 repo 根，之後要重新確認 skill 子目錄完整）、plugin（由 plugin 系統更新，updater **完全不動**）。安裝時登記來源，updater 依來源決定能做什麼；同一個 skill 被兩種來源各裝一份時要偵測並警告 | updater 要重寫；三種來源各要一組共存測試 |
| checker 不併 | 沒有共用程式碼；併入後產品中立更難守（§3.4）。「只裝一次」可由安裝說明或 marketplace 清單解決，不需要同一個 repo | 使用者要裝兩個來源 |

### 3.3 檔案格式：YAML frontmatter + Markdown

**是業界標準，但只對「給模型讀的文字」成立。** Agent Skills 規格定義 skill 的形狀就是一份 `SKILL.md`——`---` 之間的 YAML frontmatter 加下方的 Markdown 正文；frontmatter 必須從檔案第一行開始，否則整份檔案會被當成內文。Cursor 也支援同一個格式，只是多了 `icon`、`color` 兩個外觀欄位。Claude Code 的 rules 與 subagent 定義同樣是 frontmatter + Markdown。

本設計各分類的格式：

| 分類 | 格式 | frontmatter 欄位 |
|---|---|---|
| `skills/*/SKILL.md` | YAML frontmatter + Markdown | `name`（小寫連字號、≤64 字元、與目錄同名）、`description`；正文 500 行以內 |
| `skills/*/references/*.md` | 純 Markdown，**不需要** frontmatter | — |
| `skills/aigo-builder/references/rules/*.md`（正本） | 純 Markdown | —；scaffold 落地到 `.claude/rules/` 時才加上 `paths` frontmatter（glob 清單，限定何時載入） |
| plugin 的 slash command（publish 等的薄入口，選配） | 同 skill 格式 | 另加 `disable-model-invocation: true`（見下方警告）；真正的把關在腳本的兩階段核准（§3.2） |
| `agents/*.md` | YAML frontmatter + Markdown | `name`、`description`、工具限制（唯讀） |
| `core/**`、`skills/*/scripts/**` | 程式碼，不是 Markdown | — |
| `skills/*/assets/**` | 範本與設定檔（`.md`、`.json`），不進 frontmatter | — |

**一個要留意的可攜性落差**：Agent Skills 規格只允許 `name`、`description`、`license`、`compatibility`、`metadata`、`allowed-tools` 六個欄位，上傳或打包時出現其他欄位會**硬性報錯**。Claude Code 自己支援的 `disable-model-invocation`、`context: fork`、`hooks`、`paths` 等都**不在**規格內。

這代表：

- `skills/` 維持規格內的六個欄位，才能保有「換客戶端也能用」的退路（§2 的結論）
- `disable-model-invocation` 是 **Claude Code 專屬能力**；換到不支援的客戶端時，那層保護會消失。所以「只能由人觸發」不押在它身上，而是由腳本的兩階段核准把關（§3.2）——slash command 只是其中一種核准管道
- rules 的 `paths` 同樣是客戶端專屬的。scaffold 寫進使用者專案時，除了 `.claude/rules/`，另外產一份 `AGENTS.md` 給其他客戶端讀——`AGENTS.md` 是純 Markdown、沒有條件載入機制，所以只放最精簡的硬規則

### 3.4 checker 的產品中立：不併是第一道防線，仍建議改用程式守

**為什麼在意這件事**：checker 是稽核工具。如果它的報告在列出資安問題的同時順帶推薦「這題用 AI GO 可以解決」，讀報告的人就有理由懷疑那些問題是不是為了推銷而誇大。checker 自己的 `AGENTS.md` 把這條寫得很直白：「一份會為了推銷而扭曲結論的稽核報告，對使用者與產品都是負值。」

**為什麼因此不併**：這條界線現在只是一條文字規則（產品資訊只能出現在 `references/aigo-platform.md`）。併進一個周圍全在講 AI GO 的 repo，之後改檔案的人或 agent 更容易順手把產品名稱寫進去——而合併換到的只有「少裝一次」，沒有任何共用程式碼可省。成本大於效益。

**仍然建議做的**（在 checker 自己的 repo）：依 §1.2 (a)，把這條規則從文字換成程式——CI 掃 `references/aigo-platform.md` 以外的所有檔案，出現產品名稱就失敗（要留例外：政策條文本身、以及稽核證據裡合法出現的產品名）。但要說清楚：這支掃描守的是**檢查清單與範本**不夾帶產品，守不了「報告本身中不中立」——那要靠對產出報告的 eval。§2.5 的 stack 檔降級、8 個維度改派唯讀 subagent 平行稽核，也都在該 repo 內進行。

**何時重新考慮併入**：checker 開始需要與 builder 共用程式（例如要呼叫平台 API 取證）時，先評估的是「抽一個共用程式庫」，不是併 repo；只有在 owner、發布節奏都一致、而且算得出併入省下多少維護時，才談併。

---

## 4. 對應到 MCP

MCP 是「客戶端程式 ↔ MCP server」之間的固定協定。模型只負責決定要呼叫哪個 tool、參數填什麼，實際的請求由客戶端程式送出。一個 MCP server 除了提供 tools，還能提供 resources（可讀取的文件）、prompts（預先寫好的流程），以及連線時直接注入模型 context 的 instructions。

| 本設計的分類 | 在 MCP 裡怎麼送 | 備註 |
|---|---|---|
| `skills/*/scripts/`（tools） | MCP tool | `core/auth` 改為伺服器端 OAuth，使用者的密碼不再經過 agent |
| `guards` | 由 tool 在執行前先呼叫，不合規就直接拒絕 | 所有操作都走 tool，因此比裝在客戶端的 hook 更可靠，也不受客戶端種類影響 |
| `skills` | MCP 官方 Skills extension：`skills/list`／`skills/get` 探索，內容經 `resources/read` 按需讀取 | **規格已定案（SEP-2640 Final），host 支援仍在鋪，見 §4.1** |
| 有外部副作用的流程（publish 等） | tool 走兩階段：`prepare` 回傳確切變更與核准 token，`execute` 由 server 端核准流程放行；可另附 prompt 當入口 | 有支援的客戶端會把 prompt 顯示成 slash command |
| `rules` | 三路並用：① server instructions 送最精簡的硬規則 ② scaffold tool 把 `skills/aigo-builder/references/rules/` 的正本寫進 app 專案的 `.claude/rules/` 與 `AGENTS.md` ③ tool 回傳結果時附上相關條文 | MCP 沒有辦法強迫客戶端常駐載入某份內容 |
| `agents` | 以 resource 提供定義，由客戶端自行安裝 | MCP 沒有對應機制，是整套設計裡最弱的一環 |

### 4.1 用 MCP 發送 skill：規格已定案，host 支援還在鋪

MCP 原本只有 tools、resources、prompts 三種機制，沒有「skill」這一類。Skills over MCP 工作組的結論已經出爐：官方 **Skills extension（`io.modelcontextprotocol/skills`，SEP-2640）狀態為 Final**（2026-09-21 查證）。做法是沿用既有的 Resources 機制再加兩個方法：

- server 宣告 `resources` capability 與該 extension，實作 `skills/list`、`skills/get`；skill 的檔案一律經 `resources/read` 取得
- 一個 skill 就是一個含 `SKILL.md` 的目錄，遵循 Agent Skills 規格；**相對路徑對 skill 根目錄解析**，每個 skill 附完整的檔案清單（URI、SHA-256、大小），host 逐檔驗證
- 規模上限建議：每個 skill 不超過 512 個檔案、16 MiB
- host 不得預先抓檔，只在需要時讀——與 Agent Skills 的漸進揭露一致

規格明講「SDK 與 host 的支援仍在實作中」，各客戶端的現況要看官方的 client support matrix——**Claude Code、Codex、Cursor、Antigravity 各自支援到哪裡尚未逐一查證**，列入 §6。

**這對本設計的意義**：規格把「skill 目錄自給自足」寫成了協定層的要求，與 §1.3、§2.6 (a) 的結論一致。`skills/` 維持 Agent Skills 標準格式，就同時是 `skills` CLI、git clone、plugin、MCP 四條路的共同輸入，不會白做。

### 4.2 改用 MCP 之後可以移除的東西

- **skill 自我更新機制**（builder 與 transfer 的 Phase -1、兩份 `check_update.py`、SessionStart hook 範例）：remote server 上永遠是最新版，客戶端沒有本地副本需要更新
- **transfer 的工作目錄守衛**（鐵律 1）：`work/<slug>/` 會變成伺服器端的狀態，agent 根本碰不到那個目錄，不需要再用規則去擋

### 4.3 內容去向：哪些東西會到使用者手上

| 去向 | 內容 | 使用者可見性 |
|---|---|---|
| 只留在伺服器 | tools、guards、憑證、transfer 的工作狀態 | 使用者只看得到 tool 的輸入與輸出 |
| 按需進入模型 context | skills、有副作用流程的 prompt 入口、server instructions、tool 回傳時附帶的條文 | 使用者的機器上不存檔，但內容看得到，也可以要求模型整段貼出來 |
| 落地成使用者機器上的檔案 | 專案裡的 `.claude/rules/`、`AGENTS.md`、agents 定義 | 以檔案形式存在，需要靠版本比對提醒使用者同步 |

原則：需要保護的判斷邏輯要放進 guards 與 tools；給模型讀的文字一律當作使用者看得到來撰寫。

**MCP 送出去的不是同一份 skill 目錄**：§3.1 的「每個 skill 目錄自給自足」講的是 git／CLI／plugin 三條路；MCP 那條路的 tools 與 guards 在伺服器端執行，skill 文字裡「執行 `scripts/aigo_publish.py`」「先跑 `check_update.py`」這類指示在 MCP 客戶端沒有意義。所以 MCP 要有**另一份打包產物**：由同一份正本生成（共用來源），但去掉本機更新與本機腳本的指示、改指 MCP tool。另外 Skills extension 允許 host 保留經驗證的磁碟快取，所以「使用者機器上不存檔」這句只對「我們不主動落地」成立。

### 4.4 MCP server 動工前要先回答的歸屬問題

MCP server 一旦持有 OAuth、代使用者部署與發布，它就是**平台的產品**，不再只是一個 skill repo 的附屬品。步驟 9 的設計文件動筆前，先與平台團隊對齊：

- 授權伺服器與 MCP server 由誰部署、誰值班、誰做安全審查
- 與平台既有的 Builder tools（`backend/app/services/builder_tools.py`、`builder_tool_executor.py`）的關係：server 放在平台內直接呼叫 service，還是放在平台外走公開 API？前者的話，本 repo `core/` 的 HTTP client 在伺服器端用不上，步驟 5 的投資要按「過渡期工具」來估，不要過度打磨
- 租戶隔離與稽核軌跡：server 代多個租戶操作時，憑證與操作紀錄怎麼分
- 授權範圍與撤銷：使用者授權 server 代他做哪些事、怎麼收回；每一次有副作用的操作，核准來源（§3.2 的兩階段）怎麼留痕
- 本機檔案怎麼上去：publish 要送 VFS，MCP 客戶端把本機檔案交給 server 的路徑是什麼、大小上限多少
- 重試與冪等：tool 呼叫中斷後重打會不會重複部署／重複建 app
- **發布節奏與核准的衝突**：Skills extension 把使用者的核准綁在完整的檔案清單與雜湊上，**任何一個檔變了核准就失效**、要重新核准。builder 現在單日可達數版——照這個節奏 MCP 使用者每天都會被要求重新核准。所以 MCP 那條路需要：不可變的發布版（不是追 main）、session 進行中 manifest 不變、明確的重新核准體驗；打包 CI 要守每個 skill ≤ 512 檔／16 MiB（規格建議的 server 上限，host 可以支援更大，但超過就不保證可攜）

---

## 5. 遷移步驟

順序的原則：**先出貨不依賴重構的價值，再建回歸網，然後才搬目錄**；每一步都不弄壞既有安裝（§2.6）。

0. ~~前置~~——**已完成**：PR #82（1.44.0，SKILL.md 瘦身）、#85（1.46.1，文件的 VFS 上限 200 → 500）、#88（1.46.2，`aigo_sync.py` 的上限同步修正、單檔大小改以 bytes 判定）
1. **在本 repo、現有結構內先做 guards＋最低限度的測試與 CI**：把 `aigo_sync.read_local_files` 裡既有的 SDK 檔跳過、檔數、單檔大小判斷**抽成純函式**（`sdk_files`、`vfs_limits`），加上 `forbidden_terms`（CONTEXT.md 禁用詞）；在**每個寫入遠端 VFS 的邊界**呼叫（含直接組 files 的路徑，以及發布前對「遠端現況＋本次變更」的整體驗證），比照現有的 `egress_preflight`。每支先寫測試再寫實作；同一個 PR 帶上 CI（跑測試＋`check_docs.py`）——**沒有 CI 的 guard 只是又一份會漂移的程式**。SKILL.md 對應條文改為指向該 guard。這一步不搬任何檔案，既有安裝透過自我更新直接受益
2. **建回歸網**（同樣在本 repo）：scripts 的單元測試＋CI；`check_update.py` 的更新與回滾測試；安裝 smoke test（`npx skills add`、git clone 兩條路各驗一次「裝完後 SKILL.md 指到的每個檔案都存在」）；`evals/` 由三個情境擴充到涵蓋 rules 的主要分支。**沒有這張網，後面每一步「行為不變」都無從驗證**——三個需手動對話的情境只是抽樣下限，不是回歸網
3. **定發布契約、開新 repo**：**先定案**版本策略（§6：單一 `VERSION` 或各 skill 各自）與更新權責（§3.2 三種來源）——這兩件事沒定，步驟 4 搬進去的 updater 就是錯的；然後依 §3.1 建骨架（`skills/`、`core/`、`shared-refs/`、`.claude-plugin/`、`tests/`）；把步驟 2 的安裝 smoke test 搬過去，改成**逐一 skill 單獨安裝**、三條路（CLI、git、plugin）各驗，再加三種來源的共存測試。此步同時查清 §6 的客戶端支援矩陣。**發布閘門**：smoke test 全綠才進步驟 4
4. **搬 builder**：`references/`、`resources/`、`scripts/`、`CONTEXT.md` 搬進 `skills/aigo-builder/`，先原樣搬、不改內容——**除了 `check_update.py`**：它寫死了 repo URL 與「skill 根＝repo 根」的路徑計算（`:64`、`:71`），原樣搬進子目錄就是壞的，這支在此步依步驟 3 定案的權責重寫；再抽 rules——`references/dev-rules.md` 全份、`references/environment.md` 的租戶網址與憑證規則、SKILL.md Phase 3 的規則 1–17 速查表，拆成 `references/rules/` 下五個檔；`check_docs.py` 的引用檢查同步改指新位置。遷入流程拆成 `skills/aigo-migrate/`
5. **併入 transfer、抽 `core/`**：以 builder 的 `aigo_auth.py` 為基準，補上 transfer `aigo_client.py` 的差異並補測試；兩份 `check_update.py` 與 hooks 範例收斂成一份；建立「`core/` → 各 skill `scripts/_core/`」的同步腳本與 CI 一致性檢查。transfer 的鐵律 1、7 改寫成 guards，鐵律 6 併入 `references/rules/platform-api.md`
6. **轉接層**：`agents/`（app-inventory、report-verifier）、`hooks/hooks.json`（SessionStart 更新檢查＋精簡硬規則索引、PreToolUse guards）、`.claude-plugin/plugin.json`；scaffold 增加「把 rules 落地到 app 專案的 `.claude/rules/` 與 `AGENTS.md`，附版本戳與內容雜湊」＋ `upgrade-project` 操作（§3.1 表 ④）；publish、問題回報 submit、模板送審、upgrade-project 覆寫四支改成兩階段核准（§3.2）。**發布閘門**：規則落地的兩個 eval 情境（不經 skill 直接改 code、續接舊 session）通過
7. **舊 repo 的過渡**：本 repo 維持現有結構、照常收修正，直到新 repo 穩定。之後在本 repo 發最後一版——保留完整的舊目錄樹、`VERSION` 再升一版、`check_update.py` 改為「告知新位置與遷移指令」，**不**把既有安裝 reset 成新結構。遷移指令要做四件事並有測試：裝新的、移除舊安裝的 hook 登記與狀態檔、刪掉舊目錄（避免新舊兩份 skill 同時被客戶端載入）、印出回滾方式（回到舊 repo 最後一版的方法）。transfer repo 同樣處理
8. 每完成一個步驟，跑步驟 2 的回歸網與 `evals/`，確認 agent 行為沒有變差
9. MCP server 的 transport、認證與部署另立一份設計文件（先回答 §4.4 的歸屬問題），不在本文件範圍

checker 不在遷移步驟內；§2.5 與 §3.4 的建議在它自己的 repo 另開 issue。

## 6. 待決事項

已有結論（理由見各節，審閱時可推翻）：

- [x] 合併後的 repo 怎麼生 → **新開 repo**（§2.6：在本 repo 的 main 重組會被自我更新機制直接推到所有既有安裝）。代價是 commit 歷史與既有 issue 留在舊 repo
- [x] 過渡期要不要維持舊安裝方式 → **要，而且是硬前提**（§5 步驟 7）
- [x] checker 要不要併 → **不併**（§3.4）
- [x] 做不做 Claude Code plugin → **做，當轉接層**；與 MCP 不互斥（§3.2）

仍待決定：

- [ ] 新 repo 的正式名稱；舊 repo 何時發「最後一版」、之後封存或保留並在 README 指向新 repo
- [ ] 共用程式的分享機制：`core/` 同步副本＋CI 一致性檢查（本文件的預設；CI 要實際 import），或 `scripts/pyproject.toml` 以 git 依賴釘 revision 安裝 `core`（省掉重複檔案，但首次執行需要網路、要處理版本釘選），或打成版本化 wheel 隨 skill 附上（第三選項）
- [ ] 版本與發布節奏：新 repo 用單一 `VERSION` 還是各 skill 各自一個？builder 改版頻繁（單日可達數版），transfer 的使用者是否要跟著被同步。**§5 步驟 3 的前置**，不能拖到搬完再決定
- [ ] 更新權責的三種來源（§3.2）各自的實作：skills CLI 那條路 updater 只告知——那 3 小時節流的強制同步就沒有了，可接受嗎？
- [ ] 各客戶端對 plugin、hooks、MCP Skills extension 的支援程度（Claude Code、Codex、Cursor、Antigravity；尚未逐一查證，§4.1）
- [ ] MCP server 的歸屬與維運（§4.4）
- [ ] §7 的限制查詢端點要不要做、由誰做——已開 urfit-tech/AI-GO#1673，等平台團隊回覆
- [ ] transfer 的 `template-contract.md` 與 builder 的 `platform-behaviors.md`、`data-center.md` 內容重疊多少（尚未逐段比對）

## 7. 對 AI GO 平台本體的建議：限制值改由 API 提供

### 7.1 問題：文件抄的值已經錯了

skill 文件把平台限制值抄成文字（SKILL.md 規則 14、`references/custom-app-dev-guide.md` §4、`migration-workflow.md` 等處）。查對 codebase 後發現**抄錯**：

| 項目 | skill 文件寫的 | 平台實際 | 定義位置 |
|---|---|---|---|
| VFS 檔案數上限 | **200 檔** | **500 檔** | `infra/builder/compile.go:16` `MaxFileCount = 500`；Python 端鏡像 `backend/app/services/typecheck.py:30` |
| 單檔大小 | 1MB | 1,000,000 bytes（**不是** 1048576） | `infra/builder/compile.go:17` |
| 編譯逾時 | 30 秒 | 30 秒（相符） | `infra/builder/compile.go:21` |

錯誤方向是**低估**：agent 會把 app 切成 200 檔以內，白白放棄一半的額度。

另外一個文件沒寫、但 agent 必須知道的行為：**單檔超過 1MB 不會報錯，而是被靜默跳過**（`compile.go:263` 只寫 log 然後 `continue`）。檔數超限才會回傳 error（`:252`）。也就是說超大檔案會編出一個「少一個檔」的 bundle，症狀出現在執行期，而不是編譯期。

**跳過本身是刻意設計，不是 bug**：`infra/builder/compile_test.go:88` 的 `TestWriteVFSSkipsOversizeFile` 明確鎖住這個行為（註解指向 spec §7/§11 硬化），與同段落的路徑穿越攔截、租戶 tsconfig 剝除同屬一套「可疑輸入就排除，不中斷整個編譯」的防禦模式，`backend/app/services/typecheck.py:99` 亦對齊。問題不在跳過，而在**跳過的事實只留在伺服器 log**——呼叫端與 agent 完全不知情。

這還不是第一次漂移：`references/event-triggers.md:174` 自己記著 runner ceiling 在 prod v1.13.0（#1518）之前恆為 30 秒、之後才變 120 秒。**文件靠人追著改，而且已經追丟了一次。**

### 7.2 這些值目前的型態

| 限制 | 型態 | per-tenant 可調？ |
|---|---|---|
| VFS 檔數／單檔大小／編譯逾時 | Go `const`、Python 模組常數 | ❌ 改了要重新部署 builder |
| Action `timeout_ms` 範圍 1000–120000 | 寫死三處：`schemas/action.py:24`、`builder_tool_executor.py:1061` 與 `:1137`、`builder_tools.py:242` | ❌ |
| Egress request 8 MiB、rate limit 120/min | Pydantic Settings（env 可覆蓋，全域一份）`core/config.py:419,420` | ❌ |
| Egress 單一 service 的 `timeout_ms`、`max_response_bytes` | **DB 欄位**，tenant-scoped `models/egress.py:47-48` | ✅ 但只能調低於全域硬上限 |

**目前沒有任何 API 會回傳這些限制值**——前端要用就自己再寫死一份（`frontend/src/lib/egressRequirements.ts:54` 註解直接寫「比照 backend」）。租戶只有在 PATCH 超限被 422 時，才從錯誤訊息知道上限是多少。

### 7.3 建議

**(a) 新增一個限制查詢端點。** 平台已經有現成的模式可以照抄：`GET /api/v1/builder/apps/{app_id}/crons/quota` 會回 `app_limit`、`tenant_limit`、`min_interval_minutes`，並依租戶付費檔位給不同的值（`api/builder_app_crons.py:68`、`services/app_cron_service.py:201`）。建議比照增設 `GET /api/v1/builder/apps/{app_id}/limits`，回傳 VFS 檔數、單檔大小、編譯逾時、action timeout 範圍、egress 各項上限。

**(b) skill 端改成查而非抄。** `scripts/` 呼叫該端點取得限制，`core/guards/vfs_limits.py` 用回傳值判定，文件只寫「限制由 API 取得」，不再抄數字。這樣租戶若真的分檔位，skill 自動跟著對。

**(c) 若短期內不做 API，至少先修正數字**——這是獨立於本重構、可立即進行的修正，並建議在 AI GO repo 加一個測試，確保文件值與 `compile.go` 常數一致。

**(d) 讓被跳過的檔案可被呼叫端看見**：不動跳過行為（理由見 §7.1），但把被跳過的檔案列入編譯回應，例如 `skipped_files: [{path, size, reason}]`，`reason` 涵蓋現有三種排除（`exceeds_max_file_size`、`path_traversal`、`tsconfig_stripped`）。如此安全防禦不變、既有 app 不受影響，呼叫端可在發布前就告知使用者「這個檔案沒有進 bundle」。

### 7.5 進度

| 項目 | 狀態 |
|---|---|
| 向平台提案（(a) 限制查詢端點、(d) `skipped_files`） | 已開 issue：**urfit-tech/AI-GO#1673**，待平台團隊回覆 |
| skill 文件數字修正 200 → 500，並補上靜默跳過的警告（即 (c)） | **已合併**：#85（1.46.1）。同一個數字在 `scripts/aigo_sync.py` 還有一份沒改到，由 #88（1.46.2）補上——「一個數字存兩份、改一邊漏一邊」在一天內又發生一次，正是 (b) 要根治的事 |
| (b) skill 改為呼叫 API 取得限制 | 等 #1673 的端點上線後才能做；該約定已寫進 `references/custom-app-dev-guide.md` §4，避免日後又有人抄一份新數字 |

### 7.4 已一併反映給平台的發現

盤點過程中還發現「custom app 的開發限制完全不在既有的租戶分層機制內」——平台的 `quota_service.py` 已涵蓋 k8s 資源、Data Center 表數、Cron、用量配額，唯獨這一組是跨租戶共用的常數。這件事的歸屬在平台端，已寫進 urfit-tech/AI-GO#1673 的留言，本文件不重複論述。

## 參考

- [Extend Claude Code — features overview](https://code.claude.com/docs/en/features-overview)
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference)
- [How Claude remembers your project — CLAUDE.md 與 rules](https://code.claude.com/docs/en/memory)
- [Harness engineering for coding agent users — Martin Fowler](https://martinfowler.com/articles/harness-engineering.html)
- [Skill Issue: Harness Engineering for Coding Agents — HumanLayer](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents)
- [Skills Over MCP Working Group notes](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2628)
- [MCP Skills extension（SEP-2640）](https://modelcontextprotocol.io/extensions/skills/overview)
- [Claude Code hooks reference — SessionStart 的 stdout／additionalContext](https://code.claude.com/docs/en/hooks)
- [`skills` CLI](https://github.com/vercel-labs/skills)
- [Discover Agent Skills from MCP servers — Microsoft](https://devblogs.microsoft.com/agent-framework/discover-agent-skills-from-mcp-servers-in-net/)
