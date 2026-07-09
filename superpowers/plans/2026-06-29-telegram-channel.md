# Telegram Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram as a first-class 5th channel (alongside WhatsApp, Instagram, Messenger, TikTok) — bring-your-own-bot connect, full inbox receive/reply, flows + AI auto-reply, broadcast to subscribers, welcome/keyword/button automations, and a `/start` deep-link growth tool.

**Architecture:** Clone the established channel recipe (instance `tg_*` columns → webhook router → signature dependency → webhook service → `_dispatch_*` sender → atomic billing gate → durability inbox). Telegram is the *simplest* channel because it drops four subsystems the Meta/TikTok channels needed: **no OAuth** (paste BotFather token), **no token refresh** (bot tokens are permanent), **no HMAC** (replaced by a `secret_token` header compare), **no 24h reply-window tracking** and **no per-recipient cap** (opt-in is structural — a bot literally cannot cold-message). One genuinely-new piece: a token-bucket sender throttle honoring Telegram's `429 retry_after`.

**Tech Stack:** Backend FastAPI + SQLAlchemy 2.0 + Alembic + Celery + Redis + httpx. Frontend Nuxt 3 SSR + Vue 3 `<script setup>` + Pinia + Vue I18n (15 locales) + Playwright.

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

## File Structure

**Backend (`MegaSend-CloudApi/`)**
- Modify `app/db/models/instances.py` — add `TELEGRAM` enum + `tg_*` column block + `set_telegram_bot_token()` helper.
- Create `app/db/migrations/versions/20260701_telegram_channel.py` — `tg_*` columns + unique index on `tg_bot_id`.
- Modify `app/config.py` — `TELEGRAM_ENABLED`, `TELEGRAM_DRY_RUN`, `TELEGRAM_WEBHOOK_BASE_URL`.
- Create `app/services/telegram_api_client.py` — thin Bot API client + token-bucket throttle + 429 backoff.
- Create `app/utils/telegram_ratelimit.py` — Redis per-chat (1/s) + per-bot (30/s) token buckets.
- Modify `app/services/message_service.py` — `is_telegram` detection + `_dispatch_telegram()`.
- Create `app/routes/telegram_routes.py` — connect / disconnect / status / growth-link.
- Create `app/schemas/telegram_schema.py` — request/response models.
- Create `app/services/telegram_auth_service.py` — `getMe` validate + `setWebhook`/`deleteWebhook` + instance upsert.
- Create `app/dependencies/telegram_secret_dependency.py` — `secret_token` header verify.
- Create `app/routes/telegram_webhook_router.py` — `POST /telegram-webhook/{instance_id}/callback`.
- Create `app/services/telegram_webhook_service.py` — inbound normalization → `Messages` + contact + WS + flows/AI + `callback_query`→postback.
- Modify `celery-worker/tasks/webhook_inbox_tasks.py` — `elif obj == "telegram"` drainer case.
- Modify `app/main.py` — `include_router(telegram_routes.router)` + `telegram_webhook_router.router`.
- Modify `app/db/models/flows.py` — add `postback_telegram` to the trigger-type doc/whitelist.
- Create tests under `tests/`.

**Frontend (`whatsapp-front/`)**
- Modify `types/InstanceTypes.ts` — `'telegram'` platform + `tg_*` fields.
- Modify `utils/channelTabs.ts` — `telegramAllowedTabs` / `telegramOnlyTabs` + function branch.
- Modify `components/Sidebars/dashboardSidebar.vue` — telegram tabs.
- Modify `pages/dashboard.vue` — lazy `tabLoaders` entries.
- Modify `components/Cards/InstanceCard.vue` — telegram badge.
- Modify `utils/messageTypeDetector.ts` — telegram message types (sticker/location).
- Create `components/Telegram/TelegramConnectModal.vue` — paste-token connect.
- Create `components/Telegram/TelegramProfilePage.vue` — bot settings/reconnect.
- Create `components/Telegram/TelegramAutomationsLanding.vue` + config sub-components + growth tool.
- Modify all 15 `i18n/locales/*.json` — `telegram.*` keys.
- Modify `tests/` — Playwright tab-visibility + connect flow.

---

## Task B1: Instance model + migration + config

**Files:**
- Modify: `app/db/models/instances.py:18-23` (enum), after `:137` (tk block) for tg block
- Create: `app/db/migrations/versions/20260701_telegram_channel.py`
- Modify: `app/config.py`
- Test: `tests/test_telegram_model.py`

**Interfaces:**
- Produces: `InstancePlatform.TELEGRAM`; columns `tg_bot_id, tg_bot_token, tg_bot_username, tg_bot_name, tg_webhook_secret, tg_avatar_url, tg_avatar_url_updated_at, tg_automation_settings`; method `Instances.set_telegram_bot_token(plaintext)`; settings `TELEGRAM_ENABLED, TELEGRAM_DRY_RUN, TELEGRAM_WEBHOOK_BASE_URL`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_model.py
from app.db.models.instances import Instances, InstancePlatform
from app.utils.security import decrypt_value


def test_telegram_platform_enum():
    assert InstancePlatform.TELEGRAM.value == "telegram"


def test_set_telegram_bot_token_encrypts():
    inst = Instances(nickname="t", platform="telegram")
    inst.set_telegram_bot_token("123456:ABCDEF")
    assert inst.tg_bot_token != "123456:ABCDEF"          # stored ciphertext
    assert decrypt_value(inst.tg_bot_token) == "123456:ABCDEF"
    assert inst.tg_bot_id == "123456"                     # numeric prefix extracted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_model.py -v`
Expected: FAIL — `AttributeError: TELEGRAM` / `set_telegram_bot_token`.

- [ ] **Step 3: Add the enum value**

