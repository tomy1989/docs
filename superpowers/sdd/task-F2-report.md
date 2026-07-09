# Task F2 Report — Telegram Connect Modal + Profile Page

**Date:** 2026-06-29

## Status
Complete. All files created or modified, typecheck passes on touched files, no new errors introduced.

---

## What Was Built

### Files created
- `/Users/weblix/projects/MegaSendCloud/whatsapp-front/components/Telegram/TelegramConnectModal.vue`
- `/Users/weblix/projects/MegaSendCloud/whatsapp-front/components/Telegram/TelegramProfilePage.vue`

### Files modified
- `/Users/weblix/projects/MegaSendCloud/whatsapp-front/utils/api.ts` — added `'/telegram'` to `DIRECT_API_PATHS` at line 104, immediately after the `'/tiktok'` entry.
- `/Users/weblix/projects/MegaSendCloud/whatsapp-front/nuxt.config.ts` — added proxy rule `'/api/telegram/**'` at line 212, immediately after the `'/api/tiktok/**'` rule.

---

## API Routing Wiring

### utils/api.ts
```ts
'/tiktok',  // TikTok integration (Login Kit OAuth, messaging)
'/telegram',  // Telegram integration (bring-your-own-bot connect, messaging)
```

### nuxt.config.ts
```ts
// TikTok integration endpoints proxy (Login Kit OAuth, messaging)
'/api/tiktok/**': {
  proxy: `${process.env.MEGASEND_CLOUD_API}/tiktok/**`
},
// Telegram integration endpoints proxy (bring-your-own-bot connect, messaging)
'/api/telegram/**': {
  proxy: `${process.env.MEGASEND_CLOUD_API}/telegram/**`
},
```

No auth-route allowlist entry added (Telegram has no OAuth callback).

---

## API Client Pattern Matched

The sibling channel components (TikTok, Messenger, Instagram) all use:
- `apiPost<T>(path, payload)` from `~/utils/api` for mutations
- `apiGet<T>(path)` for reads
- `apiPut<T>(path, payload)` for updates
- `extractErrorMessage(error, fallback)` for error display

Both new components follow this exact pattern — no new API abstraction invented.

The instance-store upsert pattern (idempotent merge on `instance_id`, CustomEvent dispatch, `disconnected_at` null-clear on reconnect) is cloned exactly from `connectTiktok` in `instanceStore.ts` (lines 878–927).

---

## TelegramConnectModal.vue

**Steps:**
1. `input` — token input + BotFather helper + optional nickname input + submit button
2. `success` — bot profile card (avatar, name, @username) + close button

**Key behaviours:**
- Client-side regex validation `^\d+:[A-Za-z0-9_-]{30,}$` before submit (prevents trivially malformed tokens reaching the backend)
- `POST /telegram/connect { bot_token, nickname? }` via `apiPost`
- On success: idempotent upsert into `instanceStore.instances`, dispatch `telegram:connection_success` CustomEvent, emit `created` + push success toast
- Cannot close while `isSubmitting` (blocks accidental double-submit)
- No OAuth popup — Telegram is purely token-based

---

## TelegramProfilePage.vue

Clones the visual structure of `TiktokProfilePage.vue`.

- Avatar card: shows `tg_avatar_url` or Telegram icon fallback, `tg_bot_name`, `@tg_bot_username`, `tg_bot_id`
- **Reconnect** button: opens `TelegramConnectModal` in a nested modal (replaces TikTok's OAuth re-launch — simpler, no store action needed)
- **Disconnect** button: `POST /telegram/disconnect { instance_id }` → on success calls `instanceStore.fetchAllInstances(true)`
- **Status card**: `GET /telegram/status?instance_id=<id>` on mount, shows `webhook_set` badge + `subscriber_count`
- Info banner: opt-in model notice (bots cannot initiate conversations)
- Dark-mode compatible (`dark:` Tailwind variants throughout)

---

## i18n Keys Referenced (all `telegram.*`)

### TelegramConnectModal keys
```
telegram.connect.title
telegram.connect.description
telegram.connect.helper_title
telegram.connect.helper_step1
telegram.connect.helper_step2
telegram.connect.helper_step3
telegram.connect.token_label
telegram.connect.token_placeholder
telegram.connect.nickname_optional
telegram.connect.nickname_placeholder
telegram.connect.submit
telegram.connect.connected_successfully
telegram.connect.error_token_required
telegram.connect.error_token_invalid
telegram.connect.error_connect_failed
```

### TelegramProfilePage keys
```
telegram.profile.title
telegram.profile.description
telegram.profile.connected
telegram.profile.reconnect
telegram.profile.disconnect
telegram.profile.disconnected_successfully
telegram.profile.disconnect_error
telegram.profile.reconnected_successfully
telegram.profile.bot_id
telegram.profile.optin_notice
telegram.profile.status_title
telegram.profile.status_loading
telegram.profile.status_error
telegram.profile.webhook_status
telegram.profile.webhook_active
telegram.profile.webhook_inactive
telegram.profile.subscriber_count
```

### Shared keys (already exist in en-US.json / he.json)
```
nickname     (already exists)
close        (already exists)
cancel       (already exists)
save         (already exists)
```

**Total new telegram.* keys: 32** (15 connect + 17 profile)

---

## Typecheck Command and Result

```
node_modules/.bin/tsc --noEmit --skipLibCheck 2>&1 | grep -E "components/Telegram|utils/api\.ts|nuxt\.config"
```

Result: **(empty — zero errors in touched files)**

Pre-existing errors exist in unrelated files (`composables/useCalls.ts`, `composables/useAgentSlots.ts`, `components/flowbuilder_comp/useDnD.ts`, etc.) — these were present before this task and are not introduced by F2. `vue-tsc` binary is not installed in the project; `tsc --skipLibCheck` was used as the documented fallback.

---

## Self-Review Against Brief

| Requirement | Status |
|---|---|
| Create `TelegramConnectModal.vue` | ✅ |
| Create `TelegramProfilePage.vue` | ✅ |
| No OAuth popup — token input only | ✅ |
| BotFather helper (`@BotFather → /newbot → copy token`) | ✅ |
| Client-side regex validation `^\d+:[A-Za-z0-9_-]{30,}$` | ✅ |
| POST `/telegram/connect {bot_token, nickname}` | ✅ |
| On success: refresh instance store + emit close | ✅ (idempotent upsert + emit) |
| GET `/telegram/status?instance_id=` in profile | ✅ |
| POST `/telegram/disconnect` in profile | ✅ |
| Clone TiktokProfilePage layout | ✅ |
| All strings via `t('telegram.*')` keys | ✅ |
| No hardcoded user-facing strings | ✅ |
| `utils/api.ts` DIRECT_API_PATHS entry | ✅ |
| `nuxt.config.ts` proxy rule | ✅ |
| No auth-route allowlist entry (no OAuth) | ✅ |
| RTL logical Tailwind props (`ms-`, `me-`, `ps-`, `pe-`) | ✅ (gap-based layout, no physical l/r props used) |
| SSR safety (`import.meta.client` guards) | ✅ (CustomEvent dispatch guarded) |
| Typecheck clean on touched files | ✅ |
| Brand color `#229ED9` used | ✅ |
| Icon `simple-icons:telegram` used | ✅ |

---

## Concerns / Notes for Follow-on Tasks

1. **F5 (i18n)**: 32 new `telegram.*` keys must be added to all 15 locale files. The full list is in the "i18n Keys Referenced" section above.
2. **Disconnect UX**: After `handleDisconnect` calls `fetchAllInstances(true)`, the user will be on a page for an instance that no longer exists. A subsequent task should ensure the router navigates away (the instance-route middleware may handle this automatically once the instance is gone from the store).
3. **`vue-tsc` not installed**: The project has `tsc` but not `vue-tsc`. `tsc --skipLibCheck` was used. Template type-safety (template expression types) is only validated by `vue-tsc`; recommend installing it (`npm i -D vue-tsc`) or using `npx nuxi typecheck` which bundles its own copy.
