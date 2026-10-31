#!/usr/bin/env python3
"""Weekly health check for the live site, its domains and its DNS.

Standard library only, plus the `gh` CLI for the GitHub Pages settings.
Every check returns (name, PASS|WARN|FAIL, message). A network error inside one
check becomes a WARN for that check; it never stops the run.

Exit code: 0 all PASS, 1 at least one FAIL, 2 WARN but no FAIL.
Writes a Markdown table to stdout, to $GITHUB_STEP_SUMMARY and (if set) to the
file named by HC_REPORT. Writes fail_count and warn_count to $GITHUB_OUTPUT.

Every constant below can be overridden with the environment variable named in
its comment, so each check can be tested without touching any real setting.
"""

import html
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def env(name, default):
    """Environment override; an empty value counts as unset."""
    return os.environ.get(name) or default


def env_int(name, default):
    return int(env(name, str(default)))


# --- Constants (update these in the same PR when a domain, DNS record or page changes) ---
SITE = env("HC_SITE", "https://motetechnologygroup.com").rstrip("/")  # HC_SITE
HOST = urllib.parse.urlparse(SITE).hostname
PAGES = env("HC_PAGES", "/,/home/,/business/,/faq/").split(",")  # HC_PAGES
KEYWORD = env("HC_KEYWORD", "Start a conversation")  # HC_KEYWORD (UptimeRobot keyword)
MISSING_PATH = "/health-check-no-such-page/"
INDEX_FILE = env("HC_INDEX_FILE", "index.html")  # HC_INDEX_FILE (checked-out home page)
CERT_HOST = env("HC_CERT_HOST", HOST)  # HC_CERT_HOST
CERT_FAIL_DAYS = env_int("HC_CERT_FAIL_DAYS", 14)  # HC_CERT_FAIL_DAYS
CERT_WARN_DAYS = env_int("HC_CERT_WARN_DAYS", 21)  # HC_CERT_WARN_DAYS
WWW_HOST = "www." + HOST
SECURITY_TXT_FILE = env("HC_SECURITY_TXT_FILE", "")  # HC_SECURITY_TXT_FILE (read instead of live file)
SECTXT_FAIL_DAYS = env_int("HC_SECTXT_FAIL_DAYS", 30)  # HC_SECTXT_FAIL_DAYS
SECTXT_WARN_DAYS = env_int("HC_SECTXT_WARN_DAYS", 60)  # HC_SECTXT_WARN_DAYS
DOMAINS = env("HC_DOMAINS", "motetechnologygroup.com,jacksonmote.com,motejackson.com").split(",")  # HC_DOMAINS
RDAP_URL = env("HC_RDAP_URL", "https://rdap.verisign.com/com/v1/domain/")  # HC_RDAP_URL
DOMAIN_FAIL_DAYS = env_int("HC_DOMAIN_FAIL_DAYS", 30)  # HC_DOMAIN_FAIL_DAYS
DOMAIN_WARN_DAYS = env_int("HC_DOMAIN_WARN_DAYS", 60)  # HC_DOMAIN_WARN_DAYS
EXPECTED_CAA = env("HC_EXPECTED_CAA", '0 issue "letsencrypt.org"')  # HC_EXPECTED_CAA
WWW_TARGET = env("HC_WWW_TARGET", "jacksonmote.github.io")  # HC_WWW_TARGET
DOH_SERVERS = [
    ("https://dns.google/resolve", {}),
    ("https://cloudflare-dns.com/dns-query", {"accept": "application/dns-json"}),
]
USER_AGENT = "Mozilla/5.0 (compatible; mote-health-check; +" + SITE + ")"
TIMEOUT = 20


# --- HTTP helpers ---
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http(url, method="GET", follow=True, headers=None):
    """Return (status, headers, body). HTTP error statuses are returned, not raised."""
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", USER_AGENT)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.headers, resp.read(2_000_000)
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read(2_000_000) if method == "GET" else b""


def get_text(path):
    status, _, body = http(SITE + path)
    return status, body.decode("utf-8", "replace")


_page_cache = {}


def page(path):
    if path not in _page_cache:
        _page_cache[path] = get_text(path)
    return _page_cache[path]


