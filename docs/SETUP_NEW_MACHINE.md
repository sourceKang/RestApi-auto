# 在新電腦建置本專案

這份文件的目標：讓一台乾淨的電腦，從 `git clone` 到跑出第一份報告。

專案本身沒有硬編碼專案路徑，可以放在任何目錄。真正需要逐台設定的只有三件事：
**Python 環境**、**機台專屬設定（帳密與 DUT）**、**網路可達性**。

> 設定完成後，先跑 `python tools\check_environment.py`。
> 它會一次檢查以下所有項目並指出缺什麼，不必逐項人工確認。

---

## 0. 前置需求

| 項目 | 需求 | 說明 |
| --- | --- | --- |
| Python | **3.11 以上** | `utils/cleanup.py` 使用 `ExceptionGroup` |
| 網路 | 連得到 EMS 與各 DUT | 見第 4 節 |
| Allure Commandline + Java | 選用 | 只有 `--generate-allure-html` 需要 |
| OpenAPI YAML 來源目錄 | 選用 | 只有 OpenAPI 契約比對需要，見第 5 節 |

---

## 1. 取得程式碼並建立虛擬環境

```powershell
git clone https://github.com/sourceKang/RestApi-auto.git "RestApi auto"
cd "RestApi auto"

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`.venv/` 沒有進版控，每台機器都要自己建立。

---

## 2. 建立機台專屬設定（**最常漏掉的一步**）

版控裡的 `configs/auth_accounts.yaml` 與 `configs/test_targets.yaml` 是
**去識別化的範本**，密碼欄位是 `CHANGE_ME` 佔位值。直接拿去跑會登入失敗，
DUT preflight 隨即把所有 DUT 相關測試標成 skip。

從範本複製出兩個被 gitignore 的本機檔案：

```powershell
copy configs\auth_accounts.local.yaml.example configs\auth_accounts.local.yaml
copy configs\test_targets.local.yaml.example  configs\test_targets.local.yaml
```

然後填入真實值：

| 檔案 | 要填什麼 |
| --- | --- |
| `configs/auth_accounts.local.yaml` | EMS 的 readwrite / readonly / noaccess 帳密。每個要用到的 profile 都要有 |
| `configs/test_targets.local.yaml` | 這台機器連得到的 node：`device_ip`、SSH 帳密、slot/port/ONT SN 與 ONT 密碼 |

載入優先序（先命中者勝出）：

```
EMS_AUTH_ACCOUNTS_FILE / EMS_TEST_TARGETS_FILE   （明確指定檔案）
  → configs/*.local.yaml                          （存在就自動優先）
  → configs/*.yaml                                （版控中的範本）
```

**不想把密碼寫進檔案**，也可以改用環境變數。版控範本裡的
`"${DUT_SSH_NODE3_PASSWORD:-CHANGE_ME_DUT_SSH_PASSWORD}"` 就是這個用法：

```powershell
$env:EMS_AUTH_READWRITE_DEFAULT_USERNAME = "admin"
$env:EMS_AUTH_READWRITE_DEFAULT_PASSWORD = "..."
$env:DUT_SSH_NODE3_PASSWORD = "..."
$env:EMS_ONT_NODE3_PASSWORD = "..."
```

或放進專案根目錄的 `.env`（同樣被 gitignore），格式為 `KEY=VALUE`。

> ⚠️ 任何情況下都不要把真實帳密 commit 進版控。`.local.yaml` 與 `.env` 已在
> `.gitignore` 中；`.example` 範本則刻意保持可提交，內容不得含真實值。

---

## 3. 設定 EMS 連線

`configs/ems.yaml` 有進版控，若這台機器要連不同的 EMS，改這裡：

```yaml
version: 1

ems:
  rest_api_url: "https://192.168.128.8:9116/netatlasemsapi"
  version: "03.00.11 (AAVV.221) b12"
  verify_tls: false
  timeout: 60
```

不想改動版控檔案時，指向另一份 YAML：

```powershell
$env:EMS_YAML_FILE = "D:\path\to\my-ems.yaml"
```

`ems.version` 會決定報告輸出目錄 `reports/<EMS version>/`，以及 OpenAPI 版本目錄的挑選。

---

## 4. 確認網路可達性

這是換機器後最常見的失敗原因，而且症狀容易誤導（大量 skip 而不是明確錯誤）。

必須全部通：

| 目標 | 用途 | 不通的後果 |
| --- | --- | --- |
| EMS `rest_api_url`（預設 `192.168.128.8:9116`） | 所有 REST 呼叫 | 全部 API 測試失敗 |
| 每個 node 的 `device_ip`（**ICMP ping**） | `tests/support/connectivity.py` 會實際 ping | 測試直接 fail |
| 每個 node 的 SSH（port 22） | `target_sync` 前置、NeoX CLI 驗證 | preflight 失敗 → DUT 測試全部 skip |

跨網段、VPN 未連、防火牆擋 ICMP 都會在這裡出問題。
只想先跑 REST、暫時跳過 CLI 驗證：加 `--skip-neox-cli-verify`。

---

## 5. OpenAPI YAML 來源（選用）

OpenAPI 契約比對需要隨 EMS 韌體釋出的 `NetAtlasEMS_OpenAPI_*.yaml`，
**這些檔案不在版控裡**，位置每台機器不同。在 `configs/ems.yaml` 指定：

```yaml
ems:
  # 使用正斜線。YAML loader 以 Python 字串字面值解析引號內容，
  # "D:\FW\..." 的反斜線跳脫會直接報錯。
  openapi_root: "D:/FW/NetAtlasEMS"
```

目錄結構預期為 `<openapi_root>/<EMS 版本目錄>/NetAtlasEMS_OpenAPI_<日期>.yaml`。

覆寫順序：`EMS_OPENAPI_YAML_FILE`（指定單一檔案）> `EMS_OPENAPI_ROOT` > `ems.openapi_root`。

這台機器沒有這份韌體來源時，**不必設定**——OpenAPI YAML 比對會自動 skip
並說明原因，不會 fail。

---

## 6. Allure HTML 報告（選用）

`allure-pytest` 已在 `requirements.txt` 中，raw results 一定會產出。
但要產出 HTML 報告（`--generate-allure-html`）另外需要 **Allure Commandline + Java**：

```powershell
where allure
java -version
```

Windows 安裝方式：Chocolatey、Scoop，或 `npm.cmd install -g allure-commandline`
（PowerShell 擋 `npm.ps1` 時用 `npm.cmd`）。

**兩者缺一時 `--generate-allure-html` 不會報錯，只是靜默不產出 HTML。**

---

## 7. 驗證

```powershell
.\.venv\Scripts\python.exe tools\check_environment.py --node NODE3
```

沒有 BLOCKING 項目就可以開始跑：

```powershell
.\.venv\Scripts\python.exe -m pytest -m smoke --ems-node NODE3
```

報告會出現在 `reports/<EMS version>/`。

---

## 8. 多台電腦同時跑的注意事項

**同一組 EMS 帳號不能同時在兩個地方登入** —— EMS 會讓先前的 session 失效，
表現為隨機的 `Fail / Not authorized.`。

`tools/run_multi_node.py` 在單機內會驗證各 node 使用不同 profile，
但**跨電腦沒有這層保護**。多台機器對同一台 EMS 跑測試時，必須事先分配
各自獨立的 auth profile（例如 A 機用 `default`、B 機用 `ems_local_rw2`）。

另外，具破壞性或會變更設備狀態的測試（`mutating`、`destructive`、
NeoX config）不應該讓兩台機器同時打同一個 DUT。

---

## 常見問題對照

| 症狀 | 原因 | 處理 |
| --- | --- | --- |
| 全部 DUT 測試 skip，訊息含 `DUT preflight failed` | EMS 登入失敗或 DUT 連不上 | 第 2、4 節；跑 `check_environment.py` |
| 登入回 401 / `Fail` | `.local.yaml` 沒建立，用到 `CHANGE_ME` | 第 2 節 |
| `OpenAPI version directory does not exist` | `openapi_root` 未設或路徑不存在 | 第 5 節 |
| `configs/ems.yaml: invalid quoted string` | YAML 值裡用了反斜線路徑 | 改用正斜線 |
| `--generate-allure-html` 沒有產出 HTML | 缺 Allure Commandline 或 Java | 第 6 節 |
| NeoX config 測試被 skip，訊息提到 paramiko | 沒裝 requirements 或沒用專案 venv | 第 1 節 |
| 隨機 `Fail / Not authorized.` | 同一帳號被別處登入踢掉 | 第 8 節 |
