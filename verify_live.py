#!/usr/bin/env python3
"""Wait until every file changed by the last commit is live on GitHub Pages.

GitHub Pages caches each file for up to 10 minutes, so a page, data.json or
the PDF can lag behind the commit. This fetches each changed file at its
normal public URL (no cache-busting, so it sees what Visualping sees) until
its bytes match the commit, or a removed file returns 404.

    python3 verify_live.py [--timeout-minutes 20] [--summary FILE]

Pages is served from many cache servers, and this can only see the one
nearest to where it runs. A cache server near Visualping may still hold the
old version for up to 10 minutes after the deploy (for example from the
baseline check). So once everything is live here, it keeps waiting until
10.5 minutes after the deploy was first seen, when no cache server anywhere
can still be stale. That wait is skipped when every changed file is at a URL
that has never existed before (e.g. a brand-new sandbox), since nothing can
have cached it.
"""

import argparse
import datetime
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import sitegen

ROOT = Path(__file__).resolve().parent
CACHE_SECONDS = 600     # GitHub Pages sends Cache-Control: max-age=600
SETTLE_MARGIN = 30      # a little extra for clock skew


def changed_files():
    out = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", "HEAD~1", "HEAD", "--", "docs"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    files = []
    for line in out.splitlines():
        status, path = line.split("\t", 1)
        files.append((path[len("docs/"):], status))
    return files


def never_existed(rel):
    """True if docs/<rel> never existed in any earlier commit, so no cache can hold an old copy."""
    out = subprocess.run(
        ["git", "log", "--format=%H", "-1", "HEAD~1", "--", "docs/" + rel],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    return out.strip() == ""


def utc(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%H:%M:%S UTC")


def write_summary(path, text):
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


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
    parser.add_argument("--no-settle", action="store_true",
                        help="don't wait the extra 10 minutes for far-away cache servers")
    args = parser.parse_args()

    pending = {}
    all_new = True
    for rel, status in changed_files():
        expect = None if status == "D" else (ROOT / "docs" / rel).read_bytes()
        pending[url_for(rel)] = expect
        all_new = all_new and status == "A" and never_existed(rel)
    if not pending:
        print("No files under docs/ changed in this commit.")
        return

    total = len(pending)
    start = time.time()
    first_live = None
    while pending:
        for url, expect in list(pending.items()):
            status, body = fetch(url)
            if (expect is None and status == 404) or (expect is not None and status == 200 and body == expect):
                print(f"live: {url}")
                first_live = first_live or time.time()
                del pending[url]
        if not pending:
            break
        waited = (time.time() - start) / 60
        if waited > args.timeout_minutes:
            print(f"::error::Not live after {args.timeout_minutes:g} minutes: {', '.join(pending)}. "
                  "The usual cause is GitHub's own 'pages build and deployment' run failing or getting "
                  "stuck for this commit (see the Actions tab). The change IS committed: run the "
                  "workflow again with `touch` (or the same sandbox and `touch`) to redeploy.")
            write_summary(args.summary, "**Not live after the time limit. The test is Blocked.** Check "
                          "GitHub's 'pages build and deployment' run, then re-run with `touch` to redeploy.")
            sys.exit(1)
        print(f"{waited:4.1f} min: waiting for {len(pending)} of {total} file(s)")
        time.sleep(15)

    print(f"All {total} changed file(s) are live here ({(time.time() - start) / 60:.1f} min).")

    if all_new:
        msg = "Every changed URL is brand new, so no cache can hold an old copy. Safe to click Check now."
    elif args.no_settle:
        safe = first_live + CACHE_SECONDS + SETTLE_MARGIN
        msg = f"Not waiting for far-away caches (--no-settle). Safe after {utc(safe)}."
    else:
        safe = first_live + CACHE_SECONDS + SETTLE_MARGIN
        print(f"Waiting until {utc(safe)} so cache servers near Visualping can't still serve the old version.")
        while time.time() < safe:
            print(f"  {max(0, safe - time.time()) / 60:4.1f} min to go")
            time.sleep(min(60, max(1, safe - time.time())))
        msg = f"Safe since {utc(safe)}: every cache server now has the new version. Click Check now in Visualping."
    print(msg)
    write_summary(args.summary, f"**{msg}**")


if __name__ == "__main__":
    main()
