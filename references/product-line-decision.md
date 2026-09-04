# 產品線與模式判斷（Custom App vs Hosted App × internal vs external）

> **這是 SKILL.md Phase 1.5 第 1.5 項的 SSOT，新建與遷入兩條路共用。**
> 新建情景的輸入是 §1.0 需求盤點的四問；遷入情景的輸入是
> `migration-workflow.md` §2.0 的 stack 形狀（問題二的對照表在 §2.1）。
> 判斷結果**不可逆**（§6），所以先盤再判，不憑感覺。

---

## 1. 預設立場：新建 App 以 Custom App 為主

實務上客戶要新建的 app **絕大多數是一個 Custom App**——在平台內用、吃租戶資料、
沿用平台角色與簽核。Multi Custom App 與 Hosted App 是**例外**，只在下列訊號命中時才偏離預設：

| 訊號 | 偏離成 |
|---|---|
| 需求涵蓋 2 群以上目的不同的功能（客戶管理 vs 財務報表） | **多個 Custom App**（SKILL.md Phase 1.5 第 2 項拆分） |
| 使用者「兩者都有」（員工後台 + 客戶前台） | **兩個 Custom App**（internal + external 各一） |
| 公開 web 資產：自有網域、SEO、整站匿名瀏覽 | **Hosted App**（或混合：公開站 Hosted + 後台 Custom） |
| §2 邊界表命中標「Hosted」的條目 | **Hosted App** 或 **混合** |

沒有命中 → 一個 Custom App，不要為了「彈性」建議 Hosted。

## 2. Custom App 能力邊界核對表（§1.0 問題四用）

| 需求 | Custom App 做得到嗎 | 命中時的走向 |
|---|---|---|
| 常駐進程、WebSocket、SSE 長連線 | ❌ Server Action 是 request/response | **Hosted** |
| 單次工作 > 90 秒（webhook）／> 280 秒（排程） | ❌ 逾時（`event-triggers.md` §1.6／§2.6） | 切批次；切不了 → **Hosted** |
| 自選後端框架／語言（Go、Rails、Next.js API routes…） | ❌ 後端只有 Python `execute(ctx)` | **Hosted** |
| 自有網域、SEO、整站匿名瀏覽 | ❌ `/pub` 只給少數公開頁（dev-guide §15） | **Hosted**（`hosted-apps.md` §9 綁網域） |
| 前端非 React、或要 Tailwind／CSS Modules／MUI | ❌ SKILL.md 規則 3、dev-guide §16.1 | 改設計；用戶不接受 → **Hosted** |
| DB 交易、JOIN、條件式 UPDATE、`ON CONFLICT` | ❌ **兩條線都沒有**——Hosted 走 Open Proxy 一樣沒有 | **改設計**（dev-guide §23.9 的 claim／版本列／每格一列寫法），不是換線 |
| 執行期建表、改欄位（動態 schema） | ❌ `ctx.db` 不提供結構操作 | **改設計**：表在計畫階段建好 |
| 單檔 > 100 MB、自架 storage | ❌ Storage API 單檔 100 MB | 改設計；storage 兩條線都只能走 Storage API（規則 32） |
| Node.js 原生模組、動態 `import()` | ❌ 規則 16、17 | **改設計** |
| 直連外部 DB、自帶 Postgres／Redis | ❌ **兩條線都禁**（規則 32） | 資料一律進平台的表 |

標「兩條線都沒有／都禁」的是平台的**資料層能力邊界**，換 Hosted 解決不了——
要在需求階段改設計，不要對用戶說「換 Hosted 就好」。

## 3. 兩問定位

**先問使用者、再看形狀**——使用者選錯要砍掉重建，形狀選錯頂多多花工。

### 問題一：誰在登入？

（新建：§1.0 問題一；遷入：問「原系統現在是誰在登入」）

| 答案 | 走向 |
|---|---|
| 租戶內部成員（員工工具、內部後台） | **internal** |
| 外部客戶、會員、公眾（對外網站、客戶入口） | **external** |
| 兩者都有 | **拆成兩個 app**，各走各的線——一個 app 只能有一種模式 |

拿不準 → 直接問「這系統是誰在登入」，**不可用預設值帶過**。

### 問題二：需求／系統的形狀是哪一種？

新建情景（輸入：§1.0 的面向＋邊界命中）：

| 形狀 | 走向 |
|---|---|
| 應用介面，邊界表無「Hosted」命中 | **Custom App**（預設，繼續 SKILL.md 主流程） |
| 應用介面，但部分功能命中「Hosted」 | **混合**：業務介面與租戶資料存取 → Custom App；命中的那部分 → 獨立 Hosted App（§5） |
| 公開 web 資產（自有網域、SEO、整站匿名） | **Hosted App**（→ `hosted-apps.md`，不走 SKILL.md Phase 2–4）；若還有登入後的後台 → 混合 |
| 全部功能都命中「Hosted」（自選框架整套做） | **Hosted App** |

遷入情景（輸入：§2.0 的 stack 形狀×面向）：對照表在 `migration-workflow.md` §2.1。

拿不準 Custom vs Hosted → 把 `hosted-apps.md` §1 的差異表給用戶選。

## 4. 四象限落點

| | 內部成員用 | 外部使用者用 |
|---|---|---|
| **Custom App** | `starter-internal`（access_mode=`internal`，沿用平台角色權限） | `starter-external`（access_mode=`external`，custom-app-auth 自助註冊；可開匿名 `/pub`） |
| **Hosted App** | `visibility=internal`（平台 proxy 代處理登入，僅租戶成員） | `visibility=public`（預設；app 自理或不設認證） |

## 5. 混合方案的分工原則

Custom 不夠就**搭** Hosted，不是整個換線：

- 在平台內用、要吃租戶資料、要沿用平台角色與簽核 → **Custom App**
- 公開站、常駐進程／WebSocket、自選框架 → **Hosted App**
- 兩邊共用的資料一律落**平台側**（預設表引用＋自建表），Hosted App 走 Open Proxy 讀寫
  （`hosted-apps.md` §5、§7.1）；**不因共用而硬併成一個 app**，
  也**不得**把 DB 立成 Hosted App 給對方打（SKILL.md 規則 32）
- 每個 app 各自過問題一：官網 `public` ＋ 後台 `internal` 是最常見的組合

## 6. 不可逆與硬前提（判斷前必讀）

- Custom App 的 `access_mode` 由模板決定、**建立後不可改**（dev-guide §26.1）——
  所以 **app 要等計畫確認後才建**（SKILL.md Phase 1 步驟 3 照 app 分配表建）
- **`internal` 不能開匿名存取**（回 400，`CONTEXT.md`）——「內部工具但想給訪客看一頁」
  要在此刻攤開：那一頁拆成 external app，或放棄匿名
- **「Hosted = 整套搬」指的是程式，不是資料**：不論哪條產品線，業務資料一律落 AI GO 的表
  （預設表引用＋自建）——遷入情景原 DB 退場，見 `hosted-apps.md` §7.1

## 7. 產出：app 分配表

每個 app 一列，寫進 Phase 1.5 計畫；用戶確認後照表建 app、進工作區登錄表：

```
| alias | 產品線（Custom / Hosted） | 模式（模板 slug / visibility） | 負責的功能群 | 拆分理由 |
```

- 預設情況就是一列：`| <alias> | Custom | starter-internal | 全部 | — |`
- 多列時每個 app 各自過問題一，不是複製同一個答案
- 多系統遷入時同步記入 `migration-workflow.md` §1 的全景表
