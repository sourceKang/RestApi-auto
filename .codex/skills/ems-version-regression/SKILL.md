---
name: ems-version-regression
description: 新 EMS 版本的 RestApi Auto 回歸流程：更新 EMS 版本設定、比對 OpenAPI、建立 TestLink build、以 run_multi_node 跑指定 node、分類失敗、產出 HTML 報表、回填 TestLink，並把疑似 API bug 交給 qa-bug-report。使用者提到換 EMS 版本／新 build 回歸／「跑 node 測試並回報」時使用。
---

# EMS 版本回歸

共用規範以 AGENTS.md 為準；本 skill 只定義流程順序與確認點。
⏸ 表示必須先向使用者預覽並取得明確同意，同意只涵蓋該步驟。

## 0. 輸入

向使用者確認（未提供就問，不猜）：
- EMS 版本字串，例如 `03.00.11 (AAVV.221) b13`，以及 EMS 是否已實際升版。
- node 清單與 auth profile；是否跑完整套件（含 destructive）。
- TestLink project／plan／platform；build 名稱預設為 EMS 版本字串。

## 1. 更新版本與 spec 比對

1. 確認要測的 EMS target（`configs/ems.yaml` 的 `ems.targets`，以 `EMS_TARGET`
   或 `ems.default_target` 選擇），修改該 target 的 `version`；node 須已移到該 server。
   TestLink build 依 target 的 platform 加後綴（例：`…b12_redhat`）。
2. 確認 `<openapi_root>/<版本目錄>/NetAtlasEMS_OpenAPI_*.yaml` 為最新。
3. 執行 `tools/run_openapi_version_guard.py`（先 `--local-only`，再 live）。
   有 breaking change → 停止，回報差異，由使用者決定是否先更新測試。

## 2. 環境確認 ⏸

1. `tools/run_multi_node.py --nodes <N> [--run-full-testcases] --dry-run`。
2. 回報：各 node 指令、NeoX／非 NeoX 省略的選項、destructive 範圍、
   預估時間，以及是否有他人同時使用相同 node／帳號。
3. 同意後才繼續。

## 3. 建 TestLink build ⏸

1. 以 testlink MCP `get_builds` 查詢是否已存在同名 build。
2. 不存在 → 預覽 project／plan／build 名稱與 notes，同意後 `create_build`。
3. MCP 無法使用 → 告知使用者並提供手動建立資訊，不改用其他方式寫入。

## 4. 執行測試

1. 背景執行 `tools/run_multi_node.py`（與步驟 2 相同參數，不含 `--dry-run`）。
2. 完成後讀 `reports/multi_node/<timestamp>/summary.json` 與各 node log。

## 5. 失敗分類與報表

1. 與上一次同 node 結果比較（用法見 docs/project-context.md「歷史結果查詢與
   regression 比對」）：
   1. 重產索引：`.\.venv\Scripts\python.exe tools/build_report_index.py`
      （只讀 txt 報表與 `multi_node/*/summary.json`，寫入 `reports/_index/`，
      不改既有報表）。
   2. 確認 `reports/_index/formal_runs.yaml` 中，本次與上一次 build 該 node 的
      正式執行；未標記時工具暫用最後一次完整執行，回報時需註明「未標記」。
      C0 多輪重測時逐輪列出，以 `final: true` 標最終輪。
   3. 逐 node 比對（build 目錄為 `reports/` 下的 `<version>[_<target>]`）：
      `.\.venv\Scripts\python.exe tools/build_report_index.py --compare "<上一次 build 目錄>" "<本次 build 目錄>" --node <NODE>`
      產出 `reports/_index/compare_*.html`：Regression 候選（Pass → Fail）、
      既有問題、已修復、新增／移除，附第一個狀態不同的步驟、失敗訊息與
      「不穩定」標記；有變化的 case 另有 `_index/cases/` 步驟並排頁。
      需指定特定執行時用 `<build 目錄>/<run_id>`。跨 EMS target（例如 .8 與
      .100）比對時在報表中註明。
   4. 比對結果只是差異清單，作為下一步分類的輸入，不等於 Root Cause。
2. 每個失敗依 AGENTS 分層歸類，並附證據：
   - 測資／設定過期（例：fw_version 與 CLI 不符）
   - 設備／環境前置條件（例：FEC、port disable、帳號）
   - 疑似 API bug
   - 間歇性（同版本曾通過）
3. NeoX 設定失敗須先做 CLI baseline；CLI baseline 失敗屬設備／環境，不列 API bug。
   會改設備的 CLI 操作 ⏸。
4. 未取得證據前不得寫 Root Cause；以「推測」「未確認」標示。
5. 產出 HTML 報表於 `reports/`（首屏結論、環境、各 node 統計、失敗分類、
   與上次差異、報表連結；與上次差異連到步驟 1 的 `compare_*.html`），
   內容先完成 redaction。

## 6. 回填 TestLink ⏸

1. 以 qa-integration-agent MCP `qa_preview_report_artifact` 建立預覽：
   `reports` 每個 node 一筆 `{label: <node>, path: <該 node txt 報表>}`，
   帶 environment、project、plan、build、platform（platform 不猜）；
   `redmine_create_bugs` 維持 false，Redmine 另走步驟 7。
2. 以 `qa_read_preview_artifact` 讀完 items、warnings、ignored 三段；確認
   筆數、status 分布與各 node 報表相符後，向使用者預覽。
3. 同意後才以 `qa_execute_preview_artifact` 寫入。同一 build 已回填過時
   再次執行會新增重複的 execution，先向使用者說明。
4. MCP 無法使用或 schema 缺 `reports` → 告知使用者（例如在 /mcp 重連），
   不改用其他方式寫入。

## 7. Redmine bug ⏸

1. 只針對「疑似 API bug」，以 `qa-bug-report` skill 產出草稿。
2. 先 `redmine_search_issues` 查重；預覽後經同意才 `redmine_create_bug`。

## 8. 收尾

- 更新 `docs/work-status.md`：版本、node、結果、分類、未解事項、下一步。
- 確認設備已還原（NeoX config、ONT／GE service、alarm）與 idempotency。
- 設定或測試有修改時，依 AGENTS 的 Git 規則處理；提交前確認 staged 清單。
