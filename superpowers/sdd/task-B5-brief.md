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

