# 範例：PR #20

實際用於 sourceKang/RestApi-auto#20 的內文（程式修正類：hook 順序與遮罩）。結構可直接套用。

````markdown
## 摘要
這是 retro 計畫 A～I 的 PR-A，處理兩個安全缺口：
- `pytest -m offline` 仍可能連線 EMS／DUT；
- ONT password（`registid`）沒有遮罩。

```diff
 pytest_collection_modifyitems  (tryfirst, 早於 -m/-k 篩選)
-  skip_unready_dut_items       # 連 EMS/DUT 做 preflight
-  _apply_node_capability_skips
 _pytest.mark: deselect_by_mark (-m offline)
+pytest_collection_finish       (篩選後的最終 items)
+  skip_unready_dut_items
+  _apply_node_capability_skips # 仍在 target sync 之後
```

```diff
 utils/redaction.py
-SENSITIVE_KEYS = {password, passwd, sessionid, token, authorization}
+SENSITIVE_KEYS = {..., registid}          # NeoX ONT payload 的 ONT password
+redact_text: 另遮罩 CLI `registration-id <值>`
+redact():    字串也套用 redact_text
 tests/support/neox_cli_verification.py: CLI 驗證 JSON 寫檔前先 redact
```

## 證據
| 項目 | Before | After |
|---|---|---|
| `tests/test_collection_preflight.py`（子程序實際 collect，preflight 被呼叫就丟例外） | 在舊基準 d4b1685 **失敗**：`collection.py:52` 呼叫 preflight | 通過；對照組（不加 `-m offline`）確認 guard 確實生效 |
| `tests/test_redaction.py` | — | 通過，涵蓋 payload、JSON、`key=value`、CLI 三種寫法 |
| `pytest -m offline --skip-dut-preflight` | 108 passed | **117 passed / 0 failed** |
| 完整 collect | — | 751 collected |
| `tools/check_config_secrets.py` | — | 0 筆 |
| 試合併到 `codex/prepare-github-upload`（d4b1685） | — | 衝突 0，涉及 7 檔 |

**未驗證：**
- 沒有連 EMS／DUT，preflight 在實機上的行為沒有重新跑。
- teardown 失敗訊息裡 EMS 回應的 `password` 仍可能出現在 Allure `statusDetails.message`：allure 直接取 `excinfo.exconly()`，不經過 longrepr 遮罩。這部分另列工作項。

## 合併風險
**Door：** two-way。可以直接 revert，不會寫入外部系統。

**Blast Radius：** collection／報表遮罩。

- DUT preflight 的執行時機從 modifyitems 移到 collection_finish，加上 `-m`／`-k` 時只看篩選後的項目。完整回歸不加 `-m`，項目集合不變。
- `redact()` 現在也會遮罩一般字串，所以附件裡 `token=…`、`password: …` 這類文字也會被遮蔽。這是預期行為。

🤖 Generated with [Claude Code](https://claude.com/claude-code)


````
