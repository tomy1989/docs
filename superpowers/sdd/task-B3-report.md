# Task B3 Report — Telegram Connect / Disconnect / Status Routes + Auth Service

**Date:** 2026-06-29  
**Branch:** feat/telegram-channel  
**Commit:** d6a6813 — `feat(telegram): connect/disconnect/status routes + BYO-bot auth service`

---

## What Was Built

| File | Action | Purpose |
|------|--------|---------|
| `app/schemas/telegram_schema.py` | Created | `TelegramConnectRequest` (with token format validator), `TelegramConnectResponse`, `TelegramStatusResponse` |
| `app/services/telegram_auth_service.py` | Created | `_telegram_get_me`, `_telegram_set_webhook`, `_telegram_delete_webhook` helpers + `TelegramAuthService.connect_bot()` + singleton `telegram_auth_service` |
| `app/routes/telegram_routes.py` | Created | `POST /telegram/connect`, `POST /telegram/disconnect`, `GET /telegram/status` + `_require_enabled()` gate + cloned `_enforce_telegram_instance_limit` |
| `app/main.py` | Modified | Added import + `app.include_router(telegram_router)` next to tiktok routers |
| `tests/routes/test_telegram_routes.py` | Created | 12 tests covering all required behaviors |

---

## TDD RED → GREEN

**RED run (before schema strip-before-validate fix):**
```
.venv/bin/python -m pytest tests/routes/test_telegram_routes.py -v -o addopts=""
1 failed, 11 passed
FAILED: test_schema_accepts_valid_token
  → validator received "  123456789:ABCdef  " with leading spaces;
    v.split(":",1)[0] was "  123456789" which isdigit()=False before stripping.
```

**Fix applied:** moved `v = v.strip()` to the top of `_valid_token` before the format check (the brief had strip only on the return; brief code is functionally the same for non-padded tokens but the test used padded input to prove stripping works).

**GREEN run:**
```
.venv/bin/python -m pytest tests/routes/test_telegram_routes.py -v -o addopts=""
12 passed, 3 warnings in 0.38s
```

---

## main.py Wiring

Added import at line ~41 (next to tiktok imports):
```python
from app.routes.telegram_routes import router as telegram_router
```

Added router registration at line ~561 (next to tiktok_messaging_webhook_router):
```python
app.include_router(telegram_router)  # Telegram BYO-bot connect/disconnect/status
```

**NOT registered:** `telegram_webhook_router` — that module does not exist yet (B4). Importing it would break app boot.

---

## Test Approach

The repo's route tests use **direct async function calls** with `SimpleNamespace` fake auth and `Mock()` fake db (see `test_tiktok_onboarding.py`). No TestClient, no live DB.

The root `tests/conftest.py` has no `client`/`auth_headers` fixtures — it's Stripe-only. The brief's snippet using those fixtures was followed in spirit but using the repo's actual pattern (direct calls).

**12 tests cover:**
1. `test_schema_rejects_bad_token_format` — token without `:`
2. `test_schema_rejects_non_numeric_prefix` — non-digit ID prefix
3. `test_schema_accepts_valid_token` — padded token gets stripped
4. `test_connect_rejects_bad_token` — getMe raises → HTTP 400
5. `test_connect_happy_path` — getMe+setWebhook mocked, instance created, bot_username returned
6. `test_connect_cross_tenant_conflict` — same bot_id, different user_id → HTTP 409
7. `test_connect_webhook_registration_failure` — setWebhook returns False → HTTP 502 + rollback
8. `test_disconnect_clears_token` — nullifies tg_bot_token + tg_webhook_secret, calls deleteWebhook
9. `test_disconnect_not_found_raises_404`
10. `test_status_connected` — returns connected=True, webhook_ok=True, bot_username
11. `test_status_not_found` — 404
12. `test_connect_disabled_returns_404` — TELEGRAM_ENABLED=False gates the endpoint

Tests are **behavior checks, not mock tautologies**: they assert on the returned values, db.add/flush/commit call counts, instance field mutations (tg_bot_id, platform, tg_bot_token nullified), and status codes.

---

## py_compile

