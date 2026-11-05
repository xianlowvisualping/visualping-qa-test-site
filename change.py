#!/usr/bin/env python3
"""Make on-demand changes to the Visualping QA test site.

Every file in docs/ (except style.css and js/app.js) is generated from
site-state.json by sitegen.py. Each command edits the state, rebuilds docs/,
and (with --publish) pulls, commits and pushes. The GitHub Actions workflow
"Change test site" runs the same commands without --publish and pushes itself.

    python3 change.py status
    python3 change.py price 24.99 --publish
    python3 change.py table-price 2 15.00
    python3 change.py blog-add "Launch day"
    python3 change.py touch               # only bumps the home page footer
    python3 change.py preview             # http://127.0.0.1:8000

Run `python3 change.py -h` for the full list. Standard library only. No secrets
are read or stored; pushing uses the git credentials already on this machine.
"""

import argparse
import datetime
import functools
import http.server
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import sitegen

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "site-state.json"

MAX_TEXT = 200
MAX_NEWS = 10
MAX_TABLE = 20
MAX_POSTS = 20

DEFAULT_STATE = {
    "change_number": 0,
    "last_updated": "",
    "headline": "Acme Test Store",
    "announcement": "Welcome! This page exists only for Visualping QA testing.",
    "keyword": "",
    "price": "19.99",
    "in_stock": True,
    "quantity": 42,
    "percent": "10",
    "image": "a",
    "theme": "blue",
    "news": ["Store opened for testing", "Free shipping on all test orders"],
    "table": [
        {"name": "Blue widget", "price": "19.99"},
        {"name": "Green gadget", "price": "34.50"},
        {"name": "Red gizmo", "price": "7.25"},
    ],
    "blog_posts": [
        {"title": "Post 1: Hello world", "body": "This is the first test blog post."},
        {"title": "Post 2: Our test products", "body": "This is the second test blog post."},
    ],
    "pdf_version": 1,
    "pdf_text": "This PDF changes only when you run the pdf command.",
    "js_message": "This message was rendered by JavaScript.",
    "long_note": "This note at the bottom of the long page has not changed yet.",
}

RANDOM_HEADLINES = ["Acme Test Store", "Big Summer Sale", "New Arrivals This Week", "Clearance Event"]
RANDOM_NEWS = ["Restocked the blue widgets", "Holiday hours announced", "Price match guarantee added"]


def fail(msg):
    sys.exit(f"Error: {msg}")


def clean_text(value, ascii_only=False):
    value = " ".join(value.split())
    if not value:
        fail("text cannot be empty.")
    if len(value) > MAX_TEXT:
        fail(f"text is limited to {MAX_TEXT} characters.")
    if ascii_only and not re.fullmatch(r"[ -~]+", value):
        fail("PDF text must be plain ASCII (letters, numbers, punctuation).")
    return value


def clean_price(value):
    if not re.fullmatch(r"\d{1,6}(\.\d{1,2})?", value):
        fail("price must look like 19 or 19.99.")
    return f"{float(value):.2f}"


def clean_int(value, lo, hi, what):
    if not re.fullmatch(r"\d{1,7}", value) or not lo <= int(value) <= hi:
        fail(f"{what} must be a whole number from {lo} to {hi}.")
    return int(value)


def clean_percent(value):
    if not re.fullmatch(r"\d{1,3}(\.\d{1,2})?", value) or float(value) > 100:
        fail("percent must be a number from 0 to 100, like 15 or 12.5.")
    return value


def clean_keyword(value):
    if not re.fullmatch(r"[A-Za-z0-9-]{1,40}", value):
        fail("keyword must be one word: letters, numbers or hyphens, up to 40 characters.")
    return value


