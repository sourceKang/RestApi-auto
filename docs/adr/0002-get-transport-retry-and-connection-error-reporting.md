# ADR 0002: Resend requests after safe EMS transport errors and report every connection error and slow request

## Context

On the RedHat EMS (192.168.128.100, b13) the server intermittently refuses or drops HTTPS connections (`ConnectTimeout`, `ReadTimeout`, `RemoteDisconnected`, `ConnectionResetError`). In the 2026-10-13 NODE3 full run all 5 failures were such transport errors and none was an assertion failure. EMS1-6666 failed in the full run and again in the single rerun at the same point: the POST had succeeded, and one `GET /ontservice/{sn}` inside the 300-second state polling raised a transport error, so the whole case failed without using the remaining wait, and 11 dependent cases were blocked. Other one-shot GETs (profile existence checks before cleanup) failed the same way.

`EmsApiClient` did not handle transport exceptions, and nothing in the txt/HTML report showed that a connection error had happened unless the case failed.

## Decision

- `EmsApiClient._send_request` resends GET and HEAD after `requests.ConnectionError` or `requests.Timeout`, waiting 5 s and then 15 s (3 attempts in total). The last error is raised unchanged.
- POST, PUT, PATCH and DELETE (including login) are resent only after `requests.ConnectTimeout`: the TCP connection was never established, so EMS cannot have received the request. After a read timeout, reset or dropped connection EMS may already have applied it, so it is not resent (same rule as ADR 0001). Added 2026-10-13 after run 8, where both remaining failures were PATCH connect timeouts.
- A request whose total time (all attempts and waits) exceeds 30 s is flagged as `EMS Slow Requests` in the report header and attached to Allure (`EMS slow request`), even when it succeeds. In run 8, 5 of 4013 responses took over 30 s and none over 45 s; 99 % finished within 9 s.
- Every transport error, recovered or not, is recorded with the test nodeid, method, path, attempt, error summary and outcome. It is attached to Allure (`EMS connection error`) and listed in the txt/HTML report header (`EMS Connection Errors: N (recovered by retry R, not recovered U)` plus one line per event, capped at 30 lines).
- The error summary is written in plain words with host:port, configured timeout and time spent, and says whether the request reached EMS (for example `ConnectTimeout: could not connect to 192.168.128.100:9116; connect timed out after 21.0 s (client limit 60.0 s); connection not established, request not sent`; the OS may give up before the client limit, so the time actually spent comes first). urllib3's "Max retries exceeded" wording is dropped because it is unrelated to these retries.
- Polling loops keep their own deadlines and assertions.
- Per-target timing profile (added 2026-10-14 for the resource-limited RedHat .100 EMS), set under `ems.targets.<name>` in `configs/ems.yaml`; defaults keep the original behaviour, so the Ubuntu .8 target is unchanged:
  - `wait_scale` multiplies every state-polling time limit through `config_loader.settings.scaled_wait` (services, `tests/support` CLI waits and the NeoX REST token wait). Poll intervals are not scaled, so a state reached early still returns early; only slow cases wait longer. RedHat uses 1.5.
  - `transport_retry_delays` replaces the default 5/15 s resend waits. RedHat uses 10/30/60 s (4 attempts).
  - `min_request_interval` keeps at least this many seconds between request starts, process-wide, to ease server load. RedHat uses 0.3 s; whether it reduces dropped connections is to be measured by the `EMS Connection Errors` count.
  - A non-default profile is printed as `EMS Timing` in the txt/HTML report header.

## Alternatives

- Catch transport errors in each polling loop: rejected because there are 22 loops and the failures also hit one-shot GETs outside loops.
- urllib3 `Retry` on the session adapter: rejected because the retries would be invisible to the report and harder to restrict and test.
- Retry all methods after any transport error: rejected because a mutating request may already have taken effect unless the connection was never established.

## Consequences

- A single dropped GET no longer fails a case; persistent outages still fail after about 20 s of extra waiting plus up to two extra client timeouts.
- Connection instability stays visible in the report even when every case passes, so environment problems are not hidden.
- The live Swagger fetch in `tests/test_openapi_yaml.py` uses its own HTTP call and is not covered.

## Validation

- `tests/test_ems_api_client_transport_retry.py`: GET recovered and recorded, GET raised after all attempts with every attempt recorded, mutating methods resent only after a connect timeout, error summaries, slow-request marking and report header lines.
- Compile check and collection; focused client/reporting tests.
- Rerun EMS1-6666 and its dependent cases on NODE3 (RedHat .100) and check the report header.

Removal condition: if the EMS no longer drops connections, the retry may stay (it is cheap) but the report lines remain the evidence source.
