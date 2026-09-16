# Eval：改完 skill 之後怎麼證明沒變差

**改 skill 要回答的問題是「agent 的行為有沒有變差」，不是「文件看起來有沒有比較好」。**
瘦身、搬家、加規則都可能在文件層面很漂亮、在行為層面變糟——只有跑過才知道。

官方（Anthropic skill authoring best practices）的建議是**先寫 eval 再寫文件**，
而且至少三個情境。本目錄就是那三個。

## 怎麼跑

```bash
python scripts/setup_eval.py --before main --after HEAD
```

它會建兩個工作區（`~/work/eval-before`、`~/work/eval-after`），各裝一個 git ref 的 skill，
並停用使用者層的 `~/.claude/skills/aigo-builder`——**同名兩份同時存在時哪一份生效不可靠**，
實測遇過 agent 一邊說照舊版走、一邊引用新版才有的規則。

憑證不由腳本處理：把可用的 `.aigo/.env` 放進兩個工作區（內容要相同），或各自跑
`aigo_auth.py setup` 自己填。

然後：

1. 每個工作區各開 **3 個新對話**（agent 有隨機性，一次看不出來），工作目錄選該工作區
2. 貼 `scenarios/<情境>.json` 的 `query`，**逐字一樣**
3. 照該檔 `answers` 回答；**agent 沒問的不要主動補**——它問不問正是要測的
4. 照 `expected_behavior` 逐條打勾
5. 收工：`python scripts/setup_eval.py --restore`

## 判讀

- **after ≥ before** → 可以合
- **after 變差** → 分辨兩種成因：
  - **沒去讀 reference**：指路寫得不夠明確（改 SKILL.md 的指向）
  - **讀了但沒照做**：規則本身不夠硬（把它變成閘門，或搬回主檔）

## 三個陷阱（都實際踩過）

| 陷阱 | 後果 | 怎麼避免 |
|---|---|---|
| 在 skill 的 dev repo 目錄下跑 | agent 讀得到未安裝的新版檔案，版本講不清 | 一律在 `eval-*` 工作區跑 |
| 使用者層還留著同名 skill | 兩版混用 | `setup_eval.py` 會自動停用 |
| 兩邊回答不一致 | 品質差異分不清是版本還是題目造成的 | 照 `answers` 逐字回答 |

開跑前先確認版本：問 agent「你現在載入的 aigo-builder 是哪個版本、SKILL.md 幾行」，
對得上再開**新的**對話跑正式的那一輪（問版本本身會污染那一輪）。

## 情境

| 檔案 | 測什麼 |
|---|---|
| `scenarios/new-app-planning.json` | 計畫閘門：四問、四張表、常駐結論、自建表對照、租戶盤點 |
| `scenarios/data-placement.json` | 資料雙軌分流：細節搬走後還會不會去讀 reference |
| `scenarios/deploy-discipline.json` | 部署閘門：typecheck、驗證範圍、egress preflight、不硬推 |

`baseline` 欄位記錄已跑過的結果，新的一輪拿它當對照。

## 已知的 baseline（2026-09-16，demo 租戶）

`new-app-planning`：

| 評分點 | 1.43.0（瘦身前） | 1.44.0（瘦身後） |
|---|---|---|
| 四問問齊 | ✅ | ✅ |
| 計畫確認前不建 app | ✅ | ✅ |
| 四張表（含常駐結論與自建表對照理由） | ✅ | ✅ |
| 租戶自建表盤點 | ⚠️ 報 81 張 | ✅ 報 142 張 |
| 規則 31（包 Server Action） | ✅ | ✅ |

實查確認該租戶真實筆數為 **142**——瘦身前少算 61 張，那會讓「避免重複建表」那道閘門失效。
