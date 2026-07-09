## Task F4: Automations landing + welcome/keyword config + growth tool UI

**Files:**
- Create: `components/Telegram/TelegramAutomationsLanding.vue`
- Create: `components/Telegram/TelegramWelcomeConfig.vue`
- Create: `components/Telegram/TelegramKeywordConfig.vue`
- Create: `components/Telegram/TelegramGrowthTool.vue`

**Clone source:** `components/Instagram/InstagramAutomationsLanding.vue` (card grid) + `components/Tiktok/TiktokAutomationSettings.vue` (welcome/away/FAQ form bound to `tg_automation_settings`).

- [ ] **Step 1: Landing** — cards for Welcome (`/start`), Keyword replies, Growth link. Routes to the config sub-components.

- [ ] **Step 2: Welcome + Keyword config** — forms persisting to `tg_automation_settings` via a settings endpoint (reuse the TikTok automation-settings PATCH pattern; add a `PATCH /telegram/automation-settings` mirroring it, or reuse a generic instance-settings route if one exists — verify before adding).

- [ ] **Step 3: Growth tool** — pick a flow, call `GET /telegram/growth-link`, show the `t.me/<bot>?start=…` link with copy-to-clipboard + QR (reuse the existing WhatsApp link-generator QR component).

- [ ] **Step 4: Typecheck** → clean.

- [ ] **Step 5: Commit**

```bash
git add components/Telegram/
git commit -m "feat(telegram): automations landing, welcome/keyword config, growth tool"
```

---

