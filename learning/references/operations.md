# 操作與驗證

## 設定

所有路徑以實際技能安裝目錄為準；執行時 cwd 是學員工作區，不是技能目錄。
打包會附帶相依的 `scripts/pyproject.toml`、lock 與同源工具；用 `uv run --project <技能目錄>/scripts python ...`。

1. `scripts/aigo_auth.py status <工作區>` 查本機設定（不登入）。
2. 需要新工作區時：`scripts/aigo_auth.py setup-workspace <工作區>`；租戶網址填 `https://[tenant].ai-go.app`。
3. 工作區 `.aigo/config.json` 的 `email` 與 `.aigo/learning.json` 的 `student_email` 填同一學員 email。
   學員自己在工作區 `.aigo/.env` 設定憑證；AI 不代填、不讀出密碼、不印 token、不寫進 repo。
4. 在平台介面建立自己的 internal Custom App，手動選取專屬群組，再核對設定。
5. `scripts/aigo_auth.py app --root <工作區> add <別名> --id <App UUID>` 登錄；之後每次明確選別名。

工作區與進度不放技能內。不要把教師帳號或全機器預設身分當成學生授權。
登入前、寫入前核對有效租戶網址、工作區身分與 App id；環境變數覆寫與工作區不一致時先解決。

## 開發

工具模組可由 Python 匯入，模組本身不是課程授權。不要直接執行一鍵部署或一般版的 Phase 流程。

- `aigo_auth`：`get_token(workspace)`、`resolve_base_url(workspace)`、`resolve_app(workspace, alias)`、`get_app_info(...)`。
- `aigo_scaffold`：從已讀回的 VFS 建立完整本機專案；先讀函式簽名，不能憑教材猜參數。
- `aigo_sync`：讀本機完整檔案、比較 VFS；寫入前讀回版本，保護 SDK；遠端獨有 action 中止後討論，不自動刪除。
- `aigo_compile`：只在已授權平台開發時呼叫編譯；錯誤用來驗證假設，不自動無限重試。
- `aigo_typecheck.py <專案目錄>`：本機型別檢查。缺 Node、跳過或未完整執行不能算通過。
- `aigo_publish.publish_app(...)`：僅在發布範圍與授權已確認後，經預檢發布；保留預設閘門，
  不用 `skip_preflight` 或 `confirm_*` 繞過錯誤，不呼叫 `full_deploy()` 自動刪遠端內容。

每次平台寫入前使用 `scripts/learning_scope.py --workspace <工作區> --app <別名>` 做唯讀核對。
工作區 `.aigo/learning.json` 由課程提供的資料建立，格式如下；不是權限憑證或資料隔離機制：

```json
{
  "tenant_url": "https://course.ai-go.app",
  "student_email": "student@example.test",
  "role_id": "11111111-1111-4111-8111-111111111111",
  "apps": {"practice": "22222222-2222-4222-8222-222222222222"}
}
```

核對工具會檢查實際生效租戶、明確別名、App id、登入身分、internal 模式、雲端 id 與群組設定。
回讀不完整、群組不符、非本題 App 或 Hosted 都中止；不自動修改群組。
它只約束使用此流程的操作，不能攔住其他工具或平台介面的行為，平台權限仍須由內勤管理。

## 驗證與發布

Custom App：讀現況 → 完整同步 → 本機型別檢查 → 編譯及檢查 skipped_files → 安全的預覽驗證 →
已有發布授權才 publish → 讀回發布狀態與實際版本 → 正式網址操作驗證。
sync／compile 成功不能直接宣告已發布。讀到舊版 published 狀態也不能證明本次改動已上線。
需比較本次預期內容與發布內容或可觀察的新行為；取不到時標記未驗證。

寫入測試另列測試資料、預期副作用及清理步驟；未授權不可建立／刪除資料或觸發對外 action。
無法驗證的部分如實列出，功能驗收與學員理解分開記。需要未附帶的 API 或管理操作時請教師補充。
