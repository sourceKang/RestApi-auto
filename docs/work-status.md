# 共用工作進度

更新日期：2026-10-07（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Claude Code（2026-09-22 ~ 2026-10-06）；先前由 Codex 建立共用
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

## 本次完成的工作

- `290c45e`（合併 commit `040f4c7`）：新機安裝修正。包含 README、
  tools/check_environment.py、docs/SETUP_NEW_MACHINE.md、兩個
  configs/*.local.yaml.example；cases/openapi_contract.py 的 OpenAPI root
  改為 EMS_OPENAPI_ROOT／ems.openapi_root 可設定，找不到時 skip 而非 fail；
  新增 Claude Code 入口（CLAUDE.md、.claude/skills/qa-bug-report/SKILL.md、
  CLAUDE.local.md.example）與 docs/project-context.md、本文。
- `3d64803`、`ac9a0cf`（合併 commit `ab8afb2`）：新增
  `.github/workflows/ci.yml`，只做離線檢查（compileall 全掃、
  `pytest --collect-only --skip-dut-preflight`、
  `pytest tests/test_service_bundle.py --skip-dut-preflight`），跑在
  windows-latest，觸發於 push 到 codex/prepare-github-upload 或
  codex/neox-profile-read-path-fix，以及對 codex/prepare-github-upload 的 PR。
- `46992a0`：
  - requirements.txt 七個直接依賴改為 `==` 鎖定本專案驗證過的版本
    （pytest 9.0.3、requests 2.34.2、urllib3 2.7.0、allure-pytest 2.16.0、
    PyYAML 6.0.3、paramiko 5.0.0、pytest-xdist 3.8.0），皆支援 Python 3.11。
    間接依賴未鎖定。
  - CI actions 升級為 actions/checkout@v7、actions/setup-python@v7（node24），
    消除 Node 20 棄用警告。
  - `.gitignore` 由只忽略 `local/temporary_resources/` 改為忽略整個 `local/`。
    其中是外部工具寫入的 Redmine／TestLink 稽核紀錄與快取，追蹤中的程式
    不會讀取；其中一份稽核紀錄含內部 Redmine 伺服器位址，不應公開。

仍是 untracked、尚待決定是否收進版控：
- `docs/qa_bug_drafts/`（EMS1-6652 Remote Console bug 草稿）
- `docs/sop/RestApi_Auto_測試操作_SOP_20260922.docx`（二進位檔，公開前需先
  解析內容審閱）

## 本次驗證

- 新機安裝相關的 16 個檔案逐一讀完，並對 staged diff 做關鍵字掃描
  （password/secret/token/devkey/api_key），確認無明碼密碼或非預期內容。
- 每次合併前在 scratch worktree 執行 `git merge --no-commit --no-ff`，結果皆為
  "Automatic merge went well"、零衝突；合併後以 `git diff`／`git ls-tree`
  比對，預設分支內容與工作分支一致。
- CI 步驟先在本機以「無 .local.yaml、無 EMS_*/DUT_* 環境變數」模擬（用
  EMS_AUTH_ACCOUNTS_FILE／EMS_TEST_TARGETS_FILE 指向版控範本，未動本機
  真實 .local.yaml）：compileall 0.6 秒 exit 0；collect-only 647 tests、
  0.35 秒；test_service_bundle 1 passed。`--skip-dut-preflight` 為必要，因為
  collection hook 會在收集階段做 live EMS/SSH preflight
  （tests/support/preflight.py）；utils/reporting.py 無網路呼叫。
- `46992a0`：鎖定版本與 .venv 實際安裝版本逐一相符、`pip check` 無問題；
  `git check-ignore` 確認 `local/` 下檔案皆被忽略；actions v6／v7 release
  notes 的破壞性變更（credential 存放位置、pull_request_target fork 限制、
  移除 pip-install input）不影響本 workflow。
- GitHub Actions 實際執行：CI #1（3d64803）34 秒、CI #2（ac9a0cf）41 秒、
  CI #4（ab8afb2，預設分支）44 秒、CI #5（46992a0，全新 runner 依鎖定版本
  安裝）36 秒，皆成功。
- 未連線 EMS／DUT，未執行完整 regression、NeoX CLI → REST → CLI 或外部
  系統寫入。

## 2026-09-24 EMS b13 完整 regression（Claude Code）

- 分支 codex/neox-profile-read-path-fix，基準 `09332f9`。
- 修改：configs/ems.yaml 的 `ems.version` 由 b12 改為
  `03.00.11 (AAVV.221) b13`（使用者確認 EMS 已升 b13）。
- 指令：`tools/run_multi_node.py --nodes NODE1,NODE3 --run-full-testcases`
  （jobs 1、auth profile default）。摘要：
  reports/multi_node/2026-09-24_17-22-58/summary.html。
- NODE1（IES4204）：222 passed、91 skipped（NeoX 專屬）、3 errors，20 分鐘。
- NODE3（NeoX-03）：294 passed、16 failed、6 errors，1 小時 28 分。
- 失敗分類（皆未確認 Root Cause）：
  1. 兩個 node 的 test_auth_matrix rad_external 三個角色登入回
     `Invalid username.`（6 errors），需確認 RAD external 帳號／RADIUS 設定。
  2. NODE3 test_inventory device／slot 10 筆 FW 版本不符：
     test_targets.local.yaml 期望帶 `_260604c`／`_260604b` 後綴，EMS 回報
     `V1.02(ACKG.1)` 等無後綴值；FwVersion1 為 `V1.03(ACKG.0)b5`。需以 CLI
     確認設備實際韌體後決定更新測資或提報。
  3. NODE3 GE port 1/39 `portOperationStatus=2`，GE inventory setup 失敗
     （port_* 3 failed + 3 errors），疑似 link down，需現場確認。
  4. NODE3 NNI 4/12 設定三筆失敗，設備回
     `FEC should be disable before setting speed`；依 NeoX 規則需先做 CLI
     baseline 再判定是否為 API 問題。
