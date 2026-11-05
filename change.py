#!/usr/bin/env python3
"""Make on-demand changes to the Visualping QA test site.

The page in docs/ is generated from site-state.json. Every command below
edits the state, rebuilds docs/index.html, and (with --publish) commits and
pushes so GitHub Pages serves the new version within a minute or two.

Examples:
    python3 change.py status
    python3 change.py price 24.99 --publish
    python3 change.py headline "Big summer sale" --publish
    python3 change.py stock out --publish
    python3 change.py news-add "New product launched" --publish
    python3 change.py news-remove --publish
    python3 change.py theme green --publish      # visual-only change
    python3 change.py random --publish           # one random change
    python3 change.py reset --publish
    python3 change.py preview                    # http://127.0.0.1:8000

Standard library only. No secrets are read or stored by this script; pushing
uses whatever git credentials are already set up on this machine.
"""

import argparse
import datetime
import html
import http.server
import json
import functools
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "site-state.json"
DOCS = ROOT / "docs"
INDEX = DOCS / "index.html"

MAX_TEXT = 200
THEMES = {"blue": "#2563eb", "green": "#16a34a", "red": "#dc2626", "purple": "#7c3aed"}

DEFAULT_STATE = {
    "change_number": 0,
    "last_updated": "",
    "headline": "Acme Test Store",
    "announcement": "Welcome! This page exists only for Visualping QA testing.",
    "price": "19.99",
    "in_stock": True,
    "theme": "blue",
    "news": [
        "Store opened for testing",
        "Free shipping on all test orders",
    ],
}

RANDOM_HEADLINES = [
    "Acme Test Store",
    "Big Summer Sale",
    "New Arrivals This Week",
    "Clearance Event",
    "Members-Only Deals",
]
RANDOM_NEWS = [
    "Restocked the blue widgets",
    "Holiday hours announced",
    "Price match guarantee added",
    "New warehouse location opened",
    "Customer support now open on weekends",
]


def clean_text(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        sys.exit("Text cannot be empty.")
    if len(value) > MAX_TEXT:
        sys.exit(f"Text is limited to {MAX_TEXT} characters.")
    return value


def clean_price(value: str) -> str:
    if not re.fullmatch(r"\d{1,6}(\.\d{1,2})?", value):
        sys.exit("Price must look like 19 or 19.99.")
    return f"{float(value):.2f}"


def load_state() -> dict:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_STATE, **state}
    return dict(DEFAULT_STATE)


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def render(state: dict) -> str:
    e = html.escape  # every value from state is escaped before it reaches HTML
    if state["theme"] not in THEMES:
        state["theme"] = "blue"
    stock_text = "In stock" if state["in_stock"] else "Out of stock"
    stock_class = "in" if state["in_stock"] else "out"
    news_items = "\n".join(f"        <li>{e(item)}</li>" for item in state["news"]) or \
        "        <li><em>No news right now.</em></li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="no-referrer">
  <meta name="robots" content="noindex, nofollow">
  <title>Visualping QA Test Page</title>
  <link rel="stylesheet" href="style.css">
</head>
<body class="theme-{e(state['theme'])}">
  <header>
    <p class="tag">QA test page &middot; not a real store</p>
    <h1 id="headline">{e(state['headline'])}</h1>
    <p id="announcement">{e(state['announcement'])}</p>
  </header>

  <main>
    <section class="card" id="product">
      <h2>Test Widget</h2>
      <p class="price">$<span id="price">{e(state['price'])}</span></p>
      <p id="stock" class="stock {stock_class}">{stock_text}</p>
    </section>

    <section class="card" id="news">
      <h2>Latest news</h2>
      <ul id="news-list">
{news_items}
      </ul>
    </section>
  </main>

  <footer>
    <p>Change #<span id="change-number">{state['change_number']}</span>
       &middot; Last updated <time id="last-updated">{e(state['last_updated'] or 'never')}</time>
       &middot; Theme: <span id="theme">{e(state['theme'])}</span></p>
  </footer>
