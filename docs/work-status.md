# 共用工作進度

更新日期：2026-09-24（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Claude Code（2026-09-22 ~ 2026-09-24）；先前由 Codex 建立共用
  協作入口。
- 分支：codex/neox-profile-read-path-fix（工作分支）。每批變更先在 scratch
  worktree 做 `git merge --no-commit --no-ff` dry run，確認零衝突後才合併進
  codex/prepare-github-upload（GitHub 預設分支）。
- 共用 QA skill 仍以 .codex/skills/qa-bug-report/SKILL.md 為來源，Claude 側
  （.claude/skills/qa-bug-report/SKILL.md）只轉介，未複製業務規則。
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

## 下一步

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

## 後續更新方式

每個工作條目至少記錄：日期、負責工具、任務、分支／基準 commit、
修改範圍、驗證指令與結果、未執行原因、下一步。
已解決的事項可精簡，尚未完成或缺證據的事項必須保留。
