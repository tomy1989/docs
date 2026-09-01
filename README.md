# MegaSend API Documentation

The public documentation for the MegaSend Cloud API, published with [Mintlify](https://mintlify.com).

**Live site:** built from `main`. Pushing to `main` publishes, so every change goes through a branch and a pull request.

## Layout

| Path | What it holds |
|------|---------------|
| `docs.json` | Site config: theme, navigation tabs and groups, navbar, API settings |
| `openapi.json` | Curated OpenAPI spec that generates the **API Reference** tab |
| `*.mdx` | One page per topic, grouped by folder (`messages/`, `contacts/`, `campaigns/`, ...) |
| `images/`, `logo/`, `favicon.svg` | Brand assets. `logo/light.svg` is for light backgrounds, `logo/dark.svg` for dark. |

## Local preview

```bash
npm i -g mint     # Mintlify CLI
mint dev          # run from the folder containing docs.json
```

If a page 404s, check that its path is listed in `docs.json`. If the CLI misbehaves, run `mint update`.

## Writing conventions

- **Frontmatter on every page**: `title`, `description`, `icon` (a [Font Awesome](https://fontawesome.com/icons) name). No leading whitespace before the opening `---`, or the frontmatter is not parsed.
- **No `# H1` in the body.** Mintlify renders the frontmatter `title` as the page heading, so a body H1 duplicates it.
- **Examples must run.** Code samples use the real base URL `https://api.megasend.co.il` and the `X-MEGASEND-AUTH` header. Verify field names against the live schema before publishing.
- **Document what is live.** Check an endpoint exists in production (`https://api.megasend.co.il/openapi.json`) before writing about it, and leave unlaunched features out.
- **Diagrams** are Mermaid fences (` ```mermaid `). Mintlify renders them natively, so no image export is needed.
- **Changelog**: add a dated `## YYYY-MM-DD — Title` entry with `Added` / `Changed` / `Fixed` sections for every user-visible change.

## Regenerating the OpenAPI spec

`openapi.json` is a curated subset of the production spec: customer-facing endpoints only, with admin-only paths and unlaunched features removed, plus an `X-MEGASEND-AUTH` security scheme so the reference playground authenticates correctly. Refresh it from production rather than hand-editing it, and review the diff before committing.
