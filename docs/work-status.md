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

### 2026-10-21 TD：strict cleanup 失敗記 Blocked、D3 重複報表清理（Claude Code）

- 分支 claude/td-teardown-blocked，基準為 #31 合併後的預設分支。使用者決定：strict cleanup 失敗且本體通過 → Blocked
  （TestLink b）；本體已失敗維持 Fail；非 strict teardown 錯誤只列明細。SFU 還原移進本體、失敗記 Fail 另做（PR-2）。
- utils/cleanup.py 新增 StrictCleanupError；reporting_hooks 在 teardown 標記 strict 並記錄訊息（user_properties，xdist 適用）；
  utils/reporting 新增 blocked 與 teardown_errors；txt 檔頭 `Teardown Errors`／`Teardown Error #n`，有 Blocked 時
  Summary 為 `X Pass / Y Fail / Z Blocked`；HTML、integrated、報表索引認得 Blocked。
- corp 只產生 preview（不寫入）：`Result Blocked` → b、`Result Error` → f；新檔頭與 Summary 解析無 warning；
  檔頭明細不會進 TestLink notes。TestLink EMS1-7223 步驟 6 明列「cleanup 成功」，EMS1-7130 步驟不含還原。
- 離線 `pytest -m offline`：通過 174／失敗 0（新增 tests/test_teardown_blocked.py）。
- D3：刪除 reports/multi_node 中 91 個與 build 歸檔逐檔 SHA-256 相同的 allure-current 子目錄與 3 個 dry-run 目錄
  （504,616 檔）；DIFFERENT 3、NO_ARCHIVE 6 保留；reports/ 剩 1,026,561 檔。清單：reports/summary/20261020-d3-multi-node-allure-duplicates.csv。

### 2026-10-20 R-SLP（ACL 輪詢）與 R-REG 實機驗證（Claude Code）

- 分支 claude/r-slp-acl-polling，基準為 #30 合併後的預設分支；實機 NODE3（redhat .100，b13），使用者授權。
- 新增 tests/support/ge_acl_profile.py：以 `show acl-profile mode`／`show acl-profile` 輪詢（30 秒、間隔 1 秒，
  scaled_wait），取代 test_neox_config.py ACL 模式切換與 profile 建立後的固定 sleep；mode 輪詢逾時才重送一次
  `acl-profile mode <mode>`，並附 Allure「GE ACL profile mode retry」。刪除 KNOWN_SLEEPS 兩個 ACL 條目，
  新增離線測試 tests/test_ge_acl_profile.py（5 項）。
- CLI baseline：模式切換、建立 RestApiGeAcl、切回 port 都在第一次 show 即可見（約 3.4 秒）。REST 回歸
  test_ge_config_max_create／max_variant：通過 9／失敗 0，8 個 ACL 案例皆 polls=1、約 3.4 秒，未觸發重送；
  結束後 NODE3 為 port mode，profile 與執行前相同。
- R-REG：預設跑法保留 password 與 session id 原值；`--redact-reports` 下 password、session id 全數遮罩。
  registid、CLI registration-id、teardown statusDetails 在唯讀案例未出現，僅由離線測試涵蓋。
- D0：PR #18 已關閉並留言；兩個殘留 worktree（皆乾淨）已移除，分支保留。
- 離線 `pytest -m offline`：通過 158／失敗 0。

## 下一步

標記：〔離線〕可直接做；〔需決定〕等使用者決策；〔需實機〕需使用者授權並指定 node。

retro 計畫（2026-10-20 核准）的離線 PR A～I 已全部完成；剩下的是待實機與待決策項目：

- [R-SLP]〔需實機〕（ACL 部分已完成）inventory／provision 輪詢前固定 30／15 秒以 initial_delay=0 實測，
  完成後刪除 tests/test_no_fixed_sleep.py 對應的 KNOWN_SLEEPS 條目。
- [R-REG]〔需實機〕（password／session id 已驗證）registid、CLI registration-id、teardown statusDetails
  待有寫入／teardown 失敗的回歸時以 `--redact-reports` 確認。

使用者決策（2026-10-20 已定：D6 skill 名稱 pr-description；D7 專案 settings.json／.gitattributes 這輪不做）：

- [D1]〔需決定〕（2026-10-20 使用者已定：本機報表保留原值）既有 reports/ 不需清理明文；此項可關閉。
- [D3]〔需決定〕（重複副本已清理）保留的 9 個 DIFFERENT／NO_ARCHIVE 目錄與 b1–b9 是否再以 tools/archive_reports.py 歸檔。
- [D4]〔需決定〕曾貼入對話或整檔讀出的測試帳密是否輪替。
- [D5]〔需決定〕Codex 之後是否仍在本 repo 使用（影響 skill 原檔位置）。

既有事項：

- [B13]〔需決定〕b13_redhat：既有報表明文清理（同 D1）；RAD external 11:40～15:59 恢復原因；
  formal_runs.yaml 正式執行；TestLink build／回填；configs/ems.yaml b13 版本是否已提交需核對。
- [TD]〔需實機〕（Blocked 報表已完成）PR-2：EMS1-7223 SFU 還原移進本體（比照 NNI restore_state），失敗記 Fail；需 NODE3 實機驗證。
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
