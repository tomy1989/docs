## Global Constraints

- **Connect model:** bring-your-own-bot. Customer pastes a BotFather token (`number:alphanumeric`). Validate via `getMe`, register webhook via `setWebhook`. No OAuth callback, no token refresh.
- **Bot token is a full-takeover secret** — store ENCRYPTED via `encrypt_value` (same contract as `ig_access_token`/`tk_access_token`), never log it, never return it to the client.
- **Inbound auth = `secret_token`**, not HMAC. Telegram echoes the per-bot secret in the `X-Telegram-Bot-Api-Secret-Token` header. Compare with `hmac.compare_digest`. Fail CLOSED in non-local envs (503 if the instance has no secret), logged dev-skip only when `ENVIRONMENT == "local"`.
- **Opt-in gate:** a bot cannot initiate a conversation. "Subscriber" = any chat that has `/start`-ed / messaged the bot. Outbound to a non-subscriber returns `403 Forbidden: bot can't initiate conversation with a user` — surface gracefully, do not retry.
- **Rate limits (enforce in the sender):** ≤1 msg/sec per chat, ~30 msg/sec global per bot, ≤20 msg/min per group. On `429`, honor `parameters.retry_after` with backoff — never tight-retry.
- **Status:** treat `"SENT"` as the only reliable outbound status (Telegram gives no delivered/read).
- **Webhook URL ports** must be one of 443/80/88/8443 over TLS — the existing public ingress (443) already satisfies this.
- **Platform discriminator:** `InstancePlatform.TELEGRAM = "telegram"`; webhook routes by `instance_id` in the URL path (one ingress hosts all bots), then stamps `payload["object"] = "telegram"` for the durability drainer.
- **Billing:** reuse `atomic_message_service` unchanged. No channel-specific cap.
- **i18n:** every user-facing string is a `telegram.*` key added to ALL 15 locale files (`en-US, he, es, ar, zh-CN, zh-TW, fr, de, id, it, pt-BR, ru, th, vi, nl`), translated, 2-space JSON, no trailing newline. Hebrew (`he`) is primary/RTL.
- **Feature gating:** `TELEGRAM_ENABLED` (default off) gates routes/webhook; `TELEGRAM_DRY_RUN` (default off) makes the sender log-and-mock without hitting Telegram (mirrors `TIKTOK_DRY_RUN`).
- **Migration head:** set the new migration's `down_revision` to the current head from `python -m alembic heads` (do NOT hardcode — the chain has branched since `20260622_tiktok`). Do not modify existing migrations.
- **Multi-tenant:** every query filters by `user_id`. Brand color `#229ED9`, icon `simple-icons:telegram`.

---
