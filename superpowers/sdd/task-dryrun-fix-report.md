# Telegram DRY_RUN Metering Fix Report

## Commit
`e8e90f1` — fix(telegram): exclude TELEGRAM_DRY_RUN sends from quota reserve + Stripe metering (mirror _tk_dry_run)

## Changes in `app/services/message_service.py`

### 1. Variable declaration (lines 1812–1817, after `_tk_dry_run` block)
Added `_tg_dry_run` computed once, same pattern as `_tk_dry_run`:
```python
# Dry-run Telegram sends are also FULLY side-effect-free (mirrors _tk_dry_run):
# no quota reserve, no Stripe metering when TELEGRAM_DRY_RUN=true.
_tg_dry_run = False
if is_telegram:
    from app.config import settings as _tg_settings
    _tg_dry_run = bool(getattr(_tg_settings, "TELEGRAM_DRY_RUN", False))
```

### 2. Quota reserve guard (line 2011)
```python
# Before:
if not skip_limits and not is_shopify_platform and not is_reaction and not _tk_dry_run:
# After:
if not skip_limits and not is_shopify_platform and not is_reaction and not _tk_dry_run and not _tg_dry_run:
```

### 3. Stripe metering guard (line 2607)
```python
# Before:
if not is_shopify_platform and not is_reaction and not _tk_dry_run:
# After:
if not is_shopify_platform and not is_reaction and not _tk_dry_run and not _tg_dry_run:
```

### Note on line 2302 (`if not _tk_dry_run:`)
This guard is inside TikTok's dispatch block only — it gates `tiktok_proactive_limiter.record_send()`, which is TikTok-specific. No Telegram equivalent exists, so no mirror needed here.

## Grep Parity Output
```
1808:    _tk_dry_run = False
1811:        _tk_dry_run = bool(getattr(_tk_settings, "TIKTOK_DRY_RUN", False))
1812:    # Dry-run Telegram sends are also FULLY side-effect-free (mirrors _tk_dry_run):
1814:    _tg_dry_run = False
1817:        _tg_dry_run = bool(getattr(_tg_settings, "TELEGRAM_DRY_RUN", False))
2011:        if not skip_limits and not is_shopify_platform and not is_reaction and not _tk_dry_run and not _tg_dry_run:
2302:                if not _tk_dry_run:
2607:            if not is_shopify_platform and not is_reaction and not _tk_dry_run and not _tg_dry_run:
```

Shared billing guards: 2 `_tk_dry_run` / 2 `_tg_dry_run` (parity confirmed).
Platform-only guard (line 2302): TikTok proactive cap — no Telegram equivalent.

## Test Results
`pytest tests/test_telegram_sender.py -o addopts="" -q` → **3 passed**
`py_compile app/services/message_service.py` → **OK**
