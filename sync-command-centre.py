#!/usr/bin/env python3
"""
sync-command-centre.py - make the Command Centre match your real GitHub repos.

  python3 sync-command-centre.py index.html

What it does (needs normal internet; run it on your own computer):
  1. Reads every public repo of PixelProTech-ZA, frequencyoasis and AudioHospital from the GitHub API.
  2. Keeps repos that have GitHub Pages switched on AND whose page does not return 404/410.
  3. REMOVES existing cards whose repo is deleted, has no Pages, or returns 404.
  4. ADDS a card for every live repo that has no card yet (new section: ALL REPOSITORIES).
  5. Refreshes the repo count. Writes index.synced.html (or overwrites with --in-place, keeping .bak).

Never cuts on doubt: network errors / 5xx keep the card and are reported as UNVERIFIED.
Optional: set GITHUB_TOKEN in your environment if you hit the API rate limit.
Test without network: --repos-json mock.json (a list of repo objects like the GitHub API returns).
"""
import re, os, sys, json, html, shutil, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ACCOUNTS = ["PixelProTech-ZA", "frequencyoasis", "AudioHospital"]
UA = {"User-Agent": "PixelProTech-CommandCentre-Sync/1.0"}
CARD = re.compile(r'[ \t]*<a class="card" href="(https://[^"]+\.github\.io/[^"]*)"[^>]*>.*?</a>[ \t]*\r?\n?', re.S)
SECTION = re.compile(r'[ \t]*<section aria-labelledby="[^"]+">.*?</section>[ \t]*\r?\n?', re.S)
KEY = re.compile(r'https://([^.]+)\.github\.io/([^/#?"]*)', re.I)


def api(url):
    h = dict(UA)
    if os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=20) as r:
        return json.load(r)


def all_repos():
    repos = []
    for acct in ACCOUNTS:
        page = 1
        while True:
            batch = api(f"https://api.github.com/users/{acct}/repos?per_page=100&type=owner&page={page}")
            for r in batch:
                r["_acct"] = acct
            repos += batch
            if len(batch) < 100:
                break
            page += 1
    return repos


def page_url(acct, name):
    host = acct.lower()
    if name.lower() == f"{host}.github.io":
        return f"https://{host}.github.io/"
    return f"https://{host}.github.io/{name}/"


def probe(url):
    url = url.split("#")[0]
    for _ in range(2):
        for method in ("HEAD", "GET"):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method=method, headers=UA), timeout=15) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                if e.code in (404, 410):
                    return e.code
                if method == "HEAD" and e.code in (403, 405):
                    continue
                return e.code
            except Exception:
                break
        time.sleep(1.5)
    return 0


def key_of(url):
    m = KEY.match(url)
    return (m.group(1).lower(), m.group(2).lower()) if m else None


