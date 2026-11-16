# Mote Technology Group

Source for the website at https://motetechnologygroup.com: technology help for small businesses and homes in Lexington, KY.

## How it's built

- Plain HTML and one shared stylesheet. No JavaScript, no build step, no framework.
- No third-party requests. Fonts are self-hosted, and a strict Content Security Policy blocks everything else.
- Automatic dark mode, reduced-motion support and print styles.
- Hosted on GitHub Pages with a custom domain over HTTPS.

## Quality checks

- Every pull request runs HTML validation, a check that the parts every page shares still match, link checking, accessibility tests (WCAG 2.1 AA, in light and dark mode) and a check that nothing loads from outside the site.
- A weekly health check confirms the live site is up, the certificate and domain registrations are not close to expiring, the DNS, mail and email-authentication records are as expected, the sitemap lists every page, the security policy meta tags are unchanged on every page, and the pinned CI tools are not far behind their latest releases. It opens an issue if something needs attention.
- Lighthouse scores 100 for performance, best practices and SEO on mobile and desktop (November 2026).
- Accessibility scores 100 on most runs. A page sometimes scores 95, because Lighthouse measures a scroll fade-in mid-animation.

## Contributing

See [AGENTS.md](AGENTS.md) for how to work on the site and the rules that must not break.

## Security

Report issues to security@motetechnologygroup.com. See [security.txt](https://motetechnologygroup.com/.well-known/security.txt).

## Privacy

The site sets no cookies and runs no analytics or tracking. See the [privacy policy](https://motetechnologygroup.com/privacy/).

## Copyright

© 2026 Jackson Mote. All rights reserved. This code is published for reference and is not licensed for reuse. The fonts in `/fonts` are under the SIL Open Font License (see `fonts/OFL.txt`).
