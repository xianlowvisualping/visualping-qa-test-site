#!/usr/bin/env python3
"""Make on-demand changes to the Visualping QA test site.

Every file in docs/ (except style.css and js/app.js) is generated from
site-state.json by sitegen.py. Each change edits the state, rebuilds docs/,
and (with --publish) pulls, commits and pushes. The GitHub Actions workflow
"Change test site" runs the same code and pushes itself.

    python3 change.py price 24.99 --publish
    python3 change.py run "price 24.99; stock out"     # several changes, one change number
    python3 change.py sandbox-create my-test             # a private copy at /t/my-test/
    python3 change.py --in my-test price 5               # change only that sandbox
    python3 change.py status | build | preview

Run `python3 change.py -h` for every command. Standard library only. No
secrets are read or stored; pushing uses the git credentials already on
this machine.
"""

import argparse
import copy
import datetime
import functools
import http.server
import json
import random
import re
import shlex
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
MAX_SANDBOXES = 50
MAX_BATCH = 20

# Content that exists on the home page and in every sandbox.
PAGE_DEFAULTS = {
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
}

DEFAULT_STATE = {
    **PAGE_DEFAULTS,
    "blog_posts": [
        {"title": "Post 1: Hello world", "body": "This is the first test blog post."},
        {"title": "Post 2: Our test products", "body": "This is the second test blog post."},
    ],
    "pdf_version": 1,
    "pdf_text": "This PDF changes only when you run the pdf command.",
    "js_message": "This message was rendered by JavaScript.",
    "long_note": "This note at the bottom of the long page has not changed yet.",
    "sandboxes": {},
    "lastmod": {},
}

# Keys the before/after summary skips (bookkeeping, not content).
NOT_CONTENT = {"change_number", "last_updated", "lastmod", "sandboxes"}

RANDOM_HEADLINES = ["Acme Test Store", "Big Summer Sale", "New Arrivals This Week", "Clearance Event"]
RANDOM_NEWS = ["Restocked the blue widgets", "Holiday hours announced", "Price match guarantee added"]


class ChangeError(Exception):
    pass


def fail(msg):
    raise ChangeError(msg)


# ---------- validation ----------

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
        fail(f"price must look like 19 or 19.99, not {value!r}.")
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


def clean_sandbox_name(value):
    if not sitegen.SANDBOX_NAME.fullmatch(value):
        fail("sandbox names use lowercase letters, numbers and hyphens (up to 40), e.g. price-test-1.")
    return value


# ---------- state ----------

def fix_page(page):
    if page.get("theme") not in sitegen.THEMES:
        page["theme"] = "blue"
    if page.get("image") not in sitegen.IMAGES:
        page["image"] = "a"