def new_card(acct, repo, url):
    name = re.sub(r"[-_]+", " ", repo["name"]).strip() or repo["name"]
    desc = repo.get("description") or "Live PixelProTech project."
    audio = acct.lower() in ("frequencyoasis", "audiohospital")
    tag = '<span class="card-tag t-audio">audio</span>' if audio else '<span class="card-tag t-app">app</span>'
    ico = "ico-gd" if audio else "ico-pp"
    return (
        f'      <a class="card" href="{html.escape(url, quote=True)}" target="_blank">\n'
        f'        <span class="led"></span><span class="port"></span>\n'
        f'        <i class="ti ti-box card-ico {ico}" aria-hidden="true"></i>\n'
        f'        <div class="new-badge">NEW</div>\n'
        f'        <p class="card-name">{html.escape(name)}</p>\n'
        f'        <p class="card-desc">{html.escape(desc)}</p>\n'
        f'        {tag}\n'
        f'      </a>\n'
    )


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    path = args[0]
    src = open(path, encoding="utf-8").read()

    if "--repos-json" in sys.argv:
        repos = json.load(open(sys.argv[sys.argv.index("--repos-json") + 1]))
        for r in repos:
            r.setdefault("_acct", r.get("owner", {}).get("login", ""))
    else:
        repos = all_repos()
    total = len(repos)

    # candidates: Pages enabled
    cands = {}
    for r in repos:
        if r.get("has_pages"):
            cands[(r["_acct"].lower(), r["name"].lower())] = (r["_acct"], r)
    probe_urls = {k: page_url(a, r["name"]) for k, (a, r) in cands.items()}
    offline = "--repos-json" in sys.argv
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda u: 200 if offline else probe(u), probe_urls.values()))
    status = dict(zip(probe_urls.keys(), res))
    live = {k for k, s in status.items() if s not in (404, 410)}
    unverified = [probe_urls[k] for k, s in status.items() if s == 0 or s >= 500]
    no_pages = [f"{r['_acct']}/{r['name']}" for r in repos if not r.get("has_pages")]
    dead_pages = [probe_urls[k] for k, s in status.items() if s in (404, 410)]

    # 1) remove cards whose repo is not live
    removed = []

    def cut(m):
        k = key_of(m.group(1))
        if k in live:
            return m.group(0)
        removed.append(m.group(1))
        return ""
    out = CARD.sub(cut, src)

    # safety: never wipe the page on a bad / partial API answer
    n_cards = len(CARD.findall(src))
    if (not repos or len(removed) > 0.4 * n_cards) and "--force" not in sys.argv and "--repos-json" not in sys.argv:
        sys.exit(f"STOPPED: would remove {len(removed)} of {n_cards} cards from {total} repos found. "
                 "That looks like a bad GitHub answer (rate limit?). Set GITHUB_TOKEN and retry, "
                 "or re-run with --force if you are sure.")

    # 2) add cards for live repos with no card yet
    have = {key_of(m.group(1)) for m in CARD.finditer(out)}
    missing = sorted(k for k in live if k not in have)
    added = []
    if missing:
        cards = "".join(new_card(cands[k][0], cands[k][1], page_url(cands[k][0], cands[k][1]["name"])) for k in missing)
        added = [page_url(cands[k][0], cands[k][1]["name"]) for k in missing]
        section = (
            '  <section aria-labelledby="sec-allrepos">\n'
            '  <div class="section-head"><h2 id="sec-allrepos">ALL REPOSITORIES — LIVE ON GITHUB PAGES</h2></div>\n'
            '  <div class="grid-wrap">\n'
            '    <div class="cards" id="gridAllRepos">\n' + cards +
            '    </div>\n  </div>\n  </section>\n\n'
        )
        out = out.replace("  </main>", section + "  </main>", 1)

    # 3) drop sections left with no cards, refresh the repo count
    out = SECTION.sub(lambda m: m.group(0) if 'class="card"' in m.group(0) else "", out)
    out = re.sub(r'(id="repoCount">)\d+', rf"\g<1>{total}", out)
    out = re.sub(r'(<div class="hex" style="font-size:15px">)\d+(</div><span class="hex-label">REPOS)', rf"\g<1>{total}\g<2>", out)

    print(f"GitHub repos found: {total}  |  with Pages: {len(cands)}  |  live: {len(live)}")
    print(f"Cards removed: {len(removed)}  |  Cards added: {len(added)}  |  Unverified (kept): {len(unverified)}")
    for u in removed:
        print("  REMOVED   ", u)
    for u in added:
        print("  ADDED     ", u)
    for u in unverified:
        print("  UNVERIFIED", u)
    if no_pages:
        print("\nRepos with no GitHub Pages (no live URL, so no card):")
        for n in sorted(no_pages):
            print("  ", n)

    if "--in-place" in sys.argv:
        shutil.copy(path, path + ".bak")
        target = path
    else:
        target = re.sub(r"\.html$", ".synced.html", path)
    open(target, "w", encoding="utf-8").write(out)
    print("\nwrote", target)


if __name__ == "__main__":
    main()
