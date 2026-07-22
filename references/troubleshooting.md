# 錯誤速查

> 任何一步失敗、或收到非預期狀態碼時查這裡。**先查表再動手**——
> 下面多數症狀有明確成因，自行推測修法通常會改錯地方。

---

## 錯誤速查表

| 錯誤 | 解法 |
|------|------|
| 白屏 | 確認 `src/main.tsx` 正確掛載 React |
| 路由不動 | 使用 `HashRouter`，不可用 `BrowserRouter` |
| 頁面無法捲動 | Layout 需 `height: 100vh; overflow-y: auto` |
| CSS 不生效 | 確認 `main.tsx` 中 `import "./App.css"` |
| CSS 變數遺失 | `:root` 改為 `:host, :root` |
| `db.update()` 400 | 用 `{"data": {...}}` 包裝 payload |
| `db.ts` 500 | 確認 Data Reference 已建立並發布 |
| `hasPermission()` 全 false／`getRoles()` 空陣列 | 快照**只注入 Internal App**，External／匿名恆為空——不是 bug，UI 要有降級路徑；也別改用 `/api/v1/auth/me` 硬撈 → `custom-app-dev-guide.md` §6 |
| 角色改名後條件顯示失效 | 判斷寫死了角色名稱；改用 permission 標籤（`模組.動作`），`system.admin` 自動通過 |
| 回傳帶 `approval_status: "pending"` | 命中租戶簽核流程，**既非成功也非失敗**。記錄已寫入但未生效，**不可重試 insert**（會重複建單）→ `custom-app-dev-guide.md` §24 |
| Action 拋「需要簽核審批」 | `ctx.db.update/remove` 或 `ctx.erp.*` 的 pre-guard，操作**未執行**、payload 已暫存，核准後平台自動執行 → **不重試、不換路徑繞過**（§24） |
| 寫入「成功」但 SaaS 表資料沒變 | 十之八九是簽核攔截：先看回傳有無 `approval_status` / 例外訊息，不要往 Data Reference 權限或 500 方向誤診 |
| 401 | Token 過期，重新登入 |
| 409 Conflict | VFS 版本衝突，重新 GET 後重試 |
| 423 Locked | 有待審核的發布，等待或取消 |
| Action 超時 | 控制在 30 秒內 |
| pub/ API 403 | 確認 `allow_anonymous_access=true`；且**只有 `external` / `self_built` 能啟用匿名**，`internal` app 開不了 |
| **呼叫 action 回 403** | 依序查：① **有 publish 嗎**——sync 與 compile 都不會讓 action 上線，觸發看的是**發布快照**（最常見成因）② action 在 `actions/manifest.json` 裡嗎、`is_enabled` 是不是 false、名字與 `runAction()` 傳的字串是否完全一致 ③ 帳號缺 `builder.access`（403 是權限，401 才是 token 過期）④ 403 是否其實來自 action **內部**——看執行紀錄的 `error`，不要只看外層狀態碼 |
| Compile 產物驗證失敗 | 檢查 main.tsx 入口和 App.css import |
| CRUD 驗證失敗 | 確認自建表已建立且欄位實體名正確 |
| Action 驗證失敗 | 檢查 execute(ctx) 函式、依賴模組是否可用 |
| Publish 一致性失敗 | 重新 sync → compile → publish 完整循環 |
| 建表 403 | 帳號非 `system.admin`，改輸出建表規格引導用戶到資料中心 UI 自建 |
| 建表／加欄 409 | 撞配額或實體名撞名 → 配額數值見 `data-center.md` §4 |
| 刪表／刪欄被擋 | 兩段式刪除：先取 `/impact`，確認值必須是**實體名**不是顯示名 |
| webhook 端點 404 | manifest 缺 `"webhook": true`，或**改完沒 republish** |
| webhook 驗簽失敗 | 用了重新序列化的 body；必須用 `ctx.params["body"]` 原字串 |
| 同一事件處理兩次 | 第三方登記了新舊兩條 URL，或 action 沒做冪等 |
| 建排程 400 | 撞 tier 限制 → 數值見 `event-triggers.md` §2.4；或 app 還是草稿 |
| 排程建了不跑 | `nextcall` 計算中（正常，稍候）／app 未發布／已被自動暫停 |
| 排程突然停了 | 看 `paused_reason`：403×2、error×10、或降檔 tier 違規 |
| 排程 action 逾時 | 超過上限要切批次；**webhook 的上限比 cron 短**，見 `event-triggers.md` §1.6／§2.6 |

---

## 查不到怎麼辦

1. 對照 `references/data-center.md` §7 / `references/event-triggers.md` §3 的分項速查
2. 狀態碼語義：**403**＝權限（看是 `system.admin` 還是 `builder.access`）；
   **409**＝配額或衝突；**422**＝輸入不合法（欄位／型別／查詢契約）；
   **400**＝業務規則拒絕（tier 超限、草稿 app 建排程、暫停排程 run-now）
3. 仍無解 → 回報用戶，附上完整請求與回應，**不要反覆重試**