def days_until(when):
    return int((when - datetime.now(timezone.utc)).total_seconds() // 86400)


def by_days(days, fail_under, warn_under, what):
    if days < 0:
        return FAIL, f"{what}, expired {-days} days ago"
    if days < fail_under:
        return FAIL, f"{what} in {days} days"
    if days < warn_under:
        return WARN, f"{what} in {days} days"
    return PASS, f"{what} in {days} days"


# --- Checks ---
def check_pages():
    out, bad = [], []
    for path in PAGES:
        status, _ = page(path)
        if status != 200:
            bad.append(f"{path} returned {status}")
    out.append(("Pages respond", FAIL if bad else PASS, "; ".join(bad) or f"{len(PAGES)} pages return 200"))
    home = page("/")[1]
    out.append(("Home page keyword", PASS if KEYWORD in home else FAIL,
                f'Found "{KEYWORD}"' if KEYWORD in home else f'"{KEYWORD}" not found on the home page'))
    status, _ = get_text(MISSING_PATH)
    out.append(("Missing page returns 404", PASS if status == 404 else FAIL, f"Made-up path returned {status}"))
    return out


def check_live_matches_main():
    pattern = re.compile(r"/styles\.css\?v=(\d+)")
    live = pattern.search(page("/")[1])
    with open(INDEX_FILE, encoding="utf-8") as f:
        local = pattern.search(f.read())
    if not live or not local:
        return [("Live matches main", WARN, "Could not find the stylesheet version in " + ("the live page" if not live else INDEX_FILE))]
    if live.group(1) == local.group(1):
        return [("Live matches main", PASS, f"Live stylesheet is v={live.group(1)}, same as main")]
    return [("Live matches main", FAIL, f"Live stylesheet is v={live.group(1)}, main has v={local.group(1)} (deploy may have failed)")]


def check_certificate():
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((CERT_HOST, 443), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=CERT_HOST) as tls:
                not_after = tls.getpeercert()["notAfter"]
    except ssl.SSLCertVerificationError as err:
        return ("Certificate", FAIL, f"{CERT_HOST} certificate is not valid: {err.verify_message}")
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), timezone.utc)
    status, msg = by_days(days_until(expires), CERT_FAIL_DAYS, CERT_WARN_DAYS, f"Certificate expires {expires:%Y-%m-%d}")
    return ("Certificate", status, msg)


