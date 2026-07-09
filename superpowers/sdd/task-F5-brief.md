## Task F5: i18n keys across all 15 locales

**Files:**
- Modify: all 15 `i18n/locales/*.json`

- [ ] **Step 1: Add the `telegram.*` key block** (connect, profile, automations, growth, platform_pill_label) + `dashboard.tabs.telegram_*` to `en-US.json` and `he.json` first (real translations, he is RTL primary).

- [ ] **Step 2: Propagate to the other 13 locales** — translated, not English-pasted. Keep 2-space indent, NO trailing newline (see `.claude/rules/i18n-rtl.md`).

- [ ] **Step 3: Parity check** — run the parity snippet from `.claude/rules/i18n-rtl.md` to confirm all 15 files have the identical key set.

- [ ] **Step 4: Commit**

```bash
git add i18n/locales/
git commit -m "feat(telegram): i18n keys across 15 locales"
```

---