- 未執行：cleanup_stale_test_data 稽核、失敗案例的 CLI baseline 重測。

### 2026-09-29 NODE3 CLI 只讀確認

- `show version`／`show lc st`：slot 4 NXC400 `V1.02(ACKG.1)`、slot 3 NXP316
  `V1.02(ACKI.1)`、slot 1 NXA340 `V1.02(ACQE.1)`，皆無後綴 → 第 2 類為測資
  過期，已更新本機 configs/test_targets.local.yaml NODE3 三筆 fw_version
  （未進版控；NODE5/7/8 仍帶後綴，未經 CLI 確認未改）。重跑 NODE3
  test_inventory device_*／slot_* 15 passed。
- `show interface ge 1-39 status/config`：Status `disable`、Active `No`，
  running-config 無 `enable`；EMS 仍回 Enable → 第 3 類為設備 port 未啟用，
  是否由先前測試遺留未確認。
- `show running-config interface nni 12`：`fec cl74`、`speed 10g`、
  auto-negotiation disable → 第 4 類的 `speed auto` 被設備以 FEC 啟用拒絕，
  屬測試前置條件，待決定測資或流程調整。

### 2026-09-29 NODE3 完整重測

- 指令：`tools/run_multi_node.py --nodes NODE3 --run-full-testcases`；摘要
  reports/multi_node/2026-09-29_10-02-11/summary.html。
- 結果：308 passed、5 failed、3 errors（1 小時 19 分）。上次 16 failed、
  6 errors。
- 已解：inventory FW 版本 10 筆（測資更新後通過）；GE port_* 6 筆本次通過
  （GE 1-39 狀態變化原因未確認）。
- 持續：NNI 4/12 FEC 3 筆；RAD external 登入 3 errors。
- 新增、未確認原因：
  1. inventory readwrite[slot_by_device] 以 admin 取得
     `You have no privilege to do this.`，同案例於同日單獨重跑曾通過，
     疑似間歇性 session／權限問題，需重現。
  2. test_ont_config_apply_provision_template_sfu_readwrite：ONT service
     `5A5958458CACE175` 停在 `state: Wait`，未在 timeout 內到 Success。

### 2026-09-29 NODE1＋NODE3 第三次完整測試

- 摘要：reports/multi_node/2026-09-29_13-50-39/summary.html。
- NODE1：225 passed、91 skipped、0 failed（20 分）。
- NODE3：313 passed、3 failed（1 小時 19 分）。
- RAD external 三個角色兩個 node 皆通過（前兩次 `Invalid username.`；
  本端未修改帳號設定，變化原因未確認）。
- 前次新增的 slot_by_device 權限錯誤與 ONT SFU `Wait` 本次未重現。
- 僅剩 NNI 4/12 三筆：`speed auto : Error: FEC should be disable before
  setting speed`；修正方案（CLI baseline → NNI 前置/還原 fixture → 判定
  max 是否為 EMS 下令順序問題）已提出，待使用者同意 CLI baseline。

### 2026-09-29 NNI 4/12 speed 測資調整與重測

- 修改 configs/neox_config/nni/neox_nni_full_accepted_payload.json（未提交）：
  min `portspeed` auto→`1g`、max auto→`10g`（OpenAPI NniPortInfo enum：
  auto/detect/1g/10g），CLI 預期行同步。
- 15:55 三案例：max PASSED；clear／min 在 FEC 未 disable 時 FAILED
  （`speed 1g : Error: FEC should be disable...`）。max 後 CLI 為 `fec disable`。
- 16:13 前置 CLI `fec disable`、`speed 10g` → 重跑：
  - min PASSED，CLI 確認 `speed 1g`、`flow-control disable` 落地。
  - clear FAILED：`running-config differs after REST clear`。首次 REST DELETE
    後 baseline 無 speed／flow-control 行、有 `pvid 1314`；POST min＋DELETE 後
    殘留 `speed 1g`、`flow-control disable`，`pvid 1314` 消失。REST DELETE 回
    Success。是否為 EMS DELETE 行為問題需先以 CLI baseline 確認，未判定。
- 更正：services/neox_config/cli_expectations.py 的 clear_ignored_line_prefixes
  對 NNI 刻意忽略 `speed `、`flow-control ` 行；16:13 clear 失敗的實際差異是
  `pvid 1314 pbit 0`（首次 DELETE 後仍在，POST min＋DELETE 後消失），不是
  speed／flow-control 殘留。pvid 消失原因未確認。

### 2026-09-29 NNI speed 改回 auto 重測

- 測資 min／max `portspeed` 改回 `auto`（與版控原檔相同，無 diff）。
- 16:17 前置 CLI：fec disable、speed 1g、無 pvid。clear／min／max 皆 PASSED；
  max 後 CLI：speed auto、flow-control enable、fec disable、pvid 1314、
  vlan-qinq-tpid／vlan-default-tpid enable、mtu 1500；ping 正常。
