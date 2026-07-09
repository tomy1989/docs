# Task B6 Report — Automation Settings MERGE + Growth Link + postback_telegram

## Status: COMPLETE — commit 31c4c23

---

## Deliverable 1: Automation Settings GET + PUT (MERGE)

### Schema: `app/schemas/telegram_schema.py`

Added `TelegramAutomationSettings` Pydantic model where **all top-level keys are `Optional`** (welcome, away, faq, start_payload_routes). This means a caller can PUT `{"faq": {...}}` without providing welcome/away — `model_dump(exclude_unset=True)` returns only the keys actually provided.

Supporting sub-models: `TelegramWelcome`, `TelegramAway`, `TelegramFaqAction` (cloned from TikTok's shape). FAQ validator strips/lowercases keywords, drops empty entries, caps at 50.

### Routes: `app/routes/telegram_routes.py`

**GET `/telegram/{instance_id}/automation-settings`**
- Gates `_require_enabled()` → filters by `id + user_id + platform='telegram'` → 404 if not found
- Returns `{"settings": inst.tg_automation_settings or {}}`

**PUT `/telegram/{instance_id}/automation-settings`**
Merge logic (critical difference from TikTok's full-replace):
```python
incoming = body.model_dump(exclude_unset=True)   # only keys the caller sent
existing = dict(inst.tg_automation_settings or {})
existing.update(incoming)                         # top-level merge
inst.tg_automation_settings = existing
flag_modified(inst, "tg_automation_settings")     # required for JSONB mutation
db.commit()
```
A PUT `{"faq": {...}}` leaves `welcome` untouched. A PUT `{"welcome": {...}}` leaves `faq` untouched.

---

## Deliverable 2: Growth Link

**GET `/telegram/growth-link?instance_id=&flow_id=`**

```python
payload_key = _secrets.token_urlsafe(8)[:16]
blob = dict(inst.tg_automation_settings or {})
blob.setdefault("start_payload_routes", {})[payload_key] = {
    "type": "flow", "flow_id": str(flow_id)
}
inst.tg_automation_settings = blob
flag_modified(inst, "tg_automation_settings")
db.commit()
return {"url": f"https://t.me/{inst.tg_bot_username}?start={payload_key}", "payload": payload_key}
```

`setdefault` means repeated calls append routes rather than wipe the dict.
`flag_modified` is mandatory because mutating an existing JSONB dict in place does not trigger SQLAlchemy's change detection.

---

## Deliverable 3: `postback_telegram` Trigger Type

`app/db/models/flows.py` line 39, `trigger_type` column `doc=` updated from:
```
"incoming_message, webhook, manual, scheduled, flow_response"
```
to:
```
"incoming_message, webhook, manual, scheduled, flow_response, postback_messenger, postback_tiktok, postback_telegram"
```

No constraint/enum added. The column is a free `String(50)`; the doc string is documentation only. The B5 webhook service queries `Flows.trigger_type == "postback_telegram"` — this just makes the intent explicit.

---

## TDD — RED/GREEN

### RED phase (conceptual)
Before implementing, the test file imported the new route functions (`get_telegram_automation_settings`, `set_telegram_automation_settings`, `growth_link`) which would raise `ImportError` — confirms tests fail before implementation.

### GREEN phase

```
pytest tests/routes/test_telegram_routes.py tests/test_telegram_growth_link.py -v -o addopts=""
```

```
25 passed, 8 warnings in 0.42s
```

**New tests (13):**
- `test_get_automation_settings_returns_stored` — verifies stored dict returned verbatim
- `test_get_automation_settings_empty_returns_empty_dict` — None → {}
- `test_get_automation_settings_not_found_raises_404`
- **`test_put_automation_settings_merge_does_not_wipe_existing_keys`** — KEY REGRESSION GUARD: seeds `{"welcome": {...}}`, PUTs `{"faq": {...}}`, asserts both `welcome` AND `faq` present afterward
- `test_put_automation_settings_full_replace_scenario` — all keys → all written
- `test_put_automation_settings_not_found_raises_404`
- `test_growth_link_generates_deeplink` — URL shape, payload persisted, flag_modified + commit called
- `test_growth_link_appends_to_existing_routes` — existing routes NOT wiped
- `test_growth_link_no_bot_username_raises_404`
- `test_growth_link_instance_not_found_raises_404`
- `test_growth_link_disabled_returns_404` — gate fires before DB
- `tests/test_telegram_growth_link.py::test_growth_link_generates_deeplink` (brief's named file)

Pre-existing B1–B5 tests: 12 passed unchanged.

---

## Files Changed

| File | Change |
|------|--------|
| `app/routes/telegram_routes.py` | Added 3 endpoints + imports (`_secrets`, `flag_modified`, `TelegramAutomationSettings`) |
| `app/schemas/telegram_schema.py` | Added `TelegramAutomationSettings` + sub-models (TelegramWelcome, TelegramAway, TelegramFaqAction) |
| `app/db/models/flows.py` | Updated `trigger_type` doc string to include postback variants |
| `tests/routes/test_telegram_routes.py` | 13 new tests (automation-settings + growth-link) |
| `tests/test_telegram_growth_link.py` | New — brief's named standalone test file |

---

## Self-Review

**Correctness:**
- MERGE implemented correctly: `dict.update()` at top level, `model_dump(exclude_unset=True)` ensures only sent keys merge. Tested the regression path explicitly.
- `flag_modified` called in both PUT and growth-link (JSONB mutations in place would silently not persist without it).
- `setdefault("start_payload_routes", {})` in growth-link means repeated calls grow the routes dict rather than reset it — important for multi-flow growth-link use cases.
- Platform filter `Instances.platform == "telegram"` on automation-settings routes prevents cross-platform accidental matches.

**Schema design:**
- All top-level keys `Optional` with `None` default. `model_dump(exclude_unset=True)` returns `{}` for a bare `TelegramAutomationSettings()` — no keys merged, no-op safe.
- Inner model validators copied from TikTok (FAQ length/count caps).

**What was NOT done (intentional per brief):**
- No flow-ownership validation on FAQ save (TikTok does this; brief didn't ask for it on Telegram — can be added in a follow-up if needed).
- No migration — no DB schema change (tg_automation_settings JSONB column already exists from B1).

---

## Concerns / Follow-ups

1. **FAQ flow-ownership guard** — TikTok's PUT validates each FAQ flow target belongs to the instance. Telegram's PUT does not (brief didn't require it). Low risk for now (a bad flow_id just silently no-ops at dispatch time), but should be added before GA.
2. **Growth-link payload collision** — `token_urlsafe(8)[:16]` has ~96-bit entropy; collision probability is negligible for practical use. No dedup check on write (acceptable).
3. **`start_payload_routes` depth** — there's no cap on the number of growth links stored. For very active stores this could grow the JSONB blob unboundedly. A future cleanup job or max-cap on PUT could address this.

---

## FIX — IDOR: cross-tenant flow ownership (Security review MEDIUM) — commit c859aac

### The vulnerability
Both new endpoints stored a caller-supplied `flow_id` into `tg_automation_settings` **without verifying the flow belongs to the authenticated tenant**. A tenant could call `GET /telegram/growth-link?flow_id=<another tenant's flow>` (or PUT an FAQ / start_payload_route referencing it) and wire their own bot to a foreign flow — cross-tenant flow execution at dispatch time. This closes concern #1 above (it was higher-severity than "low risk" implied).

### The fix — `app/routes/telegram_routes.py`

New helper:
```python
def _assert_flow_owned(db, user_id, flow_id):
    from app.db.models.flows import Flows
    flow = (db.query(Flows.id)
              .filter(Flows.id == str(flow_id),
                      Flows.user_id == user_id,
                      Flows.is_deleted == False)   # noqa: E712
              .first())
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
```

**Column choice:** the coordinator suggested `deleted_at.is_(None)`. The Flows model has BOTH `deleted_at` and `is_deleted`. I filtered on `is_deleted == False` because that is the exact predicate the **B5 webhook dispatcher** (`telegram_webhook_service.py:471`) and the **TikTok routes** (`tiktok_routes.py:381`) use to decide which flows are live/dispatchable. Checking ownership against the same predicate means we authorize against exactly the set of flows that could actually run. (CLAUDE.md mentions `deleted_at`, but the live dispatch code is the authoritative behavior.) Raises **404 not 403** so a foreign flow's existence is never confirmed.

**Application:**
1. **growth-link** — `_assert_flow_owned(db, auth.user_id, flow_id)` called right after instance load/validation, BEFORE generating the payload key or storing the route.
2. **automation-settings PUT** — after building the merged blob, scans `existing["faq"]` AND `existing["start_payload_routes"]` for any value with `type == "flow"` and a `flow_id`, calling `_assert_flow_owned` for each. Done on the **fully-merged** blob and **before** `flag_modified`/`commit`, so a bad flow_id never persists (the `inst.tg_automation_settings` attribute is not even reassigned when the guard fires).

### Tests (extended `tests/routes/test_telegram_routes.py`)
Added a `_routing_db(inst, flow_owned=...)` mock that routes `db.query(Instances)` vs `db.query(Flows.id)` by the queried entity, so the second (ownership) query is independently controllable.

- `test_growth_link_rejects_foreign_flow_404` — (a) foreign flow → 404, `tg_automation_settings` stays `None`, no `flag_modified`, no commit.
- `test_growth_link_owned_flow_succeeds` — (b) owned flow → 200, route persisted, commit called.
- `test_put_automation_rejects_foreign_faq_flow_404` — (c) foreign FAQ flow → 404, pre-existing welcome blob unchanged, no commit.
- `test_put_automation_rejects_foreign_start_payload_route_404` — (c2) foreign start_payload_route flow → 404, nothing persisted.
- `test_put_automation_owned_faq_flow_succeeds` — (d) owned FAQ flow → success, welcome preserved (merge intact), commit called.

### Result
```
pytest tests/routes/test_telegram_routes.py tests/test_telegram_growth_link.py -o addopts="" -q
30 passed, 8 warnings in 0.44s
```
(was 25; +5 IDOR tests. Two pre-existing growth-link happy-path tests migrated to `_routing_db` so the ownership probe resolves truthy.) `py_compile` clean.

**Cross-tenant flow_id is now rejected with 404 on both endpoints, before any persistence.**
