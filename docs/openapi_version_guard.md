# OpenAPI Version Guard

這個 guard 用來確認每版 EMS 的 OpenAPI YAML 是否和 live Swagger 對得上。

目前比對目標是每版目錄下的：

```text
D:\FW\NetAtlasEMS\<EMS version>\NetAtlasEMS_OpenAPI_*.yaml
```

例如：

```text
D:\FW\NetAtlasEMS\03.00.11 (AAVV.221)\NetAtlasEMS_OpenAPI_20260605.yaml
```

它不會掃描 `configs/` 裡的測試資料 YAML。

## 執行方式

```powershell
.\.venv\Scripts\python.exe tools\run_openapi_version_guard.py
```

等同於：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_openapi_yaml.py -x --run-live-swagger-check --neox-swagger-api-docs-url "https://192.168.128.100:9116/netatlasemsapi/swagger-ui/index.html#/"
```

只做 local OpenAPI YAML 與 baseline 檢查，不連 live Swagger：

```powershell
.\.venv\Scripts\python.exe tools\run_openapi_version_guard.py --local-only
```

需要一次列出完整差異時使用：

```powershell
.\.venv\Scripts\python.exe tools\run_openapi_version_guard.py --collect-all
```

如果要刻意測某一份非預設 YAML，可以用：

```powershell
$env:EMS_OPENAPI_YAML_FILE="D:\FW\NetAtlasEMS\03.00.11 (AAVV.221)\NetAtlasEMS_OpenAPI_20260605 - test.yaml"
.\.venv\Scripts\python.exe tools\run_openapi_version_guard.py --collect-all
```

## 測試流程

1. 讀取 `configs/ems.yaml` 的 EMS version。
2. 依照 EMS version 找到對應目錄，例如 `D:\FW\NetAtlasEMS\03.00.11 (AAVV.221)`。
3. 在該目錄選擇最新的 `NetAtlasEMS_OpenAPI_*.yaml`。同一天若同時有正式檔與 ` - test.yaml` 這類測試檔，會優先選正式檔 `NetAtlasEMS_OpenAPI_YYYYMMDD.yaml`。
4. Parse OpenAPI YAML，確認格式可以被讀取。
5. 確認 YAML 的 `info.version` 和 `configs/ems.yaml` 設定的 EMS version 一致。
6. 比對 local OpenAPI YAML 和本專案 baseline。
7. 連到 live Swagger UI，轉成 `/v3/api-docs` 後下載 live OpenAPI JSON。
8. 比對 live Swagger 和 local OpenAPI YAML 的 OpenAPI key contract。

## Live Swagger Key Contract 會抓什麼

這個 live 比對專注在「參數數量不同」和「key 名稱不同」：

- endpoint path 新增或刪除，例如 `/ont/{devicename}/{slotid}/{portid}/{ontid}`。
- HTTP method 新增或刪除，例如 `get`、`post`、`put`、`delete`。
- path/query/header parameter 名稱或數量不同。
- request body / response 直接引用的 schema 不同。
- request/response schema 裡的 leaf key 新增或刪除，例如 `Content.anti_spoofing` 被改成 `Content.anti_spoofingno`。

目前 live Swagger key contract 不把 type、enum、nullable、default 這類值差異當成 fail。這是為了讓版本檢查先穩定抓出 key drift，而不是被 Swagger generator 的細節差異干擾。

## 常見結果

- `$.paths.<path> was removed`：live Swagger 有這個 endpoint，但 local YAML 沒有。
- `$.paths.<path> was added`：local YAML 有這個 endpoint，但 live Swagger 沒有。
- `$.paths.<path>.<method>.parameters length changed`：同一個 endpoint/method 的參數數量不同。
- `$.schemas.<schema>.leaf_keys.<key> was removed`：live Swagger 有這個 schema key，但 local YAML 沒有。
- `$.schemas.<schema>.leaf_keys.<key> was added`：local YAML 有這個 schema key，但 live Swagger 沒有。

如果差異是 RD 預期修改，就更新 local OpenAPI YAML 和 baseline；如果不是預期修改，就先回報 RD 確認 Swagger 或 YAML 是否有誤。