- 結論：三案例在 `fec disable` 時可通過；在 FEC 啟用時失敗，屬設備前置條件。
  clear 通過與否仍受前一狀態（pvid 是否存在）影響，尚未有 NNI 前置/還原
  fixture。

### 2026-09-29 NNI 還原試驗與 max 流程修改

- 試驗（scratch script，REST＋CLI）：POST max（fec cl74、portspeed 10g）成功；
  單次 POST 改回 `fec disable`＋`portspeed auto` 失敗
  （`speed auto : Error: FEC should be disable...`）；分兩次 POST
  `{fec: disable}` → `{portspeed: auto}` 成功。
- 觀察（未判定是否為 bug）：POST 會移除 payload 未帶欄位（僅帶 fec 時
  `pvid 1314` 消失）；回 Fail 的 POST 仍移除了 vlan-qinq-tpid、
  vlan-default-tpid、mtu。
- 修改：
  - configs/neox_config/nni/neox_nni_full_accepted_payload.json：max 改為
    `fec: cl74`、`portspeed: 10g`（CLI 預期同步），新增 `restore_steps`
    （`{fec: disable}` → `{portspeed: auto}`，各自 CLI 驗證）與 restore_note。
  - tests/test_neox_nni_cli_verify.py：max 驗證後執行 restore_steps；以
    `cleanup_registry.add_strict_final` 保證前段失敗時仍還原，還原失敗會在
    teardown 報錯；抽出 `verify_nni_running_config` 共用 CLI 驗證。
- 驗證：py_compile；collect 2 tests；離線 44 passed（neox data paths、
  cli expectations、case metadata、collection reporting）。NODE3 NNI clear／
  min／max 連跑兩輪皆 3 passed，每輪前後 CLI 皆為 `fec disable`、
  `speed auto`；max 報表確認 `fec cl74`、`speed 10g` 落地。

### 2026-09-29 max 修改後 NODE1＋NODE3 完整測試

- 摘要：reports/multi_node/2026-09-29_16-34-15/summary.html。
- NODE1：225 passed、91 skipped、0 failed（19 分）。
- NODE3：315 passed、1 failed（1 小時 20 分）。NNI clear／error／min／max
  全數通過。
- 唯一失敗：test_ont_config_apply_provision_template_sfu_readwrite，ONT
  service 停在 `state: Wait`（template `#RestApi_provision_temp_SFU`）。四次
  完整測試中第 2、4 次出現，與 NNI 修改無關；事後 CLI 顯示 ONT IS、
  Authentication PASS、VEIP Not provisioned，ONT 上線時間 41 分，顯示測試期間
  曾重新註冊。原因未確認，需觀察 ONT 重新註冊與 EMS 下發時序。

### 2026-09-29 ONT SFU 等待時間延長與 NODE3 完整測試

- tests/test_neox_config.py：test_ont_config_apply_provision_template_sfu_readwrite
  的 `wait_for_ont_service_state` timeout 180→600 秒（polling 到 Success 即
  返回；使用者決定保留）。單獨重跑：30 秒即 Success、PASSED，但 teardown
  restore 時 `GET /ont/sn/...` 回 HTTP 500 而 ERROR；事後 ONT 上線僅 5 分，
  推測 template 套用／還原會使 ONT 重新註冊，未證實。
- NODE3 完整測試：reports/multi_node/2026-09-29_18-39-24/summary.html，
  316 passed、0 failed（1 小時 23 分）。事後 CLI：NNI 12 `fec disable`、
  `speed auto`；ONT 3-16-1 IS、Template Not set。
- NODE1 最近一次完整測試（16:34）225 passed；其後修改僅影響 NeoX 專屬案例，
  NODE1 未重跑。

### 2026-09-30 PR #3 程式（137aaff）NODE1＋NODE3 完整測試

- 摘要：reports/multi_node/2026-09-30_08-55-36/summary.html。
- NODE1：225 passed、91 skipped、0 failed（21 分）。
- NODE3：316 passed、0 failed（1 小時 27 分）。
- 同一次執行兩個 node 皆全數通過；RAD external、NNI 4 案例、ONT SFU 皆 PASSED。
- 事後 CLI：NNI 12 `fec disable`、`speed auto`；ONT 3-16-1 IS、Template Not set，
  上線 41 分（測試期間仍有重新註冊）。

### 2026-09-30 b13 結果回填 TestLink（UseTestlink 多報表流程）

- UseTestlink（另一 repo）新增批次與多報表匯入，疊在未合併的 PR #9 上：
  PR #10 `claude/batch-mcp-session`（修正每筆一個 MCP 子行程造成的 preview
  逾時、execution_duration 空值），PR #11 `claude/multi-report-import`
  （`reports: [{label, path}]`，contracts v2）。離線測試 329 OK。PR #9 合併被
  auto mode 以未經 review 拒絕，需專案負責人合併；#9 合併後 #10 base 改 main。
- 以 worktree D:/UseTestlink-multireport 的新程式預覽並寫入：project
  NetAtlasEMS、plan NetAtlas EMS、build `03.00.11 (AAVV.221) b13`（id 20588）、
  platform NetAtlas EMS；NODE1＋NODE3（2026-09-30 報表）合併 254 筆，全部 p，
  append（未 overwrite），52 秒，0 錯誤。以 get_last_result 抽查 EMS1-6640、
  EMS1-7118 已寫入。audit 位於 local/testlink_audit/qa_audit/（不進版控）。
