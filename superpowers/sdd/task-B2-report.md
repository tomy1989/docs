# Task B2 Report: Bot API Client + Sender Throttle + Dispatch

**Date:** 2026-06-29  
**Branch:** feat/telegram-channel  
**Commit:** 9773ed4 — `feat(telegram): bot API client, token-bucket throttle, _dispatch_telegram`

---

## What Was Done

### Files Created

1. **`app/utils/telegram_ratelimit.py`** — Fixed-window Redis throttle
   - `acquire_send_slot(bot_id, chat_id) -> float | None`
   - Per-chat: 1 msg/sec via Redis SET NX EX 1 lock
   - Per-bot: ≤30 msg/sec via incrementing 1s bucket key (expire=2)
   - Returns seconds-to-wait on a hit, None if allowed

2. **`app/services/telegram_api_client.py`** — Minimal Bot API client
   - `parse_retry_after(body) -> Optional[int]` — extracts `parameters.retry_after`
   - `TelegramApiClient(bot_token)` with `send_message(chat_id, *, text, photo_url, video_url, document_url, buttons)`
   - `_call()` retries up to 3× on 429, honors `retry_after`, surfaces 403 without retry
   - Returns project-standard `MetaApiResponse`

3. **`tests/test_telegram_sender.py`** — 2 tests
   - `test_dispatch_telegram_dry_run` — verifies `TELEGRAM_DRY_RUN=True` short-circuits and returns `dry_run=True`
   - `test_429_returns_retry_after` — verifies `parse_retry_after` extracts the field correctly

### Files Modified

4. **`app/services/message_service.py`** — 3 edits:
   - Line ~1803: Added `is_telegram = getattr(instance, 'platform', 'whatsapp') == InstancePlatform.TELEGRAM.value`
   - Line ~2162: Extended `effective_platform` ternary to include `"telegram" if is_telegram else ...`
   - Lines ~2312-2341: Added `elif is_telegram:` dispatch block (mirrors `is_tiktok` pattern exactly)
   - Lines ~4641-4686: Added `_dispatch_telegram()` function after `_dispatch_tiktok`

---

## Key Design Decisions

- **Import style**: `_dispatch_telegram` imports `settings` and `MetaApiResponse` locally (inside the function body), matching the `_dispatch_tiktok` pattern exactly.
- **Recipient resolution**: Uses `data.recipient or getattr(data, 'recipient_bsuid', None) or ""` — same resolution chain as TikTok/Messenger dispatchers.
- **No dry-run side-effects gate**: Unlike TikTok (which also guards billing/cap slots), Telegram has no per-conversation 10-msg cap, so no `_tg_dry_run` is needed at the top of `send_message_service`.
- **Test import fix**: Brief said `from app.schemas.enums import MessageType` — corrected to `from app.models.enums import MessageType` to match every other test in the project.

---

## Test Results

```
tests/test_telegram_sender.py::test_dispatch_telegram_dry_run PASSED
tests/test_telegram_sender.py::test_429_returns_retry_after PASSED
2 passed, 16 warnings in 0.27s
```

## Compile Results

```
py_compile: app/services/telegram_api_client.py app/utils/telegram_ratelimit.py app/services/message_service.py — All OK
```

---

## What B3 Will Need

- The `_dispatch_telegram` function is in place and tested.
- `is_telegram` is detected and `effective_platform` is set.
- `tg_bot_token` is stored encrypted on `Instances`; `decrypt_value` is already imported in `message_service.py` (line 37).
- Next task (B3: inbound webhook handler) can consume `TelegramApiClient` directly and reference `instance.tg_bot_token`.

---

## Review Fixes (2026-06-29)

Review came back **Approved** with 2 Important throttle findings + 1 spec-gap test. All three fixed in the same files.

### I1 (Important) — throttle ordering, `app/utils/telegram_ratelimit.py`
The per-chat `SET NX EX 1` lock was acquired BEFORE the per-bot counter check. On per-bot overflow (return `1.0`) the per-chat lock was left poisoned, locking that chat out for an extra second. **Fix:** reordered so the per-bot bucket `INCR` is checked FIRST; the per-chat lock is only acquired once the per-bot slot is granted (reorder, not deletion of the chat key).

