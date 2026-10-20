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

依賴方向見 AGENTS.md，由 `tests/test_import_layers.py` 依允許依賴表檢查（含函式內的 lazy import）；
`KNOWN_VIOLATIONS` 目前為空；新增例外須附原因與移除條件。各目錄責任：

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

## 工具使用與搜尋

- 搜尋程式碼不要把 `reports/` 當路徑引數（約 150 萬個檔案，全文搜尋會逾時）。查歷史結果用
  `reports/_index/`（tools/build_report_index.py），或只指定單一 `reports/<version>/` 子目錄；
  全 repo 搜尋排除 `reports/`、`.claude/worktrees/`、`.codex-validation/`。
- 不整檔讀取含憑證的檔案（`configs/auth_accounts*.yaml`、`configs/test_targets*.yaml`、`.env`、
  外部工具的 env 檔）。確認欄位時只列 key 名，或執行 `tools/check_config_secrets.py`。
- 大檔（如 tests/test_neox_config.py、tests/support/report_writer.py）先搜尋 test／函式名稱，再讀需要的行範圍；
  測試 log 只看尾端與失敗段落。
- 離線驗證固定用 `pytest -m offline -q --skip-dut-preflight`。
- 完整回歸超過 30 分鐘時以獨立程序執行（見 project-context「EMS server 切換」）；進度只用
  `tools/run_status.py` 查詢，間隔至少 5 分鐘，不自行撰寫輪詢腳本。
- 回報 EMS 版本、target 或 server 前，以 `configs/ems.yaml`、`summary.json` 與報表表頭核對，不憑對話記憶。
- 一個 session 聚焦一個主題；主題完成先更新 work-status，再換 session 或壓縮 context。

## Review 檢查清單

review（含 PR 自我檢查）時逐項確認。以下只列需要判斷的項目；能由機器檢查的規則已由 CI 強制：
設定檔明文（`tools/check_config_secrets.py`）、offline 測試不寫正式報表（CI 防護步驟）、
import 依賴方向（`tests/test_import_layers.py`）、固定 sleep（`tests/test_no_fixed_sleep.py`：只有「迴圈內有讀取狀態」的
輪詢自動通過；`tests/test_*.py` 不得直接 sleep，helper 放 tests/support；其餘須登記在 `KNOWN_SLEEPS` 並附移除條件）、
失敗訊息的回應本體須經 `utils.diagnostics.masked_response_body()`（`tests/test_no_raw_response_in_messages.py`；
Allure 直接把例外字串寫進 statusDetails，經由它才能讓 `EMS_REPORT_REDACT` 一致生效）。

- 修正位於最接近原因的責任層，沒有由 testcase 補償底層缺陷。
- 沒有放寬正確 assertion、吞掉 exception 或忽略錯誤。
- 非同步結果以含 timeout 與退避的 polling 驗證最終狀態，不靠固定 sleep。
- NeoX 設定變更附 CLI baseline → REST → CLI 證據；REST-only 結果沒有宣稱為完整驗證。
- 沒有硬編碼環境、node、slot、port、ONT 或資源 ID；上游資料由 fixture 傳遞並負責 teardown。
- 破壞性案例使用專屬拋棄式測資；中途失敗也能清理，且可重跑。
- 本機報表與附件經 `utils.redaction.report_*`（預設保留原值、`EMS_REPORT_REDACT=1` 時遮罩）；PR 內文、Redmine、
  TestLink notes 與提交的檔案一律遮罩（`redact`／`redact_text`）。
- 會影響 EMS／設備的新行為預設關閉，需明確 option／marker 才執行。
- 新增測試檔或 case 前，先確認能否併入既有檔案或資料驅動 case（破壞性案例的專屬測資除外）；
  清理殘留檔案先列清單，經使用者確認後才刪。
- 證據中的數字取自實際指令輸出；未驗證的部分明確寫出。
- 文件、設定範例或 ADR 是否需要同步更新。

## 拆解與平行子代理

輕量做法，不建立 skill。適用：同時有 2 個以上可離線完成、彼此不改同一檔案的項目。

1. 列出項目，每項寫目標、要改的檔案、完成條件與依賴；標出依賴已完成、可離線、不需使用者決定的「就緒」項目。
2. 先把計畫給使用者確認。
3. 每個就緒項目由一個子代理在自己的 worktree 執行（`git worktree add .claude/worktrees/<topic> -b claude/<topic> <整合分支>`）；
   子代理先寫會失敗的 offline 測試再修到通過，回報 commit、檔案清單與驗證結果。
4. 子代理只可執行 compileall 與 `pytest -m offline -q --skip-dut-preflight`；不得連 EMS／DUT／TestLink／Redmine、
   不得執行 tools/run_multi_node.py 或 `--run-*` 選項、不改 work-status.md／project-context.md／AGENTS.md、
   不刪 reports/、不 push。
5. 主 agent 依序 dry run 合併到整合分支，跑全量 offline 測試與 `tools/check_config_secrets.py`，
   寫一筆 work-status；實機驗證在使用者核准後依序執行；清理 worktree 前先詢問使用者。

不適用：只有一個項目、需要實機重現或調查、等待使用者決定、兩個以上項目要改同一共用熱點
（如 tests/support/report_writer.py、utils/redaction.py），或涉及需要 CLI baseline 的 configs/neox_config。
若同時出現 3 個以上就緒項目的情形發生 2 次以上（例如 OpenAPI breaking change 要逐一更新 cases/），
再考慮建立正式 skill。

## Retro

- 時機：每輪 EMS 版本回歸結束後，或每月一次；由使用者發起，不自動執行。
- 輸入：該期間的 session 紀錄、work-status 與 work-history。
- 檢查兩部分：
  - context：找檔案是否費時、AGENTS.md 是否膨脹、是否有不影響行為的指令、缺少哪些資訊。
  - 防護：固定、可判定對錯的錯誤改為測試、CI 或工具檢查；需要判斷的才加入上方 Review 檢查清單。
- 輸出依嚴重度排序的提案；每一項都由使用者逐條核准後才修改。結論與基準數字記入 work-history，下次 retro 比較。