- 待辦：UseTestlink PR #9→#10→#11 依序合併並重新部署 MCP（本專案側已於
  2026-09-30 收尾，見下節）。

### 2026-09-30 多報表預覽確認與 skill 收尾（Claude Code）

- 分支 codex/neox-profile-read-path-fix，基準 `137aaff`（PR #3）。
- qa-integration-agent MCP 的 `qa_preview_report_artifact` schema 已含
  `reports` 參數。以 environment corp、NODE1（2026-09-30_08-55-38）＋NODE3
  （2026-09-30_09-16-37）txt 預覽：parsed／write 254、全部 p、warnings 0、
  ignored 0；兩份報表 testcase ID 集合相同（254），NODE1 的 Skip 由 NODE3
  Pass 合併為 p；target 解析為 build id 20588。只做預覽，未執行寫入（b13 已
  回填，再寫會重複）。MCP 目前指向已合併 main 或 worktree 未確認。
- 移除 tools/update_testlink_multi_node_notes.py（無其他程式引用），TestLink
  多 node 回填改走 qa-integration-agent `reports` 預覽 → 讀取 → 同意後執行。
- 新增 ems-version-regression skill：.codex/skills/ems-version-regression/
  （SKILL.md、agents/openai.yaml）為內容來源，.claude/skills/
  ems-version-regression/SKILL.md 只轉介。與 tmp/handoff_20260930 草稿差異：
  步驟 5.1 改為手動比對 summary.json／txt（compare 工具尚未實作）；步驟 6
  改用 qa-integration-agent `reports` 流程。
- 驗證：compileall exit 0；`pytest --collect-only --skip-dut-preflight`
  647 tests；版控檔案無殘留引用（只剩已忽略的 .pyc 快取）。未連線 EMS／DUT，
  未寫入 TestLink／Redmine。

### 2026-10-01 更新後 MCP 重新上傳測試（Claude Code）

- 先以 `get_last_result` 只讀查 254 筆：皆有結果、全 p、Operation ID 皆
  `b13-multinode-20260930`（2026-09-30 15:42:46～15:43:36）。
- 使用者要求再上傳一次以測試更新後工具，以前一節的預覽執行
  `qa_execute_preview_artifact`（write、audit_dir 為本專案 local/testlink_audit/qa_audit）：
  status `partial-failure`，254/254 `TESTLINK_ERROR`
  `[WinError 5] 存取被拒: 'local'; additionally, the required TestLink audit could not be written.`
  抽查 EMS1-6640、EMS1-7110 最新 execution 仍為 9/30 那批 → 未寫入 TestLink。
- 推論（未證實 MCP 行程實際 cwd）：UseTestlink main `965a9c0`（v1.8.0）的
  qa_integration_agent 以 `subprocess.Popen` 開 testlink_mcp 子行程時未指定
  cwd，coordinator 呼叫 `testlink_execution(write=True)` 也未傳 audit_dir，
  子行程用預設相對路徑 `local/testlink_audit`；MCP 由 Claude 以
  `qa-integration-agent-mcp.exe` 啟動、未設 cwd，相對路徑落在不可寫目錄。
  上次成功寫入是在 UseTestlink worktree 內執行，相對路徑可寫。
- 待辦：UseTestlink 修正子行程 audit 路徑（傳遞或改為絕對路徑／設定 cwd）並
  重新部署後，以 `qa_resume_preview_artifact` 或重新預覽再測一次。

### 2026-10-01 雙 EMS server 切換設定（Claude Code）

- 分支 codex/neox-profile-read-path-fix，基準 `137aaff`；未 commit。
- 需求：實驗室兩台 EMS 輪流測試，ubuntu `192.168.128.8`（b13）與 redhat
  `192.168.128.100`（b12，RedHat 9 HA）；兩台不會同時納管同一 node，使用者
  測試前手動把 node 移到要測的 server。
- configs/ems.yaml 改為 `ems.targets`（ubuntu／redhat）＋共用設定，
  `default_target: redhat`；`EMS_TARGET` 環境變數可覆蓋。不含 targets 的
  平面寫法仍相容。
- config_loader/settings.py 新增 `load_ems_settings()` 統一解析 target；
  `EnvironmentConfig` 新增 `ems_target`、`ems_platform`（預設空字串）。
  OpenAPI root／版本讀取（cases/openapi_contract.py、tests/test_openapi_yaml.py、
  tools/update_openapi_baselines.py）改用同一解析。
- 報表：txt／HTML／integrated 皆記錄 `EMS Target`、`EMS Platform`，標題為
  `<version> (<platform>) / <node>`；有 target 時輸出目錄為
  `reports/<version>_<target>/`。run_multi_node 的 summary.json／html 與
  dry-run 輸出記錄所選 EMS。integrated 報表 EMS Version 卡片原本寫死 `b7`，
  改為讀實際版本。
- 移除寫死的 `192.168.128.8` Swagger 預設（run_openapi_version_guard、
  `--neox-swagger-api-docs-url`），改由所選 target 的 `rest_api_url` 推算。
- 文件：SETUP_NEW_MACHINE.md、openapi_version_guard.md、project-context.md、
  ems-version-regression skill 步驟 1。
- 驗證（離線）：.venv compileall 通過；test_config／test_reporting／
  test_run_multi_node／test_openapi_yaml 65 passed、3 skipped（live Swagger）；
  collect-only 655 tests。兩個 target 都解析正確，redhat 的 OpenAPI 對應
  `03.00.11 (AAVV.221)/NetAtlasEMS_OpenAPI_20260716.yaml`。未連線 EMS，
  未建立 TestLink build。
