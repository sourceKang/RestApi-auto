# RestApi Auto — Claude Code 入口

@AGENTS.md

共用規範由上面的 AGENTS.md 載入；請勿在本檔維護第二份規則。

開始工作先閱讀：
- [專案脈絡與操作方式](docs/project-context.md)
- [目前進度與接續事項](docs/work-status.md)

只在需要本機偏好時，參考 CLAUDE.local.md.example 建立已忽略的
CLAUDE.local.md；檔案中只記錄設定位置，不放帳密，也不視為設備操作授權。

QA bug 撰寫可使用 /qa-bug-report；入口位於
.claude/skills/qa-bug-report/SKILL.md，實際流程沿用專案既有 skill。
Codex 的插件、MCP 連線與登入狀態不會由這份入口自動移轉。
