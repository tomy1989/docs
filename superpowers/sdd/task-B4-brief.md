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

