## Task F1: Frontend types + tab gating (+ unit test)

**Files:**
- Modify: `types/InstanceTypes.ts:28` (platform union + tg fields)
- Modify: `utils/channelTabs.ts`
- Test: `tests/unit/channelTabs.telegram.spec.ts` (or extend the existing channelTabs unit test)

**Interfaces:**
- Produces: `Instance.platform` includes `'telegram'`; `telegramAllowedTabs`, `telegramOnlyTabs`; `isTabAllowedForPlatform(tab, 'telegram')`.

- [ ] **Step 1: Write the failing unit test**

```ts
// tests/unit/channelTabs.telegram.spec.ts
import { describe, it, expect } from 'vitest'
import { isTabAllowedForPlatform } from '~/utils/channelTabs'

describe('telegram tab gating', () => {
  it('allows broadcast surfaces (campaigns/segments) — free broadcast channel', () => {
    expect(isTabAllowedForPlatform('campaigns', 'telegram')).toBe(true)
    expect(isTabAllowedForPlatform('segments', 'telegram')).toBe(true)
  })
  it('shows telegram_profile only on telegram', () => {
    expect(isTabAllowedForPlatform('telegram_profile', 'telegram')).toBe(true)
    expect(isTabAllowedForPlatform('telegram_profile', 'whatsapp')).toBe(false)
    expect(isTabAllowedForPlatform('telegram_profile', 'tiktok')).toBe(false)
  })
  it('hides IG-only tabs', () => {
    expect(isTabAllowedForPlatform('follower_welcome', 'telegram')).toBe(false)
  })
})
```

- [ ] **Step 2: Run to verify fail** → `npx vitest run tests/unit/channelTabs.telegram.spec.ts`

- [ ] **Step 3: Extend `channelTabs.ts`** — add the type + allow/only lists and the function branch. Telegram is broadcast-capable, so it gets campaigns/segments/growth (unlike Messenger/TikTok):

```ts
export type ChannelPlatform = 'whatsapp' | 'instagram' | 'messenger' | 'tiktok' | 'telegram';

// Telegram allow-list. Broadcast IS supported (free, no template approval), so
// unlike Messenger/TikTok it also gets campaigns + segments + its growth tool.
export const telegramAllowedTabs = [
  'overview', 'chat', 'contacts', 'flows', 'ai', 'settings',
  'campaigns', 'segments',
  'telegram_profile', 'telegram_automations', 'telegram_growth',
];

export const telegramOnlyTabs = ['telegram_profile', 'telegram_automations', 'telegram_growth'];
```
Update `isTabAllowedForPlatform`:
```ts
  if (platform === 'telegram') return telegramAllowedTabs.includes(tabId);
```
And add `!telegramOnlyTabs.includes(tabId)` to the messenger/tiktok/instagram/default branches so the new telegram-only tabs never leak (mirror the existing `tiktokOnlyTabs` exclusions on lines 70-75).

- [ ] **Step 4: Add types** in `InstanceTypes.ts` line 28 union → add `| 'telegram'`, and tg fields:
```ts
  tg_bot_id?: string;
  tg_bot_username?: string;
  tg_bot_name?: string;
  tg_avatar_url?: string;
```

- [ ] **Step 5: Run test** → PASS. `npx vue-tsc --noEmit` clean.

- [ ] **Step 6: Commit**

```bash
git add types/InstanceTypes.ts utils/channelTabs.ts tests/unit/channelTabs.telegram.spec.ts
git commit -m "feat(telegram): frontend platform type + tab gating"
```

---

