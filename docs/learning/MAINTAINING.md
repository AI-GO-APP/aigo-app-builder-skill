# aigo-learning 維護與交付

## 來源與產物

一般版入口、VERSION 與既有工具保持原行為。learning/ 是學生版來源，不是可直接安裝的成品。
兩個入口不互相載入；共用技術內容在打包時複製，學生端不需要原始 repo 或完整 Builder。
本版教學實作範圍是 internal Custom App；進階需求可規劃，但須教師補齊核對資料後實作。

```powershell
python scripts/build_skill_packages.py --variant both --output <全新的輸出資料夾>
python <輸出資料夾>/aigo-learning/scripts/check_update.py
python -m unittest discover -s tests -p 'test_learning*.py' -v
```

輸出兩個資料夾、兩個 zip 與 RECEIPTS.json；zip 可重現，輸出已存在就拒絕覆蓋。
一般版依 git 已追蹤檔案打包，排除學生來源、學生測試與新打包工具；一般版入口與工具逐位元保留。
學生版採工具明確清單及指定技術章節，檢查 import 相依閉包、文件連結與來源 lock。
學生版含 PACKAGE.json（版本、同源資料雜湊、摘錄清單、檔案雜湊）；完整性檢查不是數位簽章，
交付端仍須用可信來源取得 zip 並比對 RECEIPTS.json 的 SHA-256。

## 安裝與並存

只交付 aigo-learning.zip 給學員，解壓成目標客戶端技能目錄下的 aigo-learning/。
不要 clone 整個 repo 給學員，不要交付原始 learning/，不要執行會遞迴安裝所有技能的指令。
教師可保留一般版在另一工作區；學生的有效技能清單只啟用 learning。
各客戶端如何停用全域技能不同，安裝驗證必須實查清單；資料夾名稱與 skill 自稱不是證據。
不要擅自改使用者全域設定。若機器仍有一般版，需依客戶端設定停用學生環境的那份或分開環境。
模式切換用新對話，不在既有學生對話載入完整一般版。設定並存不等於權限隔離。

學員作業與工作區在技能目錄外。教師提供租戶、學員 email、專屬角色 id 與 App 對照；
學生自己選取群組。learning_scope 是唯讀檢查，不能替代伺服器權限，不能防止其他工具繞開。
它可能進行登入／刷新及寫入本機 token 快取，但不修改平台 App、群組或業務資料。
尚未在指定租戶實打前，不宣稱 runtime/存取隔離驗收完成。

## 學生閱讀材料與 PDF 輸出（0.1.1）

學生閱讀材料統一為「AI GO 學員開始手冊」PDF，合併安裝、設定、練習、教材輸出與三頁學習計畫。
可編輯來源是 docs/learning/student-handbook.json；租戶、email 與群組的實際值須由內勤提供，不猜測填入。
技能程式仍由課程平台提供學生 ZIP；PDF 是閱讀材料，不是可執行安裝包。

```powershell
python learning/scripts/learning_pdf.py docs/learning/student-handbook.json --output <工作區>/output/pdf/AI_GO_學員開始手冊_v0.1.1.pdf --expected-pages 6 --render-dir <新的暫存目錄>
```

PDF 選用相依在 learning/scripts/requirements-pdf.txt，不改根 scripts/pyproject.toml 或一般版更新器。
學生套件含產生器、相依清單與輸出指引。教材存 output/pdf/，來源存 output/source/，不放技能目錄。
需使用相容繁體字型，產生後核對頁數、文字及逐頁圖片；工具不會把渲染成功誤報為人工視覺驗收。

## 更新

一般版 VERSION 與強制更新器不改；學生版有獨立 learning/VERSION，自己的 check_update 只做離線完整性檢查。
上游工具、版本或指南內容一變，學生版打包會失敗。先查差異，確認摘錄語意、引用、工具契約與課程適用性，
更新必要內容、重跑測試後，才更新來源 lock：

```powershell
python scripts/build_skill_packages.py --review-sources --review-note '<實際複核內容與理由>'
```

lock 只記錄維護者聲明與雜湊，不能取代人工複核或測試。不可把 refresh-lock 當成每次 CI 的自動步驟。
教學／技術變更需調整 learning/VERSION，重新打包、驗證、交付整份學生套件。
不把進度寫進套件，不下載 Builder main 覆蓋學生端，也不沿用 ~/.aigo/update_check.json 的更新註冊。
重大相容性修正優先複核發版；未核對的新功能保留未知，不宣稱不存在，暫停受影響的寫入即可。

## 測試層次

1. 單元／打包：來源漂移、缺相依、斷鏈、可重現 zip、完整性、錯租戶／App／角色／身分中止。
2. 行為：evals/learning/scenarios.json 的真實學員題目，以乾淨上下文、安裝產物與必要 fixture 測。
   評估代理只拿題目、技能與原始資料，評分規準由審核者保留，不提示答案。
3. 安裝／租戶：各目標客戶端實查技能清單，再以課程核准帳號與虛構資料做功能驗收；另記錄，不以離線測試代替。

新入口完成的行為評測不能證明一般版模型輸出完全一致；一般版檔案位元比較證明程式與指令未改。
同機仍有一般版可發現時需要額外並存評測，不能用「技能名稱不同」直接視為解決。
