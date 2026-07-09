# Task B5 Report — Telegram Inbound Webhook Service

**Date:** 2026-06-29
**Branch:** feat/telegram-channel
**Commit:** 4c4774c

---

## Files Changed

| File | Change |
|---|---|
| `app/services/telegram_webhook_service.py` | Created (new) |
| `tests/test_telegram_webhook_service.py` | Created (new) |

---

## Messages Fields Mirrored

| Messages field | Value set |
|---|---|
| `user_id` | `instance.user_id` |
| `instance_id` | `instance.id` |
| `recipient` | `None` (Telegram has no phone) |
| `recipient_bsuid` | `str(chat_id)` (Telegram chat.id) |
| `sender_bsuid` | `str(chat_id)` (same — private DM) |
| `message_type` | classified via `_classify()` |
| `payload` | `{"text": text, "media_url": media_url}` |
| `status` | `MessageStatus.RECEIVED` |
| `direction` | `"inbound"` |
| `platform` | `"telegram"` |
| `source` | `"telegram_dm"` |
| `wa_message_id` | dedup key: `tg_{tg_bot_id}_{message_id}` |
| `wa_recipient_id` | `str(instance.tg_bot_id or "")` |
| `wa_phone_id` | `None` |
| `is_echo` | `False` |
| `media_source_url` | `None` (Telegram file_id is not a URL) |

---

## Instance Resolution

`_resolve_instance(db, payload)` reads `payload["_megasend_instance_id"]`, which was stamped by the B4 router at HTTP ingestion time before the payload was stored in `webhook_inbox`. This is a direct PK + platform filter query:

```python
db.query(Instances).filter(
    Instances.id == str(instance_id),
    Instances.platform == "telegram",
).first()
```

When the stamp is absent or the row doesn't exist, returns `None` → `{"status": "no_instance"}`.

---

## Automation Dispatch

`_try_fire_automation` runs in priority order:

1. **`/start` command** — checks `tg_automation_settings.start_payload_routes` for a deep-link key (e.g. `/start promo_abc`). Falls back to `welcome.enabled + welcome.text` with a Redis SETNX once-per-contact claim (`tg_welcome:{instance_id}:{chat_id}`, 1-year TTL).
2. **FAQ keywords** — iterates `tg_automation_settings.faq` dict, case-insensitive substring match. Dispatches a `reply_text` or a live flow (validated via `_faq_flow_is_live` before dispatch, so a deleted flow falls through rather than silently dropping the conversation).
3. **Away** — when outside business hours (via `_is_outside_business_hours`), once per 12h per contact (`tg_away:{instance_id}:{chat_id}`). Fails CLOSED on Redis error.

When any automation fires → returns `True` → caller suppresses generic flow + AI to prevent doubled replies.

---

## How Auto-Reply Reaches the Telegram Send Path

`_send_auto_reply(db, instance, chat_id, text, *, source)` calls `send_whatsapp_message` (the unified send path) with:
- `recipient=None`, `recipient_bsuid=chat_id`
- `message_type=MessageType.TEXT`

The `send_whatsapp_message` dispatch logic routes by `instance.platform`. The B2 message service (`telegram_message_service.py`) and the B1 API client (`telegram_api_client.py`) handle the actual Bot API `sendMessage` call, including the `TELEGRAM_DRY_RUN` guard and rate-limiting. This is the same path used by outbound sends, so billing metering + dry-run are inherited automatically.

---

## TDD RED/GREEN

### RED (tests before service existed)

```
$ cd /Users/weblix/projects/MegaSendCloud/MegaSend-CloudApi
$ .venv/bin/python -m pytest tests/test_telegram_webhook_service.py -v -o addopts=""

ERROR collecting tests/test_telegram_webhook_service.py
ImportError: No module named 'app.services.telegram_webhook_service'
```

### GREEN (after implementation)

```
$ .venv/bin/python -m pytest tests/test_telegram_webhook_service.py -v -o addopts=""

tests/test_telegram_webhook_service.py::test_inbound_text_materializes_message PASSED
tests/test_telegram_webhook_service.py::test_start_command_with_welcome_enabled_fires_auto_reply PASSED
tests/test_telegram_webhook_service.py::test_callback_query_triggers_postback_flows PASSED
tests/test_telegram_webhook_service.py::test_no_instance_id_returns_no_instance PASSED
tests/test_telegram_webhook_service.py::test_duplicate_dedup_does_not_reinsert PASSED
tests/test_telegram_webhook_service.py::test_image_message_classified_correctly PASSED

======================== 6 passed, 3 warnings in 0.14s =========================
```

All 10 pre-existing telegram tests (B1-B4) still pass after B5 is added.

---

## Self-Review

- `_classify()` handles all major Telegram media types (photo/video/document/sticker/voice/audio/location). Photo returns the `file_id` of the largest size (last in the array). This is a file_id, not a CDN URL — callers that need a URL would need to call `getFile`. For now this mirrors TikTok's approach (store the identifier, download separately).
- The dedup is a pre-insert query + IntegrityError catch. In concurrent high-volume scenarios a race between two workers claiming the same `(instance_id, wa_message_id)` is caught by the IntegrityError path, which returns `{"status": "duplicate"}` cleanly.
- Redis welcome/away claims fail CLOSED (return `False` on error), consistent with the TikTok and IG patterns — an outage never turns into welcome/away spam.
- `_trigger_postback_flows` uses `message_type="postback_telegram"` as the trigger discriminator, matching the spec. The flows engine on the other end can filter by this.
- `_run_route` for `/start` deep-link reply uses `loop.create_task` when in an async context. This is the same approach used elsewhere in the codebase for fire-and-forget work launched from a sync helper called during async execution.

