# 共用工作進度

更新日期：2026-10-20（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Claude Code（2026-09-22 起）；先前由 Codex 建立共用協作入口。
- 分支：每個任務從 codex/prepare-github-upload（GitHub 預設分支）切出 `claude/<topic>` 或
  `codex/<topic>`。合併前先在 scratch worktree 做 `git merge --no-commit --no-ff` dry run，
  零衝突才開 PR，由使用者審閱後合併。
- 共用 skill 以 .codex/skills/<name>/SKILL.md 為來源（qa-bug-report、ems-version-regression），
  Claude 側 .claude/skills/<name>/SKILL.md 只轉介，未複製業務規則。
- 未新增全域權限設定、MCP 憑證或設備操作自動化。
- Repo 公開性：專案負責人已明確決定維持 Public（帳密皆為 per-person 環境變數），不需要轉 Private。

## 最近一次工作

較早的紀錄見 docs/work-history/（依月份）。

### 2026-10-20 本機報表保留原值、EMS_REPORT_REDACT 開關（Claude Code）

- 分支 claude/report-redact-switch，基準為 R-T2 合併後的預設分支。使用者決定：Allure 附件與測試報表要保留原始資料
  （密碼、session id、token、devKey）以便回查。
- utils/redaction.py 新增 `report_value`／`report_text`／`report_mask_values`：預設回傳原值，`EMS_REPORT_REDACT=1`
  （或 pytest `--redact-reports`，在 pytest_configure 設定環境變數，xdist worker 與子程序同樣生效）時遮罩。
  `redact`／`redact_text`／`mask_values` 維持一律遮罩，供對外內容使用。報表路徑 14 處改用 report_*。
- AGENTS.md、engineering-guidelines、report-format、project-context、ems-version-regression 規則改為「本機報表保留原值、
  分享前以開關重產；PR、Redmine、TestLink notes、提交的檔案一律遮罩」。txt 報表（TestLink 回填來源）不含回應本體或帳密。

### 2026-10-20 R-T2：失敗訊息遮罩（Claude Code）

- 分支 claude/r-t2-mask-failure-messages，基準為 PR-I 合併後的預設分支。
- 原因：Allure 的 statusDetails.message 直接取例外字串（test 用 `excinfo.exconly()`、fixture teardown 與 step 用
  例外物件），不經 reporting_hooks 的 longrepr 遮罩；19 處 assert／`pytest.fail` 訊息嵌入原始回應
  （rest_polling 3、test_neox_config 9、test_neox_profile 7），teardown 還原 ONT baseline 時 password 因此進入報表。
- 新增 `utils.diagnostics.masked_response_body()`（JSON 經 redact、文字經 redact_text，內容不截斷），19 處訊息改用它；
  比對 token 用的原始字串不變。services/invalid_params 那處原本已經 format_value_summary 遮罩，不需修改。
- 新增 tests/test_no_raw_response_in_messages.py：AST 檢查 assert／raise／pytest.fail 訊息不得含未遮罩的
  `<response>.text`、`json.dumps(<x>.json)`、`body`／`response_text`；另含 helper 與 rest_polling 逾時訊息的行為測試。
- 驗證：反例（service 內加 `{response.text}`）被擋；舊基準上行為測試失敗（密碼出現在訊息中），新版通過。

## 下一步

標記：〔離線〕可直接做；〔需決定〕等使用者決策；〔需實機〕需使用者授權並指定 node。

retro 計畫（2026-10-20 核准）的離線 PR A～I 已全部完成；剩下的是待實機與待決策項目：

- [R-SLP]〔需實機〕test_neox_config.py ACL 設定後固定等 2～3 秒（:814、:915）改輪詢後做 CLI baseline；
  inventory／provision 輪詢前固定 30／15 秒以 initial_delay=0 實測。完成後刪除 tests/test_no_fixed_sleep.py 對應的 KNOWN_SLEEPS 條目。
- [R-REG]〔需實機〕下次回歸以 `--redact-reports` 跑一次，確認 registid、CLI registration-id 與 teardown statusDetails 都會遮罩；預設跑法則確認原值保留。

使用者決策（2026-10-20 已定：D6 skill 名稱 pr-description；D7 專案 settings.json／.gitattributes 這輪不做）：

- [D0]〔需決定〕PR #18（claude/record-pr10-history）與兩個殘留 worktree 的去留。
- [D1]〔需決定〕（2026-10-20 使用者已定：本機報表保留原值）既有 reports/ 不需清理明文；此項可關閉。
- [D3]〔需決定〕reports/ 約 153 萬檔，是否以 tools/archive_reports.py 歸檔 b1–b9。
- [D4]〔需決定〕曾貼入對話或整檔讀出的測試帳密是否輪替。
- [D5]〔需決定〕Codex 之後是否仍在本 repo 使用（影響 skill 原檔位置）。

既有事項：

- [B13]〔需決定〕b13_redhat：既有報表明文清理（同 D1）；RAD external 11:40～15:59 恢復原因；
  formal_runs.yaml 正式執行；TestLink build／回填；configs/ems.yaml b13 版本是否已提交需核對。
- [TD]〔需決定〕teardown 失敗（cleanup 未收斂）是否反映到 txt／TestLink 結果。
- [EMS100]〔需實機〕.100 連線中斷判定為 server 資源不足（ADR 0002）；下次完整測試確認
  `EMS Connection Errors` 行與重送恢復，仍頻繁再以報表時間點查 .100 log。
- [SOP]〔需決定〕docs/sop/ 的 SOP docx（9/22 版）未納入版控；要給同事用需先改寫為 Markdown 並更新
  EMS server 切換與 qa-integration-agent 回填流程（repo 為 Public）。docs/qa_bug_drafts/ 維持不進版控。
- [SFU]〔需實機〕ONT SFU 間歇 `Wait`／teardown HTTP 500：測試期間以 CLI 記錄 ONT 狀態，確認
  provision template 套用／還原是否觸發 ONT 重新註冊。
- [NNI]〔需決定〕NNI POST 移除 payload 未帶欄位、回 Fail 仍部分套用：待確認規格後決定是否用 /qa-bug-report。
- [FW]〔需實機〕NODE5／NODE7／NODE8 test_targets.local.yaml fw_version 仍帶後綴，需 CLI 確認後更新。
- [CI]〔離線〕推送到預設分支曾出現兩個 push run、其一被 concurrency 取消；原因未確認，持續發生再查。
- [DEP]〔離線〕依賴手動升級：改 requirements.txt 後確認 CI 與本機離線檢查通過。

## 後續更新方式

- 每個工作條目記錄：日期、負責工具、任務、分支／基準、修改範圍、驗證指令與結果、未執行原因、下一步。
- 只在任務完成或交接時更新一次，不逐步記帳。PR 編號、merge commit、CI run id 不寫入本檔，
  以 GitHub 與 git log 為準。
- 本檔只保留最近 1～2 筆工作條目，較舊的原文移到 docs/work-history/<YYYY-MM>.md，全檔維持在 120 行以內。
- 已解決的事項移除或精簡；尚未完成或缺證據的事項保留，並標上 ID 與類型。
