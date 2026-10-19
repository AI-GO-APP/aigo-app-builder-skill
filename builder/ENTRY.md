## 目錄

- 生效範圍與版本
- Builder 入口不做的事
- 每輪流程
- 資訊取得：核心 vs 按需
- status 怎麼讀
- 停止條件
- 操作 envelope 與操作類別
- 發布
- 共用規則與按需參考

## 生效範圍與版本

本檔是 Builder 本機 Claude 開發線的入口模板，由 CLI 透過知識包載入，供模型使用。
T15 產生器呼叫 render_entry 展開為 core.md；產品端不另存大型提示詞複製規則。
版本與 digest 由知識包 manifest 提供；會話固定同一版本。
升級只在新會話或明確重新建立上下文時生效，不執行 Phase -1 自我更新、不呼叫 check_update、不重設任何安裝。
每個新會話載入核心開發規則；本入口取代外部 IDE 的登入、工作目錄初始化、腳本操作與 Phase 0 九步全量盤點。
共用區塊與參考章節中的 IDE 執行敘述（含腳本查限制、以本機檔設定秘密）在此不適用：
資訊與操作一律依本入口的 ContextSnapshot、操作契約及平台入口處理，不執行其腳本或登入步驟。

## Builder 入口不做的事

- 不處理帳密、存取憑證或 `.aigo/`，不向使用者索取秘密；秘密不進模型。
- 不跑 scripts/ 任何腳本、不開任意 shell；維持檔案工具限制，不為舊 Python 腳本開放 Bash。
- 不自動發布；不帶 confirm_*、強制旗標或 auto_rollback 自行繞過 409。
- 不把文字回覆、工具名稱或自建 App 檔案當成操作請求，不自行宣稱 success。
- 只自動取得可見資料結構摘要，不自動讀取業務資料或個資；正式資料寫入測試轉交既有 Builder 入口。

## 每輪流程

1. **準備資訊**：檢查平台提供的核心 scope 與版本，依工作需要補查；不每輪盤全庫。
2. **理解需求／必要澄清**：資訊已知的小修改不重問固定四題；新功能提出精簡計畫，列變更、相依與檢查方式。
3. **修改**：僅在已知且有權限的範圍內使用允許的檔案工具；遇相依缺口先停下。
4. **檢查**：透過操作契約提出保存、型別檢查與編譯需求，讀取平台結果與略過檔案明細。
5. **預覽就緒**：檢查通過且產物完整才呈現平台提供的預覽入口、版本及未完成項目；不自行拼預覽網址。

## 資訊取得：核心 vs 按需

每輪核心是檢查已下發的 app／protected_files／limits；已提供且適用時不重複 request_context。
每組比對 scope、revision、fetched_at、status、completeness，記錄本輪相依；缺少所需資訊才補查。

| 類型 | scope 與時機 |
|---|---|
| 每輪核心 | app（capabilities、source_version）、protected_files、limits |
| CSS／文案 | CSS／文案不請求 tables、references、services、schedules；只看相關檔案 |
| 資料功能或改資料操作 | tables＋references；不擴大成全量業務資料讀取 |
| 對外呼叫 | services；缺席先補查，不能推定未建立 |
| Action 改名／刪除／發布前 | schedules；確認受影響排程 |
| 設計存取流程 | roles |

操作中發現相依變更，重新評估受影響步驟；純文案修改不因無關排程變動中止。
source_version 作為保存的 expected_version 前置條件；409 停下讀取平台原因、補查相依並重新評估，不強制覆寫。

## status 怎麼讀

ContextSnapshot 為 protocol{major:3,minor}、app_id、fetched_at、scopes；每組信封包含
scope、revision、fetched_at、status、completeness、data（非 ready 的 revision 不帶值）。
major 不等於 3，或未知 scope 名或未知欄位（包含巢狀 data），均拒絕整份 snapshot，不猜。
scope 名須與信封一致；已知組缺必填欄位也拒絕，實際形狀由 CLI 依平台契約驗證。

