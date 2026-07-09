## Task F2: Connect modal + profile page

**Files:**
- Create: `components/Telegram/TelegramConnectModal.vue`
- Create: `components/Telegram/TelegramProfilePage.vue`

**Clone source:** `components/Tiktok/TiktokConnectModal.vue` + `TiktokProfilePage.vue`. The delta: **no OAuth popup** — a single text input for the BotFather token + a "How to get a token" helper, POSTing to `/telegram/connect`.

- [ ] **Step 1: Build `TelegramConnectModal.vue`** — token input, inline BotFather instructions (`@BotFather → /newbot → copy token`), submit → `useApi().post('/telegram/connect', { bot_token, nickname })`, on success refresh instance store + emit close. Validate `^\d+:[\w-]{30,}$` client-side before submit. All strings via `t('telegram.connect.*')`.

- [ ] **Step 2: Build `TelegramProfilePage.vue`** — show `@username`, bot name, avatar, connected status (GET `/telegram/status`), and a Reconnect/Disconnect button (POST `/telegram/disconnect`). Clone the layout of `TiktokProfilePage.vue`.

- [ ] **Step 3: Typecheck** `npx vue-tsc --noEmit` → clean.

- [ ] **Step 4: Commit**

```bash
git add components/Telegram/
git commit -m "feat(telegram): connect modal (paste token) + profile page"
```

---