- 注意：pytest（含 --collect-only）結束時都會寫入 reports/<version>…；本次
  離線執行產生的空報表已刪除。

### 2026-10-01 b12 RedHat（.100）NODE3 完整測試（Claude Code）

- 使用者確認：RedHat 版本目前僅支援 NeoX 系列設備（已記在 configs/ems.yaml
  註解與 TestLink build notes）；NODE3 已由使用者手動移到 .100。
- TestLink：經使用者同意建立 build `03.00.11 (AAVV.221) b12_redhat`（id 20607，
  project NetAtlasEMS、plan NetAtlas EMS）。尚未回填。
- 指令：`tools/run_multi_node.py --nodes NODE3 --run-full-testcases`；摘要
  reports/multi_node/2026-10-01_11-22-03/summary.html。
- 結果：313 passed、3 failed（1:36:32）；TestLink case 251 Pass／3 Fail。
  與 b13 NODE3（2026-09-30 09:16，254 Pass）相比，case 集合相同。
- 失敗分類：
  1. EMS1-7121 test_ge_config_error_readwrite（ConnectTimeout）、EMS1-6794
     test_patch_profile_by_ontaclprofile（ConnectionReset 10054）：間歇性
     連線問題，單獨重跑兩筆都 Pass（..._13-04-27_NODE3_rerun.txt）。原因未確認。
  2. EMS1-7223 SFU provision template：`/ontservice` POST 回
     `'qoss' item 1 field 'qosds' Bandwidth Profile not found.`。唯讀 GET 顯示
     EMS 層 `/profile/ONTBandwidthProfile/#RestApi_1G` 在 .8 存在、在 .100
     不存在。測試只建立 NeoX 設備層的同名 profile，payload 的 qosds 退回固定值
     `#RestApi_1G`（cases/payloads.py），隱含依賴 EMS 既有測資。屬前置條件問題，
     不是 API bug；未修改。
- 還原：ONT service 5A5958458CACE175 執行前後皆為 No data found；log 沒有
  teardown error。
- 報表：reports/20261001_03.00.11-AAVV.221-b12_redhat_NODE3_regression.html。

### 2026-10-01 b12 RedHat NODE3 第二次完整測試（Claude Code）

- 使用者要求先不回填 TestLink，再測一次。摘要
  reports/multi_node/2026-10-01_13-33-52/summary.html。
- 結果：311 passed、5 failed（1:31:41）；TestLink case 249 Pass／5 Fail。
- 失敗：EMS1-7223（同上，前置條件）；EMS1-7121 ConnectTimeout（兩次都在
  開始後約 25 分鐘、同一 GE POST 迴圈，但 payload 不同）；EMS1-7120、
  EMS1-6903、EMS1-6930 ConnectionReset 10054。第一次失敗的 EMS1-6794 本次 Pass。
- 判斷：.100 每次執行都有連線錯誤，案例不固定；.8 從未出現。connect timeout
  約 21 秒（TCP SYN 無回應），client 每個 request 都開新連線
  （`requests.request`）。推論為 .100 HA VIP／防火牆／EMS 前端環境問題，
  未確認；需要以錯誤時間點對照 .100（.25/.26）伺服器端 log。
- 兩次都沒有 teardown fixture 失敗；ONT service 仍為 No data found；GE 1/39
  portAdminState 2。報表已加入兩次對照。

### 2026-10-01 EMS1-7223 歷史資料查證（Claude Code，唯讀）

- 本 repo 的 Python 程式從初始 commit `1b27c67`（2026-04-21）起，都沒有建立
  EMS 層 `#RestApi_1G`。只有舊版腳本 `test_prepare_for_get_ont_`（legacy 註冊
  資料，`1eb74db` 已移除）會依序 POST 7 筆 provision profile。保留的
  reports／.codex-validation／tmp 中沒有任何 EMS 層 `#RestApi_1G` 的 request。
- 唯讀 GET：configs/profiles 的 7 筆 `provision_ont_*` 在 .8 全部存在，內容與
  yaml 定義完全一致（diff 0）；在 .100 全部不存在，其中包括 SFU ontservice
  引用的 `#RestApi_provision_temp_SFU`。

### 2026-10-02 EMS1-7223 修正（Claude Code）

- tests/test_neox_config.py SFU 測試：`upsert_ont_service` 前呼叫
  `services.inventory.ensure_profile_by_name(readwrite_session, PROVISION_TEMPLATE_SFU_NAME)`，
  依 configs/profiles 定義遞迴確保 7 筆 EMS 層 provision profile（已存在就比對
  內容後沿用，不在 teardown 刪除）。
- tests/test_profile_prerequisites.py 新增離線測試：qosds 的預設 `#RestApi_1G`
  必須在 SFU template 的相依清單內。
- 驗證：離線 50 passed、collect 656；經使用者同意，在 .100 單獨重跑 EMS1-7223
  通過（11:13，..._2026-10-02_09-09-13_NODE3_sfu_fix.txt）。7 筆 profile 已建立在
  .100（內容 diff 0，持久保留），teardown 正常，ONT service 回到 No data found。

### 2026-10-02 NODE3 第三次完整測試（Claude Code）