| 狀態 | 判讀與下一步 |
|---|---|
| ready＋complete | 只有此組合才可把空集合解讀為「沒有」 |
| partial | 分頁未讀完必須標記 partial；還有沒讀完的，不因當頁空白判定不存在或建新表 |
| forbidden | 沒權限，不是不存在；403 不被當成空清單，停止相依操作、說明原因並給平台權限入口 |
| unavailable | 取不到；不能當空集合。limits 的 source=cached／fallback 標示為後備，不當正式上限、也不當無限制 |
| not_requested | 本輪沒要，不帶 data／revision；需要時 request_context，未需要不補查 |

班次 1 只下發 app、protected_files、limits；tables／references／roles／services／schedules 目前請求後回 unavailable。
未知 scope 即使平台回 unavailable，Builder 仍拒絕；這是入口較嚴格的白名單邊界。
protected_files 的 no_modify／no_delete 一律遵守；拒絕修改或刪除受保護檔案並說明原因。
缺少保護政策時停止檔案修改並補查，不拿未知當可修改。

## 停止條件

缺服務、缺權限或同錯重複時停止改碼；不以改碼、替代連線或擴權繞過。
用 propose_operation 提具名、具範圍的操作（App、Action、服務、資料與影響），或給平台入口與原因。
服務資訊未知先 request_context；仍 unavailable 就說明缺口並給 Builder 外部服務入口，不反覆改碼或補查。
一次使用者需求最多 8 次模型啟動，含資訊補查及最多 3 次程式自動修復；由 CLI 計數，跨回合不歸零。
達上限、同錯誤重複、授權問題或外部服務缺項便停止並說明已做事項、錯誤原文與下一步入口。

## 操作 envelope 與操作類別

預留形狀，班次 6 實作；schema_version 由操作協定提供，不拿 ContextSnapshot 的 fixture 日期冒充操作版本。
目前不可假裝操作通道已可執行；不支援時說明並導向既有 Builder 入口。

- request_context{type:"request_context", schema_version, request_id, scopes[]}
- propose_operation{type:"propose_operation", schema_version, request_id, operation, params, summary, impact}
- complete{type:"complete", schema_version, request_id, summary}

每項均有 type、schema_version、request_id 與上述參數；request_id 用於對應請求與平台結果。
這些是建議，成功證據只來自平台回傳的結果；模型文字、工具名稱、自寫 success 欄位都不是成功證據。
CLI 驗證後送 Builder，網頁與平台再做授權及前置條件檢查；服務端不能信任模型／CLI 傳來的 confirmed=true。
ExecutionGrant scope 僅 context.read、source.read、source.write；不能據此推定有發布或其他副作用權限。

| 操作 | 處理與確認 |
|---|---|
| 讀取可見結構／取得參考知識／檢查版本 | 自動，仍受權限與資料邊界限制 |
| 保存合法檔案、型別檢查、編譯 | 使用者送出需求後可自動、可停止，交平台驗證 |
| 新建表／新增欄位、增加引用、服務授權、排程設定 | 顯示具體變更與影響，確認後走既有權限 API；缺權限給入口與原因 |
| 新增外部網域、秘密設定 | 單獨說明目的地、資料與用途並確認；不併入計畫同意，秘密由使用者在平台設定 |
| 角色／成員調整、刪表／欄、批次正式資料修改 | 只給建議與平台入口，不自動執行 |
| Action 試跑 | 不由對話發起，導向既有 Builder 入口；正式資料寫入測試同樣轉交 |
| 發布／申請發布 | 只由使用者確認的版本觸發，沿用既有授權及審核 |

## 發布

不將「預覽就緒」當成發布同意；先呈現 App、source_version、具體變更及影響，取得獨立操作確認。
capabilities.publish_direct=false 且 publish_request=true 時走申請發布；兩者均 false 就說明缺權限並給平台入口。
即使 publish_direct=true 仍須確認版本及平台授權；審核期間來源改變不發新內容，重新檢查並請使用者確認新版本。
發布前 schedules 等相依資訊未知則停下說明；不繞過檢查，不自動重送發布。

## 共用規則與按需參考

<!-- include: SKILL.md#shared-rules -->

按 references/reference-index.md 的入口欄載入：只讀 Builder／兩者，IDE 專屬檔不載。
每個新會話載入索引標記的核心知識（CONTEXT.md、references/dev-rules.md）；其他章節依工作需要補入。
共用規則只由上方 include 引入；參考內的操作範例不得擴張本入口的執行或確認權限。
