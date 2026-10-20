# 工程分析與設計準則

本文件由 [AGENTS.md](../AGENTS.md) 指向，供設計修正、分析失敗與 review 時使用。
強制的安全、授權與驗證規則仍以 AGENTS.md 為準。

## 第一性原理分析與決策

修改前先理解現有架構、測試方式與設定來源。從可驗證事實出發，先拆解需求與限制，不將既有實作或慣例當成未經驗證的前提。修改前依序確認：

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

## 目錄責任與設計

依賴方向見 AGENTS.md。各目錄責任：

- `clients/`：REST client、EMS 溝通。
- `services/`：domain 測試服務、共用 case helper。
- `config_loader/`：config、profile、hardware、auth、環境解析。
- `cases/`：endpoint case、payload、資料驅動內容。
- `models/`：API、case、response model。
- `utils/`：assertion、Allure、diagnostics、reporting、redaction。
- `tests/`：pytest 案例；避免低階 request 邏輯。
- `tests/support/`：pytest options、fixtures、preflight、collection、reporting hooks。

架構維持簡單、直覺、可維護；測試聚焦「測什麼」，登入、request、config、parsing 交給共用層。

共用邏輯放在對應 fixture、client、service、helper 或 utility；底層不得反向依賴 tests 或特定 testcase。只在相同業務規則或 policy 重複時抽象，不為文字相似或未確認的未來需求新增 framework、inheritance、generic abstraction 或 config。

若正確修正需改變既有分層或公共介面，先說明影響。主要分層、公共介面、核心 config/schema/profile、全域 polling/retry/error policy、主要 dependency 或外部整合方式改變時，考慮建立 ADR（放在 [adr/](adr/)）；至少記錄 Context、Decision、Alternatives、Consequences、Validation。小型修正通常不需要 ADR。

## API 與測試

- EMS REST 下令後可能非同步生效；以含 timeout 與指數退避的 GET polling 驗證最終狀態，不只斷言同步 response。
- `429`/`Retry-After` 需退避重試；限流失敗不視為產品 bug。
- 測試名稱需描述行為與場景；資料驅動內容放 `cases/` 或 `configs/`。
- Assertion 使用 `utils/assertions.py` 或既有 helper。
- 上游資料以動態 fixture 傳遞 context，不寫死或猜測 ID；fixture 負責 teardown。
- 測試需可重跑（idempotent），中途失敗也能清理。
- 破壞性案例使用拋棄式專屬測資，不與正向案例共用。

## 設定與規格

- EMS node/user/slot/port/ONT/topology 集中管理；slot 與 card type 必須符合環境。
- 環境差異透過 config、profile 或 pytest option 處理，不硬編碼特定環境資訊。
- 修改 Swagger/OpenAPI/schema 比對前，確認 `NetAtlasEMS_OpenAPI_*.yaml` 為最新版本（見 [openapi_version_guard.md](openapi_version_guard.md)）。
- 回歸前先做 spec/schema diff；遇 breaking change 時依差異更新測試。
- `reports/` 是 generated output，除非使用者要求，不作為主要修改範圍。
- 僅在需要完整附件調查時啟用 `EMS_ATTACH_FULL_JSON=1`。

## Git 與 config 提交

更新 GitHub 前檢查 `git status -sb`、staged 清單與 staged diff，避免混入非預期或敏感內容。

- `configs/neox_config/**`：可與相關測試或服務一併提交。
- `configs/ems.yaml`、`configs/hardware_matrix.yaml`、`configs/test_targets.yaml`：確認無帳密或 token 後可提交。
- `configs/auth_accounts.yaml`：禁止提交明文密碼、token、devKey 或真實帳號；改用 placeholder、環境變數或 sanitized template。
- 本機私有 config 保持 unstaged；commit/push 前再次確認 staged 清單。

## 完成前檢查

確認 redaction、idempotency、cleanup、相容性，以及是否需更新文件、設定範例或 ADR。
