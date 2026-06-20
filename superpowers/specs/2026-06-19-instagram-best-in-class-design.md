# Instagram → best-in-class: full hardening sweep + Marketing Messages

**Date:** 2026-06-19
**Status:** Approved, in execution
**Scope owner:** platform (MegaSend-CloudApi + whatsapp-front)

## Goal

Take the Instagram surface to the ceiling of what Meta's Instagram Platform
permits: close every real gap, build Instagram Marketing Messages
(opt-in recurring notifications) end-to-end, and harden every IG path against
correctness/compliance/multi-tenant bugs. No speculative features, no bloat.

## Guardrails (what we deliberately do NOT build)

- **No "DM new followers / story viewers" beyond what exists.** Meta has no
  follower webhook and no story-viewer API; follow-triggered DMs are
  policy-unsanctioned (codes 10/551/613, subcodes 2534001/2534022). Current
  polling (no-identity → no DM) + `ack_policy_risk`-gated webhook path is the
  correct ceiling. Do not push it further.
- **No per-customer Meta application flow.** Marketing Messages access is
  granted at the **App level** (MegaSend applies once via App Review / beta
  enrollment). Connected customers inherit it; they capture their own per-topic
  opt-ins. Application is a business action, not code.
- **Reuse existing chokepoints** — `send_ig_with_guards`, the consent model,
  the flow engine, `InstagramPhoneMockup`. No new abstractions where one exists.

## Key technical insight: Marketing Messages is TOKEN-based

Meta's mechanism (renamed from "Recurring Notifications" → "Marketing
Messages"):

1. Inside an **open 24h window**, send an **opt-in request template**
   (`template_type: notification_messages`) for a `topic` (title defaults to
   "Updates and promotions").
2. User accepts → Meta issues a **`notification_message_token`** for that topic,
   delivered via the **`messaging_optins` webhook** (currently handled
   audit-only).
3. Send recurring messages **using that token**, outside the 24h window, at the
   opted frequency (DAILY/WEEKLY/MONTHLY), ongoing until revoked/expired.
4. `GET /{id}/notification_message_tokens` lists valid tokens.

The existing `instagram_marketing_consent` model stores topic/consent but has
**no column for the token / frequency / token-expiry** — necessary but not
sufficient. The build must capture the token from `messaging_optins` and send
against it.

## Phases

### Phase 0 — Adversarial IG audit (read-only)
Parallel multi-agent sweep of all IG paths: webhook ingestion/dedup/HMAC/replay,
`send_ig_with_guards` (24h CSW, rate limit, quota/metering, refund races), token
refresh + invalid-token handling, comment automation + moderation, follower
welcome/polling races + policy, **multi-tenant isolation (cross-tenant webhook
forward leak — see [[review-fixes-2026-06-16-round2]])**, and the
consent-model-vs-token gap. Each finding adversarially verified. Output: ranked,
verified findings → feeds Phase 4.

### Phase 1 — Webhook completeness
- Add `response_feedback`, `story_insights`, `messaging_policy_enforcement` to
  `WEBHOOK_SUBSCRIBED_FIELDS` (`instagram_auth_service.py`).
- `response_feedback` handler: thumbs up/down → store + AI reply-quality signal.
- `story_insights`: persist metrics (currently a stub at
  `instagram_webhook_service.py:_process_story_insights`).
- **Gate:** unit tests for each new handler; subscription readback test updated.

### Phase 2 — Marketing Messages backend (flag: `INSTAGRAM_MARKETING_MESSAGES_ENABLED`)
- Migration: add `notification_message_token`, `token_frequency`,
  `token_expires_at`, `topic_title` to `instagram_marketing_consent`.
- Opt-in **request** send (notification_messages template, in-window only).
- Token **capture** in `_process_optin` → upsert consent row (replaces
  audit-only).
- Recurring **broadcast send path** via token — reuse `send_ig_with_guards`
  (new rate bucket), frequency cap, expiry/revoke workers, revoke-on-webhook.
- Consent **CRUD routes** + billing/metering hookup.
- **Gate:** service + route + webhook-capture tests; migration applies to a
  scratch DB.

### Phase 3 — Marketing Messages frontend
Topics manager, consent dashboard, broadcast composer (live `InstagramPhoneMockup`),
opt-in capture config (attach topic to ice-breaker/menu/flow), analytics. Full
i18n/RTL/empty-error-loading states. **Gate:** `typecheck` + `build` clean.

### Phase 4 — Hardening fixes
Fix the verified bugs from Phase 0. Each fix adversarially re-checked. **Gate:**
regression tests for each fix.

