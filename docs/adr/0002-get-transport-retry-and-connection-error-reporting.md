# ADR 0002: Resend GET/HEAD after EMS transport errors and report every connection error

## Context

On the RedHat EMS (192.168.128.100, b13) the server intermittently refuses or drops HTTPS connections (`ConnectTimeout`, `ReadTimeout`, `RemoteDisconnected`, `ConnectionResetError`). In the 2026-10-13 NODE3 full run all 5 failures were such transport errors and none was an assertion failure. EMS1-6666 failed in the full run and again in the single rerun at the same point: the POST had succeeded, and one `GET /ontservice/{sn}` inside the 300-second state polling raised a transport error, so the whole case failed without using the remaining wait, and 11 dependent cases were blocked. Other one-shot GETs (profile existence checks before cleanup) failed the same way.

`EmsApiClient` did not handle transport exceptions, and nothing in the txt/HTML report showed that a connection error had happened unless the case failed.

## Decision

- `EmsApiClient._send_request` resends GET and HEAD after `requests.ConnectionError` or `requests.Timeout`, waiting 5 s and then 15 s (3 attempts in total). The last error is raised unchanged.
- POST, PUT, PATCH and DELETE are never resent: EMS may already have applied the request (same rule as ADR 0001).
- Every transport error, recovered or not, is recorded with the test nodeid, method, path, attempt, error summary and outcome. It is attached to Allure (`EMS connection error`) and listed in the txt/HTML report header (`EMS Connection Errors: N (recovered by retry R, not recovered U)` plus one line per event, capped at 30 lines).
- Polling loops are unchanged; they keep their own deadlines and assertions.

## Alternatives

- Catch transport errors in each polling loop: rejected because there are 22 loops and the failures also hit one-shot GETs outside loops.
- urllib3 `Retry` on the session adapter: rejected because the retries would be invisible to the report and harder to restrict and test.
- Retry all methods: rejected because a mutating request may already have taken effect.

## Consequences

- A single dropped GET no longer fails a case; persistent outages still fail after about 20 s of extra waiting plus up to two extra client timeouts.
- Connection instability stays visible in the report even when every case passes, so environment problems are not hidden.
- The live Swagger fetch in `tests/test_openapi_yaml.py` uses its own HTTP call and is not covered.

## Validation

- `tests/test_ems_api_client_transport_retry.py`: GET recovered and recorded, GET raised after all attempts with every attempt recorded, mutating methods not resent, report header lines.
- Compile check and collection; focused client/reporting tests.
- Rerun EMS1-6666 and its dependent cases on NODE3 (RedHat .100) and check the report header.

Removal condition: if the EMS no longer drops connections, the retry may stay (it is cheap) but the report lines remain the evidence source.