### I2 (Important) — redundant slot re-acquire on retry, `app/services/telegram_api_client.py`
On a 429 retry, `_call` re-invoked `acquire_send_slot` on top of the `retry_after` sleep, double-charging the per-chat slot. **Fix:** guarded the throttle acquire with `if attempt == 0:` — the `parameters.retry_after` sleep already paces the retry.

### M3 (spec-gap test) — 403 opt-in, `tests/test_telegram_sender.py`
Added `test_403_opt_in_not_retried`: mocks `httpx.AsyncClient.post` to return a 403 with body `{"ok": false, "description": "Forbidden: bot can't initiate conversation with a user"}`, drives the real `client.send_message()` → `_call` path, and asserts `MetaApiResponse.success is False` AND `post.await_count == 1` (no retry on 403). `acquire_send_slot` is monkeypatched to a no-op so the test exercises pure `_call` behavior without hitting Redis. Verified the 403 path in `_call` returns immediately (403 is neither 200 nor 429, so it falls through to the failed-response return).

### Verification

Command:
```
.venv/bin/python -m pytest tests/test_telegram_sender.py -v -o addopts=""
```

Output:
```
tests/test_telegram_sender.py::test_dispatch_telegram_dry_run PASSED     [ 33%]
tests/test_telegram_sender.py::test_429_returns_retry_after PASSED       [ 66%]
tests/test_telegram_sender.py::test_403_opt_in_not_retried PASSED        [100%]
======================== 3 passed, 16 warnings in 0.28s ========================
```

`py_compile` on both changed source files (`telegram_ratelimit.py` + `telegram_api_client.py`): OK.

Fix commit: `fix(telegram): B2 throttle ordering + retry slot + 403 opt-in test`

---

## Fix round (review remediation) — commit 3f87aab

`fix(telegram): B2 throttle ordering + retry slot + 403 opt-in test`

Three review findings addressed in the same files:

- **I1 (Important) — throttle ordering** (`app/utils/telegram_ratelimit.py` `acquire_send_slot`): reordered so the per-bot 1s bucket is checked FIRST; the per-chat `SET NX EX 1` lock is now only acquired once the per-bot slot is granted. Previously a per-bot overflow (return 1.0) left a poisoned per-chat lock that blocked that chat for an extra second.
- **I2 (Important) — retry slot double-charge** (`app/services/telegram_api_client.py` `_call`): guarded `acquire_send_slot` with `if attempt == 0:`. On a 429 retry the `retry_after` sleep already paces the retry, so re-acquiring the per-chat slot is redundant.
- **M3 (spec gap) — 403 opt-in test** (`tests/test_telegram_sender.py`): added `test_403_opt_in_not_retried`, which patches `httpx.AsyncClient.post` (via a fake async client returning a 403 `{"ok": false, "description": "Forbidden: bot can't initiate conversation with a user"}`), drives the real `client.send_message(...)` → `_call` path, and asserts `resp.success is False`, `status_code == 403`, the description is surfaced, and the POST was awaited exactly once (no retry on 403). Throttle is neutralized via monkeypatch so it is a pure behavior test of the return/retry path.

### Test command + output

```
$ .venv/bin/python -m pytest tests/test_telegram_sender.py -v -o addopts=""
tests/test_telegram_sender.py::test_dispatch_telegram_dry_run PASSED      [ 33%]
tests/test_telegram_sender.py::test_429_returns_retry_after PASSED        [ 66%]
tests/test_telegram_sender.py::test_403_opt_in_not_retried PASSED         [100%]
======================== 3 passed, 16 warnings in 0.24s ========================
```

`py_compile` clean on `app/services/telegram_api_client.py` and `app/utils/telegram_ratelimit.py`.

Commit scoped to the three Telegram files only; unrelated working-tree modifications (instagram_auth_service.py, instance_service.py, a webhook test) were deliberately excluded.