### Phase 5 — UX polish
`generic_template` editor (current stub), `pages/instagram/auth/callback.vue`
i18n, moderation error-handling/spinners, drag-reorder (ice breakers/menu/
carousel), native `confirm()` → modal, AdAttribution locale, Graph-version check
(verify v25.0 is current).

### Phase 6 — Tests + verification
Tests authored per phase. Full gate run at each boundary.

## Verification plan (run by user; Bash is blocked in the authoring env)

```
# backend
cd MegaSend-CloudApi && pytest -m unit && alembic upgrade head   # scratch DB first
# frontend
cd whatsapp-front && npm run typecheck && npm run build   # NODE_OPTIONS=--max-old-space-size=8192
```

## Risks & rollout

- Marketing Messages send path codes against the **beta API shape** → isolated
  behind `INSTAGRAM_MARKETING_MESSAGES_ENABLED` (default off); contained rework
  when Meta access lands.
- Migrations target the **remote DB** — apply to scratch first, then live in a
  maintenance window.
- All work lands on production `main`; per repo history, much IG work is already
  uncommitted there — coordinate before further commits.

## Execution status (2026-06-19) — DONE, uncommitted

Built via 6 waves of file-owner subagents (no edit collisions); two integration-review
passes came back clean (backend seams + frontend↔backend contract all OK).

- **Phase 0 audit:** 67-agent adversarial sweep → 44 confirmed findings (verified).
- **Phase 4 / Wave A — correctness fixes (DONE):** 4 HIGH (silent DM loss on commit fail
  → `unique_event_key`+ON CONFLICT & post-commit dedup; ~53-day token blackout →
  token-fingerprint guard + clear-on-healthy; dry-run/flag silently disabling auto-DM →
  `short_circuit()` only on real hide; welcome-DM lost on retry → release lock before
  retry) + ~12 MEDIUM (CSW postback-blind, vol-counter leak, quota-refund key,
  hide-200-false-success, private-reply TOCTOU, product/generic false-success, daily-cap
  race, subcode-classify, empty-ig-user-id cross-tenant key sharing, silent inbox drop,
  notify-spam, no-clear-on-healthy). Each with tests.
- **Phase 1 (DONE):** subscribed `response_feedback` (+ best-effort `story_insights`,
  `messaging_policy_enforcement`); `response_feedback` + `story_insights` handlers.
- **Phase 2 (DONE):** migration `20260619b_ig_consent_token` (token columns), opt-in token
  capture + STOP/RESUME in `_process_optin`, `send_optin_request`/`send_marketing_message_by_token`/
  `list_notification_message_tokens`, consent service + CRUD routes + broadcast worker
  (`is_marketing_message` CSW-bypass + `marketing` rate bucket). All behind
  `INSTAGRAM_MARKETING_MESSAGES_ENABLED` (default off).
- **Phase 3 (DONE):** `MarketingMessages/MarketingMessagesTab.vue` (consent dashboard +
  broadcast composer w/ live mockup + opt-in capture/import), tab registered, i18n he+en.
- **Phase 5 (DONE):** generic_template carousel editor, callback i18n + no-opener fallback,
  IG `<img>` @error fallbacks, moderation error/loading states.

### Deferred (deliberate — defensible per audit verdicts)
substring keyword match (merchant default), cross-trigger 24h cooldown (anti-spam),
code-368-as-permanent (conservative), daily-cap UTC vs IL (documented), IGSU-conflict
reconnect (tested tradeoff), out-of-order edit/reaction (cosmetic), callback-no-opener-stuck
(orphaned route — fixed anyway).

### Open decisions for product owner
1. Keep code `200` in `_TOKEN_INVALID_CODES` (now self-heals via clear-on-healthy) vs remove it.
2. Local-dev webhooks with unset `APP_SECRET` now persist `signature_valid=False` (audit-only) —
   keep honest-audit, or restore local processing.

### Verification gates (run by user — Bash blocked in authoring env)
- `cd MegaSend-CloudApi && pytest -m unit` then `alembic upgrade head` (scratch DB first;
  `20260619b` chains off `20260619_whatsapp_groups`, not yet applied to remote).
- `cd whatsapp-front && NODE_OPTIONS=--max-old-space-size=8192 npm run typecheck && npm run build`.

### Business action
Apply (App-level, once) for Meta Marketing Messages beta access; flip
`INSTAGRAM_MARKETING_MESSAGES_ENABLED` on once granted.
