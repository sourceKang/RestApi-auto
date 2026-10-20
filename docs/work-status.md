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

### 2026-10-20 retro 計畫 PR-E：run_multi_node 不再依賴 tests.support（Claude Code）

- 分支 claude/pr-e-preflight-services，基準為 PR-D 合併後的預設分支。
- 純函式 neox_parallel_auth_profile_for_worker／validate_neox_parallel_settings／xdist_worker_count 移到
  config_loader/neox_parallel.py（tests/support/options.py 重新匯出）；preflight 核心（DutPreflightResult、
  run_*_preflight 與判讀函式）移到 services/preflight.py；tests/support/target_sync.py 以 git mv 移到 services/。
  tests/support/preflight.py 只留 pytest skip hook，並由本模組參照 run_startup_preflight，PR-A 的 guard 仍可替換。
- 搬移程式碼與原檔逐字相同（腳本比對）；KNOWN_VIOLATIONS 刪除 run_multi_node 的 2 筆。

### 2026-10-20 retro 計畫 PR-D：import 依賴方向測試（Claude Code）

- 分支 claude/pr-d-import-layers，基準為 PR-C 合併後的預設分支。
- 新增 tests/test_import_layers.py（offline、純 AST、不執行 import）：允許依賴表涵蓋 models、config_loader、utils、
  cases、clients、services、tests.support、tools、tests、conftest；計入 lazy import、略過 TYPE_CHECKING、禁止相對 import、
  新頂層套件須登記。既有 4 筆違規列入 KNOWN_VIOLATIONS（附移除條件），修好卻未刪除也會失敗。
- 順帶修正 tools/check_environment.py docstring 的無效跳脫（改 raw docstring，內容不變），消除 compile 與 AST 掃描的 SyntaxWarning。
- 驗證：5 passed（1.3 s，無警告）；暫存 worktree 實測「新增 clients→services lazy import」與「修好違規未刪 allowlist」皆會失敗。

## 下一步

標記：〔離線〕可直接做；〔需決定〕等使用者決策；〔需實機〕需使用者授權並指定 node。

retro 計畫（2026-10-20 核准，依序開 PR）：

- [R-F]〔離線〕utils/reporting.py 不再 lazy import tools：整合報表產生器移到 utils。完成後刪除 KNOWN_VIOLATIONS 中 reporting→tools 1 筆。
- [R-G]〔離線〕固定 sleep 檢查（先搬 wait_for_rest_tokens、合併冷卻延遲、假延遲改 Event）。
- [R-H]〔離線〕唯讀 tools/run_status.py，查完整回歸進度。
- [R-I]〔離線〕拆分 utils/reporting.py（渲染移出 utils），最後做。完成後刪除 KNOWN_VIOLATIONS 中 reporting→cases 1 筆。
- [R-T2]〔離線〕teardown 失敗訊息中 EMS 回應的 `password` 會進 Allure `statusDetails.message`
  （allure 直接取 `excinfo.exconly()`）；需在組例外訊息處遮罩。
- [R-SLP]〔需實機〕test_neox_config.py ACL 設定後固定等 2～3 秒（:814、:915）改輪詢後做 CLI baseline；
  inventory／provision 輪詢前固定 30／15 秒以 initial_delay=0 實測。
- [R-REG]〔需實機〕registid 遮罩於實機報表確認。

使用者決策（2026-10-20 已定：D6 skill 名稱 pr-description；D7 專案 settings.json／.gitattributes 這輪不做）：

- [D0]〔需決定〕PR #18（claude/record-pr10-history）與兩個殘留 worktree 的去留。
- [D1]〔需決定〕既有 reports/ 內 registid／password 明文是否清理。
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