def load_state():
    state = copy.deepcopy(DEFAULT_STATE)
    if STATE_FILE.exists():
        state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    fix_page(state)
    for name in list(state["sandboxes"]):
        if not sitegen.SANDBOX_NAME.fullmatch(name):
            del state["sandboxes"][name]
            continue
        sb = {**copy.deepcopy(PAGE_DEFAULTS), **state["sandboxes"][name]}
        fix_page(sb)
        state["sandboxes"][name] = sb
    return state


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bump(page):
    page["change_number"] += 1
    page["last_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------- commands ----------

CHANGE_COMMANDS = {
    "touch": "only bump the change number and time (home page or sandbox footer)",
    "random": "one random change",
    "reset": "restore default content (still bumps the change number)",
    "headline": "TEXT  page heading",
    "announcement": "TEXT  line under the heading",
    "keyword-add": "WORD  put one word in the keyword slot",
    "keyword-remove": "empty the keyword slot",
    "price": "AMOUNT  price",
    "stock": "in|out  stock badge",
    "quantity": "N  whole number 0-999999",
    "percent": "N  0-100, like 12.5",
    "image": "a|b|c  swap the product image",
    "theme": "blue|green|red|purple  colours only",
    "news-add": f"TEXT  add a news item (keeps the newest {MAX_NEWS})",
    "news-remove": "remove the newest news item",
    "table-add": "NAME PRICE  add a table row (/products/, or the sandbox's own table)",
    "table-remove": "remove the last table row",
    "table-price": "ROW PRICE  change one row's price",
    "blog-add": "TITLE  add a blog post page (and sitemap entry)",
    "blog-remove": "remove the last blog post page (it then returns 404)",
    "blog-edit": "N TEXT  change a blog post's body",
    "pdf": "TEXT  rewrite the PDF (plain ASCII)",
    "js-message": "TEXT  change the JS-rendered message on /js/",
    "long-note": "TEXT  change the line at the bottom of /long/",
    "sandbox-create": "NAME  create /t/NAME/, a fresh home page copy owned by one test",
    "sandbox-delete": "NAME  delete /t/NAME/ (it then returns 404)",
    "sandbox-list": "list sandboxes (changes nothing; also works as a workflow run)",
}
# Commands that only make sense on the shared site, not inside a sandbox.
SITE_ONLY = {"blog-add", "blog-remove", "blog-edit", "pdf", "js-message", "long-note",
             "sandbox-create", "sandbox-delete"}
# Commands that change nothing at all.
READ_ONLY = {"sandbox-list"}
# Commands that don't change the page they target, so they don't bump its change number.
NO_BUMP = {"sandbox-create", "sandbox-delete", "sandbox-list"}


def random_change(page):
    choice = random.choice(["price", "headline", "stock", "news-add", "theme", "image", "quantity"])
    if choice == "price":
        page["price"] = f"{random.uniform(5, 99):.2f}"
    elif choice == "headline":
        page["headline"] = random.choice([h for h in RANDOM_HEADLINES if h != page["headline"]])
    elif choice == "stock":
        page["in_stock"] = not page["in_stock"]
    elif choice == "news-add":
        page["news"] = ([random.choice(RANDOM_NEWS)] + page["news"])[:MAX_NEWS]
    elif choice == "image":
        page["image"] = random.choice([i for i in sitegen.IMAGES if i != page["image"]])
    elif choice == "quantity":
        page["quantity"] = random.randint(0, 500)
    else:
        page["theme"] = random.choice([t for t in sitegen.THEMES if t != page["theme"]])


def apply(cmd, a, page, state, sandbox):
    """Apply one command. `page` is the state itself, or the sandbox being changed."""
    def need(n):
        if len(a) != n:
            fail(f"'{cmd}' takes {n} value(s), got {len(a)}.")

    if cmd not in CHANGE_COMMANDS:
        fail(f"unknown command '{cmd}'. Run with -h to see the list.")
    if sandbox and cmd in SITE_ONLY:
        fail(f"'{cmd}' changes the shared site, so it can't be used with --in.")

    if cmd == "touch":
        need(0)
    elif cmd == "random":
        need(0)
        random_change(page)
    elif cmd == "reset":
        need(0)
        keep = {k: page[k] for k in ("change_number", "sandboxes", "lastmod") if k in page}
        fresh = copy.deepcopy(PAGE_DEFAULTS if sandbox else DEFAULT_STATE)
        page.clear()
        page.update(fresh)
        page.update(keep)
    elif cmd in ("headline", "announcement", "js-message", "long-note"):
        need(1)
        page[cmd.replace("-", "_")] = clean_text(a[0])
    elif cmd == "price":
        need(1)
        page["price"] = clean_price(a[0])
    elif cmd == "stock":
        need(1)
        if a[0] not in ("in", "out"):
            fail("stock must be 'in' or 'out'.")
        page["in_stock"] = a[0] == "in"
    elif cmd == "quantity":
        need(1)
        page["quantity"] = clean_int(a[0], 0, 999999, "quantity")
    elif cmd == "percent":
        need(1)
        page["percent"] = clean_percent(a[0])
    elif cmd == "keyword-add":
        need(1)
        page["keyword"] = clean_keyword(a[0])
    elif cmd == "keyword-remove":
        need(0)
        page["keyword"] = ""
    elif cmd == "theme":
        need(1)
        if a[0] not in sitegen.THEMES:
            fail(f"theme must be one of: {', '.join(sitegen.THEMES)}.")
        page["theme"] = a[0]
    elif cmd == "image":
        need(1)
        if a[0] not in sitegen.IMAGES:
            fail(f"image must be one of: {', '.join(sitegen.IMAGES)}.")
        page["image"] = a[0]
    elif cmd == "news-add":
        need(1)
        page["news"] = ([clean_text(a[0])] + page["news"])[:MAX_NEWS]
    elif cmd == "news-remove":
        need(0)
        if not page["news"]:
            fail("there is no news to remove.")
        page["news"].pop(0)
    elif cmd == "table-add":
        need(2)
        if len(page["table"]) >= MAX_TABLE:
            fail(f"the table is limited to {MAX_TABLE} rows.")
        page["table"].append({"name": clean_text(a[0]), "price": clean_price(a[1])})
    elif cmd == "table-remove":
        need(0)
        if not page["table"]:
            fail("the table is empty.")
        page["table"].pop()
    elif cmd == "table-price":
        need(2)
        if not page["table"]:
            fail("the table is empty.")
        row = clean_int(a[0], 1, len(page["table"]), "row")
        page["table"][row - 1]["price"] = clean_price(a[1])
    elif cmd == "blog-add":
        need(1)
        if len(state["blog_posts"]) >= MAX_POSTS:
            fail(f"the blog is limited to {MAX_POSTS} posts.")
        n = len(state["blog_posts"]) + 1
        state["blog_posts"].append({"title": clean_text(a[0]), "body": f"This is test blog post {n}."})
    elif cmd == "blog-remove":
        need(0)
        if not state["blog_posts"]:
            fail("there are no posts to remove.")
        state["blog_posts"].pop()
    elif cmd == "blog-edit":
        need(2)
        if not state["blog_posts"]:
            fail("there are no posts.")
        n = clean_int(a[0], 1, len(state["blog_posts"]), "post number")
        state["blog_posts"][n - 1]["body"] = clean_text(a[1])
    elif cmd == "pdf":
        need(1)
        state["pdf_text"] = clean_text(a[0], ascii_only=True)
        state["pdf_version"] += 1
    elif cmd == "sandbox-create":
        need(1)
        name = clean_sandbox_name(a[0])
        if name in state["sandboxes"]:
            fail(f"sandbox '{name}' already exists. Use `--in {name} reset` to reset it.")
        if len(state["sandboxes"]) >= MAX_SANDBOXES:
            fail(f"there are already {MAX_SANDBOXES} sandboxes. Delete some first.")
        state["sandboxes"][name] = copy.deepcopy(PAGE_DEFAULTS)
        bump(state["sandboxes"][name])
    elif cmd == "sandbox-list":
        need(0)
    elif cmd == "sandbox-delete":
        need(1)
        name = clean_sandbox_name(a[0])
        if name not in state["sandboxes"]:
            fail(f"there is no sandbox called '{name}'.")
        del state["sandboxes"][name]


def parse_batch(text):
    """Split 'price 24.99; stock out' (or one command per line) into [(cmd, [values])]."""
    commands = []
    for line in text.splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";")
        lexer.whitespace_split = True
        lexer.commenters = ""
        current = []
        try:
            tokens = list(lexer)
        except ValueError as err:  # e.g. an unclosed quote
            fail(f"could not read {line!r}: {err}.")
        for tok in tokens + [";"]:
            if set(tok) == {";"}:
                if current:
                    commands.append((current[0], current[1:]))
                current = []
            else:
                current.append(tok)
    if not commands:
        fail("no commands given.")
    if len(commands) > MAX_BATCH:
        fail(f"a run is limited to {MAX_BATCH} commands.")
    return commands


