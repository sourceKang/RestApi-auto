# 報表輸出格式

本文件由 [AGENTS.md](../AGENTS.md) 指向；彙整測試結果、QA summary 或任務總結頁時使用。
GitHub PR 描述不是報表，改依 [pr-description skill](../.codex/skills/pr-description/SKILL.md)。

## 測試／QA 報表

彙整測試、照片或 Redmine/TestLink 比對、QA summary 時，預設產出瀏覽器可開啟的 HTML report，放在 `reports/`，檔名包含日期、EMS version 與 node；Markdown 僅作草稿。

- 首屏先給結論，再呈現環境、pytest、TestLink/txt、失敗清單、逐項比對與「已解／未解／部分／需確認」狀態。
- 有 Allure raw results 時解析重點。每個 testcase 至少可查到 nodeid、TestLink case ID、title、status、duration、request、EMS response、CLI 驗證、failure/traceback/contract diff 與附件摘要。
- 大型 request/response、CLI output、traceback 另存檔案；報表只放摘要與連結。
- 保留原始 txt、HTML、Allure raw、log 的回查連結。本機報表預設保留原始資料（含密碼、session id、token、devKey）以便回查；
  要給他人或放到外部時，先以 `EMS_REPORT_REDACT=1` 重產或只提供已遮罩的摘要。
- txt／TestLink 結果有四種：Pass、Fail、Skip（回填略過）與 Blocked（TestLink `b`）。Blocked 表示本體通過，
  但 strict cleanup（`cleanup_registry.add_strict_final`，還原設備 baseline）失敗；本體已失敗時維持 Fail。
  所有 teardown 錯誤都列在檔頭 `Teardown Errors`／`Teardown Error #n`（strict cleanup 或 other teardown），
  other teardown（例如 session 登出斷線）只列明細、不改結果。同一 case ID 合併順序為 Fail > Blocked > Skip > Pass。
  檔頭明細不會帶入 TestLink notes，需要時另行補充。
- ONT baseline 還原（EMS1-7130／7133／7223）超過 12 次 REST 輪詢時，檔頭加 `ONT Baseline Restore (...)：SLOW ...`，
  只標記不改結果；輪詢窗 600 秒乘 wait_scale 用完才判失敗。

## 任務總結頁

只在修改 3 個以上檔案、測試有失敗或使用者要求時產生：存 `reports/summary/YYYYMMDD-HHMM-<任務名>.html`，單檔、手機好讀，依序列結論、目標 Checklist（✅／⚠️／❌／⏭️＋證據或原因）、修改檔案、測試結果、風險、下一步。
