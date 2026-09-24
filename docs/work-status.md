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

## 下一步

1. 決定 `docs/qa_bug_drafts/`、`docs/sop/` 是否收進版控（SOP 為二進位檔，
   公開前需先解析內容審閱）。
2. 觀察 CI：推送 ab8afb2 到預設分支時觸發了兩個 push run，其中 CI #3 被
   concurrency 設定取消；原因未確認，若後續推送持續重複再查。對
   codex/prepare-github-upload 的 PR 流程尚未實際跑過 CI。
3. 依賴改為手動升級：升級時修改 requirements.txt，並確認 CI 與本機離線
   檢查通過。

## 後續更新方式

每個工作條目至少記錄：日期、負責工具、任務、分支／基準 commit、
修改範圍、驗證指令與結果、未執行原因、下一步。
已解決的事項可精簡，尚未完成或缺證據的事項必須保留。