# ---------- before/after summary ----------

def show(value):
    if value == "":
        return "(empty)"
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = text.replace("`", "'")
    return f"`{text[:120]}{'…' if len(text) > 120 else ''}`"


def describe(before, after, where):
    lines = []
    for key in after:
        if key in NOT_CONTENT or before.get(key) == after[key]:
            continue
        old, new = before.get(key), after[key]
        if isinstance(new, list) and isinstance(old, list):
            if len(old) == len(new):
                for i, (o, n) in enumerate(zip(old, new), start=1):
                    if o == n:
                        continue
                    if isinstance(o, dict) and isinstance(n, dict):
                        for field in n:
                            if o.get(field) != n[field]:
                                lines.append(f"{where}{key} row {i} {field}: {show(o.get(field))} → {show(n[field])}")
                    else:
                        lines.append(f"{where}{key} row {i}: {show(o)} → {show(n)}")
            else:
                added = [x for x in new if x not in old]
                removed = [x for x in old if x not in new]
                parts = [f"{len(old)} → {len(new)} items"]
                parts += [f"added {show(x)}" for x in added] + [f"removed {show(x)}" for x in removed]
                lines.append(f"{where}{key}: " + ", ".join(parts))
        else:
            lines.append(f"{where}{key}: {show(old)} → {show(new)}")
    return lines


def summarize(before, after, sandbox):
    if sandbox:
        return describe(before["sandboxes"][sandbox], after["sandboxes"][sandbox], f"/t/{sandbox}/ ")
    lines = describe(before, after, "")
    for name in after["sandboxes"].keys() - before["sandboxes"].keys():
        lines.append(f"sandbox created: /t/{name}/")
    for name in before["sandboxes"].keys() - after["sandboxes"].keys():
        lines.append(f"sandbox deleted: /t/{name}/")
    return lines


# ---------- running ----------

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


def sandbox_lines(state):
    boxes = state["sandboxes"]
    lines = [f"{len(boxes)} of {MAX_SANDBOXES} sandboxes in use"]
    for name, sb in sorted(boxes.items()):
        lines.append(f"/t/{name}/ (sandbox change #{sb['change_number']}, last updated {sb['last_updated'] or 'never'})")
    return lines