</body>
</html>
"""


def build(state: dict) -> None:
    DOCS.mkdir(exist_ok=True)
    INDEX.write_text(render(state), encoding="utf-8")


def bump(state: dict) -> None:
    state["change_number"] += 1
    state["last_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def random_change(state: dict) -> str:
    choice = random.choice(["price", "headline", "stock", "news-add", "news-remove", "theme"])
    if choice == "price":
        state["price"] = f"{random.uniform(5, 99):.2f}"
        return f"price -> {state['price']}"
    if choice == "headline":
        state["headline"] = random.choice([h for h in RANDOM_HEADLINES if h != state["headline"]])
        return f"headline -> {state['headline']}"
    if choice == "stock":
        state["in_stock"] = not state["in_stock"]
        return f"stock -> {'in' if state['in_stock'] else 'out'}"
    if choice == "news-add":
        item = random.choice(RANDOM_NEWS)
        state["news"].insert(0, item)
        return f"news added: {item}"
    if choice == "news-remove" and state["news"]:
        return f"news removed: {state['news'].pop(0)}"
    state["theme"] = random.choice([t for t in THEMES if t != state["theme"]])
    return f"theme -> {state['theme']}"


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def publish(summary: str) -> None:
    git("add", "docs/index.html", "site-state.json")
    git("commit", "-m", f"QA change: {summary}")
    git("push")
    print("Pushed. GitHub Pages usually updates within 1-2 minutes.")


def preview() -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DOCS))
    # Bound to 127.0.0.1 so the preview is only reachable from this computer.
    with http.server.ThreadingHTTPServer(("127.0.0.1", 8000), handler) as server:
        print("Previewing at http://127.0.0.1:8000  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Change the Visualping QA test site.")
    parser.add_argument("--publish", action="store_true", help="commit and push after the change")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show the current state")
    sub.add_parser("build", help="rebuild docs/index.html without changing anything")
    sub.add_parser("preview", help="serve docs/ at http://127.0.0.1:8000")
    sub.add_parser("random", help="make one random change")
    sub.add_parser("reset", help="restore the default content")
    sub.add_parser("news-remove", help="remove the newest news item")
    sub.add_parser("headline").add_argument("text")
    sub.add_parser("announcement").add_argument("text")
    sub.add_parser("price").add_argument("amount")
    sub.add_parser("stock").add_argument("value", choices=["in", "out"])
    sub.add_parser("news-add").add_argument("text")
    sub.add_parser("theme").add_argument("name", choices=sorted(THEMES))
    args = parser.parse_args()

    state = load_state()

    if args.cmd == "status":
        print(json.dumps(state, indent=2))
        return
    if args.cmd == "preview":
        build(state)
        preview()
        return
    if args.cmd == "build":
        build(state)
        print(f"Built {INDEX.relative_to(ROOT)}")
        return

    if args.cmd == "reset":
        state = {**DEFAULT_STATE, "news": list(DEFAULT_STATE["news"]), "change_number": state["change_number"]}
        summary = "reset to defaults"
    elif args.cmd == "random":
        summary = random_change(state)
    elif args.cmd == "headline":
        state["headline"] = clean_text(args.text)
        summary = f"headline -> {state['headline']}"
    elif args.cmd == "announcement":
        state["announcement"] = clean_text(args.text)
        summary = "announcement changed"
    elif args.cmd == "price":
        state["price"] = clean_price(args.amount)
        summary = f"price -> {state['price']}"
    elif args.cmd == "stock":
        state["in_stock"] = args.value == "in"
        summary = f"stock -> {args.value}"
    elif args.cmd == "news-add":
        item = clean_text(args.text)
        state["news"].insert(0, item)
        state["news"] = state["news"][:10]
        summary = f"news added: {item}"
    elif args.cmd == "news-remove":
        if not state["news"]:
            sys.exit("There is no news to remove.")
        summary = f"news removed: {state['news'].pop(0)}"
    elif args.cmd == "theme":
        state["theme"] = args.name
        summary = f"theme -> {args.name}"

    bump(state)
    save_state(state)
    build(state)
    print(f"Change #{state['change_number']}: {summary}")

    if args.publish:
        publish(summary)
    else:
        print("Not published. Re-run with --publish, or run: git add -A && git commit && git push")


if __name__ == "__main__":
    main()