---

## Concerns / Deferred

1. **Telegram file_id is not a URL** — `media_source_url` is set to `None` for all Telegram media. The media download service (used by IG) would need a Telegram-aware branch to call `getFile` and fetch the URL before downloading. Deferred to a later task.
2. **`_trigger_postback_flows` is sync** — consistent with TikTok/Messenger pattern; the celery enqueue itself is non-blocking. If flows need to be awaited in the future, this would require a refactor of all channel services uniformly.
3. **Welcome re-fires on `/start` after a year** — the 365-day TTL on `tg_welcome` is by design (mirrors TikTok). If a customer explicitly `/start`s again after a year, they get a welcome message. This is intentional.

---

## Code Review Fixes (commit d321235)

A peer review found 5 cloning gaps vs the TikTok/Messenger templates. All fixed; tests extended 6 -> 8.

### CRITICAL 1 — Generic + postback flows were silently DEAD

**Root cause:** `_trigger_flows` passed `webhook_event_id=None`. The Celery task `trigger_flows_for_message_task` does `UUID(webhook_event_id)` (crashes on None) and the inline `FlowExecutionService.trigger_flows_for_incoming_message` looks up a `WhatsAppWebhookEvent` by that id and returns `[]` when missing. Either way, zero flows fire.

**Fix:** Refactored to a `_materialize()` method (mirroring `messenger_webhook_service._materialize`) that inserts BOTH the `Messages` row and a `WhatsAppWebhookEvent` audit/window row inside one savepoint + commit, and returns the real event UUID. That UUID is now threaded into `_trigger_flows(..., event_id, full_payload)`. For the postback path, a dedicated `_materialize_postback_event()` creates a `WhatsAppWebhookEvent` (keyed on the callback id) and its real UUID is passed to the flow service.

**Confirmation:** `test_inbound_text_materializes_message` now asserts exactly one `WhatsAppWebhookEvent` row is created and that `_trigger_flows` receives a non-None UUID that round-trips through `uuid.UUID(...)`. `test_postback_passes_trigger_type_to_flow_service` asserts `webhook_event_id is not None` reaches the flow service.

### CRITICAL 2 — Premature commit could drop the Messages row

**Root cause:** `_upsert_contact` called `db.commit()` while the Messages row was added-but-uncommitted in the same session; a contact failure + rollback would silently lose the Messages row, yet the caller still broadcast/triggered flows against a nonexistent row.

**Fix:** The Messages + event rows are now committed by the single `_materialize()` commit BEFORE `_upsert_contact` runs. `_upsert_contact` no longer owns the message write — it adds the contact inside its own `begin_nested()` savepoint so a contact-insert failure rolls back ONLY the contact, never the already-persisted Messages row. `db.refresh(message)` happens inside `_materialize` after its commit.

**Confirmation:** `test_materialize_integrity_race_returns_winner_not_created` exercises the savepoint/IntegrityError path; `_materialize` is the sole commit point for the message.

### IMPORTANT — Postbacks never matched

**Root cause:** `_trigger_postback_flows` enqueued via the Celery task with `message_type="postback_telegram"`, but the flow engine filters on `Flows.trigger_type` (default `incoming_message`) and the Celery task drops any trigger_type kwarg entirely.

**Fix:** `_trigger_postback_flows` is now an `async` method that calls `FlowExecutionService.trigger_flows_for_incoming_message` INLINE (awaited) with `trigger_type="postback_telegram"` — the same pattern as `messenger_webhook_service._trigger_postback_flows` (`postback_messenger`). The caller in `process_webhook_event` now `await`s it.

**Confirmation:** `test_postback_passes_trigger_type_to_flow_service` asserts `kw["trigger_type"] == "postback_telegram"` reaches the flow service.

### MINOR — `_run_route` fire-and-forget

**Fix:** `_run_route` is now `async` and `await`s `_send_auto_reply` directly (no `loop.create_task` that swallowed exceptions / leaked coroutines in tests). The call site in `_try_fire_automation` now `await`s it.

### MINOR — Inbound status sentinel

**Fix:** Inbound `status` changed from `MessageStatus.RECEIVED` to `MessageStatus.SENT` (matches TikTok/Messenger/Widget; some billing/status queries filter `status in [SENT, DELIVERED, READ]`). Comment retained noting there is no INBOUND enum.

**Confirmation:** `test_inbound_text_materializes_message` asserts `m.status == MessageStatus.SENT`.

### Test output (after fixes)

```
$ .venv/bin/python -m pytest tests/test_telegram_webhook_service.py -v -o addopts=""
8 passed, 16 warnings in 0.29s

$ .venv/bin/python -m pytest tests/test_telegram_webhook_service.py tests/test_telegram_webhook_ingest.py tests/test_telegram_model.py tests/test_telegram_sender.py -o addopts="" -q
18 passed, 159 warnings in 3.44s
```

(`pytest -k telegram` over the whole `tests/` dir hits 2 PRE-EXISTING collection errors in unrelated AI modules — `test_ai_analytics_empty_data.py` / `test_ai_billing_stripe_only.py`, both `cannot import name 'User' from app.db.models.users` — not introduced by B5. Telegram tests run clean by explicit path.)
