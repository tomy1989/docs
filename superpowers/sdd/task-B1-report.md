# Task B1 Report — Instance model + migration + config

**Date:** 2026-06-29  
**Branch:** feat/telegram-channel  
**Commit:** a25fd1c — "feat(telegram): instance tg_* columns + migration + config"

---

## What Was Built

### 1. `app/db/models/instances.py`
- Added `TELEGRAM = "telegram"` to `InstancePlatform` enum (after `WEB = "web"`).
- Added 8 `tg_*` columns after the TikTok `tk_automation_settings` block:
  - `tg_bot_id` (String, unique, indexed) — numeric token prefix, bot identity
  - `tg_bot_token` (String) — ENCRYPTED at rest via `set_telegram_bot_token`
  - `tg_bot_username` (String(64)) — @botusername, plain
  - `tg_bot_name` (String(100)) — display name, plain
  - `tg_webhook_secret` (String) — per-bot `X-Telegram-Bot-Api-Secret-Token`, plain
  - `tg_avatar_url` (String) — cached bot avatar
  - `tg_avatar_url_updated_at` (DateTime(timezone=True)) — freshness stamp
  - `tg_automation_settings` (JSONB) — owner-configured automation blob
- Added `set_telegram_bot_token(plaintext_token)` method, placed immediately before `set_business_account_id` (consistent with the encrypt-setter pattern). Validates token format, splits the numeric prefix into `tg_bot_id`, and encrypts the full token via `encrypt_value`.

### 2. `app/db/migrations/versions/20260701_telegram_channel.py`
- `revision = "20260701_telegram"`
- `down_revision = "20260626_conv_phone_no_plus"` (actual head at time of writing — NOT hardcoded from the brief's placeholder)
- `upgrade()`: adds all 8 columns + unique index `ix_instances_tg_bot_id`
- `downgrade()`: drops index then drops all 8 columns in reverse order
- Safety guards: `SET LOCAL statement_timeout = '2min'` and `SET LOCAL lock_timeout = '15s'`

### 3. `app/config.py`
- Added three Telegram settings after the `TIKTOK_DRY_RUN` line:
  ```python
  self.TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
  self.TELEGRAM_DRY_RUN = os.getenv("TELEGRAM_DRY_RUN", "false").lower() == "true"
  self.TELEGRAM_WEBHOOK_BASE_URL = os.getenv("TELEGRAM_WEBHOOK_BASE_URL", "")
  ```
  All three default to safe/off values.

### 4. `tests/test_telegram_model.py`
- `test_telegram_platform_enum` — asserts `InstancePlatform.TELEGRAM.value == "telegram"`
- `test_set_telegram_bot_token_encrypts` — instantiates `Instances`, calls `set_telegram_bot_token`, asserts ciphertext != plaintext, `decrypt_value` round-trips correctly, `tg_bot_id` == `"123456"`

---

## TDD RED/GREEN Evidence

### RED phase
```
$ .venv/bin/python -m pytest tests/test_telegram_model.py -v -o addopts=""
FAILED tests/test_telegram_model.py::test_telegram_platform_enum
  AttributeError: type object 'InstancePlatform' has no attribute 'TELEGRAM'
FAILED tests/test_telegram_model.py::test_set_telegram_bot_token_encrypts
  AttributeError: 'Instances' object has no attribute 'set_telegram_bot_token'
2 failed
```

### GREEN phase
```
$ .venv/bin/python -m pytest tests/test_telegram_model.py -v -o addopts=""
PASSED tests/test_telegram_model.py::test_telegram_platform_enum
PASSED tests/test_telegram_model.py::test_set_telegram_bot_token_encrypts
2 passed
```

---

## Syntax Gate
```
$ .venv/bin/python -m py_compile app/db/models/instances.py app/db/migrations/versions/20260701_telegram_channel.py app/config.py
SYNTAX OK
```

---

## Alembic Heads
```
$ .venv/bin/python -m alembic heads
20260701_telegram (head)
```

Single head — the migration chains correctly from `20260626_conv_phone_no_plus` and does NOT create a second head.

**Live migration application is DEFERRED to the controller** — the remote DB is not mutated here per project convention.

---

## Files Changed
- `app/db/models/instances.py` — enum + 8 columns + setter method
- `app/db/migrations/versions/20260701_telegram_channel.py` — new (created)
- `app/config.py` — 3 new settings
- `tests/test_telegram_model.py` — new (created)

---

## Self-Review

- Enum value `"telegram"` matches global constraints exactly.
- `tg_bot_token` is encrypted at rest; `tg_bot_id` (plain) is the dedup/routing key — same split pattern used by `fb_page_id` (plain) vs `fb_page_access_token` (encrypted).
- `set_telegram_bot_token` raises `ValueError` on malformed tokens (no colon).
- The unique index on `tg_bot_id` enforces one instance per bot across all tenants (a bot token can only be registered once — if someone re-registers the same bot it must replace, not duplicate).
- Config defaults are all fail-safe (off/empty).
- Migration has safe DDL timeouts matching the pattern from TikTok/Messenger migrations.

## Concerns
None — implementation is straightforward and follows existing patterns exactly. The only deferred item (live migration application) is by design.
