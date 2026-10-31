# Working on this repo

Source for https://motetechnologygroup.com: a small static site (home page, `/home/`, `/business/`, `/faq/`, `404.html`) served by GitHub Pages. The [README](README.md) covers the stack, the quality checks and the security contact. This file says how to change the site without breaking it. Follow it as written, whatever tool or agent you use.

## Checklist for every change

1. Run the CI checks locally where you can. Workflow: `.github/workflows/checks.yml` (HTML validation, stylesheet version, manifest, links, pa11y accessibility at 1280px and 390px in light and dark mode, no outside requests). Use the tool versions pinned there.
2. Preview visible changes at about 390px, 768px and 1280px, in light and dark mode, and tab through with the keyboard. Serve from the repo root: `python -m http.server 8000`. The local server does not serve `404.html` for missing paths, so open `/404.html` directly.
3. Update the README in the same PR when something it claims changes (stack, checks, scores, security contact). The README must contain nothing private, no em dashes, no badges or images. CI does not check links in `.md` files, so check them by hand.
4. Run `git status` and review the staged files before every commit. Stage only site files and `.github/` files.

## Invariants (never break these)

Stack
- No JavaScript, no build step, no framework. The only scripts are the JSON-LD `<script type="application/ld+json">` data blocks.
- No inline `style=""` and no per-page `<style>`. All styling is classes in `/styles.css`.
- Whenever `styles.css` changes, bump `?v=N` in `<link rel="stylesheet" href="/styles.css?v=N">` on all five pages. CI fails if they differ.
- No third-party requests: no analytics, widgets, embeds or external fonts.
- Every page carries the same Content Security Policy meta tag and the same `referrer` meta tag. Keep them identical on all five pages. Anything that loads from another origin, or inline scripts or styles, must be added to the policy deliberately.
- Fonts are self-hosted in `/fonts/` and preloaded on every page. Never request Google Fonts. Never delete `fonts/OFL.txt`. Keep one `@font-face` per weight, as in `styles.css`; do not collapse them into a weight range.
- Keep `CNAME` and `.nojekyll`. Keep `.well-known/security.txt` valid: its `Expires` date must stay in the future.
- Images and SVGs: strip all metadata (C2PA Content Credentials, color profiles, EXIF) before committing. The headshot is a `<picture>` with a WebP source and a JPG fallback. Keep `.about-inner picture` as `display: flex`, never `display: contents`. `apple-touch-icon.png` is a full-bleed square with no transparency.

Pages
- Each of the five pages is a standalone document with its own head, header, nav and footer. Keep header, nav, footer and the inline logo SVG identical across all five.
- Subpages and `404.html` use root-relative URLs.
- Home page `<meta name="description">`, `og:description`, `twitter:description` and the JSON-LD description are the same sentence. `site.webmanifest`'s description must equal it (CI checks). Titles stay under about 60 characters, descriptions under about 155.
- The FAQ JSON-LD must match the visible questions and answers exactly.
- The home page services must match the cards on `/home/` and `/business/`. The home page writes "&" where the subpages write "and".
- The hero button text "Start a conversation" is monitored by an uptime check and by `.github/scripts/health_check.py`. Do not change it without updating both.
- `sitemap.xml` lists every page. Change a page's `lastmod` only for meaningful copy changes, never for technical edits.
- Mailto subjects are per page ("Project inquiry" on the home page, "Home services inquiry", "Business inquiry", "Question" on the FAQ). The footer email link has none.

Styling
- Use role tokens (`--heading`, `--card`, `--tile`, `--on-accent`, `--on-inverse`, `--about-bg`, and so on), not raw palette tokens. A new color use needs a role token with a light value and a dark value, or it breaks dark mode.
- Link-like classes that must not turn link-hover brown (buttons, nav links, brand, footer email) list their own `:hover` state.
- Transitions use `var(--ease)` and lifts use `var(--lift)`. Animate only color, background-color, border-color, box-shadow, transform and text-decoration-color. Hard-coded durations or transforms ignore reduced motion.
- Use `:focus-visible` for focus rings, never `:focus`. Never remove outlines.
- Write fluid sizes in this exact form so they hit the end points exactly: `clamp(min, min + (max - min) * (100vw - 390px) / 890, max)`.
- Keep text contrast at WCAG AA (4.5:1) and touch targets at least 44px.
- Never hide nav links. The two long nav links hold `<span class="nav-long">` and `<span class="nav-short">` with an `aria-label` carrying the full name. Keep each label as one span; splitting it around a nested span breaks the current-page underline.
- Dark mode is automatic (`prefers-color-scheme`), with no toggle and no script. It is screen-only, so print stays light.
- Scroll fade-ins live only inside `@supports (animation-timeline: view())` and `prefers-reduced-motion: no-preference`. Never animate the hero text.
- The hero graphic is SVG SMIL on one shared clock. Do not move its dots to CSS animation, because the two clocks drift. Any new SVG animation must also be hidden under `prefers-reduced-motion: reduce`, since SMIL ignores it.
- Print styles must keep working: no nav, buttons or graphic, FAQ answers expanded, and cards, FAQ items and steps not split across pages.

Copy
- No em dashes anywhere in site copy.
- Do not change positioning, copy or the palette without the owner's approval.
- Do not add testimonials, client logos, case studies or pricing until they are real.
- Do not put "LLC" in the name until the company is formed.
- Do not add industry-specific services or an open-source license (the site is all rights reserved).
- This repo is public. Never commit personal contact details, addresses, credentials or anything private.

## Repo hygiene

- Only project files belong here: no plans, notes, drafts or local paths.
- Pin every GitHub Action to a full commit SHA with a version comment. The repo requires it, and unpinned actions fail. Keep tool versions pinned too. Review each Dependabot PR and let the checks pass before merging.
- Workflows trigger on `pull_request`, never `pull_request_target`. Give them minimal permissions (`contents: read`, and extra scopes per job only when needed). No secrets beyond `GITHUB_TOKEN`.
- When a domain, DNS record, hosting setup or page changes, update the constants in `.github/scripts/health_check.py` in the same PR.

## Collaboration

- Branch from the latest `main`. Never commit to `main`.
- Bring your branch up to date with `main` before pushing. One PR per change.
- Required checks, by exact job name: `HTML`, `Links`, `Accessibility`, `No outside requests`. All four must pass before merge.
- When several branches are open, they often touch the same `<head>` lines or `styles.css` rules. Trial-merge them on a throwaway branch before pushing and say which order to merge in.
- The repo owner merges. After a merge, pull `main` and delete the branch locally and on GitHub.
