# Custom Fields + Segments (ManyChat parity)

**Date:** 2026-06-19 · **Status:** Approved, building

## Goal
Per-contact dynamic attributes (ManyChat "User Fields") + condition-based audience
Segments, shared across WhatsApp + Instagram contacts. Unlocks the flow set-field
action and condition/segment targeting.

## Data (lazy, no EAV)
- `ContactCustomFieldDefinition` — tenant catalog: `user_id`, `key` (slug, unique per
  tenant), `label`, `field_type` (text|number|date|boolean|select), `options` JSONB,
  `default_value`. New table.
- `contacts.custom_fields JSONB` (default `{}`) — key→value map. New column + GIN index.
  Contacts are shared WA+IG, so fields work on both channels.
- `ContactSegment` — `user_id`, `name`, `match` (AND|OR), `conditions` JSONB (list of
  `{type: tag|field|system, key, op, value}`). New table.

## Services + routes
- custom-fields service: definition CRUD; get/set/clear value on a contact (validate by
  type). Routes `/api/contact-custom-fields/*`.
- segments service: CRUD + `resolve(segment) -> contacts` compiling conditions to
  SQLAlchemy filters over labels + `custom_fields` JSONB + system columns (reuse the
  label-search ANY/ALL pattern) + a count preview. Routes `/api/contact-segments/*`.
- Both routers registered in `app/main.py`.

## Flow engine
- New `set_custom_field` action node (set/clear, `{{var}}` templating) — mirrors
  `contact_update`/`label_action`.
- Extend `condition` node with a custom-field source (key + op + value) and an
  "in segment" check.

## Targeting
- Campaign + Instagram Marketing-Messages broadcast audiences accept a `segment_id` →
  resolver → recipient list.

## UI
- Custom-field manager (settings); field values on the contact drawer; `SetCustomFieldNode`
  + condition custom-field option in the flow builder; segment builder (condition rows +
  live count preview) + a "target a segment" picker on campaigns/broadcast. i18n he+en.

## Scope boundaries (deliberate)
JSONB values not EAV; conditions as JSON not a rules engine; segments resolve on demand
(not materialized); no per-field analytics in v1.

## Waves
G1 models+migration → G2 services+routes → G3 flow nodes+segment resolver+targeting →
G4 UI → integration review. Each with tests; user runs the gates (Bash blocked here).
