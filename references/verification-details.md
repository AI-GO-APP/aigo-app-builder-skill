# 驗證項目細節與里程碑驗證

> 要**實際執行**驗證時讀這份。只是想知道「這次變更該跑哪幾項」，看 SKILL.md Phase 4.2 的表就夠。

---

## 1. 四個驗證項目的完整定義

使用 `scripts/aigo_runtime_verify.py` 執行。

**⓪ 語意檢查**（★ 前端有實質修改時必跑；在 ① 之前）
```
uv run --project scripts python scripts/aigo_typecheck.py <專案目錄>
  ✓ 沒有會炸 runtime 的語意錯誤（TS2448 宣告前使用／TS2304 找不到名稱／重複宣告…）
  ℹ 缺 @types 的噪音只列不擋；無 Node 時略過並告知用戶
```
esbuild compile 不驗型別，這些錯誤只會在發布後以白畫面浮現（`troubleshooting.md`）。

**① Compile 產物驗證**（★ 每次必跑）
```
verify_compile_output(compile_result)
  ✓ compile_success == true      ← 只代表轉譯成功，語意正確與否看 ⓪
  ✓ html 含 <!DOCTYPE> 和 id="root"
  ✓ bundle_js 含 React（> 500 bytes）
  ✓ css 非空（> 50 bytes）
```

**② Publish 一致性驗證**（元件新增 / 路由變更 / 發布後必跑）
```
verify_publish_consistency(base_url, token, app_id)
  ✓ status == "published"
  ✓ published_at 已更新
  ✓ published_vfs 與 vfs_state 檔案路徑一致
  ✓ published_vfs 與 vfs_state 內容一致
```

**③ 自建表記錄 CRUD 驗證**（使用了 api.ts / db.ts 時必跑）
```
verify_custom_data_crud(base_url, token, table_key)   # table_key = 實體名
  ✓ CREATE → 201 + 回傳 id
  ✓ GET 確認寫入（二次驗證）
  ✓ DELETE → 204
  ✓ GET 確認刪除（二次驗證）
```

**④ Server Action 呼叫驗證**（actions/*.py 變更時必跑）
```
verify_server_action(base_url, token, app_id, action_name, params)
  ✓ HTTP 200
  ✓ execution_id 非空
  ✓ status == "success"
  ✓ result 非 null
  ✓ 無 error
  ✓ 執行時間 < 30 秒
```

---

## 2. Phase 5：里程碑完整驗證

> Phase 4 的驗證閘門在每次迭代中自動執行。
> Phase 5 是在**開發里程碑完成**（例如功能全部完成、準備交付）時執行的完整驗證。

### 完整驗證 = Phase 4 所有項目 + 以下補充

5. **全功能 Runtime 驗證**
   ```python
   from aigo_runtime_verify import run_full_runtime_verification, format_verification_report
   results = run_full_runtime_verification(
       base_url, token, app_id, slug,
       table_key="...",         # 自建表實體名（physical_name）
       action_name="..."        # 任一 Server Action 名稱
   )
   print(format_verification_report(results))
   ```
6. **External Auth**（可選）— 註冊 → 登入 → 取得用戶 → 登出
7. **匿名存取驗證**（可選）— 確認 allow_anonymous_access 已啟用 → /pub/ API 讀取 → 確認寫入被拒

可使用 `scripts/aigo_e2e.py` 和 `scripts/aigo_runtime_verify.py`。
