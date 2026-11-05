#!/usr/bin/env python3
"""
check_links.py - find dead links in the Command Centre index.html and cut their cards.

Usage (run on your own PC, needs internet, Python 3 only, no installs):
    python check_links.py index.html

Writes:
    index.clean.html   same page with every dead card removed
    link-report.txt    every URL with its HTTP status

A link is DEAD if the page answers 404/410, or the host can't be reached.
Anything else (200, 3xx that ends in 200) is kept. Timeouts / 5xx / 429 are
listed as UNSURE and are NOT removed - re-run to confirm those by hand.
Only github.io URLs are checked; mailto: and your own anchors are untouched.
"""
import re, sys, urllib.request, urllib.error, concurrent.futures as cf

SRC = sys.argv[1] if len(sys.argv) > 1 else "index.html"
FAKE_DEAD = sys.argv[2] if len(sys.argv) > 2 else None   # test hook: substring treated as 404

html = open(SRC, encoding="utf-8").read()
card_re = re.compile(r'[ \t]*<a class="card" href="(https://[^"]+)"[^>]*>.*?</a>\n?', re.S)

def status(url):
    if FAKE_DEAD:                         # test hook only
        return 404 if FAKE_DEAD in url else 200
    clean = url.split("#")[0]            # fragment never reaches the server
    req = urllib.request.Request(clean, headers={"User-Agent": "link-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0                          # DNS / connection failure

urls = []
for m in card_re.finditer(html):
    u = m.group(1)
    if "github.io" in u and u not in urls:
        urls.append(u)

with cf.ThreadPoolExecutor(8) as ex:
    results = dict(zip(urls, ex.map(status, urls)))

unreached = [u for u, s in results.items() if s == 0]
if len(unreached) > len(urls) / 2:
    sys.exit(f"ABORTED: {len(unreached)} of {len(urls)} links could not be reached at all. "
             "This is a network problem (offline / blocked / proxy), not 404s. Nothing was changed.")

dead = {u for u, s in results.items() if s in (404, 410)}      # only real 'not found' removes a card
unsure = {u for u, s in results.items() if s not in (200, 404, 410) and not (300 <= s < 400)}

out, removed = html, 0
def drop(m):
    global removed
    if m.group(1) in dead:
        removed += 1
        return ""
    return m.group(0)
out = card_re.sub(drop, out)

with open("index.clean.html", "w", encoding="utf-8") as f:
    f.write(out)
with open("link-report.txt", "w", encoding="utf-8") as f:
    for u, s in sorted(results.items(), key=lambda x: (x[1], x[0])):
        tag = "DEAD " if u in dead else ("UNSURE" if u in unsure else "ok    ")
        f.write(f"{tag} {s:>3}  {u}\n")

print(f"checked {len(urls)} unique github.io links")
print(f"dead: {len(dead)}  (card blocks removed: {removed})   unsure: {len(unsure)}")
for u in sorted(dead):
    print("  DEAD  ", u)
for u in sorted(unsure):
    print("  UNSURE", u)
print("wrote index.clean.html and link-report.txt")
if dead:
    sys.exit(1)      # non-zero exit = GitHub Actions run fails = you get the failure email
