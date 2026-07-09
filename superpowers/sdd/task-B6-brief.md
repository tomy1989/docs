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

