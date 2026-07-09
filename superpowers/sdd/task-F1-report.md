# Task F1 Report — Frontend platform type + tab gating

**Date:** 2026-06-29
**Branch:** feat/telegram-channel
**Commit:** 6a286f8 — "feat(telegram): frontend platform type + tab gating"

---

## What was built

### Files changed

| File | Change |
|------|--------|
| `types/InstanceTypes.ts` | Added `'telegram'` to platform union (line 28); added `tg_bot_id`, `tg_bot_username`, `tg_bot_name`, `tg_avatar_url` optional fields |
| `utils/channelTabs.ts` | Added `'telegram'` to `ChannelPlatform` type; added `telegramAllowedTabs` + `telegramOnlyTabs` exports; added `telegram` branch + `!telegramOnlyTabs.includes(tabId)` exclusions to all other branches |
| `utils/channelTabs.test.ts` | Added `telegramAllowedTabs` + `telegramOnlyTabs` imports; extended `ALL_TABS` catalog with `...telegramOnlyTabs`; added full `describe('per-channel dashboard tab gating — Telegram', ...)` suite (7 `it` cases) |

---

## TDD RED/GREEN

### RED — failing before implementation

```
node_modules/.bin/vitest run utils/channelTabs.test.ts

FAIL  utils/channelTabs.test.ts [ utils/channelTabs.test.ts ]
TypeError: telegramOnlyTabs is not iterable
 ❯ utils/channelTabs.test.ts:22:6  (...telegramOnlyTabs)
```
Suite-level failure because the exported symbols didn't exist yet — correct RED signal.

### GREEN — after implementation

```
node_modules/.bin/vitest run utils/channelTabs.test.ts

✓ utils/channelTabs.test.ts (22 tests) 3ms

Test Files  1 passed (1)
Tests  22 passed (22)
```

One test case required a fix during GREEN: the initial draft asserted that `campaigns` must be hidden for Telegram (iterating all of `whatsappOnlyTabs`), but `campaigns` and `segments` are in `whatsappOnlyTabs` yet Telegram IS a broadcast channel and explicitly includes them in `telegramAllowedTabs`. The test was updated to assert `campaigns`/`segments` are ALLOWED for Telegram (broadcast channel) while the rest of `whatsappOnlyTabs` are hidden.

---

## Exact exclusion edits to isTabAllowedForPlatform

Before (each branch):
```ts
if (platform === 'instagram') return !instagramHiddenSet.has(tabId) && !messengerOnlyTabs.includes(tabId) && !tiktokOnlyTabs.includes(tabId);
if (platform === 'messenger') return messengerAllowedTabs.includes(tabId) && !tiktokOnlyTabs.includes(tabId);
if (platform === 'tiktok') return tiktokAllowedTabs.includes(tabId);
// default:
return !instagramOnlyTabs.includes(tabId) && !messengerOnlyTabs.includes(tabId) && !tiktokOnlyTabs.includes(tabId);
```

After (each branch appended with `&& !telegramOnlyTabs.includes(tabId)`):
```ts
if (platform === 'instagram') return !instagramHiddenSet.has(tabId) && !messengerOnlyTabs.includes(tabId) && !tiktokOnlyTabs.includes(tabId) && !telegramOnlyTabs.includes(tabId);
if (platform === 'messenger') return messengerAllowedTabs.includes(tabId) && !tiktokOnlyTabs.includes(tabId) && !telegramOnlyTabs.includes(tabId);
if (platform === 'tiktok') return tiktokAllowedTabs.includes(tabId) && !telegramOnlyTabs.includes(tabId);
if (platform === 'telegram') return telegramAllowedTabs.includes(tabId);  // NEW
// default:
return !instagramOnlyTabs.includes(tabId) && !messengerOnlyTabs.includes(tabId) && !tiktokOnlyTabs.includes(tabId) && !telegramOnlyTabs.includes(tabId);
```

The `tiktok` branch also received `&& !telegramOnlyTabs.includes(tabId)` — even though currently TikTok's allow-list doesn't include any telegram-only tab, this is consistent defensive gating that mirrors the existing pattern (each platform blocks all other platforms' own tabs).

---

## Typecheck

```
node_modules/.bin/tsc --noEmit --skipLibCheck --strict false types/InstanceTypes.ts utils/channelTabs.ts
(no output — clean)
```

---

## Self-review

- `telegramAllowedTabs` matches the brief exactly (11 tabs: 6 common + campaigns + segments + 3 telegram-only).
- `telegramOnlyTabs` matches the brief exactly (`telegram_profile`, `telegram_automations`, `telegram_growth`).
- Leak prevention verified: `telegram_profile`, `telegram_automations`, `telegram_growth` all return `false` for whatsapp/instagram/messenger/tiktok/undefined (covered by the "never leak" and "exposes ONLY its allow-list" test cases).
- The `ChannelPlatform` type now exports `'telegram'` which downstream FE tasks (sidebar, health overview, connect flow) will consume.
- The `tg_*` optional fields on `Instance` are all `string` (not nullable) matching the brief — slightly different from `tk_avatar_url?: string | null` but the brief specifies plain `string` for telegram.

## Concerns

None. The implementation is self-contained, the test suite is comprehensive (7 cases covering allow-list, isolation of telegram-only tabs, IG-only hiding, broadcast tabs, cross-platform no-leak, messenger/tiktok no-leak on telegram). All 22 tests pass.
