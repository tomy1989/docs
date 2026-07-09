# Task B4 Report — Telegram Webhook Ingestion

**Date:** 2026-06-29  
**Branch:** feat/telegram-channel

---

## enqueue Signature Matched

From `app/services/webhook_inbox_service.py`:

```python
def enqueue(
    db: Session,
    *,
    raw_payload: Dict[str, Any],
    headers: Optional[Dict[str, Any]] = None,
    signature: Optional[str] = None,
    signature_valid: bool = False,
    instance_hint: Optional[str] = None,
) -> Optional[UUID]:
```

The router calls it as:
```python
enqueue_webhook_inbox(
    db,
    raw_payload=body,           # with body["object"] = "telegram" pre-stamped
    headers=dict(request.headers),
    signature=request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""),
    signature_valid=True,       # secret verified BEFORE calling enqueue
    instance_hint=str(inst.id),
)
```

---

## Secret Dependency Behavior

`app/dependencies/telegram_secret_dependency.py` — `verify_telegram_secret(instance_id, request, db)`:

1. Queries `Instances` for `id == instance_id AND platform == 'telegram'`.
2. If no instance or no `tg_webhook_secret`: 404 in prod, dev-skip warning in `ENVIRONMENT=='local'`.
3. Extracts `X-Telegram-Bot-Api-Secret-Token` header (defaults to empty string on missing header).
4. `hmac.compare_digest(header, inst.tg_webhook_secret)` — constant-time compare, no timing leak.
5. Mismatch → 401. Match → returns the `Instances` row.

Called as a regular function (not a `Depends`) inside the route handler so `instance_id` from the path and the `db` session are both in scope.

---

## Drainer Case Added

`celery-worker/tasks/webhook_inbox_tasks.py` — added `elif obj == "telegram":` block after the `tiktok_messaging` branch (~line 146):

```python
elif obj == "telegram":
    from app.services.telegram_webhook_service import TelegramWebhookService  # noqa: E402
    coro = TelegramWebhookService().process_webhook_event(db, payload, webhook_config)
```

Also added `"telegram"` to the `webhook_config = None if obj in (...)` guard so no WABA lookup is wasted on Telegram payloads (instance_hint is the instance UUID, not a WABA id).

---

## main.py Registration

Two changes:

1. Import added next to `telegram_routes`:
   ```python
   from app.routes.telegram_webhook_router import router as telegram_webhook_router
   ```

2. `include_router` added after `telegram_router`:
   ```python
   app.include_router(telegram_webhook_router)  # Telegram inbound webhook (secret-token-authed)
   ```

---

## TDD RED → GREEN

### RED (before implementation)

```
$ .venv/bin/python -m pytest tests/test_telegram_webhook_ingest.py -v -o addopts=""
FAILED test_webhook_rejects_bad_secret          — 404 == 401 (route didn't exist)
FAILED test_webhook_rejects_missing_secret_header — 404 == 401
FAILED test_webhook_accepts_good_secret_returns_200_and_enqueues — 404 == 200
PASSED test_webhook_unknown_instance_returns_404  — trivially 404 from FastAPI
3 failed, 1 passed
```

Failure reason: `404 Not Found` — the route `/telegram-webhook/{id}/callback` didn't exist. All 3 meaningful tests failed for the right reason.

### GREEN (after implementation)

```
$ .venv/bin/python -m pytest tests/test_telegram_webhook_ingest.py -v -o addopts=""
PASSED test_webhook_rejects_bad_secret
PASSED test_webhook_rejects_missing_secret_header
PASSED test_webhook_accepts_good_secret_returns_200_and_enqueues
PASSED test_webhook_unknown_instance_returns_404
4 passed, 159 warnings
```

### Syntax check

```
$ .venv/bin/python -m py_compile app/dependencies/telegram_secret_dependency.py \
    app/routes/telegram_webhook_router.py app/main.py \
    celery-worker/tasks/webhook_inbox_tasks.py
ALL SYNTAX OK
```

---

## Files Changed

