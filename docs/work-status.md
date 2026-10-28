# 共用工作進度

更新日期：2026-10-28（Asia/Taipei）。此檔是交接快照；
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

### 2026-10-28 NODE3 完整測試與 b13_redhat 回填（Claude Code）

- UseTestlink 已發版並安裝 v1.9.7（含 v1.9.5 回填前把關、v1.9.6 `testlink_mark_automated`、v1.9.7 預覽與 audit 預設目錄），
  10-27 RC-5 記錄的「發版與安裝」已完成。
- 使用者授權含破壞性測試；分支 claude/backfill-gate-docs 7cfab88（只改文件，之後以 #38 合併為 2eca0ea），
  `tools/run_multi_node.py --nodes NODE3 --run-full-testcases`，reports/multi_node/2026-10-28_14-35-27。
- 結果：316 selected，pytest 通過 316／失敗 0，1:29:10；報表 254 Pass／0 Fail，Completeness 316/316，沒有 Case ID Drift。
- 回填：使用者審閱預覽（254 筆 Pass、warnings 0、ignored 0）後寫入 TestLink build `03.00.11 (AAVV.221) b13_redhat`，
  錯誤 0；`testlink_get_latest_results` 回讀 254 筆皆 Pass。未建立 Redmine bug。
- 手動／自動：寫入後預覽 `testlink_mark_automated`，2 個仍為 Manual（EMS1-7056 v2、EMS1-7223 v1），
  使用者確認後改為 Automated 並回讀驗證；這批 254 個現在都是 Automated。
- 待處理：UseTestlink 產生的 TestLink notes 含 node 名稱與 IP，與本專案「對外內容遮罩」不一致；
  這次使用者決定照原格式寫入，遮罩需在 UseTestlink 另外處理。

### 2026-10-27 RC-5 回填前把關（UseTestlink，Claude Code）

- 使用者決定：把關做在 UseTestlink（匯入前驗證是它的責任，所有回填路徑都會經過），不在本專案另做檢查工具；
  Incomplete／Drift 擋下、可帶原因放行並寫入 audit、沒有 Completeness 行只警告；先不發版。
- D:\UseTestlink 分支 claude/report-readiness-gate（基準 main 8112c2d）：解析檔頭 `Completeness`／`Case ID Drift`；
  qa-integration-agent 預覽與 testlink_upload_report（CLI upload-report）都在呼叫 TestLink／Redmine 前回
  `REPORT_NOT_READY`；`readiness_override_reason` 放行時記入預覽、warnings 與 workflow audit；JUnit 不檢查。
- 驗證：UseTestlink `python -m unittest discover -s tests` 通過 445／失敗 0（新增 tests/test_report_readiness.py 10 個）。
  以真實報表與測試用假連線離線驗證：10-27 safe lane、10-22 完整測試通過；10-27 漂移實測報表被擋下；
  b12_redhat 判定版（無 Completeness）只出 warning。
- 本專案：ems-version-regression 第 6 步補上 REPORT_NOT_READY 的處理方式（分支 claude/backfill-gate-docs）。
- 未完成：UseTestlink 發版與安裝（mcp-release，需使用者同意）；安裝前回填流程行為不變。

### 2026-10-27 Case ID 漂移檢查（Claude Code）

- 分支 claude/case-id-drift，基準為 b07702c（#36 合併後的預設分支）。
- 原因：PR #34 之後 ID 同時寫在測試 marker 與 services 的 `attach_case_id`，只檢查「有 ID」，不檢查兩邊一致；
  改了 service 的 ID 卻沒改 marker 時，同一個測試會在報表掛兩個 case。
- 修改：收集結束時凍結每個選中測試的 ID；執行時 `register_case` 登記不在其中的 ID，報表檔頭加
  `Case ID Drift: N` 與 `Case ID Drift #n: <nodeid> registered <id>; collection had <ids>`（使用者決定只寫檔頭，不改結果）。
  新增 `testlink_runtime_case(case_id)` marker，lifecycle 測試用它宣告執行時補登的 6641／6642／6652／6658／6670／6674。
  新增 tests/test_case_id_drift.py：AST 掃描 services／tests 的 `attach_case_id` 字面 ID，必須有測試在收集時持有；
  marker ID 必須是已知 case，名稱與 service 字面一致（`register_txt=False` 的權限摘要排除）。
- 驗證：compile 通過；`pytest -m offline` 通過 206／失敗 0。刻意改 service ID 與 marker 名稱，兩個守門測試都失敗。
  b12／b13 共 80 輪 Allure 結果比對 81 個測試函式，沒有漂移。
- 實機 NODE3（redhat .100，safe lane，唯讀）：通過 39／skipped 34／error 1，Completeness 74/74，沒有 Case ID Drift。
  error 是 readonly 登入時 .100 `RemoteDisconnected`（連帶 EMS1-7109 Fail），單獨重跑通過。暫時把
  services/invalid_params 的 EMS1-7031 改為 EMS1-6699 跑該測試：檔頭列出 1 筆 Drift，結果列出現 7031 與 6699 兩列；檔案已用 git 還原。
