# Codex 與 Claude Code 共用專案脈絡

本文件提供接手所需的入口與已確認的操作方式；強制規範以
[AGENTS.md](../AGENTS.md) 為共用來源，進度見
[work-status.md](work-status.md)。程式、設定與規格變更後，應同步校正文中的對應說明。

## 文件與責任

| 來源 | 用途 |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | 共用工程、安全、驗證及報表規範；Codex 入口 |
| [CLAUDE.md](../CLAUDE.md) | Claude Code 入口，以 @AGENTS.md 載入共用規範 |
| [README.md](../README.md) | 安裝、runner、測試與報表使用方式 |
| [新增測試指南](ADDING_TESTS.md) | services fixture 與測試分層 |
| [YAML 設定說明](yaml_configuration.md) | 設定結構 |
| [OpenAPI 版本防護](openapi_version_guard.md) | 規格來源與版本比對 |
| [新機建置指南](SETUP_NEW_MACHINE.md) | 本機建置；本次接手時仍屬既有未提交文件，須另行審閱 |
| [ADR](adr/0001-session-cache-and-safe-auth-retry.md) | Session cache 與 auth retry 決策 |
| [工作進度](work-status.md) | 可更新的接續快照，不代表測試結果永久有效 |

## 架構與查找入口

本專案是 Python／pytest 的 NetAtlas EMS REST API 自動化框架。
依賴方向與目錄責任見 AGENTS.md；具體入口如下：

- conftest.py：匯出 tests/support 下的 fixtures 與 hooks。
- tests/support/options.py：pytest CLI options 與環境選項。
- tests/support/fixtures.py、service_bundle.py：services 聚合 fixture 與 domain service 組裝。
- tests/support/collection.py、preflight.py、target_sync.py：測試收集、DUT 檢查與 CLI 同步。
- tests/support/reporting_hooks.py、utils/reporting.py：結果與 HTML／Allure 報表。
- config_loader/settings.py、auth.py、hardware.py、simple_yaml.py：環境、帳號、設備與變數解析。
- cases/registry.py、case_catalog.py、neox_case_ids.py：案例與 TestLink ID 對應。
- services/neox_config/、configs/neox_config/：NeoX 行為與資料；兩者應一起理解。

## 環境與設定

使用 Python 3.11 以上及 requirements.txt。Windows 專案環境通常是
.venv/Scripts/python.exe；每個 worktree／新電腦需確認可用的 interpreter，
不要假設虛擬環境或私有檔案會被 Git 帶過去。

已核對 loader 的設定來源：

| 設定 | 來源與順序 |
| --- | --- |
| EMS | 明確傳入 loader 的 path → EMS_YAML_FILE → configs/ems.yaml |
| 帳號 | EMS_AUTH_ACCOUNTS_FILE → configs/auth_accounts.local.yaml → configs/auth_accounts.yaml |
| DUT | EMS_TEST_TARGETS_FILE → configs/test_targets.local.yaml → configs/test_targets.yaml |
| dotenv | EMS_ENV_FILE 或根目錄 .env；既有程序環境變數不被覆蓋 |
| OpenAPI | 由 cases/openapi_contract.py 解析 EMS_OPENAPI_YAML_FILE、EMS_OPENAPI_ROOT 與 ems.openapi_root；該檔目前有既有未提交變更，接手時再確認版本與可用性 |

實際帳密留在被忽略的本機檔案或環境變數。不要把整份私有 config、.env、
request／response 或 MCP 設定原文放進交接文件。
EMS version、node、slot、card、port、ONT 與 auth profile 以當次設定及設備證據為準。

## 本機檢查與外部驗證

從專案根目錄執行，先確認 interpreter 存在：

~~~powershell
git status -sb
git diff --stat
.\.venv\Scripts\python.exe --version
~~~

修改 Python 時，只對修改檔案做 compile check，例如：

~~~powershell
.\.venv\Scripts\python.exe -m py_compile path/to/changed_file.py
~~~

上述 path/to/changed_file.py 是佔位，必須替換為實際修改檔案。

小範圍的離線 service 組裝檢查：

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_service_bundle.py -q
~~~

