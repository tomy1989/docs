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