- 帳號事件：同日 NODE3 preflight 兩次失敗，default profile 的 readwrite 帳號登入成功，但 `GET /device` 與
  `GET /device/<NODE3>` 都回 `You have no privilege to do this.`。使用者確認 NODE3 仍由 redhat .100 管理並修正帳號權限，
  第一次修正後仍失敗、再次修正後兩個 GET 皆 Success，之後實測正常。

### 2026-10-22 NODE3 完整測試（Claude Code）

- 使用者授權含破壞性測試；預設分支 b07702c，`tools/run_multi_node.py --nodes NODE3 --run-full-testcases`，
  reports/multi_node/2026-10-22_full-NODE3-b07702c。
- 結果：316 selected，pytest 通過 313／失敗 3，1:58:17；報表 251 Pass／3 Fail，Completeness 316/316，無 Teardown Errors。
  ONT error 測試的 baseline 還原 219 秒、14 次輪詢，標 SLOW（門檻 12）。
- 3 個失敗都是 .100 連線層錯誤：EMS1-7195（RemoteDisconnected）、EMS1-7116（/v3/api-docs 讀取逾時）、
  EMS1-6922（RemoteDisconnected）；單獨重跑 3 個都通過，判定為環境問題。
- CLI show 確認 ONT 3-16-1 為 IS、description REST_API_NEOX_ONT、無 template。沒有回填 TestLink。

### 2026-10-22 RC-1 完整性檢查：缺漏測試與中斷標記（Claude Code）

- 分支 claude/run-completeness-check，基準為 a98039d（#35 合併後的預設分支）；commit f67499c。
- PR #36 CI 通過，head f67499c，於 2026-10-22 14:38（台北）以 merge commit 合併為 b07702c。
- 實機 NODE3 safe lane：檔頭、`EMS completeness:`、summary.json 與總表都顯示 Complete (74/74)，corp 解析 33 列不變；
  同日第一次執行時 .100 拒絕連線，preflight 標 Blocked、pytest 未執行，重跑正常。
- 原因：2026-07-21 與 2026-10-02 09:54 兩輪中途停止，沒有 summary.json，也沒有任何地方標出沒跑完；
  b12_redhat 判定版回填的來源就是 10-02 09:54 那輪（log 停在 99%）。
- 修改：收集結束（-m／-k 之後）記錄選中的 nodeid；pytest 被中斷（ExitCode 2）時標記。txt／HTML 檔頭加
  `Completeness: Complete|Incomplete (X/Y selected tests have a result[; run interrupted])` 與
  `Missing Test #n: <case ID> <nodeid>`（最多 30 行）；xdist 標「not evaluated」。結束時印 `EMS completeness: …`。
  run_multi_node 讀這一行：檔頭 Incomplete、exit code 2 或 log 沒有最後摘要行時，node 狀態為 Incomplete，
  summary.json 加 completeness 欄位，整輪 exit code 非 0。不改 Summary 與結果列。
- 驗證：compile 通過；`pytest -m offline` 通過 199／失敗 0（新增 tests/test_run_completeness.py 15 個）。
  corp 離線解析 Incomplete 範例報表：只讀到結果列與 Summary，新檔頭不影響。
- 限制：單一 node 回填時，corp 仍會寫入有結果的列，缺漏的 case 不寫；要擋回填需做建議第 4 項（回填前把關）。
  Incomplete 的情境只有離線測試，實機尚未遇到。

### 2026-10-22 修正假 Pass：收集階段登記 TestLink case ID（Claude Code）

- 分支 claude/run-completeness，基準為 8c32c6d（#33 合併後的預設分支）；commit 76199b8、ab30db5。
- PR #34 CI 通過，head ab30db5，由使用者於 2026-10-22 11:10（台北）以 merge commit 合併為 a9d9273。
- 問題證據：b12 NODE1（2026-09-08）報表有 152 Pass／0 Fail，pytest 結果是 26 skipped。EMS1-6667／6669 的主測試被 skip，
  但報表顯示 Pass（只有 readonly／noaccess 權限變體有跑）；EMS1-6642／6668／6670 被 skip 後在報表中消失。
  原因：這些測試的 case ID 在 services 執行時才由 attach_case_id 登記，setup 或本體前段被 skip 時拿不到 ID。
- 修改：新增 `testlink_case(case_id, name)` marker（pytest.ini），collection.py 在收集時登記；32 個非參數化測試加上 marker，
  ID 和名稱沿用 services 字面值，並用 b12／b13 共 80 輪 Allure 結果交叉確認。profile 參數化 case（catalog dict）也改在收集時登記。
  lifecycle 測試只標它獨有的 6654／6659，避免停用時把其他測試的 Pass 變成 Skip。
