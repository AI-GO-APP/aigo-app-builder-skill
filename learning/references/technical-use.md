# 技術使用方式

本版重點是 internal Custom App 的基礎練習。實際開發前先確認需求：誰用、做什麼、資料在哪、如何驗收。
公開網站、SEO、自有後端框架或長連線等需求需評估 Hosted；不可為了配合教材硬塞 Custom。
Hosted 的發布依專案既有流程與教師核對資料，不走 Custom VFS 編譯。

## 摘錄索引

打包後提供以下同源摘錄，每份保留原本章節編號；按需讀取：

| 檔案 | 用途 |
|---|---|
| `technical/vfs.md` | VFS 樹、同步、編譯、SDK 保護與 Shadow DOM |
| `technical/actions.md` | Python `execute(ctx)`、權限與限制 |
| `technical/data-placement.md` | 預設表／自建表、custom_data、延伸欄位的選擇 |
| `technical/data-references.md` | 用引用面查表與欄位、正確資料引用 |
| `technical/frontend-states.md` | 載入、有資料、空資料、錯誤與送出中 |

摘錄包含的歷史測試數字只代表該次環境；當前限制要核對實際平台資訊。
文中的「教師補充」代表本套件沒有附帶該進階資料；不要猜測內容，也不要回頭找完整 Builder 流程。
技術定義不隨教學模式改變，不能因為學生版本就改寫 API 語意或省略授權要求。

## 必須沿用的技術原則

- 先查平台是否有同語意預設表、現有自建表與實際欄位，讀不到不等於不存在；資料模型不憑記憶猜。
- 預設表不改結構；新增自建表需有規格與權限，屬租戶資源；不任意重建、清空或刪表。
- 新自建表以英文實體名設計，引用登記完成後再讓 App 讀寫。不引用資料中心目錄表。
- internal App 不以直接呼叫前端自建表 SDK、提高一般人的 builder 權限解決資料存取；
  由 Server Action 按 `ctx.user_id`／`ctx.user_permissions` 與已確認需求授權，前端隱藏不算授權。
- 持久業務資料落平台表或 Storage，不用 action 本機檔案、程序記憶體或 localStorage 當業務資料庫。
- API、欄位或存取方式超出摘錄時，先請教師提供經核對的必要資料；可以繼續不依賴該能力的練習。