def emit(summary_file, head, lines):
    print(head)
    for line in lines:
        print(f"  {line}")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(f"### {head}\n\n" + "".join(f"- {line}\n" for line in lines) + "\n")


def content(state):
    """State without bookkeeping, for 'did this command change anything?' checks."""
    snap = {k: v for k, v in state.items() if k not in ("change_number", "last_updated", "lastmod", "sandboxes")}
    snap["sandboxes"] = {n: {k: v for k, v in sb.items() if k not in ("change_number", "last_updated")}
                         for n, sb in state["sandboxes"].items()}
    return copy.deepcopy(snap)


def run_changes(commands, sandbox, summary_file):
    """Apply a batch. Returns a one-line summary, or None if nothing was written."""
    state = load_state()
    if sandbox and sandbox not in state["sandboxes"]:
        fail(f"there is no sandbox called '{sandbox}'. Create it with: sandbox-create {sandbox}")
    before = copy.deepcopy(state)
    page = state["sandboxes"][sandbox] if sandbox else state

    warnings = []
    for cmd, values in commands:
        snap = content(state)
        apply(cmd, values, page, state, sandbox)
        if cmd not in READ_ONLY | {"touch"} and content(state) == snap:
            shown = " ".join([cmd] + values).replace("`", "'")
            warnings.append(f"⚠️ `{shown}` changed nothing: that was already the current "
                            "value. Don't expect an alert for that element.")

    if all(cmd in READ_ONLY for cmd, _ in commands):
        emit(summary_file, "Read-only run: nothing changed", sandbox_lines(state))
        return None

    if any(cmd not in NO_BUMP for cmd, _ in commands):
        bump(page)
    sitegen.build(state, now_iso())
    save_state(state)

    lines = summarize(before, state, sandbox)
    if not lines:
        only_touch = all(cmd in ("touch",) + tuple(READ_ONLY) for cmd, _ in commands)
        lines = ["no content changed (touch)"] if only_touch else \
            ["⚠️ net result: no content changed (later commands undid earlier ones, or values were already set)"]
    lines += warnings
    where = f"/t/{sandbox}/" if sandbox else "home page"
    head = f"Change #{page['change_number']} on {where}"
    if all(cmd in NO_BUMP for cmd, _ in commands):
        head = "Sandbox change (no page change number)"
    if any(cmd in ("sandbox-create", "sandbox-delete", "sandbox-list") for cmd, _ in commands):
        lines += sandbox_lines(state)
    emit(summary_file, head, lines)
    return f"{head}: " + "; ".join(lines)


def main():
    epilog = "change commands:\n" + "\n".join(f"  {k:<15} {v}" for k, v in CHANGE_COMMANDS.items())
    epilog += "\n  run            'CMD ARGS; CMD ARGS'  several changes, one change number"
    parser = argparse.ArgumentParser(
        description="Change the Visualping QA test site.", epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--publish", action="store_true", help="git pull, commit and push after the change")
    parser.add_argument("--in", dest="sandbox", metavar="NAME", help="apply the change to sandbox /t/NAME/")
    parser.add_argument("--summary", metavar="FILE", help="append a Markdown before/after summary to FILE")
    parser.add_argument("command", help="status, build, preview, run, or a change command below")
    parser.add_argument("values", nargs="*", help="values for the command")
    args = parser.parse_args()

    try:
        if args.command in ("status", "build", "preview"):
            state = load_state()
            if args.command == "status":
                print(json.dumps(state, indent=2))
                print("\n".join(sandbox_lines(state)))
                return
            sitegen.build(state, now_iso())
            save_state(state)
            print("Built docs/")
            if args.command == "preview":
                preview()
            return

        sandbox = clean_sandbox_name(args.sandbox) if args.sandbox else None
        if args.command == "run":
            commands = parse_batch("\n".join(args.values))
        else:
            commands = [(args.command, args.values)]

        if args.publish:
            git("pull", "--rebase", "--quiet")  # start from the latest state, e.g. after a workflow run
        message = run_changes(commands, sandbox, args.summary)
    except ChangeError as err:
        sys.exit(f"Error: {err}")

    if message is None:
        return  # read-only: nothing to publish
    if args.publish:
        git("add", "-A", "docs", "site-state.json")
        git("commit", "--quiet", "-m", f"QA {message}"[:500])
        git("pull", "--rebase", "--quiet")
        git("push", "--quiet")
        print("Pushed. Pages serves it within ~1 minute, but caches each file for up to 10 minutes.")
    else:
        print("Not published. Re-run with --publish, or use the 'Change test site' workflow on GitHub.")


if __name__ == "__main__":
    main()
