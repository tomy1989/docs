#!/usr/bin/env python3
"""Pre-publish checks for the MegaSend docs site.

Run from the repo root (the folder containing docs.json):

    python3 scripts/verify_docs.py            # structure + content checks
    python3 scripts/verify_docs.py --live     # also verify every example
                                              # request against production

Exits non-zero when a check fails, so it can gate a PR.
"""

import collections
import glob
import json
import os
import re
import sys
import urllib.request

PROD_SPEC = "https://api.megasend.co.il/openapi.json"
METHODS = ("get", "post", "put", "patch", "delete")

# Keys Mintlify accepts at the top level of docs.json. Anything else is
# silently ignored by the build, which is how the support link, the footer
# and the whole OpenAPI spec once went missing without an error.
VALID_CONFIG_KEYS = {
    "$schema", "api", "appearance", "background", "banner", "colors",
    "contextual", "description", "errors", "favicon", "fonts", "footer",
    "icons", "integrations", "interaction", "logo", "markdown", "metadata",
    "name", "navbar", "navigation", "public", "redirects", "search",
    "seo", "styling", "theme", "thumbnails", "variables",
}

failures = []
notes = []


def fail(msg):
    failures.append(msg)


def mdx_files():
    return sorted(glob.glob("**/*.mdx", recursive=True))


def nav_pages(cfg):
    nav = cfg["navigation"]
    pages = []
    groups = []
    if "tabs" in nav:
        groups = [g for tab in nav["tabs"] for g in tab.get("groups", [])]
    elif "groups" in nav:
        groups = nav["groups"]
    for g in groups:
        pages += g.get("pages", [])
    return pages, groups


def check_config():
    cfg = json.load(open("docs.json"))
    for key in cfg:
        if key not in VALID_CONFIG_KEYS:
            fail(f"docs.json: '{key}' is not a Mintlify docs.json key and will be ignored")
    pages, groups = nav_pages(cfg)
    files = {f[:-4] for f in mdx_files()}

    for page, count in collections.Counter(pages).items():
        if count > 1:
            fail(f"docs.json: '{page}' appears {count} times in the navigation")
    for page in pages:
        if page not in files:
            fail(f"docs.json: navigation points at '{page}' but {page}.mdx does not exist")
    for orphan in sorted(files - set(pages)):
        fail(f"{orphan}.mdx exists but is not in the navigation, so nobody can reach it")

    notes.append(f"navigation: {len(pages)} pages in {len(groups)} groups")
    return cfg


def check_pages():
    for f in mdx_files():
        text = open(f, encoding="utf-8").read()

        if not text.startswith("---"):
            fail(f"{f}: frontmatter must start at the very first byte, no leading whitespace")
            continue

        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not m:
            fail(f"{f}: no closing --- on the frontmatter block")
            continue

        front = m.group(1)
        for key in ("title", "description", "icon"):
            if not re.search(rf"^{key}:", front, re.M):
                fail(f"{f}: frontmatter is missing '{key}'")

        if text.count("```") % 2:
            fail(f"{f}: unbalanced ``` code fences")

        title = re.search(r"^title:\s*['\"]?(.*?)['\"]?\s*$", front, re.M)
        body_no_code = re.sub(r"```.*?```", "", text[m.end():], flags=re.S)
        if title:
            for line in body_no_code.split("\n"):
                if line.startswith("# ") and line[2:].strip().lower() == title.group(1).strip().lower():
                    fail(f"{f}: body '# {title.group(1)}' duplicates the frontmatter title")
                    break


def check_links():
    files = {f[:-4] for f in mdx_files()}
    pattern = re.compile(r"\]\((/[^)\s]*)\)")
    for f in mdx_files():
        for link in pattern.findall(open(f, encoding="utf-8").read()):
            target = link.split("#")[0].rstrip("/").lstrip("/")
            if not target:
                continue
            if target in files or os.path.exists(target) or os.path.exists(target + ".mdx"):
                continue
            fail(f"{f}: link to /{target} has no page or asset behind it")


def check_spec():
    spec = json.load(open("openapi.json"))
    schemes = spec.get("components", {}).get("securitySchemes", {})
    if not any(s.get("name") == "X-MEGASEND-AUTH" for s in schemes.values()):
        fail("openapi.json: no security scheme declares the X-MEGASEND-AUTH header, "
             "so the reference playground will ask for the wrong credential")
    if not spec.get("servers"):
        fail("openapi.json: no servers entry, so the playground has no base URL")
    notes.append(f"openapi.json: {len(spec['paths'])} paths")
    return spec


def check_live_examples():
    """Every request in a code sample must exist in production."""
    with urllib.request.urlopen(PROD_SPEC, timeout=60) as r:
        prod = json.loads(r.read())
    paths = set(prod["paths"])

    def resolve(path):
        for candidate in (path, path + "/", path.rstrip("/")):
            if candidate in paths:
                return candidate
        matches = []
        for candidate in paths:
            rx = "^" + re.sub(r"\{[^}]+\}", "[^/]+", candidate.rstrip("/")) + "$"
            if re.match(rx, path.rstrip("/")):
                matches.append(candidate)
        return sorted(matches, key=lambda c: c.count("{"))[0] if matches else None

    curl = re.compile(
        r'curl\s+(?:-X\s+(GET|POST|PUT|PATCH|DELETE)\s+)?"?https://api\.megasend\.co\.il([^"\s?\\]+)')
    fetch = re.compile(r"""fetch\(\s*[`'"]https://api\.megasend\.co\.il([^`'"?]+)""")

    checked = 0
    for f in mdx_files():
        lines = open(f, encoding="utf-8").read().split("\n")
        for i, line in enumerate(lines):
            hits = []
            m = curl.search(line)
            if m:
                hits.append(((m.group(1) or "GET").lower(), m.group(2)))
            m = fetch.search(line)
            if m:
                window = "\n".join(lines[i:i + 6])
                verb = re.search(r"method:\s*['\"](\w+)['\"]", window)
                hits.append(((verb.group(1) if verb else "GET").lower(), m.group(1)))

            for method, raw in hits:
                # Template literals: cut the URL at the first interpolation and
                # treat the rest as a path parameter.
                path = raw.split("${")[0]
                checked += 1
                resolved = resolve(path)
                if resolved is None:
                    fail(f"{f}:{i + 1}: {method.upper()} {path} does not exist in production")
                elif path.endswith("/") and raw != path:
                    continue  # truncated template literal, cannot judge the method
                elif method not in prod["paths"][resolved]:
                    allowed = sorted(k.upper() for k in prod["paths"][resolved] if k in METHODS)
                    fail(f"{f}:{i + 1}: {method.upper()} {path} is not allowed, production has {allowed}")
    notes.append(f"live check: {checked} example requests verified against production")


def main():
    if not os.path.exists("docs.json"):
        print("Run this from the folder containing docs.json")
        return 2

    check_config()
    check_pages()
    check_links()
    check_spec()
    if "--live" in sys.argv:
        check_live_examples()

    for note in notes:
        print(f"  {note}")
    if failures:
        print(f"\n{len(failures)} problem(s):\n")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