- 第一次啟動（reports/multi_node/2026-10-02_09-22-23）於 09:52 被工具背景時限
  （30 分鐘）中止：已完成 92 筆（91 passed、1 broken：09:45
  ge_config_max_variant[vlan_trunk_vlan] ConnectTimeout），teardown 皆正常；
  中止時在 SFU 測試的 NeoX 層 profile 準備步驟，尚未改 ONT。CLI 唯讀
  `show vlan 4094` 與未使用的 4093 輸出相同，確認沒有殘留 VLAN。
- 改以獨立程序（Start-Process）重新執行同一指令（reports/multi_node/2026-10-02_09-54-35）：
  pytest 314 passed、2 broken（1:38:34）；TestLink 252 Pass／2 Fail
  （..._2026-10-02_09-54-36_NODE3.txt）。EMS1-7223 在完整測試中通過。剩下的
  2 筆是 .100 連線錯誤：EMS1-7120 [vlan_tls] ConnectTimeout（10:10:05）、
  EMS1-6903 RemoteDisconnected（11:18:22）。teardown 皆正常。
- runner 問題：以 Start-Process 啟動時，tools/run_multi_node.py 的 `Popen(text=True)`
  用 cp950 解碼 pytest 輸出，遇到 UTF-8 中文時 `UnicodeDecodeError` 崩潰。NODE3.log
  停在 99%，沒有產生 summary.json／html；pytest 子程序已跑完並寫出報表。未修改。
- 單獨重跑第 3 次失敗的兩筆（2026-10-02 14:25，..._14-25-48_NODE3_rerun2.txt）：
  `test_ge_config_max_variant_readwrite[vlan_tls]` PASSED（REST POST 成功，CLI 驗證
  報告 reports/device-verification/neox_config_ge_cli_verify_max_variant_vlan_tls_20261002_142717.json
  含 `vlan tls svlan 1314 spbit 0`）；`test_profile_post_invalid_param_cases[EMS1-6903]`
  PASSED（29 組不合法參數全部執行）。teardown 正常。

### 2026-10-02 b12 RedHat NODE3 回歸統整（Claude Code）

- 最終狀態：254 個 TestLink case 全部 Pass（第 3 次完整測試 252 Pass，加上
  EMS1-7120、EMS1-6903 單獨重跑 Pass）。沒有疑似 API bug。
- 已修正測試問題：EMS1-7223（EMS 層 provision profile 前置條件）。
- .100 連線中斷：三次完整測試都有出現（時間點列在報表中）。使用者判定（2026-10-02）
  原因是目前 .100 server 資源不足，屬環境因素，受影響的案例判定為 Pass（單獨重跑都
  通過）。未取得 server 端資源或 log 數據。使用者說 255 個，報表中不重複的 case ID
  是 254 個（b13 同樣是 254），以 254 記錄。
- 統整報表：reports/20261001_03.00.11-AAVV.221-b12_redhat_NODE3_regression.html
  （已重寫為統整版）。

### 2026-10-02 TestLink 回填 b12_redhat（Claude Code）

- 使用者同意回填。以第 3 次 txt 為基礎另存判定版
  `..._2026-10-02_09-54-36_NODE3_judged.txt`：只把 EMS1-7120、EMS1-6903 改為
  10/02 14:25 重跑的 Pass，Summary 改為 254／0，檔頭加 Judgement 說明；原始 txt
  沒有更動。
- 因為多報表合併規則是「任一份 Fail 就算 Fail」，且每份報表必須列出相同的 case，
  不能直接合併重跑報表，所以另存判定版。notes 不能逐筆自訂，判定說明放在 node
  label（最多 64 字元）：`NODE3 judged; 7120/6903 rerun Pass (.100 low server resource)`。
- qa-integration-agent：預覽 `b12-redhat-node3-20261002-v2`，254 筆全部 p、warnings 0、
  ignored 0，build id 20607、platform NetAtlas EMS；寫入 completed，254 筆、0 錯誤
  （2026-10-02 14:36）。第一版預覽 `b12-redhat-node3-20261002`（label 只有 NODE3）
  沒有執行。audit：local/testlink_audit/qa_audit/b12-redhat-node3-20261002-v2-qa-workflow-*.json。
- 用 get_last_result 抽查 EMS1-7120、EMS1-6903、EMS1-7223，皆為 p，notes 正確。

### 2026-10-02 run_multi_node 輸出編碼修正（Claude Code）

- 原因：PowerShell 環境有 `PYTHONIOENCODING=utf-8:surrogateescape`，Bash 沒有。
  pytest 子程序沿用這個設定，用 UTF-8 輸出；runner 的 `Popen(text=True)` 卻用系統
  預設的 cp950 解碼，遇到中文就 `UnicodeDecodeError`。從 Bash 啟動時兩邊都是 cp950，
  所以沒有發生。
- 修正（tools/run_multi_node.py）：子程序 env 固定 `PYTHONIOENCODING=utf-8`，
  `Popen` 加上 `encoding="utf-8", errors="replace"`。
- 測試：tests/test_run_multi_node.py 新增實際啟動子程序的測試，子程序繼承
  `PYTHONIOENCODING=utf-16`（與 runner 不一致）並輸出中文。修正前會重現同樣的
  `UnicodeDecodeError`，修正後通過。
- 驗證：compileall 通過；相關離線測試 117 passed、3 skipped；collect-only 657 tests。
  離線執行產生的空報表已刪除。

### 2026-10-02 commit、push 與合併到預設分支（Claude Code）

