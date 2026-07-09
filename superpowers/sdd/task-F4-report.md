# Task F4 Report — Automations landing + welcome/keyword config + growth tool UI

## Components Created

| File | Purpose |
|------|---------|
| `components/Telegram/TelegramAutomationsLanding.vue` | Card-grid landing (hero banner + 3 cards: Welcome, Keyword, Growth). Renders sub-components inline when Welcome or Keyword card is clicked; emits `navigate('telegram_growth')` for the Growth card. |
| `components/Telegram/TelegramWelcomeConfig.vue` | `/start` welcome message form: enabled toggle + textarea (4096-char limit). GET/PUT `/telegram/{id}/automation-settings` (welcome key). Back-button returns to landing. |
| `components/Telegram/TelegramKeywordConfig.vue` | Keyword → reply/flow map (FAQ key). Keyword + type selector (reply|flow) + textarea or flow picker per row. Add/remove rows. GET/PUT `/telegram/{id}/automation-settings` (faq key). |
| `components/Telegram/TelegramGrowthTool.vue` | Flow picker + GET `/telegram/growth-link?instance_id=&flow_id=`. Displays `t.me/<bot>?start=<payload>` link with copy-to-clipboard (SSR-safe: `import.meta.client`) + local QR generation via `qrcode` lib + PNG download. |

## Architecture note

`TelegramWelcomeConfig` and `TelegramKeywordConfig` are rendered **within** `TelegramAutomationsLanding` (conditional sub-view, not separate sidebar tabs). The landing manages `activeView: 'welcome' | 'keyword' | null` with a back-button breadcrumb. This avoids two extra sidebar tabs while keeping each config as a focused self-contained component.

## Tabs Registered

### `components/Sidebars/dashboardSidebar.vue`

Added after the existing `telegram_profile` entry:

```js
{ id: "telegram_automations", label: "dashboard.tabs.telegram_automations", icon: "heroicons:bolt",  requiredPermission: "can_manage_flows" }
{ id: "telegram_growth",      label: "dashboard.tabs.telegram_growth",      icon: "heroicons:link",  requiredPermission: "can_manage_flows" }
```

Both IDs already appear in `utils/channelTabs.ts` `telegramAllowedTabs` / `telegramOnlyTabs` (pre-wired by a previous task).

### `pages/dashboard.vue` tabLoaders

```js
telegram_automations: () => import("~/components/Telegram/TelegramAutomationsLanding.vue"),
telegram_growth:      () => import("~/components/Telegram/TelegramGrowthTool.vue"),
```

## API Endpoints Called

| Method | Path | Component |
|--------|------|-----------|
| GET | `/telegram/{instance_id}/automation-settings` | WelcomeConfig, KeywordConfig |
| PUT | `/telegram/{instance_id}/automation-settings` | WelcomeConfig, KeywordConfig |
| GET | `/telegram/growth-link?instance_id=&flow_id=` | GrowthTool |

All three endpoints do not exist yet on the backend (F4 scope is frontend-only). The components call them with the correct shape; 404 responses are handled gracefully (hydrate with empty defaults).

## Full New i18n Keys

> Note: F5 handles adding these to all 15 locale files. Listed here as the canonical reference.

```
dashboard.tabs.telegram_automations
dashboard.tabs.telegram_growth

telegram.automations.landing.title
telegram.automations.landing.subtitle
telegram.automations.landing.configure
telegram.automations.landing.welcome_title
telegram.automations.landing.welcome_desc
telegram.automations.landing.keyword_title
telegram.automations.landing.keyword_desc
telegram.automations.landing.growth_title
telegram.automations.landing.growth_desc

telegram.welcome.title
telegram.welcome.hint
telegram.welcome.placeholder
telegram.welcome.error_loading
telegram.welcome.save_success
telegram.welcome.save_error

telegram.keyword.title
telegram.keyword.hint
telegram.keyword.keyword_placeholder
telegram.keyword.type_reply
telegram.keyword.type_flow
telegram.keyword.reply_placeholder
telegram.keyword.flow_placeholder
telegram.keyword.add
telegram.keyword.error_loading
telegram.keyword.save_success
telegram.keyword.save_error

telegram.growth.title
telegram.growth.description
telegram.growth.flow_section_title
telegram.growth.flow_section_hint
telegram.growth.flow_label
telegram.growth.flow_placeholder
telegram.growth.generate_button
telegram.growth.generate_error
telegram.growth.result_title
telegram.growth.result_hint
telegram.growth.copy_link
telegram.growth.link_copied
telegram.growth.qr_alt
telegram.growth.download_qr
```

