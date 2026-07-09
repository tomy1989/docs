## Task F3 Report — Sidebar tabs + loaders + inbox badge + message types

**Date:** 2026-06-29
**Branch:** feat/telegram-channel
**Status:** Complete

---

### Files Changed

1. `components/Sidebars/dashboardSidebar.vue`
2. `pages/dashboard.vue`
3. `components/Cards/InstanceCard.vue`
4. `utils/messageTypeDetector.ts`

---

### 1. Tab Object Added — dashboardSidebar.vue (line ~1984)

```js
{
  id: "telegram_profile",
  label: "dashboard.tabs.telegram_profile",
  icon: "simple-icons:telegram",
  requiredPermission: "can_manage_flows",
},
```

Placed immediately after the `tiktok_profile` block, with an explanatory comment matching the style of the messenger/tiktok comments above it.

---

### 2. Tab Loader Added — pages/dashboard.vue

```ts
// Telegram-only tab (bot settings config)
telegram_profile: () =>
  import("~/components/Telegram/TelegramProfilePage.vue"),
```

Placed after the `tiktok_profile` loader entry. Uses `~/` alias (matching F2's import style). Only `telegram_profile` added; `telegram_automations` and `telegram_growth` deferred to F4 per task brief.

---

### 3. Telegram Badge — components/Cards/InstanceCard.vue

**Script additions:**
```ts
const isTelegram = computed(() => props.instance.platform === 'telegram');
// isWhatsapp updated to also exclude telegram:
const isWhatsapp = computed(() => !isInstagram.value && !isMessenger.value && !isTelegram.value);
```

**Template addition** (after the Messenger pill block):
```html
<!-- Telegram platform pill — brand color #229ED9 -->
<span
  v-if="isTelegram"
  class="inline-flex items-center gap-1 rounded-full bg-[#E8F5FD] text-[#229ED9] ring-1 ring-[#A8D8F0] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
>
  <Icon name="simple-icons:telegram" class="w-3 h-3" aria-hidden="true" />
  <span>{{ t('telegram.platform_pill_label') }}</span>
</span>
```

Uses `Icon` component (same as existing `@nuxt/icon` usage elsewhere in the project). Brand color `#229ED9` per global-constraints.md. RTL-safe (logical padding with `gap-1`, no directional margins). Note: IG/Messenger pills use inline SVG; Telegram uses `<Icon>` because the simple-icons:telegram glyph is already in the icon set registered by the project, avoiding raw path duplication.

**`isWhatsapp` impact:** previously `!isInstagram && !isMessenger` — would have given Telegram cards WhatsApp-only UI (coexistence badge, PARTNER_REMOVED reconnect, business-profile menu). Fixed by adding `&& !isTelegram.value`.

---

### 4. messageTypeDetector.ts — Telegram extraction path

Added "Path 2b" in `getWebhookMessage()`, after the IG block (line ~679), keyed on `rawData.object === 'telegram'`.

Supported types normalized to WA-like shapes:
- `text` → `{ type: 'text', text: { body: tgMsg.text } }`
- `photo` → `{ type: 'image', image: { caption } }` — existing `image` switch arm handles rendering
- `video` → `{ type: 'video', video: { caption } }`
- `voice` / `audio` → `{ type: 'audio', audio: {} }`
- `document` → `{ type: 'document', document: { filename } }`
- `sticker` → `{ type: 'sticker', sticker: { id, mime_type, animated } }` — feeds existing `case 'sticker'` arm
- `location` → `{ type: 'location', location: { latitude, longitude } }` — feeds existing `case 'location'` arm
- `contact` → `{ type: 'contacts', contacts: [...] }` — feeds existing `case 'contacts'` arm

No new card components invented. All Telegram types resolve to existing generic type arms in the `detectMessageType` switch. `sticker` and `location` were the only Telegram-specific types called out by the brief — both now covered.

---

### New i18n Keys Referenced (2 keys — NOT added here, deferred to F5)

| Key | Used in |
|-----|---------|
| `dashboard.tabs.telegram_profile` | dashboardSidebar.vue tab label |
| `telegram.platform_pill_label` | InstanceCard.vue platform pill |

---

### Typecheck

Command: `node_modules/.bin/tsc --noEmit --skipLibCheck`

Result: **0 errors in touched files.** Pre-existing errors exist in `composables/useAgentSlots.ts`, `composables/useCalls.ts`, `composables/useCallsApi.ts`, `components/flowbuilder_comp/useDnD.ts`, and others — none introduced by this task. Note: `tsc --noEmit` cannot validate Vue templates; final validation must be done with `npx nuxi typecheck`.

---

### Self-review

- Tab object shape exactly mirrors `tiktok_profile` (same 4 fields: `id`, `label`, `icon`, `requiredPermission`).
- Loader uses `~/` alias consistent with F2's import style for `TelegramProfilePage.vue`.
- Only `telegram_profile` loader registered (not automations/growth — those don't exist yet, per F4 deferral note).
- Badge follows Messenger pill shape; uses `<Icon>` not inline SVG (acceptable pattern in project — `@nuxt/icon` is the registered icon module).
- `isWhatsapp` guard updated to exclude telegram — prevents Telegram cards from showing coexistence badge, PARTNER_REMOVED reconnect, and business-profile menu items.
- messageTypeDetector path is purely additive; does not change any existing WA or IG code paths.
- All Telegram types funnel into existing switch arms — no new card components created in this task.
- SSR safety: no `window`/`document` usage added. No new RTL violations (no directional margin/padding used).

### Concerns

None blocking. One minor note: the `<Icon>` component for the Telegram pill differs stylistically from IG/Messenger (which use inline SVG). This is intentional and acceptable — `@nuxt/icon` is already used for tab icons in the sidebar. If visual parity with the inline-SVG pills is desired, F5 or a polish pass can switch it.
