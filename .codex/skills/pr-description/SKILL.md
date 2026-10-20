---
name: pr-description
description: 撰寫或更新 RestApi Auto 的 GitHub PR 描述（摘要／證據／合併風險）。在建立 PR、改寫 PR 內文或交接合併時使用；只產生內文草稿，建立或修改 PR 前必須取得使用者同意。
---

# PR 描述

PR 描述的讀者是要決定能不能合併的人。目標是讓他在一分鐘內看懂改了什麼、有什麼證據、合併有多危險。
構想參考 Matt Pocock skills 的 `pr`（MIT），依本專案的 QA 證據與風險另行改寫。

## 流程

1. 讀 `git log <base>..HEAD`、`git diff --stat <base>...HEAD` 與 docs/work-status.md 最近條目；
   base 預設為 `codex/prepare-github-upload`。
2. 依變更類型選一張最小的圖（見「摘要」）。
3. 收集證據：只引用已有的指令輸出（pytest 摘要行、CI run、TestLink 結果、CLI show），或重跑 offline 指令
   （`pytest -m offline -q --skip-dut-preflight`）。不為了寫 PR 去連 EMS／DUT／TestLink。
4. 在 scratch worktree 做 `git merge --no-commit --no-ff` dry run 到 base，記下衝突數與檔案數，結束後移除 worktree。
5. 依下方判準寫合併風險。
6. 對照 [Review 檢查清單](../../../docs/engineering-guidelines.md#review-檢查清單)，未符合的項目寫進證據的「未驗證」或合併風險。
7. 內文先寫到暫存檔並完成遮罩，給使用者預覽；使用者同意後才執行 `gh pr create --body-file` 或 `gh pr edit --body-file`。
   repo 是 Public，PR 內文屬公開內容。

## 內文格式

```markdown
## 摘要
<一句話說明為什麼改；接一張最小的圖>

## 證據
| 項目 | Before | After |
|---|---|---|
| ... | ... | ... |

**未驗證：** <沒有就寫「無」；沒連 EMS／DUT 要明講>

## 合併風險
**Door：** <one-way／two-way>，<一句理由>
**Blast Radius：** <一個詞或短語>

- <可能的後續影響，最多 3 點>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

用專案用語（node、target、build、formal run、CLI baseline、TestLink build）；每段 3～8 行，不重貼整段程式碼。

### 摘要：選一張最小的圖

| 變更類型 | 用什麼圖 |
|---|---|
| client／service 修正 | 呼叫樹 diff（test → service → client → EMS），標出改的那一層 |
| hook、collection、fixture 流程 | 呼叫順序 diff |
| 文件、CI、檔案重整 | 檔案樹，附行數或一句說明 |
| retry、polling、節流政策 | 虛擬碼或 Mermaid sequence（10 個節點以內） |
| config／profile | YAML key 的 diff，值一律不寫 |
| 報表格式 | 報表開頭 Before／After 片段 |

多個 commit 時，可在圖下加最多 5 點 commit 清單。

### 證據：由強到弱

1. 實機最終狀態（CLI show、EMS GET）與 TestLink 結果；需要使用者授權才可取得，沒有就不寫。
2. 修正前失敗、修正後通過的同一個測試（例如在舊基準的暫存 worktree 重跑）。
3. pytest 摘要行（通過 X／失敗 Y）、collect 數。
4. GitHub CI run。
5. dry run 合併結果（固定一列：衝突 N、涉及 M 檔）。

數字直接取自指令輸出，不從記憶或舊文件抄。證據片段先遮罩 devKey、密碼、token、ONT password；config 只寫 key 名。

### 合併風險判準

**one-way door**（合併或其效果無法單純 revert）：
- 會改變 EMS／DUT 狀態的預設行為，或讓破壞性操作不再需要明確 option／marker。
- 內文記錄的 TestLink／Redmine 寫入、報表刪除或 node 搬移（PR 本身可 revert，但這些已發生的效果不能）。
- config、schema、profile 格式改變，使既有本機設定或報表需要遷移。

其餘為 **two-way door**。PR 本身可 revert、但記錄了外部寫入時，寫成「two-way（PR 本身）；記錄的 TestLink 寫入已在 PR 外完成，無法撤回」。

**Blast Radius** 用語：`docs`、`offline-tests`、`CI`、`collection／hooks`、`報表`、`遮罩`、`共用 fixture／client`、
`EMS-mutating`、`NeoX config`、`config 格式`。可列多個，最多三個。

## 給非技術讀者時

PR 要轉給 RD／PM 時，摘要第一句用白話描述行為變化（例如「離線測試不會再連到實驗室設備」），其餘格式不變。

## 範例

見 [references/example-pr20.md](references/example-pr20.md)。
