# MegaSend Docs — Copilot Instructions

## Architecture

API documentation site built with [Mintlify](https://mintlify.com/). Content in MDX format, navigation defined in `docs.json`.

### Repo layout
- `docs.json` — navigation structure, theme config, API reference settings
- `openapi.json` — OpenAPI spec (source of truth for API reference pages)
- `api-reference/` — API endpoint documentation
- `messages/`, `contacts/`, `templates/`, `instances/`, `webhooks/`, `analytics/`, `media/`, `unsubscribe/` — feature documentation sections
- `images/`, `logo/` — static assets

## Conventions

- All content files use `.mdx` extension (Markdown + JSX components)
- Navigation order is controlled by `docs.json` — update it when adding/removing pages
- API reference pages auto-generate from `openapi.json` — edit the spec to change endpoint docs
- Use Mintlify components (`<Card>`, `<CodeGroup>`, `<Tabs>`, etc.) for rich content
- Keep parameter examples consistent with the backend's Pydantic schemas

## Development

```bash
npm i -g mint    # Install Mintlify CLI
mint dev         # Local preview (requires docs.json in cwd)
mint update      # Update CLI if dev server fails
```

Changes auto-deploy to production on push to `main` via Mintlify GitHub App.
