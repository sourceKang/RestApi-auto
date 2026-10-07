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
| EMS | 明確傳入 loader 的 path → EMS_YAML_FILE → configs/ems.yaml；有 ems.targets 時以 EMS_TARGET → ems.default_target 選 server（ubuntu 192.168.128.8、redhat 192.168.128.100），由 config_loader.settings.load_ems_settings 統一解析 |
| 帳號 | EMS_AUTH_ACCOUNTS_FILE → configs/auth_accounts.local.yaml → configs/auth_accounts.yaml |
| DUT | EMS_TEST_TARGETS_FILE → configs/test_targets.local.yaml → configs/test_targets.yaml |
| dotenv | EMS_ENV_FILE 或根目錄 .env；既有程序環境變數不被覆蓋 |
| OpenAPI | 由 cases/openapi_contract.py 解析 EMS_OPENAPI_YAML_FILE、EMS_OPENAPI_ROOT 與 ems.openapi_root；該檔目前有既有未提交變更，接手時再確認版本與可用性 |

實際帳密留在被忽略的本機檔案或環境變數。不要把整份私有 config、.env、
request／response 或 MCP 設定原文放進交接文件。
EMS version、node、slot、card、port、ONT 與 auth profile 以當次設定及設備證據為準。

### EMS server 切換

實驗室有兩台 EMS 輪流測試，設定在 configs/ems.yaml 的 `ems.targets`：

| target | EMS | 平台 | 說明 |
| --- | --- | --- | --- |
| `redhat`（`default_target`） | 192.168.128.100 | RedHat 9 HA | 目前僅支援 NeoX 系列設備 |
| `ubuntu` | 192.168.128.8 | Ubuntu | |

- 切換方式：PowerShell 執行 `$env:EMS_TARGET = "ubuntu"`；沒設定時使用
  `default_target`。target 的版本字串寫在各自的 `version`。
- 兩台 EMS 不會同時納管同一個 node。測試前由使用者手動把 node 移到要測的
  server；agent 不得自行搬移 node，也不要假設 node 在哪台上。
- 連線外部 EMS 前，先用 `tools/run_multi_node.py --nodes <N> --dry-run` 確認
  輸出的 `EMS:` 行（target／platform／version／URL）是預期的 server。
- 報表輸出到 `reports/<version>_<target>/`，報表內記錄 `EMS Target`、
  `EMS Platform`。TestLink build 依平台加後綴，例如 `03.00.11 (AAVV.221) b12_redhat`。
- `.100` 是全新安裝：舊版腳本留在 `.8` 的 EMS 層測資（例如 provision profile）
  在 `.100` 上不存在；測試需要的前置資料要由測試自行建立。
- `.100` 在密集連線時偶有 connect timeout／connection reset（使用者判定為
  server 資源不足，2026-10-02）。這類失敗先單獨重跑確認，不列為 API bug。
- 完整測試約 1.5 小時，超過 agent 背景工作的時間上限（30 分鐘）；需要長時間執行時
  改用獨立程序（例如 PowerShell `Start-Process`）並另外監看結果。

### 報表保存

- 以版本號區分版本線（例如 `03.00.11`、`03.00.12`），專案代碼
  `(AAVV.221)` 不用來區分。版本順序：`03.00.11 (AAVV.221) b1`～`b13` →
  `03.00.11 (AAVV.221)C0`（正式發行，可能另外測試）→ `03.00.12 (AAVV.221) b1`。
  C0 若有問題會以相同版本字串測試好幾次，各次只能以執行時間區分。
- 下一條版本線的第一個 build 有測試結果後，前一條版本線的所有 build 報表
  即可刪除。例：`03.00.12 (AAVV.221) b1` 有結果後，刪除
  `03.00.11 (AAVV.221)` 的 b1～b13（含 `b12_redhat` 等 target 變體）
  （使用者確認，2026-10-07）。
- 刪除時保留比對基準，且保留的執行連同 Allure 原始資料一起保留（步驟的完整
  request／response 只在 Allure，integrated 報表每個附件只預覽 6000 字）：
  C0 有測就保留 C0 各輪；C0 沒測就保留最後一個 build 的正式執行。
  一次 NODE3 完整執行的 Allure 約 8 MB／1 萬檔。
- 刪除前先列出清單與大小給使用者確認；agent 不自行永久刪除。
- 刪除前也要檢查版控檔案是否引用要刪的報表：例如
  `configs/neox_config/ge/neox_ge_full_accepted_payload.json` 以
  `reports/03.00.11 (AAVV.221) b7/...txt`、`reports/device-verification/...`、
  `reports/full-probes/`、`reports/negative-probes/` 作為佐證來源。
- 最上層零散檔案用 `tools/archive_reports.py --version-line <版本號>` 歸到
  `reports/_archive/<版本號>/<logs|testlink|probes|runs|analysis>/`；預設只列出
  計畫，加 `--apply` 才搬移（不刪除），並記錄在該資料夾的 MANIFEST.csv。
  程式固定讀寫的路徑、build 資料夾、`YYYYMMDD_` 統整報表，以及版控檔案中
  出現 `reports/<名稱>` 的項目都會保留原位。

### 歷史結果查詢與 regression 比對

`tools/build_report_index.py` 掃描 `reports/<version>[_<target>]/*.txt` 與
`reports/multi_node/*/summary.json`，在 `reports/_index/` 產生索引（只新增
索引檔，不搬動或修改既有報表；約十幾秒）：

~~~powershell
.\.venv\Scripts\python.exe tools/build_report_index.py
.\.venv\Scripts\python.exe tools/build_report_index.py --compare "03.00.11 (AAVV.221) b12_redhat" "03.00.11 (AAVV.221) b13" --node NODE3
~~~

- `index.html`：各 node 最新比對（Regression 候選／既有問題／已修復／
  新增／移除，含第一個狀態不同的步驟與失敗訊息）、case × build 歷史矩陣、
  所有執行清單。結果連到 integrated 報表的 `#<case ID>`，開啟時自動展開步驟。
- `runs.csv`、`case_history.csv`：每次執行／每個 case 每次執行一列。
- `formal_runs.yaml`：人工標記各 build × node 的正式判定執行（C0 可列多輪，
  `final: true` 為最終輪）；工具不會覆寫。未標記時暫用該 build 最後一次完整
  執行（≥ 同 build 最大 case 數 80%，且 ≥ 版本線最大 case 數 50%）。
- `--compare` 的參數可為 build 目錄（取 `--node` 的正式執行）或
  `<build 目錄>/<run_id>`；加 `--case <case ID>` 只產生該 case 的步驟並排頁。
- 比對中結果有變化或持續失敗的 case 會產生 `_index/cases/` 步驟並排頁：
  逐步對齊兩次執行，列出 request／response 欄位差異與兩邊完整 JSON。
  request URL 的 EMS 主機會先去除；耗時、時間、告警流水號、光功率標為
  「可能為動態值」，顯示但不計入差異數（依兩次 NODE3 完整執行實測）。
- node 以報表的 `Node IP` 對應有 `_NODEx` 標籤的報表；步驟差異的訊息會遮罩
  敏感值與 IP。

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
仍會讀取本機設定，因此需要可解析的環境設定。沒有任何 TestLink case 結果的
session（離線單元測試、`--collect-only`）不寫 txt／html／integrated 報表，
只輸出 `EMS report: skipped; ...`；`reports/.allure-results-current/` 仍是
Allure 的暫存目錄，下次執行開始時會清空。
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