- 經使用者確認範圍後，在 codex/neox-profile-read-path-fix 建立並 push：
  `c4a9d3d`（雙 EMS target、報表欄位、run_multi_node UTF-8 修正）、
  `99cae51`（EMS1-7223 SFU 前置 profile）、`d332549`（work-status）、
  `585fbd3`（AGENTS.md 與 project-context.md 的 EMS server 切換規則）。
- PR #3（原為 NNI fec/speed，標題與描述已更新為涵蓋上述修改）合併為 `4865c46`；
  PR #4（EMS 切換規則文件）合併為 `921de33`。兩者合併前 CI 皆通過、scratch
  worktree dry run 零衝突，合併後預設分支 CI 也通過。
- 預設分支 codex/prepare-github-upload 目前在 `921de33`；工作分支保留，同事仍會使用。
- 未納入版控（維持原狀）：已 staged 的刪除 tools/update_testlink_multi_node_notes.py；
  未追蹤的 docs/qa_bug_drafts/、docs/sop/、.claude/skills/ems-version-regression/、
  .codex/skills/ems-version-regression/。

### 2026-10-07 integrated 報表摘要卡片改用實際資料（Claude Code）

- 分支 claude/stoic-gates-76f17f（worktree），基準 `0d79302`；未 commit。
- 問題：tools/generate_integrated_evidence_report.py 的 Node 卡片寫死 `Node3`，
  缺值時預設 `Taiwan_NeoX-03_169.58`／`NXC400`；pytest raw 卡片寫死
  `422 / 28 / 5` 與「26 failed + 2 broken」，每份報表都顯示舊執行的數字。
- 修正：Node 卡片值取 txt 的 `Node Name`，note 為 `Chassis: <Node Chassis>`，
  缺值顯示 `N/A`。新增 `allure_status_counts()`，由已載入的 Allure result
  統計 passed／failed＋broken／skipped，note 列出 failed 與 broken 各自數量，
  其他狀態另列 unknown。`render_report()` 多一個 `results` 參數（唯一呼叫端
  `write_integrated_evidence_report()` 已同步）。
- 測試：tests/test_reporting.py 的
  `test_write_reports_generates_integrated_evidence_report_by_default` 加入
  failed／broken／skipped 各一筆 Allure result，斷言卡片為 `DemoNode`／
  `Chassis: IES4204` 與 `1 / 2 / 1`、`1 failed + 1 broken`，且不含舊值。
- 驗證：py_compile 通過；`pytest tests/test_reporting.py --skip-dut-preflight -q`
  11 passed。本次 pytest session 自己產生的 integrated 報表卡片為
  `11 / 0 / 0`，與實際結果一致。worktree 內沒有 .venv，使用主 repo 的
  `.venv/Scripts/python.exe` 執行。
- pytest session 寫入的 worktree `reports/`（0 個 case 的報表與
  `.allure-results-current`）經使用者同意已刪除。
- 同一頁寫死的「8 Failures in txt Report」標題已改為 txt 報表實際失敗數
  （與失敗清單同一判定，單數時為 Failure）；tests/test_reporting.py 新增
  0／1／2 筆失敗的斷言。驗證：相關離線測試 61 passed、collect-only 678。

### 2026-10-07 reports/ 整理規劃（Claude Code，僅盤點與規劃）

- 主 repo `reports/` 唯讀盤點：各 build 資料夾的 txt 報表中，0 個 case 的
  空報表 813 份、部分執行 566 份、完整執行（≥200 case）46 份；體積主要是
  Allure 附件（b10 約 991 MB／31 萬檔，已量測的 11 個 build 合計約 1.9 GB）。
- 程式／設定依賴、不可搬動的路徑：`<version>_<target>/`、
  `.allure-results-current/`、`multi_node/`、`device-verification/`、
  `stale_cleanup/`、`swagger-readonly/`、`neox_ug_text.txt`、
  `testlink_backfill_steps.json`。
- 已確認：版本線保存規則（記在 project-context.md「報表保存」）。
- 規劃中（未實作）：原始輸出不動，新增 `reports/_index/`（runs、
  case_history、人工標記的 formal_runs），最上層雜檔依版本號歸到
  `_archive/<版本號>/<用途>/`。
- 已確認：版本順序 b1～b13 → `03.00.11 (AAVV.221)C0`（正式發行，可能另測）
  → `03.00.12 (AAVV.221) b1`。C0 是正式發行版，有問題時會以同一版本字串
  測試好幾次。
- 已確認保存方式（2026-10-07 修正）：使用者會看步驟結果與完整
  request／response，因此保留的執行連同 Allure 一起保留。C0 有測就保留
  C0 各輪；C0 沒測就保留最後一個 build 的正式執行；case_history 全部保留。
- 已確認需求：比對檢視要有步驟差異；未來可能需要跨 build 比對同一步驟的
  request／response。
- 已確認分享範圍：偶爾給老闆或 RD 看，不常發生。
- 使用者確認計畫後完成階段 1a＋1b（未 commit）：
  - 新增 tools/build_report_index.py（索引、case 歷史矩陣、比對與步驟差異）、
    tests/test_report_index.py（9 項）。
  - utils/redaction.py 新增 `redact_text()`（自由文字中的敏感 key=value 遮罩，
    含 devKey）。
  - integrated 報表加入依網址 `#<case ID>` 自動展開該 case 的 script。
  - 用法見 project-context.md「歷史結果查詢與 regression 比對」。