def check_pages_settings():
    try:
        proc = subprocess.run(["gh", "api", "repos/{owner}/{repo}/pages"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as err:
        return [("Pages HTTPS setting", WARN, f"Could not run gh: {err}")]
    if proc.returncode != 0:
        return [("Pages HTTPS setting", WARN, "GitHub Pages settings could not be read")]
    data = json.loads(proc.stdout)
    out = []
    enforced = data.get("https_enforced")
    out.append(("Pages HTTPS setting", PASS if enforced else FAIL, "Enforce HTTPS is on" if enforced else "Enforce HTTPS is off"))
    state = (data.get("https_certificate") or {}).get("state")
    out.append(("Pages certificate state", PASS if state == "approved" else WARN, f"Certificate state is {state}"))
    return out


def check_redirects():
    out = []
    for name, url, want_host in (("HTTP redirects to HTTPS", f"http://{HOST}/", HOST), ("www redirects to apex", f"https://{WWW_HOST}/", HOST)):
        status, headers, _ = http(url, follow=False)
        location = headers.get("Location", "") if headers else ""
        parsed = urllib.parse.urlparse(location)
        ok = status in (301, 302, 307, 308) and parsed.scheme == "https" and parsed.hostname == want_host
        out.append((name, PASS if ok else FAIL, f"{url} -> {status} {location}".strip() if not ok else f"{url} redirects ({status}) to {location}"))
    return out


def check_security_txt():
    if SECURITY_TXT_FILE:
        with open(SECURITY_TXT_FILE, encoding="utf-8") as f:
            text = f.read()
    else:
        status, text = get_text("/.well-known/security.txt")
        if status != 200:
            return [("security.txt", FAIL, f"/.well-known/security.txt returned {status}")]
    out = []
    has_contact = re.search(r"^Contact:\s*\S+", text, re.M) is not None
    out.append(("security.txt contact", PASS if has_contact else FAIL, "Contact line present" if has_contact else "No Contact line"))
    m = re.search(r"^Expires:\s*(\S+)", text, re.M)
    if not m:
        out.append(("security.txt expiry", FAIL, "No Expires line"))
        return out
    expires = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    status, msg = by_days(days_until(expires), SECTXT_FAIL_DAYS, SECTXT_WARN_DAYS, f"security.txt expires {expires:%Y-%m-%d}")
    out.append(("security.txt expiry", status, msg))
    return out


def check_domain(domain):
    name = f"Domain expiry: {domain}"
    try:
        status, _, body = http(RDAP_URL + domain, headers={"accept": "application/rdap+json"})
        if status != 200:
            return (name, WARN, f"Registry lookup returned {status}")
        events = json.loads(body)["events"]
        date = next(e["eventDate"] for e in events if e["eventAction"] == "expiration")
        expires = datetime.fromisoformat(date.replace("Z", "+00:00"))
    except (StopIteration, KeyError, ValueError):
        return (name, WARN, "Registry reply had no expiration date")
    s, msg = by_days(days_until(expires), DOMAIN_FAIL_DAYS, DOMAIN_WARN_DAYS, f"{domain} registration expires {expires:%Y-%m-%d}")
    return (name, s, msg)


_doh_cache = {}


def doh(name, rtype):
    """DNS-over-HTTPS JSON query; Google first, Cloudflare as a fallback."""
    key = (name, rtype)
    if key not in _doh_cache:
        last = None
        for base, headers in DOH_SERVERS:
            try:
                url = f"{base}?name={urllib.parse.quote(name)}&type={rtype}&do=1"
                status, _, body = http(url, headers=headers)
                if status == 200:
                    _doh_cache[key] = json.loads(body)
                    break
                last = RuntimeError(f"{base} returned {status}")
            except (OSError, ValueError) as err:
                last = err
        else:
            raise last
    return _doh_cache[key]


def answers(name, rtype, code):
    return [a["data"] for a in doh(name, rtype).get("Answer", []) if a.get("type") == code]


def txt_value(data):
    parts = re.findall(r'"([^"]*)"', data)
    return "".join(parts) if parts else data


def caa_text(data):
    """Google returns `0 issue "x"`; Cloudflare returns hex (`\\# 22 00 05 ...`)."""
    if data.startswith("\\#"):
        raw = bytes.fromhex("".join(data.split()[2:]))
        return f'{raw[0]} {raw[2:2 + raw[1]].decode()} "{raw[2 + raw[1]:].decode()}"'
    return data


def check_dns():
    out = []
    caa = sorted(caa_text(d) for d in answers(HOST, "CAA", 257))
    out.append(("DNS: CAA", PASS if caa == [EXPECTED_CAA] else FAIL,
                f"CAA is {', '.join(caa)}" if caa else "No CAA record found"))
    ad = doh(HOST, "A").get("AD")
    out.append(("DNS: DNSSEC", PASS if ad else FAIL, "DNSSEC validates (AD flag set)" if ad else "DNSSEC did not validate (AD flag not set)"))
    spf = [txt_value(d) for d in answers(HOST, "TXT", 16) if txt_value(d).startswith("v=spf1")]
    out.append(("DNS: SPF", PASS if spf else FAIL, "SPF record present" if spf else "No SPF TXT record on the apex"))
    dmarc = [txt_value(d) for d in answers("_dmarc." + HOST, "TXT", 16) if txt_value(d).startswith("v=DMARC1")]
    out.append(("DNS: DMARC", PASS if dmarc else FAIL, "DMARC record present" if dmarc else "No DMARC record at _dmarc"))
    cname = [d.rstrip(".").lower() for d in answers(WWW_HOST, "CNAME", 5)]
    out.append(("DNS: www CNAME", PASS if cname == [WWW_TARGET] else FAIL,
                f"www points to {cname[0]}" if cname else "www has no CNAME record"))
    return out


def check_external_links():
    link = re.compile(r'<a\b[^>]*?\bhref="(https://[^"]+)"', re.I)
    urls = set()
    for path in PAGES:
        for u in link.findall(page(path)[1]):
            u = html.unescape(u)
            if urllib.parse.urlparse(u).hostname not in (HOST, WWW_HOST):
                urls.add(u)
    out = []
    for u in sorted(urls):
        name = "Link: " + u
        try:
            status, _, _ = http(u, method="HEAD")
            if status >= 400:
                status, _, _ = http(u)
        except OSError as err:
            out.append((name, WARN, f"Could not connect: {getattr(err, 'reason', err)}"))
            continue
        if status == 999 and "linkedin.com" in u:
            out.append((name, PASS, "LinkedIn returns 999 to bots (expected)"))
        elif status < 400:
            out.append((name, PASS, f"Returned {status}"))
        else:
            out.append((name, WARN, f"Returned {status}"))
    return out


def run(label, func):
    """Run one check; any unexpected error becomes a WARN for that check."""
    try:
        result = func()
    except Exception as err:  # noqa: BLE001 - one broken check must not stop the run
        return [(label, WARN, f"Check could not run: {type(err).__name__}: {err}")]
    return result if isinstance(result, list) else [result]


def main():
    results = []
    for label, func in (
        ("Site", check_pages),
        ("Live matches main", check_live_matches_main),
        ("Certificate", check_certificate),
        ("Pages settings", check_pages_settings),
        ("Redirects", check_redirects),
        ("security.txt", check_security_txt),
        *[(f"Domain {d}", lambda d=d: check_domain(d)) for d in DOMAINS],
        ("DNS", check_dns),
        ("External links", check_external_links),
    ):
        results.extend(run(label, func))

    fails = sum(r[1] == FAIL for r in results)
    warns = sum(r[1] == WARN for r in results)
    rows = ["| Check | Result | Details |", "| --- | --- | --- |"]
    for name, status, msg in results:
        shown = status if status == PASS else f"**{status}**"
        rows.append(f"| {name} | {shown} | {msg.replace('|', '/')} |".replace("\n", " "))
    table = "\n".join(rows)
    summary = f"{len(results)} checks: {len(results) - fails - warns} passed, {warns} warning(s), {fails} failure(s)."

    print(table + "\n\n" + summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"## Health check\n\n{table}\n\n{summary}\n")
    if os.environ.get("HC_REPORT"):
        with open(os.environ["HC_REPORT"], "w", encoding="utf-8") as f:
            f.write(f"{table}\n\n{summary}\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"fail_count={fails}\nwarn_count={warns}\n")
    return 1 if fails else 2 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
