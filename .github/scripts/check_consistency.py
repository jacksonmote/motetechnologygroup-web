#!/usr/bin/env python3
"""Pull request check for the "must match" rules in AGENTS.md.

Run from the repo root. Standard library only. Prints one line per rule and
exits 1 if any rule is broken.

Rules checked:
- every page has exactly one Content Security Policy meta tag and one referrer
  meta tag, and both are identical on all six pages;
- the header (with the nav and the inline logo) and the footer are identical on
  all six pages, apart from the nav's aria-current="page";
- the FAQ structured data equals the visible questions and answers, in order;
- the home page description is the same sentence in the meta description,
  og:description, twitter:description and the JSON-LD description;
- sitemap.xml lists exactly the pages that have a canonical URL, each canonical
  URL is the page's own address and equals its og:url, and a page without a
  canonical URL is marked noindex.
"""

import html
import json
import re
import sys

SITE = "https://motetechnologygroup.com"
PAGES = ["index.html", "404.html", "home/index.html", "business/index.html", "faq/index.html", "privacy/index.html"]
HOME, FAQ = "index.html", "faq/index.html"

errors = []


def fail(message):
    errors.append(message)


def plain(markup):
    """Visible text of a piece of markup: tags removed, entities decoded, whitespace collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", markup)).split())


def meta(text, attr, name):
    """Content of every <meta attr="name" content="..."> tag, entities decoded."""
    pattern = r'<meta\s+%s="%s"\s+content="([^"]*)"' % (attr, re.escape(name))
    return [html.unescape(value) for value in re.findall(pattern, text)]


def json_ld(text, path):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
    if len(blocks) != 1:
        fail(f"{path}: expected one JSON-LD block, found {len(blocks)}")
        return {}
    try:
        return json.loads(blocks[0])
    except ValueError as err:
        fail(f"{path}: JSON-LD is not valid JSON ({err})")
        return {}


def groups(values):
    """Pages grouped by value, largest group first, for a readable message."""
    found = {}
    for path, value in values.items():
        found.setdefault(value, []).append(path)
    return sorted(found.values(), key=len, reverse=True)


def check_security_meta(pages):
    before = len(errors)
    for label, attr, name in (("Content Security Policy", "http-equiv", "Content-Security-Policy"), ("referrer", "name", "referrer")):
        values = {}
        for path, text in pages.items():
            tags = meta(text, attr, name)
            if len(tags) != 1:
                fail(f"{path}: expected one {label} meta tag, found {len(tags)}")
            else:
                values[path] = tags[0]
        if len(set(values.values())) > 1:
            fail(f"The {label} meta tag differs: " + " / ".join(", ".join(g) for g in groups(values)))
    return len(errors) == before, f"Same Content Security Policy and referrer meta tag on all {len(pages)} pages"


def check_shared_parts(pages):
    before = len(errors)
    for label, pattern in (("header", r"<header\b.*?</header>"), ("footer", r"<footer\b.*?</footer>")):
        values = {}
        for path, text in pages.items():
            blocks = re.findall(pattern, text, re.S)
            if len(blocks) != 1:
                fail(f"{path}: expected one <{label}>, found {len(blocks)}")
            else:
                values[path] = blocks[0].replace(' aria-current="page"', "")
        if len(set(values.values())) > 1:
            fail(f"The {label} differs: " + " / ".join(", ".join(g) for g in groups(values)))
    return len(errors) == before, f"Same header and footer on all {len(pages)} pages"


def check_faq(pages):
    before = len(errors)
    text = pages[FAQ]
    visible = []
    for item in re.findall(r"<details\b[^>]*>(.*?)</details>", text, re.S):
        question = re.search(r"<summary\b[^>]*>(.*?)</summary>(.*)", item, re.S)
        if not question:
            fail(f"{FAQ}: a <details> item has no <summary>")
            continue
        visible.append((plain(question.group(1)), plain(question.group(2))))
    data = json_ld(text, FAQ)
    listed = [(q.get("name", ""), q.get("acceptedAnswer", {}).get("text", "")) for q in data.get("mainEntity", [])]
    if len(visible) != len(listed):
        fail(f"{FAQ}: {len(visible)} visible questions but {len(listed)} in the JSON-LD")
    for number, (shown, structured) in enumerate(zip(visible, listed), 1):
        if shown[0] != structured[0]:
            fail(f'{FAQ}: question {number} differs: page "{shown[0]}" / JSON-LD "{structured[0]}"')
        elif shown[1] != structured[1]:
            fail(f'{FAQ}: answer to "{shown[0]}" differs: page "{shown[1]}" / JSON-LD "{structured[1]}"')
    return len(errors) == before, f"FAQ JSON-LD matches the {len(visible)} visible questions and answers"


def check_home_description(pages):
    before = len(errors)
    text = pages[HOME]
    found = {
        "meta description": meta(text, "name", "description"),
        "og:description": meta(text, "property", "og:description"),
        "twitter:description": meta(text, "name", "twitter:description"),
        "JSON-LD description": [json_ld(text, HOME).get("description", "")],
    }
    for label, values in found.items():
        if len(values) != 1 or not values[0]:
            fail(f"{HOME}: expected one {label}, found {len([v for v in values if v])}")
    sentences = {values[0] for values in found.values() if len(values) == 1 and values[0]}
    if len(sentences) > 1:
        fail(f"{HOME}: the description is not the same sentence in " + ", ".join(found))
    return len(errors) == before, "Home page description is the same sentence in all four places"


def check_sitemap(pages):
    before = len(errors)
    with open("sitemap.xml", encoding="utf-8") as f:
        listed = re.findall(r"<loc>(.*?)</loc>", f.read())
    if len(listed) != len(set(listed)):
        fail("sitemap.xml lists a page twice")
    canonicals = set()
    for path, text in pages.items():
        found = re.findall(r'<link rel="canonical" href="([^"]*)"', text)
        if not found:
            if "noindex" not in " ".join(meta(text, "name", "robots")):
                fail(f"{path}: no canonical URL, and not marked noindex")
            continue
        expected = SITE + "/" + path.removesuffix("index.html")
        if found != [expected]:
            fail(f"{path}: canonical URL is {', '.join(found)}, expected {expected}")
        if meta(text, "property", "og:url") != found:
            fail(f"{path}: og:url does not equal the canonical URL")
        canonicals.update(found)
    for url in sorted(canonicals - set(listed)):
        fail(f"sitemap.xml does not list {url}")
    for url in sorted(set(listed) - canonicals):
        fail(f"sitemap.xml lists {url}, which is not the canonical URL of any page")
    return len(errors) == before, f"sitemap.xml lists the {len(canonicals)} pages that have a canonical URL"


def main():
    pages = {}
    for path in PAGES:
        with open(path, encoding="utf-8") as f:
            pages[path] = f.read()
    for title, check in (
        ("Security meta tags", check_security_meta),
        ("Header and footer", check_shared_parts),
        ("FAQ structured data", check_faq),
        ("Home page description", check_home_description),
        ("Sitemap and canonical URLs", check_sitemap),
    ):
        ok, message = check(pages)
        print(f"OK    {message}" if ok else f"FAIL  {title}")
    if errors:
        print()
        sys.exit("\n".join(errors))
    print(f"All {len(PAGES)} pages are consistent")


if __name__ == "__main__":
    main()
