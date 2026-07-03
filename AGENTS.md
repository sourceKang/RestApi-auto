# RestApi Auto 專案指引

## 語言與協作
- 修改前先讀懂現有結構、測試方式與設定來源。
- 輸出預設繁體中文。
- 規格/行為不確定時先問，不要臆測。

## 專案目標
- 架構簡單、直覺、好維護；測試聚焦「測什麼」，登入/request/config/parsing 交給共用層。
- 新測試優先用 `services` fixture。

## 架構分層
- `clients/`：REST client、EMS 溝通邏輯
- `services/`：domain 測試服務、共用 case helper
- `config_loader/`：設定、profile、hardware、auth、環境解析
- `cases/`：endpoint case、payload、資料驅動測試資料
- `models/`：API/case/response 結構化模型
- `utils/`：assertion、Allure、diagnostics、reporting、redaction
- `tests/`：pytest 案例，優先用 `services` fixture，避免複製低階 request 邏輯
- `tests/support/`：pytest options、fixtures、preflight、collection、reporting hooks
- 共用邏輯放 fixture/client/helper/service/utility，不要複製貼上

## API 驗證方式
- REST 是 EMS 北向介面，下令後非同步生效：一律輪詢 GET 確認最終狀態（timeout+指數退避），不可只斷言同步回應。
- 429/Retry-After 需退避重試，限流失敗不計入 bug。

### NeoX config 類服務的驗證順序

針對涉及 NeoX 設定變更的服務（config-related services），新增測試前須依下列順序驗證，確認問題不是出在設備/CLI 本身：

1. **CLI baseline**：先 SSH 登入 NeoX，用對應 CLI command 手動下同一筆設定，確認 CLI 本身能正常下設定並生效，排除設備/環境問題。
2. **REST API 測試**：CLI baseline 確認可行後，才透過 REST API 對同一設定情境撰寫並執行測試。
3. **CLI 覆核（ground-truth 比對）**：REST API 測試執行後，再次 SSH 登入 NeoX 下 show 指令，比對設定是否確實透過 REST 正確落地。

若步驟 1 CLI baseline 就失敗，代表問題在設備/環境本身，不應繼續往下走 REST 測試或視為 API bug。

## 測試設計
- 優先用既有 fixture/marker/CLI option pattern；測試名稱需清楚描述行為/場景。
- 資料驅動測試放 `cases/`/`configs/`，不要硬編碼。
- Assertion 用 `utils/assertions.py` 或既有 helper。
- 需上游資料一律用動態 fixture 傳遞 context（禁止寫死/盲猜 id），fixture 負責 teardown。
- 破壞性案例用拋棄式專屬測資，不共用正向資料。
- 測試需可重跑（idempotent），中途崩潰也要能清理。

## 設定與敏感資料
- EMS node/user/slot/port/ONT/topology 集中管理；slot 對應 card type 需與環境一致。
- 輸出 request/response/report 一律套用 redaction（devKey、密碼、token、ONT password 等遮罩）。
- 環境差異走 config/profile/pytest option，不寫死正式或特定設備資訊。
- 動 Swagger/OpenAPI/schema 比對前，先確認 `NetAtlasEMS_OpenAPI_*.yaml` 是否為最新日期版本。
- 回歸前先做 spec/schema diff；偵測到 breaking change 需回頭局部更新測試，不可直接沿用舊測試碼。
- `reports/` 視為 generated output，非使用者要求不當作修改重點。
- 只有需要完整附件調查時才開 `EMS_ATTACH_FULL_JSON=1`，避免報告暴增或外洩敏感內容。

## 外部整合可靠性
- 呼叫 TestLink/Redmine 等外部 API 一律加 Retry（指數退避）+ 請求間隔/限速，避免批次回填時逾時漏寫。

## 安全原則
- 影響外部 EMS、硬體、正式環境或破壞性操作，執行前先詢問。
- 刪除 alarm、改設備狀態、開 remote console、provision、cleanup 等測試不得預設執行，需明確 option/marker（如 `--run-alarm-delete`、`--run-remote`）。
- 破壞性測試排在正向/負向/邊界案例都跑完後才執行，用拋棄式測資，測後對設備做快照/還原。

## 驗證
- 改 Python 程式後至少跑 compile check。
- 改 fixture/client/config loader/case registry 後需跑對應 pytest。
- 測試會連外部 EMS/設備時，執行前先確認 node/profile 與風險。

## Report 輸出偏好
- 要求彙整測試結果、照片比對、Redmine/TestLink 比對或 QA summary 時，預設產出可用瀏覽器開啟的 HTML report（放 `reports/`，檔名含日期/EMS version/node，如 `reports/node3_b7_issue_comparison_YYYY-MM-DD.html`）；Markdown 僅為草稿。
- 首屏先給結論，再展開證據；至少含：環境摘要、pytest 結果、TestLink/txt 結果、失敗清單、照片/Redmine 逐項比對、結論狀態（已解/未解/部分/需確認）。
- 有 Allure raw results 時直接解析嵌入重點，不只放資料夾連結；每個 testcase 展開需見：nodeid、TestLink case id、title、status、duration、request payload、EMS response、CLI command/output/驗證結果、failure message/traceback 摘要/contract diff、相關 attachments 摘要。
- 保留原始 txt/html/allure raw/log 連結供回查。
- 大體積 raw 內容（request/response/CLI output/traceback）不嵌入報表本體，落地成檔，report 只放摘要+連結。
- 嵌入任何內容前先套用 redaction，避免敏感資訊外洩。