In `app/db/models/instances.py` `InstancePlatform`, add after `WEB = "web"` (line 23):
```python
    TELEGRAM = "telegram"
```

- [ ] **Step 4: Add the `tg_*` column block** after the TikTok block (after line 137):

```python
    # Telegram credential fields (platform == 'telegram').
    # A Telegram instance is a connected bot (Bot API, bring-your-own-bot).
    # Unlike the Meta/TikTok channels there is NO OAuth and NO token refresh —
    # BotFather tokens are permanent until revoked. The bot token is a FULL-
    # takeover secret, ENCRYPTED at rest (use set_telegram_bot_token). Webhook
    # routing is by instance_id in the URL path; tg_bot_id (the numeric token
    # prefix) is the bot identity + dedup key. tg_webhook_secret is the
    # per-bot secret_token Telegram echoes in X-Telegram-Bot-Api-Secret-Token.
    tg_bot_id = Column(String, nullable=True, unique=True, index=True)   # numeric token prefix — bot identity
    tg_bot_token = Column(String, nullable=True)                          # ENCRYPTED — full bot token
    tg_bot_username = Column(String(64), nullable=True)                   # @botusername (plain)
    tg_bot_name = Column(String(100), nullable=True)                      # bot display name (plain)
    tg_webhook_secret = Column(String, nullable=True)                     # per-bot secret_token (plain — opaque random)
    tg_avatar_url = Column(String, nullable=True)                         # cached bot avatar
    tg_avatar_url_updated_at = Column(DateTime(timezone=True), nullable=True)
    # Owner-configured Telegram automation. Mirrors tk_automation_settings shape:
    # {"welcome":{"enabled":bool,"text":str},
    #  "away":{"enabled":bool,"text":str,"business_hours":{...}},
    #  "faq":{"<keyword>":{"type":"reply","reply_text":str}|{"type":"flow","flow_id":str}},
    #  "start_payload_routes":{"<payload>":{"type":"flow","flow_id":str}}}
    tg_automation_settings = Column(JSONB, nullable=True)
```

- [ ] **Step 5: Add the setter method** alongside the existing `set_business_account_id` setter (search for `def set_business_account_id` and add nearby):

```python
    def set_telegram_bot_token(self, plaintext_token: str) -> None:
        """Encrypt + store the BotFather token and derive tg_bot_id.

        Token format is ``<bot_id>:<secret>`` — the numeric prefix is the
        stable bot identity (used for dedup / the unique index). The full
        token is the credential and is encrypted at rest.
        """
        if not plaintext_token or ":" not in plaintext_token:
            raise ValueError("Invalid Telegram bot token format")
        self.tg_bot_id = plaintext_token.split(":", 1)[0]
        self.tg_bot_token = encrypt_value(plaintext_token)
```

- [ ] **Step 6: Create the migration**

Get the current head first: `python -m alembic heads` → use it as `down_revision`.

```python
# app/db/migrations/versions/20260701_telegram_channel.py
"""Telegram channel — instances.tg_* credential columns.

Revision ID: 20260701_telegram
Revises: <OUTPUT OF `alembic heads`>
Create Date: 2026-07-01

Adds Telegram as a 5th instance platform. A Telegram instance is a connected
bot (Bot API, bring-your-own-bot). No OAuth, no token refresh (bot tokens are
permanent). All columns nullable — only populated for platform='telegram' rows.
Column adds on a populated table are metadata-only in Postgres; the single
unique-index build on an all-NULL new column is trivial.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260701_telegram"
down_revision: Union[str, None] = "<HEAD>"  # from `alembic heads`
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = '2min'")
    op.execute("SET LOCAL lock_timeout = '15s'")
    op.add_column("instances", sa.Column("tg_bot_id", sa.String(), nullable=True))
    op.add_column("instances", sa.Column("tg_bot_token", sa.String(), nullable=True))
    op.add_column("instances", sa.Column("tg_bot_username", sa.String(length=64), nullable=True))
    op.add_column("instances", sa.Column("tg_bot_name", sa.String(length=100), nullable=True))
    op.add_column("instances", sa.Column("tg_webhook_secret", sa.String(), nullable=True))
    op.add_column("instances", sa.Column("tg_avatar_url", sa.String(), nullable=True))
    op.add_column("instances", sa.Column("tg_avatar_url_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instances", sa.Column("tg_automation_settings", JSONB(), nullable=True))
    op.create_index("ix_instances_tg_bot_id", "instances", ["tg_bot_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_instances_tg_bot_id", table_name="instances")
    for col in ("tg_automation_settings", "tg_avatar_url_updated_at", "tg_avatar_url",
                "tg_webhook_secret", "tg_bot_name", "tg_bot_username", "tg_bot_token", "tg_bot_id"):
        op.drop_column("instances", col)
```

- [ ] **Step 7: Add config settings** in `app/config.py` (near the `TIKTOK_*` settings):

```python
    TELEGRAM_ENABLED: bool = False
    TELEGRAM_DRY_RUN: bool = False
    TELEGRAM_WEBHOOK_BASE_URL: str = ""   # e.g. https://api.megasend.co.il — public TLS ingress
```

- [ ] **Step 8: Run tests + syntax check**

Run: `python -m pytest tests/test_telegram_model.py -v` → PASS
Run: `python -m py_compile app/db/models/instances.py app/db/migrations/versions/20260701_telegram_channel.py app/config.py`

- [ ] **Step 9: Apply migration locally** (remote DB per project convention — confirm target): `python -m alembic upgrade head`. Verify `alembic current` shows `20260701_telegram`.

- [ ] **Step 10: Commit**

