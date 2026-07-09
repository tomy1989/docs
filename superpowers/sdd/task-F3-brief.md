## Task F3: Sidebar tabs + loaders + inbox badge + message types

**Files:**
- Modify: `components/Sidebars/dashboardSidebar.vue` (tab registry — telegram block near the tiktok block ~line 1977)
- Modify: `pages/dashboard.vue` (`tabLoaders`)
- Modify: `components/Cards/InstanceCard.vue` (telegram badge)
- Modify: `utils/messageTypeDetector.ts` (sticker/location)

- [ ] **Step 1: Add telegram tabs** to `dashboardTabs` — `telegram_profile`, `telegram_automations`, `telegram_growth` with `icon: 'simple-icons:telegram'`, labels `dashboard.tabs.telegram_*`.

- [ ] **Step 2: Add lazy loaders** in `pages/dashboard.vue` `tabLoaders`:
```ts
  telegram_profile: () => import('~/components/Telegram/TelegramProfilePage.vue'),
  telegram_automations: () => import('~/components/Telegram/TelegramAutomationsLanding.vue'),
  telegram_growth: () => import('~/components/Telegram/TelegramGrowthTool.vue'),
```

- [ ] **Step 3: Add the telegram badge** to `InstanceCard.vue` — clone the messenger pill block, brand `#229ED9`, `<Icon name="simple-icons:telegram" />`, label `t('telegram.platform_pill_label')`.

- [ ] **Step 4: Extend `messageTypeDetector.ts`** — map Telegram `sticker` → IMAGE-like card, `location` → a location chip. Default text/photo/video/document already covered by generic types.

- [ ] **Step 5: Typecheck** → clean.

- [ ] **Step 6: Commit**

```bash
git add components/Sidebars/dashboardSidebar.vue pages/dashboard.vue components/Cards/InstanceCard.vue utils/messageTypeDetector.ts
git commit -m "feat(telegram): sidebar tabs, loaders, inbox badge, message types"
```

---