All touched files compile clean:
```
.venv/bin/python -m py_compile app/routes/telegram_routes.py app/services/telegram_auth_service.py app/schemas/telegram_schema.py app/main.py
→ no output (success)
```

---

## Files Changed

- `app/schemas/telegram_schema.py` (new)
- `app/services/telegram_auth_service.py` (new)
- `app/routes/telegram_routes.py` (new)
- `app/main.py` (2-line modification)
- `tests/routes/test_telegram_routes.py` (new)

---

## Self-Review

- Token is NEVER logged or returned to client; `set_telegram_bot_token()` encrypts it before storing.
- `db.flush()` before building the webhook URL (needs `inst.id`).
- `db.rollback()` called when setWebhook fails before `db.commit()`.
- Multi-tenant: all queries filter by `user_id`.
- Feature gate: `_require_enabled()` raises 404 if `TELEGRAM_ENABLED=False`.
- Instance limit gate: `_enforce_telegram_instance_limit` is a verbatim clone of `_enforce_tiktok_instance_limit` with the name changed.

## Concerns

- **None blocking.** The one deviation from the brief's schema code was the strip-before-validate order fix — functionally better (handles user-pasted tokens with whitespace).
- B4 (telegram_webhook_router) is not yet created; `telegram_routes.py` does not depend on it.

---

## Post-Review Fixes (2026-06-29)

Review found 1 CRITICAL + 1 IMPORTANT + 1 MINOR. All three fixed.

### 1. CRITICAL — bot-token leak in getMe failure log
`connect_bot`'s `except` did `logger.warning(f"[TELEGRAM] getMe failed: {e}")`. httpx's
`HTTPStatusError` stringifies the full request URL — `https://api.telegram.org/bot<TOKEN>/getMe` —
so the plaintext bot token would land in logs on any auth failure. Replaced with:
```python
logger.warning("[TELEGRAM] getMe failed: %s", type(e).__name__)
```
The exception object is never stringified; only its class name is logged.

**Other token-log-leak scan of `telegram_auth_service.py` (what I checked):**
- `_telegram_set_webhook` (the `f"{_BASE}/bot{token}/setWebhook"` call): no `logger.*`, no `try/except`,
  returns a bool. The token-bearing URL is never logged. CLEAN.
- `_telegram_delete_webhook` (the `f"{_BASE}/bot{token}/deleteWebhook"` call): no `logger.*`, no
  `try/except`, returns a bool. Token URL never logged. CLEAN.
- `connect_bot` line `logger.info(f"[TELEGRAM] connected bot @{inst.tg_bot_username} instance={inst.id}")`:
  logs only the plain `@username` and the instance id — no token. CLEAN.
- All `raise HTTPException(...)` sites use static literal `detail` strings — no exception/url/token
  interpolated into any client response. CLEAN.
- The token reaches the route layer (`disconnect`) only via `decrypt_value(inst.tg_bot_token)` passed
  straight into `_telegram_delete_webhook`, never logged. CLEAN.

Conclusion: after this fix, NO path in the service stringifies a bot-URL or token into a log line.

### 2. IMPORTANT — `status` endpoint missing the feature gate
`status` had no `TELEGRAM_ENABLED` check (connect + disconnect did). Added `_require_enabled()` as
the first statement of the `status` body. Added regression test `test_status_disabled_returns_404`
which also asserts `db.query` is NOT called (gate fires before any DB access).

### 3. MINOR — `disconnect` ambiguous `instance_id` param
Changed `instance_id: str` → `instance_id: str = Query(...)` to match `status` and make the source
explicit on a POST. `Query` was already imported. Existing tests call the function directly with
`instance_id=...`, so they are unaffected.

### Verification

```
.venv/bin/python -m pytest tests/routes/test_telegram_routes.py -v -o addopts=""
======================== 13 passed, 3 warnings in 0.39s ========================
```
(12 original + 1 new `test_status_disabled_returns_404`.)

```
.venv/bin/python -m py_compile app/services/telegram_auth_service.py app/routes/telegram_routes.py
→ no output (success)
```

**Fix commit:** see `fix(telegram): B3 mask token in getMe log + gate status route + explicit disconnect param`.