```bash
git add app/db/models/instances.py app/db/migrations/versions/20260701_telegram_channel.py app/config.py tests/test_telegram_model.py
git commit -m "feat(telegram): instance tg_* columns + migration + config"
```

---

## Task B2: Bot API client + sender throttle + dispatch

**Files:**
- Create: `app/utils/telegram_ratelimit.py`
- Create: `app/services/telegram_api_client.py`
- Modify: `app/services/message_service.py` (platform detection ~line 1797; add `_dispatch_telegram` near `_dispatch_tiktok` line 4566)
- Test: `tests/test_telegram_sender.py`

**Interfaces:**
- Consumes: `Instances.tg_bot_token` (encrypted), `decrypt_value`, `MetaApiResponse`, `settings.TELEGRAM_DRY_RUN`.
- Produces: `TelegramApiClient(bot_token).send_message(chat_id, text=None, photo_url=None, video_url=None, document_url=None, buttons=None) -> MetaApiResponse`; `acquire_send_slot(bot_id, chat_id) -> float|None` (returns seconds-to-wait or None); `_dispatch_telegram(instance, recipient_chat_id, message_type, payload) -> MetaApiResponse`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_telegram_sender.py
import pytest
from app.db.models.instances import Instances
from app.services.message_service import _dispatch_telegram
from app.schemas.enums import MessageType  # adjust import to where MessageType lives


@pytest.mark.asyncio
async def test_dispatch_telegram_dry_run(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_DRY_RUN", True)
    inst = Instances(nickname="t", platform="telegram")
    inst.set_telegram_bot_token("123:ABC")
    resp = await _dispatch_telegram(inst, "555", MessageType.TEXT, {"text": "hi"})
    assert resp.success is True
    assert resp.raw_response.get("dry_run") is True


def test_429_returns_retry_after():
    from app.services.telegram_api_client import parse_retry_after
    assert parse_retry_after({"parameters": {"retry_after": 7}}) == 7
    assert parse_retry_after({}) is None
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_telegram_sender.py -v` → FAIL (import errors).

- [ ] **Step 3: Implement the rate limiter**

```python
# app/utils/telegram_ratelimit.py
"""Token-bucket throttle for Telegram Bot API sends.

Telegram limits: <=1 msg/sec to a single chat, ~30 msg/sec global per bot.
We gate with two Redis keys per attempt; on a hit we return the seconds to
wait so the caller can back off instead of hammering. ponytail: fixed-window
counters (not a strict token bucket), good enough for the documented ceilings;
swap to a leaky bucket only if 429s show the windows are too coarse.
"""
import time
from app.services.redis_client import get_redis_client

_PER_CHAT_WINDOW = 1.0     # seconds
_PER_BOT_WINDOW = 1.0
_PER_BOT_MAX = 30          # ~30/sec global per bot


def acquire_send_slot(bot_id: str, chat_id: str) -> float | None:
    """Return None if a send is allowed now, else seconds to wait."""
    r = get_redis_client()
    now = time.time()
    chat_key = f"tg:rate:chat:{bot_id}:{chat_id}"
    bot_key = f"tg:rate:bot:{bot_id}:{int(now)}"
    # per-chat: 1/sec — SET NX EX 1 acts as a 1s lock
    if not r.set(chat_key, "1", nx=True, ex=1):
        ttl = r.pttl(chat_key)
        return max(0.05, (ttl or 1000) / 1000.0)
    # per-bot: <=30 in the current 1s bucket
    count = r.incr(bot_key)
    if count == 1:
        r.expire(bot_key, 2)
    if count > _PER_BOT_MAX:
        return 1.0
    return None
```

- [ ] **Step 4: Implement the API client**

```python
# app/services/telegram_api_client.py
"""Minimal Telegram Bot API client.

Bot API only (never MTProto). Sends text/media + inline keyboards, honoring
429 retry_after. Returns the project-standard MetaApiResponse so the rest of
message_service treats it like any other channel.
"""
import asyncio
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.meta_api_client import MetaApiResponse
from app.utils.logger import logger
from app.utils.telegram_ratelimit import acquire_send_slot

_BASE = "https://api.telegram.org"
_MAX_RETRY = 3


def parse_retry_after(body: dict) -> Optional[int]:
    try:
        return int(body.get("parameters", {}).get("retry_after"))
    except (TypeError, ValueError):
        return None


class TelegramApiClient:
    def __init__(self, bot_token: str):
        self._token = bot_token
        self._bot_id = bot_token.split(":", 1)[0]

    async def _call(self, method: str, payload: dict, chat_id: str) -> MetaApiResponse:
        url = f"{_BASE}/bot{self._token}/{method}"
        for attempt in range(_MAX_RETRY):
            wait = acquire_send_slot(self._bot_id, chat_id)
            if wait:
                await asyncio.sleep(wait)
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return MetaApiResponse(success=True, status_code=200,
                                       data={"message_id": str(data.get("result", {}).get("message_id"))},
                                       raw_response=data)
            body = {}
            try:
                body = resp.json()
            except Exception:
                pass
            if resp.status_code == 429:
                ra = parse_retry_after(body) or 1
                logger.warning(f"[TELEGRAM] 429 retry_after={ra}s attempt={attempt+1}")
                await asyncio.sleep(ra)
                continue
            # 403 'bot can't initiate' = recipient hasn't started the bot
            return MetaApiResponse(success=False, status_code=resp.status_code,
                                   error_message=body.get("description") or resp.text[:300],
                                   raw_response=body or {"body": resp.text[:300]})
        return MetaApiResponse(success=False, status_code=429,
                               error_message="Telegram rate limit — retries exhausted")

    async def send_message(self, chat_id: str, *, text: Optional[str] = None,
                           photo_url: Optional[str] = None, video_url: Optional[str] = None,
                           document_url: Optional[str] = None,
                           buttons: Optional[list] = None) -> MetaApiResponse:
        markup = {"inline_keyboard": buttons} if buttons else None
        if photo_url:
            payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo_url}
            if text:
                payload["caption"] = text
            method = "sendPhoto"
        elif video_url:
            payload = {"chat_id": chat_id, "video": video_url}
            if text:
                payload["caption"] = text
            method = "sendVideo"
        elif document_url:
            payload = {"chat_id": chat_id, "document": document_url}
            if text:
                payload["caption"] = text
            method = "sendDocument"
        else:
            payload = {"chat_id": chat_id, "text": text or ""}
            method = "sendMessage"
        if markup:
            payload["reply_markup"] = markup
        return await self._call(method, payload, chat_id)
