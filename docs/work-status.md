# 共用工作進度

更新日期：2026-10-13（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Claude Code（2026-09-22 ~ 2026-10-12）；先前由 Codex 建立共用
  協作入口。
- 分支：codex/neox-profile-read-path-fix（工作分支）。每批變更先在 scratch
  worktree 做 `git merge --no-commit --no-ff` dry run，確認零衝突後才合併進
  codex/prepare-github-upload（GitHub 預設分支）。
- 共用 skill 以 .codex/skills/<name>/SKILL.md 為來源（qa-bug-report、
  ems-version-regression），Claude 側 .claude/skills/<name>/SKILL.md 只轉介，
  未複製業務規則。
- 未新增全域權限設定、MCP 憑證或設備操作自動化。
- Repo 公開性：專案負責人已明確決定維持 Public（自動化測試專案，帳密皆為
  per-person 環境變數，非共用明碼密碼），不需要轉 Private。

## 最近一次工作

較早的紀錄見 docs/work-history/（依月份）。

### 2026-10-13 第九次完整測試：慢請求標記與錯誤摘要實機驗證（Claude Code）

- 以未提交的上述修改執行（reports/multi_node/2026-10-13_17-08-09）：pytest 314 passed、2 failed、
  1 error（1:44:56）；TestLink 252 Pass／2 Fail。
- 報表開頭 `EMS Connection Errors: 5 (recovered by retry 3, not recovered 2)`、
  `EMS Slow Requests: 5 (total time over 30 s)`，txt／HTML 與 Allure 附件一致。
  - GET 重送恢復 3 次（ConnectTimeout 2、Connection reset 1）。
  - EMS1-6900、6908 失敗：PATCH 送出後 .100 切斷連線（Connection dropped，19.2 s），依規則不重送。
  - mutating request 遇 ConnectTimeout 的重送本次未觸發（PATCH 皆為 dropped）。
  - 慢請求 5 筆皆為 POST `/configNeoXSeries/profile/.../ONTUNIProfile/RestUNI`（34.5～36.5 s，HTTP 200，
    EMS1-7172／7173），其他 endpoint 無；ONTUNIProfile 建立固定偏慢，待確認是否回報。
- 實機發現 Windows 約 21 秒即放棄建立連線（早於 client 60 秒上限），摘要改為
  「connect timed out after 21.0 s (client limit 60 s)」，以實際耗時為主。
- ERROR：test_ont_config_apply_provision_template_sfu_readwrite 本體 PASSED，teardown 還原 ONT baseline
  未收斂（第 1 次 GET /ont/sn HTTP 500＋CLI UnReg；第 2 次 REST 連續穩定 2/4）；同既有事項
  「ONT SFU 間歇 teardown HTTP 500」。之後 ONT 查詢類 case 皆 Pass。
- 第 10 次（2026-10-14，未提交的 redhat 時間設定：wait_scale 1.5、重送 10/30/60 s、請求間隔 0.3 s；
  reports/multi_node/2026-10-14_10-01-12，1:52:54）：TestLink 237 Pass／3 Fail／14 Skip。
  - 連線錯誤 4 筆全部重送恢復（含首次實機觸發的 DELETE ConnectTimeout 重送，EMS1-7130）；慢請求 8 筆
    （3 筆為重送造成、5 筆為 ONTUNIProfile POST 約 36 s）。
  - 失敗與 Skip 全部來自 session 過期：test_profiles 的 module-scope `profile_workspace` 以
    `role_session` 取得一次性、不會更新的 readwrite session，整個模組共用；EMS session 600 秒後失效。
    模組耗時第 8 次 550 s、第 9 次 529 s（已接近上限），第 10 次因請求間隔變為 618 s，578 s 起回
    `Not authorized.`：EMS1-6922、6914、6920 失敗，其後 14 筆 invalid-param case Skip，workspace
    cleanup ERROR（暫時 profile 可能殘留在 EMS）。
