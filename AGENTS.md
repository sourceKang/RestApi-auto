# RestApi Auto 專案指引

本檔是 Codex 與 Claude Code 共用的強制規範，只放每次都需遵守的規則；細節依下列文件按需讀取：

- [專案脈絡與操作](docs/project-context.md)：架構入口、設定來源、EMS server 切換、雙工具工作流程。
- [工程分析與設計準則](docs/engineering-guidelines.md)：第一性原理、目錄責任、ADR、API／測試細則、config 提交、工具使用與搜尋、Review 檢查清單、平行子代理、Retro。設計修正、分析失敗、review 或搜尋大量檔案前讀。
- [報表輸出格式](docs/report-format.md)：測試／QA 報表與任務總結頁。產出報表時讀。

## 協作

- 開始工作先讀 docs/work-status.md（最近狀態與下一步；查舊紀錄才讀 docs/work-history/<YYYY-MM>.md），並確認 Git 分支、HEAD、未提交變更及相關子目錄指引；文件進度只是快照，以當下程式與驗證證據為準。
- 保留前一位的未提交變更，不逕自還原、覆蓋或納入提交；同時修改時各用獨立 worktree 與分支。worktree 不隔離 EMS 帳號或設備，外部測試仍需協調資源及授權。
- 完成實質工作或交接前，更新 work-status.md 的負責工具、分支／基準 commit、修改範圍、驗證結果、未完成事項與下一步；不記錄密碼、token 或未經證實的 Root Cause。
- 共用規則只在本檔維護，不在工具入口複製第二份。

## 核心原則

- 預設使用繁體中文。
- 未知資訊若會實質改變結果且無法由本地證據確認，才向使用者詢問，不臆測。
- 完成最小、完整、可驗證且位於正確責任層的修正，不是只讓測試通過；不得以放寬 assertion、吞 exception、固定 sleep 或硬編碼 ID 掩蓋問題。
- 新測試優先使用 `services` fixture 與既有 fixture、marker、CLI option pattern。
- 規則衝突時，優先序為：安全與使用者明確授權 → 最新規格與證據 → 架構與責任分層 → 最小完整變更 → 輸出格式。

## 架構

```text
tests
  → services / fixtures
  → clients
  → config_loader / models / utils
```

底層不得反向依賴 tests 或特定 testcase；改變分層或公共介面前先說明影響。

## NeoX config 驗證

涉及 NeoX 設定變更時依序執行：

1. **CLI baseline**：以相同設定確認 CLI 可成功套用並生效。
2. **REST API**：baseline 成功後才測試相同情境。
3. **CLI ground truth**：REST 執行後以 show 指令確認設定確實落地。

若 CLI baseline 失敗，視為設備或環境問題，停止 REST 驗證，不得列為 API bug。

## 敏感資料與 EMS target

- EMS server 由 `configs/ems.yaml` 的 `ems.targets` 搭配 `EMS_TARGET` 選擇。連線外部 EMS 前，先確認所選 target 與 node 實際納管的 server 一致；node 搬移由使用者手動進行。
- request、response、log、attachment、report 一律遮罩 devKey、密碼、token、ONT password 等敏感資料。
- `configs/auth_accounts.yaml` 禁止提交明文密碼、token、devKey 或真實帳號（CI 以 `tools/check_config_secrets.py` 檢查 configs）；commit/push 前檢查 `git status -sb` 與 staged diff。

## 外部整合與安全

- TestLink、Redmine 等外部 API 使用指數退避 Retry，並加入請求間隔或限速。
- 任何會影響外部 EMS、硬體、正式環境或具破壞性的操作，執行前先取得使用者確認。
- 刪除 alarm、變更設備狀態、remote console、provision、cleanup 等不得預設執行，必須使用明確 option/marker（如 `--run-alarm-delete`、`--run-remote`）。
- 破壞性測試在正向、負向與邊界案例完成後才執行；使用拋棄式資料，結束後確認設備快照或還原。

## 驗證

- 修改 Python 後至少執行 compile check；修改 fixture、client、config loader 或 case registry 後執行對應 pytest。
- EMS REST 可能非同步生效：以含 timeout 與指數退避的 GET polling 驗證最終狀態；`429` 退避重試，不視為產品 bug。
- 連線外部 EMS 或設備前確認 node/profile 與操作風險。

## 回報格式

- 改檔或跑測試前：先列「主目標 → 子目標」（5 行內），每個子目標寫完成條件，接著直接做。
- 完成回報 10 行內，三段：結論（附「子目標完成 X／Y」）→ 重點最多 3 點 → 下一步 2～3 步。測試只寫「通過 X／失敗 Y」，有失敗才列原因；不重貼程式碼。
- 測試／QA 報表與任務總結頁依 [報表輸出格式](docs/report-format.md)。