```

- [ ] **Step 5: Wire platform detection** in `app/services/message_service.py` near line 1797 (where `is_tiktok` is set):

```python
    is_telegram = instance.platform == InstancePlatform.TELEGRAM.value
```
Route to `_dispatch_telegram` in the same dispatch branch structure that calls `_dispatch_tiktok` (follow the existing `if is_messenger: ... elif is_tiktok: ...` shape; add `elif is_telegram: resp = await _dispatch_telegram(instance, recipient_bsuid, message_type, payload)`).

- [ ] **Step 6: Implement `_dispatch_telegram`** next to `_dispatch_tiktok` (after line 4612):

```python
async def _dispatch_telegram(
    instance: Instances,
    recipient_chat_id: str,
    message_type,
    payload: dict,
) -> "MetaApiResponse":
    """Send a Telegram Bot API message.

    DRY_RUN short-circuit mirrors _dispatch_tiktok. The recipient MUST have
    started the bot first — a 403 'bot can't initiate' is surfaced (not
    retried). Inline buttons come through payload['buttons'] as Telegram's
    inline_keyboard shape.
    """
    from app.config import settings
    from app.services.meta_api_client import MetaApiResponse

    text = payload.get("text", "")
    photo = video = document = None
    if message_type == MessageType.IMAGE:
        photo = payload.get("image_url") or payload.get("url")
    elif message_type == MessageType.VIDEO:
        video = payload.get("video_url") or payload.get("url")
    elif message_type == MessageType.DOCUMENT:
        document = payload.get("document_url") or payload.get("url")
    buttons = payload.get("buttons")

    if settings.TELEGRAM_DRY_RUN:
        logger.info(
            f"[TELEGRAM][DRY_RUN] would send to chat_id={recipient_chat_id} "
            f"type={getattr(message_type, 'value', message_type)} text_len={len(text or '')} "
            f"media={'yes' if (photo or video or document) else 'no'}"
        )
        return MetaApiResponse(success=True, status_code=200,
                               data={"message_id": f"dryrun_{recipient_chat_id}"},
                               raw_response={"dry_run": True})

    from app.services.telegram_api_client import TelegramApiClient
    token = decrypt_value(instance.tg_bot_token)
    client = TelegramApiClient(token)
    return await client.send_message(recipient_chat_id, text=text, photo_url=photo,
                                     video_url=video, document_url=document, buttons=buttons)