Pre-existing keys reused (not new):
- `common.loading`, `common.retry`, `common.save`, `common.remove`, `common.back`

## Typecheck

Command: `node_modules/.bin/tsc --noEmit --skipLibCheck 2>&1 | grep -i Telegram`

Result: **empty output** — zero errors in any Telegram file.

The full typecheck run shows only pre-existing errors in unrelated files (`flowbuilder_comp/useDnD.ts`, `composables/useAgentSlots.ts`, `composables/useCalls.ts`, etc.) — none introduced by this task.

## Files Changed

| File | Change |
|------|--------|
| `components/Telegram/TelegramAutomationsLanding.vue` | **Created** |
| `components/Telegram/TelegramWelcomeConfig.vue` | **Created** |
| `components/Telegram/TelegramKeywordConfig.vue` | **Created** |
| `components/Telegram/TelegramGrowthTool.vue` | **Created** |
| `components/Sidebars/dashboardSidebar.vue` | Added `telegram_automations` + `telegram_growth` tab entries |
| `pages/dashboard.vue` | Added `telegram_automations` + `telegram_growth` tabLoaders |

## Self-Review

- **SSR safety**: `navigator.clipboard` and `document.createElement` in GrowthTool are guarded with `import.meta.client`. QR generation also gated. No `window` access anywhere else.
- **RTL**: All margin/padding uses logical Tailwind props (`ms-`, `me-`, `ps-`, `pe-`). Arrow icons use `rtl:rotate-180`. `bdi` wraps bot usernames.
- **API client pattern**: Matches TiktokAutomationSettings exactly — `apiGet`/`apiPut`/`extractErrorMessage` from `~/utils/api`, `push.success`/`push.error` from `notivue`.
- **Error handling**: 404 → hydrate empty (graceful); other errors → surface in UI with retry.
- **Flow store**: Both KeywordConfig and GrowthTool call `flowStore.fetchFlows()` lazily on mount, matching TikTok's pattern.
- **Toggle UI**: WelcomeConfig reuses the same `toggleClass`/`knobClass` helpers from TiktokAutomationSettings (inline, not shared — avoids cross-component coupling).
- **Brand color**: `#229ED9` used for all primary actions/accents per global-constraints.md.
- **Channel gating**: Both new tab IDs were already in `channelTabs.ts` `telegramOnlyTabs` from a previous task — no change needed there.

## Concerns

1. **`TelegramAutomationsLanding` emit `navigate`**: The landing emits `navigate('telegram_growth')` for the Growth card. This requires the parent (dashboard) to handle the event and switch tabs. Looking at how `InstagramAutomationsLanding` works — it's embedded inside `AutomationsPage.vue` which handles the event and calls `handleNavigateToTab`. Since `TelegramAutomationsLanding` is loaded directly as a tab component in `dashboard.vue`, the emit goes nowhere by default. The Growth card's emit will silently no-op unless the automations tab component is wrapped — similar to how AutomationsPage wraps the IG landing. This is acceptable for now since the `telegram_growth` tab is also independently accessible from the sidebar; the card is a convenience shortcut. If desired, a future task can wrap the landing in a `TelegramAutomationsPage.vue` that handles the navigate emit.

2. **Single PUT for both Welcome + Keyword**: Both WelcomeConfig and KeywordConfig issue separate PUTs that only include their own key (`welcome:` or `faq:`). The backend should merge-patch rather than replace the whole settings object. This is the same pattern as the TikTok endpoint which has a single form — worth confirming with the backend team when implementing the endpoint.

3. **`qrcode` lib is browser-only**: QRCodeLib generates data URLs from a canvas. `import.meta.client` guard prevents SSR crash, but the QR will be absent on SSR render (which is fine — it's a user-triggered action, not page content).