def load_state():
    state = json.loads(json.dumps(DEFAULT_STATE))  # deep copy
    if STATE_FILE.exists():
        state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    if state["theme"] not in sitegen.THEMES:
        state["theme"] = "blue"
    if state["image"] not in sitegen.IMAGES:
        state["image"] = "a"
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def bump(state):
    state["change_number"] += 1
    state["last_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def random_change(state):
    choice = random.choice(["price", "headline", "stock", "news-add", "theme", "image", "quantity"])
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
        state["news"] = ([item] + state["news"])[:MAX_NEWS]
        return f"news added: {item}"
    if choice == "image":
        state["image"] = random.choice([i for i in sitegen.IMAGES if i != state["image"]])
        return f"image -> {state['image']}"
    if choice == "quantity":
        state["quantity"] = random.randint(0, 500)
        return f"quantity -> {state['quantity']}"
    state["theme"] = random.choice([t for t in sitegen.THEMES if t != state["theme"]])
    return f"theme -> {state['theme']}"


def apply(cmd, a, state):
    """Apply one command to state. Returns a one-line summary."""
    def need(n):
        if len(a) != n:
            fail(f"'{cmd}' takes {n} value(s), got {len(a)}.")

    if cmd == "touch":
        need(0)
        return "touch (footer only)"
    if cmd == "random":
        need(0)
        return random_change(state)
    if cmd == "reset":
        need(0)
        keep = state["change_number"]
        state.clear()
        state.update(json.loads(json.dumps(DEFAULT_STATE)))
        state["change_number"] = keep
        return "reset to defaults"
    if cmd in ("headline", "announcement", "js-message", "long-note"):
        need(1)
        key = cmd.replace("-", "_")
        state[key] = clean_text(a[0])
        return f"{cmd} changed"
    if cmd == "price":
        need(1)
        state["price"] = clean_price(a[0])
        return f"price -> {state['price']}"
    if cmd == "stock":
        need(1)
        if a[0] not in ("in", "out"):
            fail("stock must be 'in' or 'out'.")
        state["in_stock"] = a[0] == "in"
        return f"stock -> {a[0]}"
    if cmd == "quantity":
        need(1)
        state["quantity"] = clean_int(a[0], 0, 999999, "quantity")
        return f"quantity -> {state['quantity']}"
    if cmd == "percent":
        need(1)
        state["percent"] = clean_percent(a[0])
        return f"percent -> {state['percent']}"
    if cmd == "keyword-add":
        need(1)
        state["keyword"] = clean_keyword(a[0])
        return f"keyword -> {state['keyword']}"
    if cmd == "keyword-remove":
        need(0)
        state["keyword"] = ""
        return "keyword removed"
    if cmd == "theme":
        need(1)
        if a[0] not in sitegen.THEMES:
            fail(f"theme must be one of: {', '.join(sitegen.THEMES)}.")
        state["theme"] = a[0]
        return f"theme -> {a[0]}"
    if cmd == "image":
        need(1)
        if a[0] not in sitegen.IMAGES:
            fail(f"image must be one of: {', '.join(sitegen.IMAGES)}.")
        state["image"] = a[0]
        return f"image -> {a[0]}"
    if cmd == "news-add":
        need(1)
        item = clean_text(a[0])
        state["news"] = ([item] + state["news"])[:MAX_NEWS]
        return f"news added: {item}"
    if cmd == "news-remove":
        need(0)
        if not state["news"]:
            fail("there is no news to remove.")
        return f"news removed: {state['news'].pop(0)}"
    if cmd == "table-add":
        need(2)
        if len(state["table"]) >= MAX_TABLE:
            fail(f"the table is limited to {MAX_TABLE} rows.")
        state["table"].append({"name": clean_text(a[0]), "price": clean_price(a[1])})
        return f"table row {len(state['table'])} added"
    if cmd == "table-remove":
        need(0)
        if not state["table"]:
            fail("the table is empty.")
        state["table"].pop()
        return "last table row removed"
    if cmd == "table-price":
        need(2)
        row = clean_int(a[0], 1, max(len(state["table"]), 1), "row")
        if row > len(state["table"]):
            fail("the table is empty.")
        state["table"][row - 1]["price"] = clean_price(a[1])
        return f"table row {row} price -> {state['table'][row - 1]['price']}"
    if cmd == "blog-add":
        need(1)
        if len(state["blog_posts"]) >= MAX_POSTS:
            fail(f"the blog is limited to {MAX_POSTS} posts.")
        n = len(state["blog_posts"]) + 1
        state["blog_posts"].append({"title": clean_text(a[0]), "body": f"This is test blog post {n}."})
        return f"blog post {n} added"
    if cmd == "blog-remove":
        need(0)
        if not state["blog_posts"]:
            fail("there are no posts to remove.")
        state["blog_posts"].pop()
        return f"blog post {len(state['blog_posts']) + 1} removed"
    if cmd == "blog-edit":
        need(2)
        n = clean_int(a[0], 1, max(len(state["blog_posts"]), 1), "post number")
        if n > len(state["blog_posts"]):
            fail("there are no posts.")
        state["blog_posts"][n - 1]["body"] = clean_text(a[1])
        return f"blog post {n} edited"
    if cmd == "pdf":
        need(1)
        state["pdf_text"] = clean_text(a[0], ascii_only=True)
        state["pdf_version"] += 1
        return f"pdf -> version {state['pdf_version']}"
    fail(f"unknown command '{cmd}'. Run with -h to see the list.")


CHANGE_COMMANDS = {
    "touch": "only bump the home page change number and time",
    "random": "one random change on the home page",
    "reset": "restore all default content (still bumps the change number)",
    "headline": "TEXT  home page heading",
    "announcement": "TEXT  line under the heading",
    "keyword-add": "WORD  put one word in the keyword slot",
    "keyword-remove": "empty the keyword slot",
    "price": "AMOUNT  home page price",
    "stock": "in|out  stock badge",
    "quantity": "N  whole number 0-999999",
    "percent": "N  0-100, like 12.5",
    "image": "a|b|c  swap the product image",
    "theme": "blue|green|red|purple  colours only",
    "news-add": f"TEXT  add a news item (keeps the newest {MAX_NEWS})",
    "news-remove": "remove the newest news item",
    "table-add": "NAME PRICE  add a row to the products table",
    "table-remove": "remove the last products table row",
    "table-price": "ROW PRICE  change one row's price",
    "blog-add": "TITLE  add a blog post page (and sitemap entry)",
    "blog-remove": "remove the last blog post page (it then returns 404)",
    "blog-edit": "N TEXT  change a blog post's body",
    "pdf": "TEXT  rewrite the PDF (plain ASCII)",
    "js-message": "TEXT  change the JS-rendered message on /js/",
    "long-note": "TEXT  change the line at the bottom of /long/",
}


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def preview():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(sitegen.DOCS))
    # Bound to 127.0.0.1 so the preview is only reachable from this computer.
    with http.server.ThreadingHTTPServer(("127.0.0.1", 8000), handler) as server:
        print("Previewing at http://127.0.0.1:8000  (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    epilog = "change commands:\n" + "\n".join(f"  {k:<15} {v}" for k, v in CHANGE_COMMANDS.items())
    parser = argparse.ArgumentParser(
        description="Change the Visualping QA test site.", epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--publish", action="store_true", help="git pull, commit and push after the change")
    parser.add_argument("command", help="status, build, preview, or a change command below")
    parser.add_argument("values", nargs="*", help="values for the command")
    args = parser.parse_args()

    if args.command in ("status", "build", "preview"):
        state = load_state()
        if args.command == "status":
            print(json.dumps(state, indent=2))
        else:
            sitegen.build(state)
            print("Built docs/")
            if args.command == "preview":
                preview()
        return

    if args.command not in CHANGE_COMMANDS:
        fail(f"unknown command '{args.command}'. Run with -h to see the list.")

    if args.publish:
        git("pull", "--rebase", "--quiet")  # start from the latest state, e.g. after a workflow run

    state = load_state()
    summary = apply(args.command, args.values, state)
    bump(state)
    save_state(state)
    sitegen.build(state)
    print(f"Change #{state['change_number']}: {summary}")

    if args.publish:
        git("add", "-A", "docs", "site-state.json")
        git("commit", "--quiet", "-m", f"QA change #{state['change_number']}: {summary}")
        git("pull", "--rebase", "--quiet")
        git("push", "--quiet")
        print("Pushed. GitHub Pages serves it within ~1 minute, but caches pages for up to 10 minutes.")
    else:
        print("Not published. Re-run with --publish, or use the 'Change test site' workflow on GitHub.")


if __name__ == "__main__":
    main()
