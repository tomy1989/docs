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

