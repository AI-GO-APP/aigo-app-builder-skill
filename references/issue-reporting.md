# 平台問題回報

把「平台自身」的問題直接回報給 AI GO 開發團隊——在 AI IDE 內執行，
不開任何 UI、不經 AI GO 平台（回報系統獨立部署，平台掛掉時照樣可報）。
回報會成為開發團隊 Scrum Board 上的一張卡，團隊的處理進度與回覆可隨時查。

## 什麼時候回報

**要回報**（平台側的問題）：

- 實測行為與 `references/` 文件明顯不符
- `troubleshooting.md` 查無此症、或照表處理後仍然卡死
- 平台缺陷把開發流程整個擋住（部署/編譯/驗證壞掉、端點 5xx、資料異常）
- 配額、權限、速率限制的行為與宣告不一致

**不要回報**：App 自己的 bug、troubleshooting 已有解的症狀、
還沒讀完錯誤訊息就想丟出去的問題。

## 怎麼寫（★ BDD：描述行為，不是開藥方）

開發團隊需要的是**可重現的行為事實**。寫：

1. **預期行為**——依文件/常理，這一步應該發生什麼
2. **實際結果**——實際發生什麼：完整狀態碼與錯誤訊息的關鍵段落，原文照貼
3. **重現步驟**——從哪個狀態、做了什麼、打了哪個端點（可含 payload 形狀）
4. **環境／補充**——租戶、app_id、發生時間、request_id（有就給）

**不要寫**：技術建議、猜測的 root cause、指定的修法或實作方式
（「建議把 X 改成 Y」「應該是 Z 沒做好」）。行為描述才可驗證；
解法判斷是開發團隊拿著完整脈絡做的事。

範例——

```
✅ 好：
  標題：compile 對含中文檔名的 VFS 回 422
  預期：文件未限制檔名字元，compile 應成功或明說限制
  實際：POST /builder/apps/{id}/compile 回 422 {"detail":"invalid path"}（全文照貼）
  步驟：VFS 內建立 src/元件.tsx → sync 成功 → compile 必現
  環境：urfit 租戶，app 1a2b3c…，2026-09-01 14:00 前後多次

❌ 壞：
  標題：compile 有 bug，建議改用 NFC 正規化處理檔名
  （直接開藥方、無預期/實際、無重現步驟）
```

## 指令

```bash
# 提交（建議用結構化參數，會自動組成 BDD 格式）
uv run python scripts/report_issue.py submit "一句話標題" \
  --expected "預期行為" --actual "實際結果（含錯誤原文）" \
  --steps "重現步驟" --context "租戶/app_id/時間"

# 內文較長時寫進檔案
uv run python scripts/report_issue.py submit "標題" --body-file report.md

# 追蹤：清單（含狀態）／單筆詳情（含官方回覆）
uv run python scripts/report_issue.py list
uv run python scripts/report_issue.py show <ticket_id>
```

狀態值域：`To be decided` →（團隊排程）→ `Backlog` / `In progress` /
`To Review` / `To Verify` / `Done`。官方回覆會出現在 `show` 的時間軸裡，
標為「★ 官方回覆」。

## 機制與隱私

- 憑證**重用 builder 既有的 `~/.aigo/.env`**，零額外設定。回報帳號與密碼
  在本地由 AIGO_EMAIL＋AIGO_PASSWORD＋租戶 slug 以 sha256 衍生——
  **AI GO 密碼不離開本機**，也不與回報系統共用。
- AI GO 密碼變更後會自動換用新的回報帳號：回報功能不中斷，
  但舊帳號的回報清單自此看不到（開發團隊側不受影響）。
- 回報內容（含你貼的錯誤訊息）會進入開發團隊的 Notion 看板，
  回報者信箱（AIGO_EMAIL）與租戶 slug 會顯示在卡片上。**不要貼機密**
  （金鑰、個資、客戶資料）——錯誤訊息含敏感值時先遮蔽。
- 認證端點有每 IP 每分鐘 30 次的速率限制，腳本會自動退避重試。
- 回報系統網址可用環境變數 `URFIT_TICKET_API` 覆寫（預設為官方部署）。
