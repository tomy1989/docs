# Telegram Channel — SDD Progress Ledger

Plan: docs/superpowers/plans/2026-06-29-telegram-channel.md
Backend branch: MegaSend-CloudApi @ feat/telegram-channel
Frontend branch: whatsapp-front @ feat/telegram-channel

## Tasks
- [ ] B1: instance model + migration + config
- [ ] B2: bot API client + throttle + dispatch
- [ ] B3: connect/disconnect/status routes + auth service
- [ ] B4: webhook ingestion + secret dep + drainer case
- [ ] B5: webhook service (normalization + automations + postback)
- [ ] B6: growth-link endpoint + postback_telegram trigger
- [ ] F1: FE types + tab gating
- [ ] F2: connect modal + profile page
- [ ] F3: sidebar tabs + loaders + badge + message types
- [ ] F4: automations landing + config + growth UI
- [ ] F5: i18n 15 locales
- [ ] V1: backend verification
- [ ] V2: frontend verification

## Log
Task B1: complete (commits 85ba310..a25fd1c, review clean — Minor: redundant index=True on tg_bot_id, pre-existing convention, defer)
Task B2: complete (commits a25fd1c..3f87aab, review Approved + I1/I2/M3 fixed, 3 passed)
Task F1: complete (commit 6a286f8, 22/22 vitest incl 7 telegram + leak checks, typecheck clean)
FOLLOWUP-RISK: campaigns/segments tabs enabled for telegram, but campaign SEND path must route through _dispatch_telegram (unified send_whatsapp_message) to actually broadcast — verify in final review.
Task F2: complete (commit fbe6c9f, 2 components + api routing wiring, typecheck clean touched files, 32 i18n keys for F5)
Task B3: complete (commits 3f87aab..4edbde2, review found+fixed CRITICAL token-log leak + status gate; 13 passed)
Task F3: complete (commit 95f4379, sidebar telegram_profile tab+loader, badge, msg types; +isWhatsapp excludes telegram; typecheck clean)
Task B4: review Approved (auth boundary sound, no Critical). Fixing I1 local-dev enqueue + I2 test patch + SEC: strip webhook secret from durability-inbox storage. Fix in flight.
Task F4: complete (4 components + telegram_automations/telegram_growth tabs+loaders, typecheck clean, 37 i18n keys). NOTE: B6 automation-settings PUT must MERGE top-level keys not replace (welcome/keyword saved separately). Minor: growth-card shortcut no-op (defer).
Task B4: complete (fix 382b79a, 5 passed, secret not stored at rest)
Task F4: committed by controller (agent forgot) — see HEAD
Task B4: COMPLETE (c47ce38 + prior fixes 382b79a; 5 passed; secret not stored; payload carries _megasend_instance_id; review Approved). 
Task B5: COMPLETE (4c4774c, 542-line service, 6/6 + 10 prior green). NOTE: postback_telegram trigger key must be doc-registered in B6.
Task B5: review NEEDS FIXES — CRIT1 _trigger_flows webhook_event_id=None (generic flows dead), CRIT2 _upsert_contact premature commit (row-drop risk), IMP postback message_type vs trigger_type. Fix in flight (concurrent w/ B6, disjoint files).
WARN: B5-fix agent a9546b8760f9c9050 looped on self-referential "relaying" — fix did NOT land (service still has webhook_event_id=None, double commit, RECEIVED). Will dispatch FRESH B5-fix implementer AFTER B6 commits (avoid auto-commit-hook tangling B6 partial edits).
WARN: b2bea8c unrelated waba commit swept into branch by auto-commit hook from pre-existing dirty files (instance_service/instagram_auth/hmac test) — isolate at merge.
Task B6: complete (31c4c23, 25/25 incl merge-not-wipe guard). SECURITY: IDOR — growth-link + automation PUT store flow_id without ownership check; fix pending.
Task B5: COMPLETE — fix committed (event-row for flows, single-commit contact, postback trigger_type, SENT sentinel, _run_route async). 42/42 telegram tests pass.
Task B6: COMPLETE (c859aac IDOR fix, 30 route tests; guard in growth-link + faq + start_payload_routes).
V1 BACKEND VERIFICATION PASS: 48/48 telegram tests, all 8 modules import OK, TELEGRAM enum present, IDOR guards confirmed. Backend B1-B6 feature-complete.
Final backend whole-branch review: READY TO MERGE (no Critical, 3 seams PASS). Important#1 TELEGRAM_DRY_RUN metering fixed (e8e90f1). Important#2 inbound-rows-billable is CROSS-CHANNEL pre-existing (Messenger+TikTok same) — OUT OF SCOPE, flagged for user. Minors noted.

=== FINAL STATE ===
BACKEND (MegaSend-CloudApi @ feat/telegram-channel): B1-B6 + dry-run fix complete. Final whole-branch review = READY TO MERGE (no Critical, 3 seams PASS). V1: 48/48 telegram tests, all modules import, IDOR guards confirmed.
FRONTEND (whatsapp-front @ feat/telegram-channel): F1-F5 + entry-point fix complete. Final FE review found 2 CRITICAL flow breaks (connect modal no entry point; growth card no-op) + url-key mismatch — ALL FIXED (e8ae492). V2: 76/76 i18n keys resolve in 15/15 locales, channelTabs 22/22.
OPEN ITEMS (for user):
 1. Migration 20260701_telegram NOT applied to remote DB (deferred; apply like other channels).
 2. Live e2e gated: needs real BotFather token + TELEGRAM_ENABLED=true + public webhook ingress. Verified via unit tests + DRY_RUN only.
 3. Cross-channel billing: inbound rows counted billable — PRE-EXISTING for Messenger+TikTok too; platform-wide fix out of scope.
 4. b2bea8c unrelated waba commit swept into backend branch by auto-commit hook — isolate at merge.
 5. Both feature branches NOT merged to mainline (backend main / frontend cloudapi-main).
 6. TELEGRAM_ENABLED + TELEGRAM_DRY_RUN both default OFF (safe-by-default).

=== MERGED 2026-06-30 ===
Backend: feat/telegram-channel → main (FF, telegram-ONLY 13 commits; b2bea8c waba WIP excluded + preserved on branch waba-hmac-wip). main @ 7893747. Post-merge: 48/48 telegram tests pass, imports OK. NOT pushed (local merge).
Frontend: feat/telegram-channel → cloudapi-main (FF, 6 commits). @ e8ae492. Post-merge: channelTabs 22/22, i18n parity 77/77 keys × 15 locales. NOT pushed.
feat/telegram-channel branches deleted (merged). waba-hmac-wip preserved for user.
STILL BLOCKED ON USER: (1) live Telegram round-trip e2e needs a BotFather token + TELEGRAM_ENABLED=true + migration applied; (2) migration 20260701_telegram apply to remote DB (deploy step).

=== MIGRATION APPLIED 2026-06-30 ===
alembic upgrade 20260626_conv_phone_no_plus -> 20260701_telegram on remote DB (s3.weblix.tech). Only this one migration was pending (no unrelated migrations applied). Verified: 8 tg_* columns + ix_instances_tg_bot_id unique index live; ORM<->schema query works (0 telegram instances, no UndefinedColumn). DB current==head.
REMAINING FOR LIVE FEATURE (user-gated): (1) deploy/push merged code (running prod app lacks telegram routes until deployed); (2) BotFather token to connect + drive a real message round-trip.