此案例使用本機 object 組裝 service，不呼叫 EMS；全域 fixture／報表 hook
仍會讀取本機設定並產生 reports，因此需要可解析的環境設定。
這只是基礎檢查，不代表所有 service、API 或設備測試通過。

既有 tools/check_environment.py 支援 --no-network，可供本機環境診斷；
本次未對其完整正確性背書。未加此選項會執行網路檢查。
該工具在本次交接前已是未提交檔案，後續需隨新機指南一起審閱。

**不要把 pytest --collect-only、-m smoke 或 -m openapi 視為離線保證。**
collection hook 在收集階段會依 DUT markers 執行 preflight；
OpenAPI 測試檔也包含 live_swagger 案例。--skip-dut-preflight
只略過前置檢查，不會阻止測試本身連線或變更設備。

完整 regression、live Swagger、NeoX、remote、provision 或 cleanup，
須先依 AGENTS.md 確認 node／profile、風險與使用者授權，再選擇明確的測試檔、
markers 與 options。NeoX 設定仍需完成 CLI baseline → REST → CLI；
不得把 REST-only 結果宣稱為完整 NeoX 驗證。

## 雙工具工作流程

### 輪流接手

1. 讀取共用規範、本文及 work-status.md。
2. 核對 git status -sb、git log -1 與 git diff --stat；不要把前一位未提交工作當成自己的變更。
3. 先確認接續目標與證據，完成最小完整變更及對應驗證。
4. 更新工作進度中的修改範圍、已執行／未執行驗證與下一步。
5. 提交前審閱實際 staged 清單與 diff；授權範圍內的檔案才可提交。

### 同時工作

每個工具使用獨立 worktree 與分支。由目前已確認的 HEAD 建立新 worktree 的範例：

~~~powershell
git worktree add ../restapi-claude -b claude/task-name HEAD
~~~

task-name 與目標路徑需依任務調整，建立前先確認沒有同名分支／目錄。
Codex 新分支預設使用 codex/ 前綴；Claude 可使用 claude/ 前綴。
worktree 不會複製目前未提交變更或被忽略的本機設定；需要的程式應先經審閱，
以 commit／整合流程帶到新分支，再配置該 worktree 的本機環境。

worktree 只隔離檔案，不隔離 EMS／DUT。兩個工具不得同時使用衝突的帳號 session、
相同可變測資或同一設備做破壞性測試。依獨立 auth profile 與資源配置協調，
並遵守外部操作授權。

work-status.md 在各分支也是各自副本；整合時保留雙方工作條目及證據，
不要用整份覆蓋方式消掉另一個工具的進度。

## Skills 與外部整合

- QA bug 的流程來源仍是 [.codex/skills/qa-bug-report/SKILL.md](../.codex/skills/qa-bug-report/SKILL.md)。
- Claude 的 [.claude/skills/qa-bug-report/SKILL.md](../.claude/skills/qa-bug-report/SKILL.md)
  只負責載入共用內容；Codex 保留原入口。
- 對外工具可能包含 Redmine、TestLink 或其他 MCP／插件；是否可用須在各工具中實際確認，
  不假設 Codex 的連線、登入或個人插件可直接被 Claude 使用。
- 本次不建立含憑證的 .mcp.json，也不預設放寬工具權限。
  外部整合未配置時先交付可審閱草稿；發送／寫入遵循既有規範與 skill 的批准流程。
- 本機偏好範本為 [CLAUDE.local.md.example](../CLAUDE.local.md.example)；
  實際 CLAUDE.local.md 與 .claude/settings.local.json 不進版控。

## Claude 首次啟動確認

在專案根目錄啟動 Claude Code，使用 /context 查看 Memory files，
確認 CLAUDE.md 與其引入的 AGENTS.md 已載入。
請它讀取本文和 work-status.md，回報分支、未提交檔案、可用的離線驗證與下一步。
檢查 /qa-bug-report 是否可用；不要以實際發送 bug 來測試 skill。

此設定使用官方文件中的 CLAUDE.md imports 與 .claude/skills 入口：
[記憶與指引](https://code.claude.com/docs/en/memory)、
[Skills](https://code.claude.com/docs/en/skills)。
Markdown 指引是行為約定，不是技術上的網路隔離或權限攔截器。
