# ADR 0001: Process-local EMS session cache and safe authorization recovery

## Context

The EMS invalidates a session 600 seconds after login even when the session calls `GET /device` every 60 seconds. The test suite currently creates and deletes sessions through function-scoped role fixtures, producing repeated logins across a pytest process. A login with the same account can also invalidate another active session, so cache ownership must remain local to one process and one resolved auth profile.

## Decision

- Keep `role_session()` and `credentials_session()` as fresh-session context managers for session behavior tests, setup/cleanup workflows, and callers that explicitly need isolation.
- Add a process-local cache used only by the common readwrite, readonly, and noaccess fixtures.
- Route inventory fixtures that only execute GET validation through the same shared role-session policy; keep inventory setup, provisioning, and cleanup sessions fresh.
- Enable cache reuse by default after the NODE3 rollout passed the full non-destructive suite and the read-only 540-second proactive-refresh probe. Keep `--session-cache-mode=off` (or `EMS_SESSION_CACHE_MODE=off`) as the immediate rollback to per-test login/logout.
- Key cached entries by role inside a `SessionManager` that already belongs to one EMS environment and auth profile.
- Refresh at 540 seconds using a monotonic clock. This is the last boundary confirmed successful by EMS1-6640 and leaves 60 seconds before the absolute lifetime.
- When a cached readwrite session receives exact `Fail / Not authorized.`, refresh it. Do the same for readonly only on GET/HEAD; noaccess denials are expected permission behavior and do not imply expiry.
- Retry once only for GET/HEAD after refresh. For POST, PUT, PATCH, and DELETE, refresh the cache for future calls but return the original response without replaying the request.
- Close and log out cached sessions when the session-scoped pytest fixture finishes.
- Publish allowlisted counters (login/logout, hit/miss, refresh, safe retry, and mutation non-replay) to Allure and the integrated TXT/HTML report. Never publish session IDs or credentials in these metrics.
- Mark EMS1-6640 as `session_lifetime` rather than `smoke`. It remains in the full and session suites, while fast smoke runs avoid the fixed ten-minute boundary wait.

## Alternatives

- Cache raw session strings in fixtures: rejected because an already-yielded string cannot follow a refreshed session.
- Retry every request after `Not authorized`: rejected because a mutating request may already have taken effect.
- Share sessions across pytest processes: rejected because process coordination and same-account invalidation would make ownership ambiguous.
- Refresh immediately before 600 seconds: rejected because server/client clock differences and request latency leave no safety margin.

## Consequences

- Service call signatures remain unchanged at runtime, but common fixtures yield a refreshable session handle rather than a raw string.
- The API client resolves the handle immediately before each request, so cleanup callbacks use the current session after a refresh.
- Expected readonly mutation denials and noaccess denials do not churn the cache.
- Explicit fresh-session flows invalidate the matching cached role first to avoid same-account session conflicts.
- Cache reuse is the normal test-run policy; disabling it for rollback requires no code change.

## Validation

- Unit tests cover cache reuse, concurrent misses, failed login recovery, idempotent close, proactive refresh, feature-flag bypass, safe GET retry, mutation non-replay, role-specific authorization handling, and metrics redaction.
- Run compile checks and the focused session/client/fixture regression tests.
- Run a fast read-only EMS testcase that uses the shared readwrite fixture, followed by another testcase in the same pytest process, and confirm one cached login is reused.