| File | Type | Change |
|------|------|--------|
| `app/dependencies/telegram_secret_dependency.py` | CREATE | `verify_telegram_secret` — constant-time secret check |
| `app/routes/telegram_webhook_router.py` | CREATE | `POST /telegram-webhook/{instance_id}/callback` |
| `app/main.py` | MODIFY | Import + `include_router` for `telegram_webhook_router` |
| `celery-worker/tasks/webhook_inbox_tasks.py` | MODIFY | `elif obj == "telegram":` drainer case + "telegram" in webhook_config skip list |
| `tests/test_telegram_webhook_ingest.py` | CREATE | 4 tests: bad-secret 401, missing-header 401, good-secret 200+enqueue, unknown-instance 404 |

---

## Self-Review

- Secret dependency uses `hmac.compare_digest` — constant-time, no timing leak.
- Fails CLOSED: 404 on unknown instance (not 200), 401 on mismatch (not 200).
- `object='telegram'` stamped BEFORE enqueue so drainer never routes to WA/IG handlers.
- `instance_hint=str(inst.id)` — the Telegram instance UUID, not a WABA id. The drainer correctly skips `_resolve_webhook_config` for telegram (added to the skip list).
- Drainer import is LAZY (`from app.services.telegram_webhook_service ...` inside the branch) — B5's absence doesn't affect app boot or these tests.
- Route returns 200 `{"status": "disabled"}` when `TELEGRAM_ENABLED=False` so Telegram's test-ping during setWebhook still gets 200.
- `signature_valid=True` is set correctly in the enqueue call because `verify_telegram_secret` already validated the secret before we reach that line; the drainer's `signature_valid=False` skip logic would NOT incorrectly skip Telegram rows.

## Concerns

- None blocking. The test for the 200/enqueue case patches `settings.TELEGRAM_ENABLED=True` — this is expected since the flag is off by default. The patch is clean via `unittest.mock.patch`.
- B5 (`TelegramWebhookService`) does not exist yet; the lazy import in the drainer branch will raise `ImportError` at drain-time (not boot-time), fast-failing to dead-letter in one attempt per the developer-error policy. This is correct behavior for an incomplete feature chain.

---

## B4 Review Remediation (2026-06-29)

Three findings closed in a single follow-up fix commit:

### I1 — local-dev no-instance enqueue guard (router)
`verify_telegram_secret` can return `inst = None` only when `ENVIRONMENT=='local'` and no instance/secret matched (the dep raises 404 in non-local envs). The handler previously stamped + enqueued with `instance_hint = instance_id` (raw path string, not a UUID), creating a row the drainer can't resolve. Fix: right after the secret check, `if inst is None:` log a local-dev warning and `return {"status": "ignored_local_no_instance"}` WITHOUT enqueuing. Production unchanged (unreachable there). Also dropped the now-dead `if inst else instance_id` ternary on `instance_hint` → always `str(inst.id)`.

### I2 — symmetric settings patching (tests)
The 200/enqueue test patched `app.routes.telegram_webhook_router.settings`, but `verify_telegram_secret` reads `settings` from `app.dependencies.telegram_secret_dependency`. Switched to `monkeypatch.setattr(app.config.settings, ...)` on the shared singleton both modules import, so env/feature-gate checks are symmetric across both modules.

### Security — secret_token must not be stored at rest (router)
The enqueue call persisted the per-bot secret into the durability inbox via `signature=<raw secret>` AND `headers=dict(request.headers)` (which contains the secret header). Fix:
- `signature=""` (verification already recorded by `signature_valid=True`; the raw value has no downstream purpose).
- Headers filtered: `{k: v for k, v in request.headers.items() if k.lower() != "x-telegram-bot-api-secret-token"}`.

Added real assertions: `signature == ""`, the secret header key is absent from stored headers, and the raw secret value appears in no stored header value. Also added a behavior test for I1 asserting `enqueue` is NOT called and status is `ignored_local_no_instance`.

### Test command + output
```
$ .venv/bin/python -m pytest tests/test_telegram_webhook_ingest.py -v -o addopts=""
5 passed, 159 warnings in 3.79s
```
Tests: bad-secret 401, missing-header 401, good-secret 200+enqueue-stamp+secret-not-stored, unknown-instance 404, local-dev-no-instance ignored-not-enqueued.

`.venv/bin/python -m py_compile app/routes/telegram_webhook_router.py app/dependencies/telegram_secret_dependency.py` → SYNTAX OK.
