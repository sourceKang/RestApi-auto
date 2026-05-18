# RestApi Auto 專案指引

## 語言與協作

- 修改前先理解目前專案結構、既有測試方式與設定來源。
- 通用協作、安全與回報規則以 `D:\CodeX\AGENTS.md` 為準；本檔只補充 RestApi Auto 專案細節。

## 專案目標

- REST API 自動化測試架構需簡單、直覺、好維護、好擴充。
- 測試案例應聚焦於「測什麼」，避免重複處理登入、request、config、response parsing。
- 新測試優先使用 `services` fixture 呼叫 `services/` 裡的 domain service。

## 新架構分層

- `clients/` 放 REST API client 與外部 EMS 溝通邏輯。
- `services/` 放各 domain 的測試服務與共用 endpoint case helper。
- `config_loader/` 放設定讀取、profile、hardware、auth 與環境解析邏輯。
- `cases/` 放 endpoint case、payload、case catalog 與資料驅動測試資料。
- `models/` 放 API、case、response 等結構化資料模型。
- `utils/` 放 assertion、Allure、diagnostics、reporting、redaction 等共用工具。
- `tests/` 放 pytest 測試案例；新增測試優先使用 `services` fixture，不要大量複製低階 request 邏輯。
- `tests/support/` 放 pytest options、fixtures、preflight、collection 與 reporting hooks。
- 共用流程優先放 fixture、client、case helper、domain service 或 utility，不在多個測試中複製貼上。

## 測試設計

- 新增測試時，優先使用既有 pytest fixture、marker、CLI option pattern。
- 測試名稱需清楚描述 API 行為或場景。
- 資料驅動測試優先放在 `cases/` 或 `configs/`，避免硬編碼散落在測試檔。
- Assertion 應使用 `utils/assertions.py` 或既有 JSON match helper，讓錯誤訊息可讀。

## 設定與敏感資料

- EMS node、user、slot、port、ONT、topology 等資料需集中管理。
- 需要輸出 request/response/report 時，必須使用 redaction helper 或既有遮罩規則。
- 環境差異應透過 config/profile/pytest option 處理，不要在測試中寫死正式或特定設備資訊。
- `reports/` 視為 generated output；除非使用者明確要求，不要把 Allure 產物或 HTML/txt 報表當作原始碼修改重點或提交內容。
- 只有需要完整 request/response 附件調查時才提高附件詳細度（例如使用 `EMS_ATTACH_FULL_JSON=1`），避免讓 Allure 報告暴增或擴散敏感內容。

## 安全原則

- 可能影響外部 EMS、硬體、正式環境或 destructive flows 的操作，執行前要先詢問。
- 會刪除 alarm、改動設備狀態、開 remote console、provision、cleanup 的測試，不得預設執行。
- 高風險測試需使用明確 pytest option 或 marker，例如 `--run-alarm-delete`、`--run-remote`。

## 驗證

- 修改 Python 程式後，至少執行 compile check。
- 修改 fixture、client、config loader 或 case registry 後，需執行或建議對應 pytest。
- 若測試會連外部 EMS 或設備，執行前需確認目標 node/profile 與風險。