```

- [ ] **Step 7: Run tests + compile**

Run: `python -m pytest tests/test_telegram_sender.py -v` → PASS
Run: `python -m py_compile app/services/telegram_api_client.py app/utils/telegram_ratelimit.py app/services/message_service.py`

- [ ] **Step 8: Commit**

```bash
git add app/utils/telegram_ratelimit.py app/services/telegram_api_client.py app/services/message_service.py tests/test_telegram_sender.py
git commit -m "feat(telegram): bot API client, token-bucket throttle, _dispatch_telegram"
```

---

## Task B3: Connect / disconnect / status routes + auth service

**Files:**
- Create: `app/schemas/telegram_schema.py`
- Create: `app/services/telegram_auth_service.py`
- Create: `app/routes/telegram_routes.py`
- Modify: `app/main.py` (include router)
- Test: `tests/test_telegram_routes.py`

**Interfaces:**
- Consumes: `Instances.set_telegram_bot_token`, `_enforce_telegram_instance_limit` (clone of `_enforce_tiktok_instance_limit`), `settings.TELEGRAM_WEBHOOK_BASE_URL`, `TelegramApiClient`.
- Produces: `POST /telegram/connect {bot_token, nickname?} -> {instance_id, bot_username}`; `POST /telegram/disconnect {instance_id}`; `GET /telegram/status?instance_id=`; `telegram_auth_service.connect_bot(db, user_id, token, nickname)`.

- [ ] **Step 1: Write the failing test** (mock `getMe`/`setWebhook`):

```python
# tests/test_telegram_routes.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_connect_rejects_bad_token(client, auth_headers):
    resp = await client.post("/telegram/connect", json={"bot_token": "garbage"}, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_connect_happy_path(client, auth_headers):
    with patch("app.services.telegram_auth_service._telegram_get_me",
               new=AsyncMock(return_value={"id": 123, "username": "mybot", "first_name": "My Bot"})), \
         patch("app.services.telegram_auth_service._telegram_set_webhook", new=AsyncMock(return_value=True)):
        resp = await client.post("/telegram/connect",
                                 json={"bot_token": "123:ABCDEF", "nickname": "Support"},
                                 headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["bot_username"] == "mybot"
```

- [ ] **Step 2: Run to verify fail** → 404 route missing.

- [ ] **Step 3: Implement schemas**

```python
# app/schemas/telegram_schema.py
from typing import Optional
from pydantic import BaseModel, field_validator


class TelegramConnectRequest(BaseModel):
    bot_token: str
    nickname: Optional[str] = None

    @field_validator("bot_token")
    @classmethod
    def _valid_token(cls, v: str) -> str:
        if not v or ":" not in v or not v.split(":", 1)[0].isdigit():
            raise ValueError("Invalid bot token format (expected <id>:<secret>)")
        return v.strip()


class TelegramConnectResponse(BaseModel):
    instance_id: str
    bot_username: Optional[str]
    bot_name: Optional[str]


class TelegramStatusResponse(BaseModel):
    connected: bool
    bot_username: Optional[str] = None
    webhook_ok: bool = False
```

- [ ] **Step 4: Implement auth service**

```python
# app/services/telegram_auth_service.py
"""Bring-your-own-bot connect: validate token via getMe, register webhook.

No OAuth, no refresh — the BotFather token is permanent. We generate a random
per-bot secret_token and pass it to setWebhook; Telegram echoes it back on
every inbound update for cheap authentication.
"""
import secrets

import httpx

from app.config import settings
from app.db.models.instances import Instances, InstancePlatform
from app.utils.logger import logger

_BASE = "https://api.telegram.org"


async def _telegram_get_me(token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{_BASE}/bot{token}/getMe")
    r.raise_for_status()
    return r.json()["result"]


async def _telegram_set_webhook(token: str, url: str, secret: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{_BASE}/bot{token}/setWebhook", json={
            "url": url,
            "secret_token": secret,
            "allowed_updates": ["message", "edited_message", "callback_query"],
            "drop_pending_updates": True,
        })
    return r.status_code == 200 and r.json().get("ok", False)


async def _telegram_delete_webhook(token: str) -> bool:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{_BASE}/bot{token}/deleteWebhook", json={"drop_pending_updates": False})
    return r.status_code == 200


class TelegramAuthService:
    async def connect_bot(self, db, user_id: str, token: str, nickname: str | None) -> Instances:
        from fastapi import HTTPException
        try:
            me = await _telegram_get_me(token)
        except Exception as e:
            logger.warning(f"[TELEGRAM] getMe failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid bot token — Telegram rejected getMe")

        bot_id = str(me["id"])
        existing = db.query(Instances).filter(Instances.tg_bot_id == bot_id).first()
        inst = existing or Instances(user_id=user_id, platform=InstancePlatform.TELEGRAM.value,
                                     nickname=nickname or me.get("first_name") or "Telegram bot")
        if existing and str(existing.user_id) != str(user_id):
            raise HTTPException(status_code=409, detail="This bot is already connected to another account")
        inst.set_telegram_bot_token(token)
        inst.tg_bot_username = me.get("username")
        inst.tg_bot_name = me.get("first_name")
        inst.tg_webhook_secret = secrets.token_urlsafe(32)
        if not existing:
            db.add(inst)
        db.flush()  # need inst.id for the webhook URL

        webhook_url = f"{settings.TELEGRAM_WEBHOOK_BASE_URL.rstrip('/')}/telegram-webhook/{inst.id}/callback"
        ok = await _telegram_set_webhook(token, webhook_url, inst.tg_webhook_secret)
        if not ok:
            db.rollback()
            raise HTTPException(status_code=502, detail="Failed to register webhook with Telegram")
        db.commit()
        logger.info(f"[TELEGRAM] connected bot @{inst.tg_bot_username} instance={inst.id}")
        return inst


telegram_auth_service = TelegramAuthService()
```

- [ ] **Step 5: Implement routes** — clone `_enforce_tiktok_instance_limit` verbatim as `_enforce_telegram_instance_limit` (same body, just rename), then:

```python
# app/routes/telegram_routes.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.billing_platforms import NON_COUNTING_PLATFORMS
from app.db.models.instances import Instances
from app.db.session import get_db
from app.dependencies.agent_auth import require_owner_access
from app.schemas.auth_schema import AuthData
from app.schemas.telegram_schema import (TelegramConnectRequest, TelegramConnectResponse,
                                          TelegramStatusResponse)
from app.services.telegram_auth_service import telegram_auth_service, _telegram_delete_webhook
from app.utils.security import decrypt_value

router = APIRouter(prefix="/telegram", tags=["Telegram"])


def _require_enabled():
    if not settings.TELEGRAM_ENABLED:
        raise HTTPException(status_code=404, detail="Telegram channel not enabled")


# (paste _enforce_telegram_instance_limit here — clone of _enforce_tiktok_instance_limit)


@router.post("/connect", response_model=TelegramConnectResponse)
async def connect(body: TelegramConnectRequest, auth: AuthData = Depends(require_owner_access),
                  db: Session = Depends(get_db)):
    _require_enabled()
    await _enforce_telegram_instance_limit(db, auth.user_id)
    inst = await telegram_auth_service.connect_bot(db, auth.user_id, body.bot_token, body.nickname)
    return TelegramConnectResponse(instance_id=str(inst.id), bot_username=inst.tg_bot_username,
                                   bot_name=inst.tg_bot_name)


@router.post("/disconnect")
async def disconnect(instance_id: str, auth: AuthData = Depends(require_owner_access),
                     db: Session = Depends(get_db)):
    _require_enabled()
    inst = db.query(Instances).filter(Instances.id == instance_id,
                                      Instances.user_id == auth.user_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    if inst.tg_bot_token:
        try:
            await _telegram_delete_webhook(decrypt_value(inst.tg_bot_token))
        except Exception:
            pass
    inst.tg_bot_token = inst.tg_webhook_secret = None
    db.commit()
    return {"status": "disconnected"}


@router.get("/status", response_model=TelegramStatusResponse)
async def status(instance_id: str = Query(...), auth: AuthData = Depends(require_owner_access),
                 db: Session = Depends(get_db)):
    inst = db.query(Instances).filter(Instances.id == instance_id,
                                      Instances.user_id == auth.user_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    return TelegramStatusResponse(connected=bool(inst.tg_bot_token),
                                  bot_username=inst.tg_bot_username,
                                  webhook_ok=bool(inst.tg_webhook_secret))
```

- [ ] **Step 6: Register router** in `app/main.py` (next to the tiktok include):

```python
from app.routes import telegram_routes, telegram_webhook_router
app.include_router(telegram_routes.router)
app.include_router(telegram_webhook_router.router)
```

- [ ] **Step 7: Run tests + compile** → PASS. `python -m py_compile app/routes/telegram_routes.py app/services/telegram_auth_service.py app/schemas/telegram_schema.py`

- [ ] **Step 8: Commit**

```bash
git add app/routes/telegram_routes.py app/services/telegram_auth_service.py app/schemas/telegram_schema.py app/main.py tests/test_telegram_routes.py
git commit -m "feat(telegram): connect/disconnect/status routes + BYO-bot auth service"
```

---

## Task B4: Webhook ingestion + secret dependency + drainer case

**Files:**
- Create: `app/dependencies/telegram_secret_dependency.py`
- Create: `app/routes/telegram_webhook_router.py`
- Modify: `celery-worker/tasks/webhook_inbox_tasks.py:135` area (add `elif obj == "telegram"`)
- Test: `tests/test_telegram_webhook_ingest.py`

**Interfaces:**
- Consumes: `Instances.tg_webhook_secret`, the durability `webhook_inbox_service` enqueue, `TelegramWebhookService` (Task B5).
- Produces: route `POST /telegram-webhook/{instance_id}/callback`; `verify_telegram_secret(instance_id, request)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_webhook_ingest.py
import pytest


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret(client, telegram_instance):
    resp = await client.post(f"/telegram-webhook/{telegram_instance.id}/callback",
                             headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                             json={"update_id": 1, "message": {"text": "hi", "chat": {"id": 5}}})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_accepts_good_secret_returns_200(client, telegram_instance):
    resp = await client.post(f"/telegram-webhook/{telegram_instance.id}/callback",
                             headers={"X-Telegram-Bot-Api-Secret-Token": telegram_instance.tg_webhook_secret},
                             json={"update_id": 1, "message": {"text": "hi", "chat": {"id": 5}}})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify fail** → 404.

- [ ] **Step 3: Implement the secret dependency**

```python
# app/dependencies/telegram_secret_dependency.py
"""Verify Telegram's per-bot secret_token header.

Telegram echoes the secret we set via setWebhook in X-Telegram-Bot-Api-Secret-
Token on every inbound update. Constant-time compare against the instance's
stored tg_webhook_secret. Fails CLOSED in non-local envs.
"""
import hmac

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.instances import Instances
from app.utils.logger import logger


def verify_telegram_secret(instance_id: str, request: Request, db: Session) -> Instances:
    inst = db.query(Instances).filter(Instances.id == instance_id,
                                      Instances.platform == "telegram").first()
    if not inst or not inst.tg_webhook_secret:
        if getattr(settings, "ENVIRONMENT", "production") == "local":
            logger.warning("[TELEGRAM] no instance/secret — local dev skip")
            return inst
        raise HTTPException(status_code=404, detail="Unknown Telegram instance")
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(header, inst.tg_webhook_secret):
        logger.warning(f"[TELEGRAM] secret mismatch for instance={instance_id}")
        raise HTTPException(status_code=401, detail="Invalid secret token")
    return inst
```

- [ ] **Step 4: Implement the webhook router** — persist to the durability inbox (same as TikTok), stamping `object='telegram'` + `instance_hint`:

```python
# app/routes/telegram_webhook_router.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.telegram_secret_dependency import verify_telegram_secret
from app.services.webhook_inbox_service import enqueue_webhook  # adjust to actual enqueue fn name
from app.utils.logger import logger

router = APIRouter(tags=["Telegram Webhook"])


@router.post("/telegram-webhook/{instance_id}/callback")
async def telegram_callback(instance_id: str, request: Request, db: Session = Depends(get_db)):
    inst = verify_telegram_secret(instance_id, request, db)
    payload = await request.json()
    if isinstance(payload, dict):
        payload["object"] = "telegram"               # drainer discriminator
    enqueue_webhook(db, payload=payload, instance_hint=str(inst.id) if inst else instance_id)
    return {"ok": True}                               # 200 immediately, drain async
```
> Match `enqueue_webhook`'s real signature to `webhook_inbox_service.py` (the TikTok router is the reference — copy its enqueue call and add the `object`/`instance_hint` stamps).

- [ ] **Step 5: Add drainer case** in `celery-worker/tasks/webhook_inbox_tasks.py` after the `tiktok_messaging` branch (line ~146):

```python
    elif obj == "telegram":
        # Telegram Bot API inbound (message / edited_message / callback_query).
        # Router stamps object='telegram'; routing is by instance_id (carried in
        # webhook_config / instance_hint), not by payload sniffing.
        from app.services.telegram_webhook_service import TelegramWebhookService  # noqa: E402

        coro = TelegramWebhookService().process_webhook_event(db, payload, webhook_config)
```

- [ ] **Step 6: Run tests + compile** → PASS (the 200 test passes once B5's service no-ops cleanly; if B5 isn't built yet, stub `process_webhook_event` to return `{}`).

- [ ] **Step 7: Commit**

```bash
git add app/dependencies/telegram_secret_dependency.py app/routes/telegram_webhook_router.py celery-worker/tasks/webhook_inbox_tasks.py tests/test_telegram_webhook_ingest.py
git commit -m "feat(telegram): webhook ingestion, secret_token verify, drainer route"
```

---

## Task B5: Webhook service (inbound normalization → message + flows + AI)

**Files:**
- Create: `app/services/telegram_webhook_service.py`
- Test: `tests/test_telegram_webhook_service.py`

**Interfaces:**
- Consumes: `Messages`, `Contacts`, `broadcast_new_message`, `_trigger_flows`/flow execution, AI enqueue (`run_ai_reply`), `instance.tg_automation_settings`.
- Produces: `TelegramWebhookService().process_webhook_event(db, payload, webhook_config) -> dict`.

**Clone source:** `app/services/tiktok_messaging_webhook_service.py` is the closest template (no-window DM channel with automation-first dispatch). Clone its structure; the deltas are the Telegram payload shape and the `callback_query` branch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_webhook_service.py
import pytest
from app.services.telegram_webhook_service import TelegramWebhookService
from app.db.models.messages import Messages


@pytest.mark.asyncio
async def test_inbound_text_materializes_message(db, telegram_instance):
    payload = {"object": "telegram", "update_id": 10,
               "message": {"message_id": 7, "text": "hello",
                           "chat": {"id": 999, "type": "private", "first_name": "Dana"},
                           "from": {"id": 999, "first_name": "Dana", "username": "dana"}}}
    await TelegramWebhookService().process_webhook_event(db, payload, {"instance_id": str(telegram_instance.id)})
    msg = db.query(Messages).filter(Messages.instance_id == telegram_instance.id).first()
    assert msg is not None
    assert msg.recipient_bsuid == "999"
    assert msg.platform == "telegram"
    assert msg.direction == "inbound"


@pytest.mark.asyncio
async def test_callback_query_triggers_postback(db, telegram_instance, monkeypatch):
    fired = {}
    monkeypatch.setattr(TelegramWebhookService, "_trigger_postback_flows",
                        lambda self, *a, **k: fired.setdefault("ok", True))
    payload = {"object": "telegram", "update_id": 11,
               "callback_query": {"id": "cb1", "data": "menu_pricing",
                                  "from": {"id": 999},
                                  "message": {"chat": {"id": 999}}}}
    await TelegramWebhookService().process_webhook_event(db, payload, {"instance_id": str(telegram_instance.id)})
    assert fired.get("ok") is True
```

- [ ] **Step 2: Run to verify fail** → import error.

- [ ] **Step 3: Implement the service.** Normalize the Telegram update; resolve the instance from `webhook_config['instance_id']` (or `tg_bot_id`); materialize one `Messages` row per inbound; upsert the contact; broadcast WS; then dispatch automations (welcome on `/start`, keyword FAQ, else generic flow + AI). Key mapping:

```python
# app/services/telegram_webhook_service.py  (skeleton — fill bodies cloning tiktok_messaging_webhook_service)
from app.db.models.instances import Instances
from app.db.models.messages import Messages
from app.utils.logger import logger


class TelegramWebhookService:
    async def process_webhook_event(self, db, payload: dict, webhook_config: dict | None = None) -> dict:
        instance = self._resolve_instance(db, payload, webhook_config)
        if instance is None:
            logger.warning("[TELEGRAM] no instance for update — ignored")
            return {"status": "no_instance"}

        if "callback_query" in payload:
            cq = payload["callback_query"]
            chat_id = str(cq.get("message", {}).get("chat", {}).get("id") or cq.get("from", {}).get("id"))
            data = cq.get("data", "")
            self._trigger_postback_flows(db, instance, chat_id, data)
            return {"status": "postback", "data": data}

        msg = payload.get("message") or payload.get("edited_message")
        if not msg:
            return {"status": "ignored_non_message"}

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id"))
        text = msg.get("text") or msg.get("caption") or ""
        mtype, media_url = self._classify(msg)        # TEXT/IMAGE/VIDEO/DOCUMENT/STICKER/LOCATION

        row = Messages(
            user_id=instance.user_id, instance_id=instance.id,
            recipient=None, recipient_bsuid=chat_id,
            message_type=mtype, payload={"text": text, "media_url": media_url},
            status="RECEIVED", direction="inbound",
            platform="telegram", source="telegram_dm",
            wa_message_id=f"tg_{instance.tg_bot_id}_{msg.get('message_id')}",  # dedup key
        )
        db.add(row)
        self._upsert_contact(db, instance, chat_id, msg.get("from", {}))
        db.commit()

        await self._broadcast(instance, chat_id, row)

        # automation-first dispatch (welcome on /start incl. deep-link payload,
        # keyword FAQ, else generic flow + AI) — clone try_fire_tiktok_automation
        handled = await self._try_fire_automation(db, instance, chat_id, text)
        if not handled:
            self._trigger_flows(db, instance, chat_id, text)
            self._enqueue_ai(db, instance, chat_id, text)
        return {"status": "processed", "type": getattr(mtype, "value", str(mtype))}
```

Implement the private helpers (`_resolve_instance`, `_classify`, `_upsert_contact`, `_broadcast`, `_try_fire_automation`, `_trigger_flows`, `_enqueue_ai`, `_trigger_postback_flows`) by cloning the equivalent methods in `tiktok_messaging_webhook_service.py`, changing the open_id→chat_id field names and the `/start <payload>` handling:

```python
    async def _try_fire_automation(self, db, instance, chat_id, text) -> bool:
        settings_blob = instance.tg_automation_settings or {}
        # /start [payload] → welcome + optional deep-link route
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            payload_key = parts[1].strip() if len(parts) > 1 else None
            routes = settings_blob.get("start_payload_routes", {})
            if payload_key and payload_key in routes:
                self._run_route(db, instance, chat_id, routes[payload_key])
                return True
            welcome = settings_blob.get("welcome", {})
            if welcome.get("enabled") and welcome.get("text"):
                await self._send(db, instance, chat_id, welcome["text"])
                return True
        # keyword FAQ
        faq = settings_blob.get("faq", {})
        for kw, action in faq.items():
            if kw.lower() in (text or "").lower():
                self._run_route(db, instance, chat_id, action)
                return True
        return False
```

- [ ] **Step 4: Run tests + compile** → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/telegram_webhook_service.py tests/test_telegram_webhook_service.py
git commit -m "feat(telegram): inbound webhook service — message + automations + postback"
```

---

## Task B6: `/start` growth-link endpoint + flow trigger type

**Files:**
- Modify: `app/routes/telegram_routes.py` (add `GET /telegram/growth-link`)
- Modify: `app/db/models/flows.py` (document `postback_telegram` trigger)
- Test: `tests/test_telegram_growth_link.py`

**Interfaces:**
- Produces: `GET /telegram/growth-link?instance_id=&flow_id=` → `{url: "https://t.me/<bot>?start=<payload>"}` and persists the payload→flow mapping into `tg_automation_settings.start_payload_routes`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telegram_growth_link.py
import pytest


@pytest.mark.asyncio
async def test_growth_link_generates_deeplink(client, auth_headers, telegram_instance, a_flow):
    resp = await client.get("/telegram/growth-link",
                            params={"instance_id": str(telegram_instance.id), "flow_id": str(a_flow.id)},
                            headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["url"].startswith(f"https://t.me/{telegram_instance.tg_bot_username}?start=")
```

- [ ] **Step 2: Run to verify fail** → 404.

- [ ] **Step 3: Implement the endpoint** in `telegram_routes.py`:

```python
import secrets as _secrets
from sqlalchemy.orm.attributes import flag_modified

@router.get("/growth-link")
async def growth_link(instance_id: str, flow_id: str, auth: AuthData = Depends(require_owner_access),
                      db: Session = Depends(get_db)):
    _require_enabled()
    inst = db.query(Instances).filter(Instances.id == instance_id,
                                      Instances.user_id == auth.user_id).first()
    if not inst or not inst.tg_bot_username:
        raise HTTPException(status_code=404, detail="Telegram instance not connected")
    payload_key = _secrets.token_urlsafe(8)[:16]          # <=64 chars, url-safe
    blob = inst.tg_automation_settings or {}
    blob.setdefault("start_payload_routes", {})[payload_key] = {"type": "flow", "flow_id": str(flow_id)}
    inst.tg_automation_settings = blob
    flag_modified(inst, "tg_automation_settings")
    db.commit()
    return {"url": f"https://t.me/{inst.tg_bot_username}?start={payload_key}", "payload": payload_key}
```

- [ ] **Step 4: Document the trigger type** — add `postback_telegram` next to `postback_tiktok` wherever the trigger-type set/whitelist lives in `app/db/models/flows.py` (the `trigger_type` column comment lists the allowed values).

- [ ] **Step 5: Run tests + compile** → PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routes/telegram_routes.py app/db/models/flows.py tests/test_telegram_growth_link.py
git commit -m "feat(telegram): /start deep-link growth tool + postback_telegram trigger"
```

---

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

## Task V1: Backend verification

- [ ] **Step 1:** `python -m pytest tests/test_telegram_*.py -v` → all PASS.
- [ ] **Step 2:** Full webhook regression — `python -m pytest tests/ -k webhook -o addopts=""` to confirm no drainer regression for WA/IG/Messenger/TikTok.
- [ ] **Step 3:** `python -m py_compile` over every new/modified backend file.
- [ ] **Step 4:** Manual dry-run e2e — set `TELEGRAM_ENABLED=true TELEGRAM_DRY_RUN=true`, connect a real BotFather test token via `/telegram/connect`, send a message to the bot, confirm an inbound `Messages` row + a `[TELEGRAM][DRY_RUN]` reply log. (True live send needs `TELEGRAM_DRY_RUN=false` + the bot started by a test user.)

## Task V2: Frontend verification

- [ ] **Step 1:** `npx vue-tsc --noEmit` → clean.
- [ ] **Step 2:** `npx vitest run tests/unit/channelTabs.telegram.spec.ts` → PASS.
- [ ] **Step 3:** `npm run build` (NODE_OPTIONS=--max-old-space-size=16384 per i18n memory) → succeeds, non-empty `.output/server`.
- [ ] **Step 4:** Playwright — telegram instance shows telegram-only tabs, hides IG/WA-only tabs; connect modal validates a bad token; growth tool renders a `t.me/…?start=` link.

---

## Self-Review notes

- **Spec coverage:** connect (B3) ✓, webhook ingest+auth (B4) ✓, normalization+automation+postback (B5) ✓, sender+throttle (B2) ✓, model/migration (B1) ✓, growth link (B6) ✓, tabs/types (F1) ✓, connect UI (F2) ✓, inbox/badge (F3) ✓, automations UI (F4) ✓, i18n (F5) ✓, billing → reuses `atomic_message_service` (no task needed, gated in the existing send path) ✓.
- **Skipped on purpose (YAGNI until asked):** Mini Apps, Telegram Stars/Payments, group/channel posting, inline mode, polls, shared-bot onboarding. Add as Phase 3 with their own plans.
- **Type consistency:** `recipient_bsuid` = Telegram `chat.id` everywhere (B2 send target, B5 store, webhook routing). `tg_bot_id` = numeric token prefix everywhere (model, dedup, unique index). `start_payload_routes` shape identical in B5 (read) and B6 (write).
- **Verify-before-build flags:** exact `enqueue_webhook` signature (B4), exact `MessageType` import path (B2/B5), whether a generic instance-settings PATCH already exists before adding `/telegram/automation-settings` (F4), and the real `alembic heads` value (B1).
