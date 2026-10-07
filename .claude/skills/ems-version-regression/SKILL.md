---
name: ems-version-regression
description: 新 EMS 版本的 RestApi Auto 回歸流程：更新 EMS 版本設定、比對 OpenAPI、建立 TestLink build、以 run_multi_node 跑指定 node、分類失敗、產出 HTML 報表、回填 TestLink，並把疑似 API bug 交給 qa-bug-report。使用者提到換 EMS 版本／新 build 回歸／「跑 node 測試並回報」時使用。
---

# EMS 版本回歸共用入口

先讀取專案根目錄的
[共用 skill](../../../.codex/skills/ems-version-regression/SKILL.md)，
並依該檔完整流程執行。共用流程只在該檔維護，不在這裡複製。

流程中的 Redmine bug 草稿改用 `/qa-bug-report`。
缺少對應 MCP 或登入設定時，先完成可離線的步驟並說明外部寫入尚未執行；
不得把執行回歸的要求當作寫入 TestLink、Redmine 或變更設備的授權。
