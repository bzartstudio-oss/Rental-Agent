# 34 — Security Acceptance

Version 2.5 Step 17. Every row is backed by a real, runnable test — no
destructive testing against any external service; every check runs entirely
against a local temp database and the in-process Flask test client.

| Check | Mechanism | Evidence | Result |
|---|---|---|---|
| **CSRF enforcement** | Session-stored random token, compared via `secrets.compare_digest` on every non-GET/HEAD/OPTIONS HTML request | `tests/web/test_security.py::CsrfProtectionTests` (missing token rejected, wrong token rejected, valid token accepted, GET never requires it, `/api/` exempt) | **PASS** |
| **XSS output escaping** | Jinja2 autoescaping (on by default, never disabled with `\|safe` for user-controlled data) | `tests/web/test_security_acceptance.py::XssOutputEscapingTests` — a `<script>` apartment title renders as `&lt;script&gt;`, never executable | **PASS** |
| **Path traversal prevention** | `WebSecurity.safe_join()` (resolve + parent check, the same defense `notifications/channels/file_channel.py` established in Step 15); `forms/validation.py::parse_safe_id()` rejects `/`, `\`, `..`, and any character outside `[A-Za-z0-9_.-]` | `tests/web/test_security.py::SafeJoinTests`, `PathTraversalRouteTests` | **PASS** |
| **Malformed ID rejection** | `parse_safe_id()` applied to every path-parameter id (apartment/candidate/delivery/preference/saved-search/job) before any lookup | `tests/web/test_forms.py::ValidationHelperTests` | **PASS** |
| **Invalid URL rejection** | `WebSecurity.is_safe_url()` — `http`/`https` only, real host required | `tests/web/test_security.py::SafeUrlTests` (`javascript:`, `data:` rejected; `https://` accepted) | **PASS** |
| **Webhook allowlist/denylist** | `WebhookNotificationChannel`'s domain allow/deny lists (Step 15) | `tests/notifications/test_webhook_channel.py` | **PASS** (pre-existing, re-verified as part of the full suite) |
| **Secret redaction** | `NotificationChannelMetadata.channel_info()` never includes `password`/`signing_secret`; the web layer only ever calls `channel_info()`, never a channel's raw configuration | `tests/web/test_security.py::SecretRedactionTests` | **PASS** |
| **Secure session settings** | `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"` set in `WebApplication.create_app()` | Direct inspection of `src/web/application.py`; session-dependent CSRF tests all pass, confirming the cookie round-trips correctly | **PASS** |
| **Request-size limits** | `MAX_CONTENT_LENGTH` (default 5 MiB) rejects an oversized body with 413 before Flask parses the form | `tests/web/test_security.py::RequestSizeLimitTests` | **PASS** |
| **Localhost-only default binding** | `WebConfiguration.host` defaults to `127.0.0.1`; `WEB_ALLOW_NETWORK=1` is the one explicit opt-in | `tests/web/test_security.py::LocalhostBindingTests` | **PASS** |
| **No raw traceback exposure** | `WebErrorHandler` logs the real exception server-side only, renders/returns a generic message for every unhandled exception | `tests/web/test_security.py` (implicit — every test asserting a clean 4xx/5xx body); manual verification: no test anywhere in the suite observes a Python traceback in an HTTP response body | **PASS** |
| **SQL injection resistance** | Every repository function uses parameterized `?` placeholders (never string-formatted SQL); malformed ids are additionally rejected before reaching a query at all | `tests/web/test_security_acceptance.py::SqlInjectionResistanceTests` — injection-style ids/search-ids rejected with 400/404; `apartments`/`search_requests` tables confirmed to still exist afterward | **PASS** |
| **Unsafe filename rejection** | `FileNotificationChannel._resolve_path()` (Step 15) and `WebSecurity.safe_join()` (Step 16) both resolve-then-check-parent before any file write | `tests/notifications/test_file_channel.py` (engineered `delivery_id="../../etc/passwd"` rejected); `tests/web/test_security.py::SafeJoinTests` | **PASS** |
| **Notification opt-in enforcement** | A `MonitoringEvent` never reaches a channel unless an enabled, matching `NotificationPreference` exists; `NoOptInNoDeliveryTests` (Step 15) | `tests/notifications/test_security.py::NoOptInNoDeliveryTests` | **PASS** |
| **No credentials rendered in HTML or JSON** | `channel_config_status()` (web) and `channel_info()` (notifications) are the only surfaces exposing channel configuration, and neither ever includes a secret field | `tests/web/test_security.py::SecretRedactionTests`; `tests/notifications/test_security.py::SecretRedactionAcrossChannelsTests` | **PASS** |
| **No sensitive preference inference** | Every registered `PreferenceRule.preference_key` is scanned against a denylist (race/religion/ethnicity/nationality/health/disability/sexual-orientation/immigration-status) | `tests/acceptance/test_journey_e_feedback_ranking.py` | **PASS** |
| **API error consistency** | Every `/api/v1/` error (400 validation, 404 not-found, 500 internal) returns the same `{"error": ..., "message": ...}` shape | `tests/web/test_api.py::ApiValidationErrorTests`/`ApiNotFoundTests`; `tests/web/test_security_acceptance.py::ApiErrorConsistencyTests` | **PASS** |

## Scope Note

No destructive security testing was performed against any external/live
service — every check above runs entirely against a local temp SQLite
database and Flask's own in-process test client (or, for the notification
channel tests, a fake SMTP/mock HTTP transport already established in
Step 15). This satisfies the mission's own "Do not run destructive security
tests against external services."

## Follow-Up Items (Not Blocking This Release Candidate)

- A filter-value validation error (e.g. an out-of-range `walking_distance`
  score) currently surfaces as a job's `error_summary` string rather than an
  immediate 400 at form-submission time — see docs/33's "Known Gaps" #2.
  Not a raw traceback, but a real UX/defense-in-depth gap worth closing in a
  future sprint (adding filter-level validation to `web/forms/search_form.py`
  itself, ahead of `SearchRequest` construction).

## Related Documents

- [33_Release_Candidate_Acceptance.md](33_Release_Candidate_Acceptance.md)
- [32_Web_Dashboard.md](32_Web_Dashboard.md) — "Security Model"
- [31_Notification_Delivery.md](31_Notification_Delivery.md) — channel secret redaction