- 離線量測（`--collect-only --run-full-testcases`）：收集時已知的 ID 從 108／254 增加到 252／254（剩下 7109／7110 是權限摘要）；
  沒有 ID 的 item 從 156 降到 3，都是非 TestLink 測試，列在 tests/test_case_id_registration.py 的允許清單。
- 驗證：compile 通過；`pytest -m offline` 通過 184／失敗 0；新測試在拿掉修正後 4 個全部失敗。
- 行為改變：被 skip 的 case 會在報表多出 `Result Skip` 列（例如沒開 --run-alarm-delete 時的 6674／6654／6659）。
  corp（D:\UseTestlink）預設 skip_policy=ignore，Skip 列列入 ignored、不寫入；blocked 才寫成 b。
- 已開 PR #34，CI 通過。b12 TestLink 唯讀查詢：6667／6668／6669 當時已人工判定為 b，沒有假 Pass 落地。
- 實機 NODE3（redhat .100，2026-10-22，safe lane，唯讀）：通過 40／skipped 34；報表 16 Pass／17 Skip，
  每個 skipped item 的 ID 都在報表，沒有 skip 被顯示成 Pass。6642／6670 以 Skip 出現（修正前會消失）。
  corp 離線解析：33 列、無錯誤，ignore 為 p 16／忽略 17。未驗證：mutating 的 6667～6669 情境（不在唯讀範圍）。
- 仍有缺口：RAD 摘要（7056／7107／7108）只在 --auth-matrix 時登記，沒開時被 skip 仍不會出現在報表。

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

### 2026-10-21 PR-2：ONT baseline 還原單一輪詢窗、SFU 還原移進本體（Claude Code）

- 分支 claude/sfu-restore-in-body，基準為 #32 合併後的預設分支。使用者決定：還原輪詢改單一 600 秒窗（乘 wait_scale）、
  固定 15 秒、不重送 baseline、超過 12 次輪詢在報表檔頭標 SLOW；EMS1-7223 還原移進本體、失敗記 Fail。
- 新增 tests/support/ont_baseline.py（converge_ont_baseline）：POST baseline 一次，REST 以每段 300 秒重新登入輪詢
  （EMS session 600 秒到期），需連續 4 次符合；附 Allure 輪詢次數／耗時；SLOW 寫入檔頭 `ONT Baseline Restore (...)`。
  EMS1-7130、7133（strict teardown）與 7223 共用；刪除舊的 120／180 秒兩輪重送與 restore_ont_config_baseline。
- EMS1-7223 比照 NNI restore_state：步驟 6 在本體執行，未執行到時才由 strict final 補救。
- 實機 NODE3（redhat .100）：EMS1-7223、EMS1-7130 通過 2／失敗 0，無 Teardown Errors；SFU 本體還原 6 次輪詢、163 秒，
  7130 teardown 還原 4 次、120 秒，皆未標 SLOW；CLI 確認 ONT 為 IS、description REST_API_NEOX_ONT、無 template。
- 離線 `pytest -m offline`：通過 178／失敗 0；相關單元測試（rest_polling、ont_cli_status、reporting 等）通過 72／失敗 0。

## 下一步

標記：〔離線〕可直接做；〔需決定〕等使用者決策；〔需實機〕需使用者授權並指定 node。

retro 計畫（2026-10-20 核准）的離線 PR A～I 已全部完成；剩下的是待實機與待決策項目：

- [RC-4]〔離線〕txt Summary 行加 Skip 數（b12 NODE1 的 `152 Pass / 0 Fail` 看不出 26 個 skipped）；corp 只把 Summary 當字串，
  但會寫進 TestLink notes，格式需使用者確認。
- [RC-5]〔需決定〕回填前把關已在 UseTestlink claude/report-readiness-gate 實作（見 2026-10-27 RC-5 條目），待合併與發版安裝。
- [RC-6]〔需決定〕b12 NODE1：formal_runs.yaml 標 2026-09-22 為正式執行，TestLink 仍是 09-08 的結果，需決定補回填或改正式執行。
- [RC-7]〔需實機〕redhat .100 在 10-22／10-27 多次出現 RemoteDisconnected／讀取逾時／拒絕連線，重跑皆通過；若持續發生再評估。
- [RC-2]〔需決定〕RAD 摘要（7056／7107／7108）沒開 --auth-matrix 時被 skip 仍不會出現在報表，是否改為列出 Skip。
- [RC-3]〔需實機〕PR #34 的 mutating 情境（6667～6669 主測試 skip）尚未實機驗證；10-22 完整測試中這三個都通過，
  沒有遇到 skip 的情況。

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
- [TD]〔需實機〕（PR-1／PR-2 已完成）累積幾次回歸的 `ONT baseline` 輪詢次數後，檢討 SLOW 門檻 12 次是否合適。
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