- 驗證：py_compile 通過；test_report_index／test_reporting／test_diagnostics／
  test_run_multi_node／test_service_bundle／test_collection_reporting 69 passed；
  collect-only 666 tests。對主 repo reports/ 實跑（約 13 秒，1425 次執行、
  14 個 build、8 個 node），已寫入 `D:\RestApi auto\reports\_index\`。抽查
  b12_redhat NODE3：11-22-12 251/3、13-34-09 249/5、09-54-36 252/2、judged
  254/0，與先前紀錄一致；b11 → b12_redhat 自動比對列出 Regression 候選
  EMS1-7120（DELETE GE ConnectTimeout）、EMS1-6903（RemoteDisconnected），
  皆標為不穩定，與先前判定（.100 連線中斷）相符。index.html 不含 IP。
- 待使用者：檢視 `reports/_index/index.html`，在 `formal_runs.yaml` 標記各
  build 的正式執行（檔案內已列出目前暫用的執行，取消註解即可）。
- 階段 1c 完成（未 commit）：新增 tools/case_step_diff.py 與
  tests/test_case_step_diff.py；build_report_index 改用其共用的步驟對齊與
  Allure 載入（移除重複實作），新增 `--case`，比對時自動產生
  `_index/cases/` 步驟並排頁。動態欄位清單依實測決定：b12_redhat 兩次
  NODE3 完整執行 6870 個對應附件中 `response.elapsed` 有 3433 個不同。
  實際資料抽查 EMS1-7120（b11 → b12_redhat）：9 個 variant 中只有
  vlan_tls 在 `DELETE /configNeoXSeries/interface/ge/...` 由 passed 變 broken
  （ConnectTimeout），之後步驟缺失；其餘 variant 0 個步驟差異。頁面無 IP，
  sessionid 維持遮罩。已重產 `reports/_index/`，formal_runs.yaml 未被改動
  （檔案 checksum 前後相同）。
- 階段 2 工具完成、尚未搬移：新增 tools/archive_reports.py 與
  tests/test_archive_reports.py。對主 repo reports/ dry run：搬移 74 項
  （25743 檔、60.5 MB），保留 28 項，未分類 0 項；`full-probes`、
  `negative-probes` 因被 configs/neox_config/ge/neox_ge_full_accepted_payload.json
  引用而保留。
- 2026-10-07 經使用者同意執行 `--apply`（執行前確認僅有 D:\EMS web auto 的
  pytest 在跑，不寫入本專案 reports/）：搬移 74 項（probes 20、logs 6、
  runs 8、analysis 12、testlink 28）、25743 檔、60,518,543 bytes 到
  `reports/_archive/03.00.11/`，逐項檢查檔案數與大小皆與 MANIFEST.csv 相符，
  原位置皆已不存在；再次 dry run 無待搬項目。reports/ 最上層剩 29 項。
- 驗證：相關離線測試 81 passed；collect-only 677 tests；compileall 通過
  （tools/check_environment.py 既有的 SyntaxWarning 非本次修改）。
- 尚未做：階段 3（03.00.12 b1 有結果後刪除 03.00.11；刪除前需處理上述
  config 對 b7 報表與 device-verification 的引用）。
- 更正：先前記錄「部分舊報表 Node Name 本身是亂碼」有誤。檢查原始位元組，
  這些值是正確的 UTF-8 中文（`北京_NeoX-03_169.58` 182 份、
  `費城_IES5206_169.54` 1 份），亂碼只是 agent 終端機以 cp950 顯示 UTF-8
  輸出造成；index.html／runs.csv／case_history.csv 皆正確寫入，無 U+FFFD。

### 2026-10-07 commit、push 與合併到預設分支（Claude Code）

- 經使用者確認 staged 清單後，在 claude/stoic-gates-76f17f 建立 `b107aad`
  （卡片修正、索引、步驟比對、歸檔工具、文件，11 個檔案）。
- 合併前 dry run：在 scratch worktree 對 `codex/prepare-github-upload`
  （`0d79302`，本機與遠端相同）執行 `git merge --no-commit --no-ff`，
  "Automatic merge went well"、零衝突，合併結果與 `b107aad` 內容一致，
  相關測試 31 passed；之後 `merge --abort` 並移除 scratch worktree。
- 使用者同意後 push 分支並開 PR #6，CI（compile check、test collection、
  offline unit test）通過，以 merge commit 合併為 `89a6d41`
  （2026-10-07 08:20 UTC）。預設分支 push CI（run 37593066612）
  也通過，約 31 秒。
- 分支 claude/stoic-gates-76f17f 保留；本條 work-status 紀錄在合併後才補，
  尚未進預設分支。

## 下一步

0. b12_redhat 回歸、TestLink 回填與合併都已完成。
0a. .100 連線中斷已判定為 server 資源不足；若 server 資源調整後仍出現，再以報表中
   的時間點查 .100 log，並評估 client 改用共用連線或限定範圍的重試。
0b. 決定上述未納入版控的變更是否收進版控（skill 目錄、qa_bug_drafts、sop、
   已 staged 的刪除）。

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
7. 實作 tools/compare_multi_node_runs.py（介面草稿在
   tmp/handoff_20260930/compare_multi_node_runs_interface.md，tmp/ 不進版控）
   與對應單元測試；完成後把 ems-version-regression 步驟 5.1 改為呼叫此工具。

## 後續更新方式

每個工作條目至少記錄：日期、負責工具、任務、分支／基準 commit、
修改範圍、驗證指令與結果、未執行原因、下一步。
已解決的事項可精簡，尚未完成或缺證據的事項必須保留。
