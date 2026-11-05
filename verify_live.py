#!/usr/bin/env python3
"""Wait until every file changed by the last commit is live on GitHub Pages.

GitHub Pages caches each file for up to 10 minutes, so a page, data.json or
the PDF can lag behind the commit. This fetches each changed file at its
normal public URL (no cache-busting, so it sees what Visualping sees) until
its bytes match the commit, or a removed file returns 404.

    python3 verify_live.py [--timeout-minutes 20] [--summary FILE]

Caveat: Pages is served from many CDN edges. This checks the edge closest to
where it runs, which is usually (not always) the one Visualping sees too.
"""

import argparse
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import sitegen

ROOT = Path(__file__).resolve().parent


def changed_files():
    out = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", "HEAD~1", "HEAD", "--", "docs"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    files = []
    for line in out.splitlines():
        status, path = line.split("\t", 1)
        rel = path[len("docs/"):]
        files.append((rel, status == "D"))
    return files


def url_for(rel):
    if rel == "index.html":
        return sitegen.BASE_URL
    if rel.endswith("/index.html"):
        return sitegen.BASE_URL + rel[: -len("index.html")]
    return sitegen.BASE_URL + rel


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "qa-site-verify"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, b""
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None, b""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-minutes", type=float, default=20)
    parser.add_argument("--summary")
    args = parser.parse_args()

    pending = {}
    for rel, deleted in changed_files():
        expect = None if deleted else (ROOT / "docs" / rel).read_bytes()
        pending[url_for(rel)] = expect
    if not pending:
        print("No files under docs/ changed in this commit.")
        return

    total = len(pending)
    start = time.time()
    while pending:
        for url, expect in list(pending.items()):
            status, body = fetch(url)
            if (expect is None and status == 404) or (expect is not None and status == 200 and body == expect):
                print(f"live: {url}")
                del pending[url]
        if not pending:
            break
        waited = (time.time() - start) / 60
        if waited > args.timeout_minutes:
            print(f"::error::Not live after {args.timeout_minutes:g} minutes: {', '.join(pending)}. "
                  "The usual cause is GitHub's own 'pages build and deployment' run failing or getting "
                  "stuck for this commit (see the Actions tab). The change IS committed: run the "
                  "workflow again with `touch` (or the same sandbox and `touch`) to redeploy.")
            if args.summary:
                with open(args.summary, "a", encoding="utf-8") as fh:
                    fh.write("**Not live after the time limit. The test is Blocked.** Check GitHub's "
                             "'pages build and deployment' run, then re-run with `touch` to redeploy.\n")
            sys.exit(1)
        print(f"{waited:4.1f} min: waiting for {len(pending)} of {total} file(s)")
        time.sleep(15)

    mins = (time.time() - start) / 60
    msg = f"All {total} changed file(s) are live ({mins:.1f} min). Safe to click Check now in Visualping."
    print(msg)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(f"**{msg}**\n")


if __name__ == "__main__":
    main()
