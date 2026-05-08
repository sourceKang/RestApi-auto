# 全域 Codex 指引

## 基本偏好

- 預設使用繁體中文回覆。
- 若使用者要求先說明計畫，執行前要先提出計畫並等待確認。
- 回覆保持清楚、精簡、可執行。

## 工作原則

- 修改前先理解目前專案結構與既有規則。
- 優先遵循目前 repository 的既有 patterns、tools 與測試方式。
- 不要主動新增 dependencies，除非使用者同意或專案已經使用。
- 不要 revert 或覆蓋使用者既有修改，除非使用者明確要求。

## 安全原則

- 不要把 API keys、tokens、passwords、session IDs 或私人 credentials 寫入檔案。
- 可能影響外部系統、硬體、正式環境或 destructive flows 的操作，執行前要先詢問。

## 驗證

- 修改後要說明改了什麼，以及已執行或建議執行的驗證方式。

--- project-doc ---

# RestApi Auto 專案指引

## 語言與協作

- 預設使用繁體中文回覆。
- 若使用者要求先說明計畫，執行前要先提出計畫並等待確認。
- 回覆保持清楚、精簡、可執行。
- 修改前先理解目前專案結構、既有測試方式與設定來源。

## 專案目標

- REST API 自動化測試架構需簡單、直覺、好維護、好擴充。
- 測試案例應聚焦於「測什麼」，避免重複處理登入、request、config、response parsing。
- 新測試優先使用 `services` fixture 呼叫 `services/` 裡的 domain service。
- 不要主動新增 dependencies，除非使用者同意或專案已經使用。

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
- 不要把 API keys、tokens、passwords、session IDs 或私人 credentials 寫入檔案。
- 需要輸出 request/response/report 時，必須使用 redaction helper 或既有遮罩規則。
- 環境差異應透過 config/profile/pytest option 處理，不要在測試中寫死正式或特定設備資訊。

## 安全原則

- 可能影響外部 EMS、硬體、正式環境或 destructive flows 的操作，執行前要先詢問。
- 會刪除 alarm、改動設備狀態、開 remote console、provision、cleanup 的測試，不得預設執行。
- 高風險測試需使用明確 pytest option 或 marker，例如：
  - `--run-alarm-delete`
  - `--run-remote`
- 不要 revert 或覆蓋使用者既有修改，除非使用者明確要求。

## 驗證

- 修改 Python 程式後，至少執行 compile check。
- 修改 fixture、client、config loader 或 case registry 後，需執行或建議對應 pytest。
- 若測試會連外部 EMS 或設備，執行前需確認目標 node/profile 與風險。
- 回覆需說明改了什麼，以及已執行或建議執行的驗證方式。
