# RestApi Auto 專案指引

## Codex 與 Claude Code 共用協作

- 本檔是兩個工具共用的規範來源；CLAUDE.md 引入本檔，只補 Claude 專用入口。
- 開始工作先讀 docs/project-context.md 與 docs/work-status.md，再確認目前 Git 分支、HEAD、未提交變更及相關子目錄指引；文件中的進度只是快照，以當下程式與驗證證據為準。
- 輪流接手時保留前一位的未提交變更，不逕自還原、覆蓋或納入提交。同時修改時使用各自獨立的 worktree 與分支；worktree 不會隔離 EMS 帳號或設備，外部測試仍需協調資源及授權。
- 完成實質工作或交接前，更新 docs/work-status.md 的負責工具、分支／基準 commit、修改範圍、驗證結果、未完成事項與下一步。不要記錄密碼、token 或未經證實的 Root Cause。
- 在不同 worktree 接續前先整合相關程式與進度文件；聊天記憶、個人工具設定和未提交檔案不會自動同步。
- 共用規則在本檔維護；架構與操作說明在 docs/project-context.md 維護。避免在工具入口複製另一份規則或流程。

## 核心原則

- 預設使用繁體中文。
- 修改前先理解現有架構、測試方式與設定來源；未知資訊若會實質改變結果，且無法由本地證據確認，才向使用者詢問，不臆測。
- 目標是完成最小、完整、可驗證且位於正確責任層的修正，不是只讓測試通過。
- 架構維持簡單、直覺、可維護；測試聚焦「測什麼」，登入、request、config、parsing 交給共用層。
- 新測試優先使用 `services` fixture 與既有 fixture、marker、CLI option pattern。
- 規則衝突時，優先序為：安全與使用者明確授權 → 最新規格與證據 → 架構與責任分層 → 最小完整變更 → 輸出格式。

## 第一性原理分析與決策

從可驗證事實出發，先拆解需求與限制，不將既有實作或慣例當成未經驗證的前提。修改前依序確認：

1. **目標與限制**：預期行為、相容性、安全限制及不可破壞的行為。
2. **事實與未知**：區分已確認事實、有證據支持的推論、尚未確認的假設。
3. **問題層級**：Requirement/OpenAPI、test data、fixture/hook、service、client、config、EMS、Device/CLI/Hardware 或外部環境。
4. **修正位置**：在最接近原因與責任來源的層級修正，不由 testcase 補償底層缺陷。
5. **驗證方式**：先做最小範圍驗證，再做受影響範圍 regression。

Ground Truth：

- API contract：最新 OpenAPI、正式文件及已確認的版本差異。
- Device：CLI、設備狀態及 Hardware Capability。
- EMS：實際 request/response、log 與最終狀態。
- 測試框架：可重現測試、fixture 流程與執行結果。

現有程式碼與舊測試僅是歷史證據，不自動等同正確規格。證據不足時，不得把假設描述為 Root Cause。

分析 bug 或測試失敗時，需確認可重現症狀、預期與實際行為、最小觸發條件、因果鏈及修正點。新增功能或重構不必虛構 Root Cause，但需說明需求、限制與設計理由。

不得以以下方式掩蓋問題：

- 放寬正確 assertion、吞掉 exception 或忽略錯誤。
- 用固定 sleep 掩蓋非同步狀態。
- 硬編碼環境、設備或資源 ID。
- 在 testcase 複製或補償共用層行為。

若外部 EMS、Device 或第三方限制迫使使用 workaround，需限制在最小範圍、保留 diagnostics、說明證據與移除條件，且不得影響正常情境。

## 架構與設計

依賴方向：

```text
tests
  → services / fixtures
  → clients
  → config_loader / models / utils
```

- `clients/`：REST client、EMS 溝通。
- `services/`：domain 測試服務、共用 case helper。
- `config_loader/`：config、profile、hardware、auth、環境解析。
- `cases/`：endpoint case、payload、資料驅動內容。
- `models/`：API、case、response model。
- `utils/`：assertion、Allure、diagnostics、reporting、redaction。
- `tests/`：pytest 案例；避免低階 request 邏輯。
- `tests/support/`：pytest options、fixtures、preflight、collection、reporting hooks。

共用邏輯放在對應 fixture、client、service、helper 或 utility；底層不得反向依賴 tests 或特定 testcase。只在相同業務規則或 policy 重複時抽象，不為文字相似或未確認的未來需求新增 framework、inheritance、generic abstraction 或 config。

