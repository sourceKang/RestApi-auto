# 共用工作進度

更新日期：2026-09-24（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Claude Code（本次更新，2026-09-22 ~ 2026-09-24）；先前由 Codex
  建立共用協作入口。
- 分支：codex/neox-profile-read-path-fix（本機工作分支）；已合併進
  codex/prepare-github-upload（GitHub 預設分支）。
- 共用 QA skill 仍以 .codex/skills/qa-bug-report/SKILL.md 為來源，Claude 側
  （.claude/skills/qa-bug-report/SKILL.md）只轉介，未複製業務規則。
- 未新增全域權限設定、MCP 憑證或設備操作自動化。
- Repo 公開性：專案負責人已明確決定維持 Public（自動化測試專案，帳密皆為
  per-person 環境變數，非共用明碼密碼），不需要轉 Private。

## 本次完成的工作

先前「交接前已存在的工作」列出的未提交／未追蹤檔案已全部處理完畢：

- commit `290c45e`（分支 codex/neox-profile-read-path-fix）：整併 16 個檔案，
  修正新機安裝流程（README、tools/check_environment.py、
  docs/SETUP_NEW_MACHINE.md、兩個 configs/*.local.yaml.example）、OpenAPI
  root 寫死路徑（cases/openapi_contract.py 改為 EMS_OPENAPI_ROOT／
  ems.openapi_root 可設定，找不到時 skip 而非 fail）、新增 Claude Code 入口
  （CLAUDE.md、.claude/skills/qa-bug-report/SKILL.md、
  CLAUDE.local.md.example）與 docs/project-context.md、本文。已推送至
  origin/codex/neox-profile-read-path-fix。
- 合併前以獨立 scratch worktree 實際執行 `git merge --no-commit --no-ff`
  驗證零衝突（另一分支的 PR #2 merge commit 對比共同祖先無任何檔案異動），
  才建立 merge commit `040f4c7` 並推送至 origin/codex/prepare-github-upload
  （GitHub 預設分支）。已用 `git ls-tree` 比對兩邊完整檔案樹確認一致。
- 新增 `.github/workflows/ci.yml`：offline-only CI（compileall 全掃、
  `pytest --collect-only --skip-dut-preflight`、
  `pytest tests/test_service_bundle.py --skip-dut-preflight`），跑在
  windows-latest，觸發於 push 到 codex/prepare-github-upload 或
  codex/neox-profile-read-path-fix，以及對 codex/prepare-github-upload 的
  PR。

未處理、仍是 untracked，屬於獨立 housekeeping 決定（與新機安裝無關）：
- `local/`（Redmine／TestLink 稽核資料與暫存資源 registry，提交前需另做
  敏感資料檢查，不可整批加入）
- `docs/qa_bug_drafts/`
- `docs/sop/RestApi_Auto_測試操作_SOP_20260922.docx`

## 本次驗證

- 逐一讀完全部 16 個待提交檔案內容，並對整個 staged diff 做關鍵字掃描
  （password/secret/token/devkey/api_key），確認無明碼密碼或非預期內容。
- Merge 安全性：scratch worktree 內 `git merge --no-commit --no-ff` 顯示
  "Automatic merge went well"，零衝突；merge 後 `git ls-tree` 比對確認檔案
  樹與來源分支完全一致。
- CI 三個步驟均已在本機以模擬的「無 .local.yaml、無 EMS_*/DUT_* 環境變數」
  情境跑過（用 EMS_AUTH_ACCOUNTS_FILE／EMS_TEST_TARGETS_FILE 指向版控範本
  檔案模擬，未動到本機真實 .local.yaml）：
  - `python -m compileall`：0.6 秒，exit 0。
  - `pytest --collect-only --skip-dut-preflight`：647 tests collected，
    collection 本身 0.35 秒（另有數秒到十餘秒屬 reports/ 目錄既有大量歷史
    檔案造成的本機 I/O，已確認 utils/reporting.py 無任何網路呼叫；全新
    checkout 的空 reports/ 目錄預期不會重現此延遲）。
  - `pytest tests/test_service_bundle.py --skip-dut-preflight`：1 passed。
  - 本機測試產生的 reports/ 暫存檔已清除，未影響既有歷史報表。
- 未連線 EMS／DUT，未執行完整 regression、NeoX CLI → REST → CLI 或外部
  系統寫入。

## 下一步

1. ~~確認 CI workflow 推送後在 GitHub Actions 的第一次實際執行結果~~ ——
   已確認：push 到 origin/codex/neox-profile-read-path-fix 後，
   GitHub Actions 上的 "CI #1"（commit `3d64803`）實際執行成功，
   34 秒完成，與本機模擬結果一致。尚未在 codex/prepare-github-upload
   （預設分支）或實際 PR 上驗證過。
2. 決定 `local/`、`docs/qa_bug_drafts/`、`docs/sop/` 是否要收進版控（獨立
   housekeeping 決定，需先對 `local/` 做敏感資料檢查）。
3. 視需要鎖定 requirements.txt 版本範圍（目前全部為 `>=`，長期可能影響
   環境可重現性）。

## 後續更新方式

每個工作條目至少記錄：日期、負責工具、任務、分支／基準 commit、
修改範圍、驗證指令與結果、未執行原因、下一步。
已解決的事項可精簡，尚未完成或缺證據的事項必須保留。
