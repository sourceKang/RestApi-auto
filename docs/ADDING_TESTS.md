# 新增 REST API 測試指南

這個專案目前以 pytest + domain service 為主要架構。新增測試時，優先讓測試描述「測什麼」，把 API 細節放在 service、case 或 helper 裡。

## 建議流程

1. 確認測試屬於哪個 domain，例如 alarm、inventory、provision、remote、session、profile。
2. 若已有對應 service，優先在 service 補語意化方法。
3. 若是資料驅動 endpoint 測試，優先在 `cases/` 補 `EndpointCase` 或 payload factory。
4. 測試檔只負責組合 fixture、session、case，並呼叫 service 方法。
5. 會改動 EMS、設備、alarm、remote console 或 provision 的測試，必須使用既有 marker 或 pytest option 保護。

## 推薦測試寫法

新測試優先使用聚合 fixture：

```python
def test_active_alarm_read(services, readwrite_session):
    services.alarm.verify_active_alarm_list(readwrite_session)
```

既有單一 domain fixture 仍保留相容性，但新增測試建議走 `services.xxx`：

```python
def test_login_and_logout(user_session_service, role):
    user_session_service.verify_login_and_logout_by_role(role)
```

## Service 命名

- 方法名稱描述行為，例如 `verify_read_success`、`ensure_ont_inventory_ready`。
- 路徑、payload、response parsing 不要散落在測試檔。
- 重複 assertion 優先放在 `utils/assertions.py` 或既有 JSON helper。

## 安全提醒

- 不要在預設 pytest run 中執行 destructive flow。
- 不要把 token、session id、password 或設備私密資訊寫入檔案。
- request/response/report 需要輸出時，使用既有 redaction helper。