若正確修正需改變既有分層或公共介面，先說明影響。主要分層、公共介面、核心 config/schema/profile、全域 polling/retry/error policy、主要 dependency 或外部整合方式改變時，考慮建立 ADR；至少記錄 Context、Decision、Alternatives、Consequences、Validation。小型修正通常不需要 ADR。

## API 與測試

- EMS REST 下令後可能非同步生效；以含 timeout 與指數退避的 GET polling 驗證最終狀態，不只斷言同步 response。
- `429`/`Retry-After` 需退避重試；限流失敗不視為產品 bug。
- 測試名稱需描述行為與場景；資料驅動內容放 `cases/` 或 `configs/`。
- Assertion 使用 `utils/assertions.py` 或既有 helper。
- 上游資料以動態 fixture 傳遞 context，不寫死或猜測 ID；fixture 負責 teardown。
- 測試需可重跑（idempotent），中途失敗也能清理。
- 破壞性案例使用拋棄式專屬測資，不與正向案例共用。

### NeoX config 驗證

涉及 NeoX 設定變更時依序執行：

1. **CLI baseline**：以相同設定確認 CLI 可成功套用並生效。
2. **REST API**：baseline 成功後才測試相同情境。
3. **CLI ground truth**：REST 執行後以 show 指令確認設定確實落地。

若 CLI baseline 失敗，視為設備或環境問題，停止 REST 驗證，不得列為 API bug。

## 設定、規格與敏感資料

- EMS node/user/slot/port/ONT/topology 集中管理；slot 與 card type 必須符合環境。
- 環境差異透過 config、profile 或 pytest option 處理，不硬編碼特定環境資訊。
- 修改 Swagger/OpenAPI/schema 比對前，確認 `NetAtlasEMS_OpenAPI_*.yaml` 為最新版本。
- 回歸前先做 spec/schema diff；遇 breaking change 時依差異更新測試。
- request、response、log、attachment、report 一律遮罩 devKey、密碼、token、ONT password 等敏感資料。
- `reports/` 是 generated output，除非使用者要求，不作為主要修改範圍。
- 僅在需要完整附件調查時啟用 `EMS_ATTACH_FULL_JSON=1`。

## Git 與 config

更新 GitHub 前檢查 `git status -sb`、staged 清單與 staged diff，避免混入非預期或敏感內容。

- `configs/neox_config/**`：可與相關測試或服務一併提交。
- `configs/ems.yaml`、`configs/hardware_matrix.yaml`、`configs/test_targets.yaml`：確認無帳密或 token 後可提交。
- `configs/auth_accounts.yaml`：禁止提交明文密碼、token、devKey 或真實帳號；改用 placeholder、環境變數或 sanitized template。
- 本機私有 config 保持 unstaged；commit/push 前再次確認 staged 清單。

## 外部整合與安全

- TestLink、Redmine 等外部 API 使用指數退避 Retry，並加入請求間隔或限速。
- 任何會影響外部 EMS、硬體、正式環境或具破壞性的操作，執行前先取得使用者確認。
- 刪除 alarm、變更設備狀態、remote console、provision、cleanup 等不得預設執行，必須使用明確 option/marker（如 `--run-alarm-delete`、`--run-remote`）。
- 破壞性測試在正向、負向與邊界案例完成後才執行；使用拋棄式資料，結束後確認設備快照或還原。

## 驗證

- 修改 Python 後至少執行 compile check。
- 修改 fixture、client、config loader 或 case registry 後執行對應 pytest。
- 非同步狀態需驗證最終結果；NeoX config 需完成 CLI → REST → CLI。
- 連線外部 EMS 或設備前確認 node/profile 與操作風險。
- 完成後確認 redaction、idempotency、cleanup、相容性，以及是否需更新文件、設定範例或 ADR。

## Report 輸出

彙整測試、照片或 Redmine/TestLink 比對、QA summary 時，預設產出瀏覽器可開啟的 HTML report，放在 `reports/`，檔名包含日期、EMS version 與 node；Markdown 僅作草稿。

- 首屏先給結論，再呈現環境、pytest、TestLink/txt、失敗清單、逐項比對與「已解／未解／部分／需確認」狀態。
- 有 Allure raw results 時解析重點。每個 testcase 至少可查到 nodeid、TestLink case ID、title、status、duration、request、EMS response、CLI 驗證、failure/traceback/contract diff 與附件摘要。
- 大型 request/response、CLI output、traceback 另存檔案；報表只放摘要與連結。
- 保留原始 txt、HTML、Allure raw、log 的回查連結；所有內容先完成 redaction。
