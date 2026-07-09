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

