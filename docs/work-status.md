# 共用工作進度

更新日期：2026-09-22（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Codex。
- 目標：保留 Codex 工作方式，新增 Claude Code 入口，共用規範與接續文件。
- 盤點分支：codex/neox-profile-read-path-fix。
- 盤點基準 HEAD：c75cb35（fix: block false-green multi-node results）。
- 本次修改：AGENTS.md 增加共用協作入口；新增 CLAUDE.md、
  CLAUDE.local.md.example、docs/project-context.md、本文及 Claude QA skill 入口；
  .gitignore 補上本機 Claude 檔案排除。
- 共用 QA skill 仍以 .codex/skills/qa-bug-report/SKILL.md 為來源，未複製另一份業務規則。
- 未新增全域權限設定、MCP 憑證或設備操作自動化；未 commit／push。

## 交接前已存在的工作

下列檔案是本次開始前即有的變更；僅記錄範圍，未驗證其功能正確性，
也不推定其作者或完成狀態。

已修改：
- README.md
- cases/openapi_contract.py
- configs/ems.yaml
- docs/redmine_bug_template.md
- tests/test_openapi_yaml.py

未追蹤：
- configs/auth_accounts.local.yaml.example
- configs/test_targets.local.yaml.example
- docs/SETUP_NEW_MACHINE.md
- docs/qa_bug_drafts/
- docs/sop/
- local/
- tools/check_environment.py

接續時優先確認上述工作要完成、審閱或提交哪一部分。
local/ 與設定檔提交前須另做敏感資料檢查，不可整批加入。
不得因共用文件已建立，就把既有 OpenAPI／新機建置／bug 草稿視為已完成驗證。

## 本次驗證

- 已讀取實際 AGENTS.md、pytest 設定、fixture／collection／preflight、
  config loader 與既有 QA skill，並核對官方 Claude 指引。
- 文件檢查：19 個本機 Markdown 連結存在；CLAUDE.md 的 @AGENTS.md 引入已確認。
- Git 檢查：git diff --check 通過；CLAUDE.local.md 與 .claude/settings.local.json 被忽略，五個新增共用檔案均未被忽略。
- Skill 格式：以 Python -X utf8 執行 skill-creator/scripts/quick_validate.py .claude/skills/qa-bug-report，結果 Skill is valid。Windows 預設 cp950 無法解碼此 UTF-8 skill，故驗證時明確指定 UTF-8。
- 最小離線測試：.venv/Scripts/python.exe -m pytest tests/test_service_bundle.py -q，結果 1 passed（Python 3.12.14／pytest 9.0.3）。
- 本次未修改 Python，無需新增 compile check；上面的測試只證明 service 組裝案例通過，不代表既有未提交變更或完整 regression 通過。
- Claude 執行檔在目前 PATH 未找到；未進行 Claude runtime 的載入與 skill 觸發測試。
- 未連線 EMS／DUT，未執行完整 regression、NeoX CLI → REST → CLI 或外部系統寫入。

## 下一步

1. 在 Claude Code 開啟專案，依 project-context.md 的首次啟動流程確認指引及 skill 載入。
2. 依使用者當次目標接續既有工作，補上各項實際驗證結果。
3. 若要同時開發，先整合需要共享的變更，再建立獨立 worktree；確認本機設定和設備資源分配。

## 後續更新方式

每個工作條目至少記錄：日期、負責工具、任務、分支／基準 commit、
修改範圍、驗證指令與結果、未執行原因、下一步。
已解決的事項可精簡，尚未完成或缺證據的事項必須保留。