- 修正：`profile_workspace` 改用 `shared_role_session(READWRITE)`（ADR 0001 補充）。第 11 次
  （reports/multi_node/2026-10-14_13-22-42，2:08:41）：pytest 316 passed、0 failed、0 error；
  TestLink **254 Pass／0 Fail**，首次一次全過。連線錯誤 6 筆全部重送恢復（POST、DELETE、PATCH
  ConnectTimeout 各 1，GET 3）；慢請求 10 筆（5 筆重送造成、5 筆 ONTUNIProfile POST 約 35 s）；
  Proactive Session Refreshes 9、Authorization Session Refreshes 0；SFU teardown 本次收斂。
  總時間較第 8／9 次多約 20 分鐘（請求間隔 0.3 s）。
- 發現遮罩缺口（未修，既有問題）：ONT password 以 `registid` 送入 NeoX ONT config payload，
  redaction 未涵蓋此 key，request 附件與 integrated HTML 可見明文；teardown 失敗訊息中的 EMS 回應
  `password` 欄位也出現在 Allure statusDetails。txt／HTML 簡易報表與 pytest log 無明文。

## 下一步

0. b13_redhat：SSH／密碼遮罩／inventory 等待／EMS1-7056 Remote Control 已提交；決定是否清理既有報表中的明文密碼；
   確認 RAD external 11:40～15:59 恢復的原因；決定 formal_runs.yaml 的
   b13_redhat NODE3 正式執行；決定 TestLink 是否建 build／回填；commit configs/ems.yaml 的
   b13 版本。
0-1. 是否讓 teardown 失敗（cleanup 未收斂）反映到 txt／TestLink 結果，待決定。
0-2. b12_redhat 回歸、TestLink 回填與合併都已完成。
0a. .100 連線中斷已判定為 server 資源不足；GET／HEAD 重送與報表連線錯誤記錄已加入
   （ADR 0002）。下次完整測試確認報表開頭的 `EMS Connection Errors` 行與重送恢復情形；
   若仍頻繁，再以報表中的時間點查 .100 log。
0b. 2026-10-13 已提交刪除 tools/update_testlink_multi_node_notes.py，並將 docs/handoff/、
   docs/qa_bug_drafts/（內部 Redmine／bug 資料，repo 為 Public）加入 .gitignore，保留本機。
   docs/sop/ 的 SOP docx（9/22 版）仍未納入：若要給同事使用，先改寫為 Markdown 並更新到
   EMS server 切換與 qa-integration-agent 回填流程。

1. ONT SFU 間歇 `Wait`／teardown HTTP 500：測試期間持續以 CLI 記錄 ONT
   狀態，確認 provision template 套用／還原是否觸發 ONT 重新註冊。
2. NNI POST 移除 payload 未帶欄位、回 Fail 仍部分套用：待確認規格後決定
   是否以 /qa-bug-report 整理。
3. 決定 `docs/qa_bug_drafts/`、`docs/sop/` 是否收進版控（SOP 為二進位檔，
   公開前需先解析內容審閱）。
4. NODE5／NODE7／NODE8 test_targets.local.yaml fw_version 仍帶後綴，需 CLI
   確認後更新。
5. 觀察 CI：推送 ab8afb2 到預設分支時觸發了兩個 push run，其中 CI #3 被
   concurrency 設定取消；原因未確認，若後續推送持續重複再查。對
   codex/prepare-github-upload 的 PR 流程尚未實際跑過 CI。
6. 依賴改為手動升級：升級時修改 requirements.txt，並確認 CI 與本機離線
   檢查通過。
7. 已由 tools/build_report_index.py `--compare` 取代（2026-10-07）；
   ems-version-regression 步驟 5.1 已改為呼叫它，不再另做
   tools/compare_multi_node_runs.py。

## 後續更新方式

每個工作條目至少記錄：日期、負責工具、任務、分支／基準 commit、
修改範圍、驗證指令與結果、未執行原因、下一步。
已解決的事項可精簡，尚未完成或缺證據的事項必須保留。
本檔只保留最近 1～2 筆工作條目，較舊的原文移到 docs/work-history/<YYYY-MM>.md，
全檔維持在 120 行以內。
