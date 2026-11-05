"""Builds every file in docs/ from the state dict.

Security model: the only inputs are site-state.json and CLI arguments, both
controlled by the repo owner (or a workflow run by someone with write access).
Even so, every value is escaped for the context it lands in (HTML, XML, PDF,
JSON), pages ship a Content-Security-Policy, and nothing here reads secrets.
"""

import html
import json
import re
import shutil
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
BASE_URL = "https://xianlowvisualping.github.io/visualping-qa-test-site/"
BASE_PATH = "/visualping-qa-test-site/"

THEMES = ("blue", "green", "red", "purple")
IMAGES = ("a", "b", "c")

# Static pages: no scripts at all. The JS page gets its own policy below.
STATIC_CSP = "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"
JS_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
          "connect-src 'self'; base-uri 'none'; form-action 'none'")

e = html.escape

NAV = [
    ("", "Home"), ("products/", "Products"), ("blog/", "Blog"), ("js/", "JS page"),
    ("long/", "Long page"), ("redirect/", "Redirect"), ("files/report.pdf", "PDF"),
]

SVGS = {
    "a": '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">'
         '<rect width="240" height="160" fill="#dbeafe"/><circle cx="120" cy="80" r="50" fill="#2563eb"/></svg>',
    "b": '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">'
         '<rect width="240" height="160" fill="#fef3c7"/><rect x="70" y="30" width="100" height="100" fill="#d97706"/></svg>',
    "c": '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">'
         '<rect width="240" height="160" fill="#dcfce7"/><polygon points="120,25 180,135 60,135" fill="#16a34a"/></svg>',
}


def layout(title, root, body, csp=STATIC_CSP, theme="blue", script=None, extra_head=""):
    nav = " ".join(f'<a href="{root}{href}">{label}</a>' for href, label in NAV)
    script_tag = f'\n  <script src="{script}" defer></script>' if script else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="{csp}">
  <meta name="referrer" content="no-referrer">
  <meta name="robots" content="noindex, nofollow">{extra_head}
  <title>{e(title)} | Visualping QA Test Site</title>
  <link rel="stylesheet" href="{root}style.css">{script_tag}
</head>
<body class="theme-{e(theme)}">
  <nav class="site-nav">{nav}</nav>
{body}
</body>
</html>
"""


def table_html(rows):
    body = "\n".join(
        f'        <tr><td>{i + 1}</td><td>{e(r["name"])}</td><td>${e(r["price"])}</td></tr>'
        for i, r in enumerate(rows)
    ) or '        <tr><td colspan="3"><em>No products.</em></td></tr>'
    return f"""    <table id="product-table">
      <thead><tr><th>#</th><th>Name</th><th>Price</th></tr></thead>
      <tbody>
{body}
      </tbody>
    </table>"""


def page_home(s, root="", sandbox=None):
    """The home page, or a sandbox copy of it at /t/NAME/ (which also gets its own table)."""
    news = "\n".join(f"        <li>{e(i)}</li>" for i in s["news"]) or "        <li><em>No news right now.</em></li>"
    keyword = f'<span id="keyword">{e(s["keyword"])}</span>' if s["keyword"] else '<span id="keyword"></span>'
    stock = ("in", "In stock") if s["in_stock"] else ("out", "Out of stock")
    tag = f"Sandbox <strong>{e(sandbox)}</strong> &middot; owned by one test" if sandbox else \
        "QA test page &middot; not a real store"
    table = f"""

    <section class="card" id="table">
      <h2>Products</h2>
{table_html(s["table"])}
    </section>""" if sandbox else ""
    counter = "Sandbox change" if sandbox else "Change"
    body = f"""  <header>
    <p class="tag">{tag}</p>
    <h1 id="headline">{e(s['headline'])}</h1>
    <p id="announcement">{e(s['announcement'])}</p>
    <p class="keyword-slot">Keyword: {keyword}</p>
  </header>

  <main>
    <section class="card" id="product">
      <h2>Test Widget</h2>
      <img id="product-image" src="{root}images/widget-{e(s['image'])}.svg" alt="Product image" width="240" height="160">
      <p class="price">$<span id="price">{e(s['price'])}</span></p>
      <p id="stock" class="stock {stock[0]}">{stock[1]}</p>
      <p>Quantity available: <span id="quantity">{int(s['quantity'])}</span></p>
      <p>Discount: <span id="percent">{e(s['percent'])}</span>%</p>
    </section>

    <section class="card" id="news">
      <h2>Latest news</h2>
      <ul id="news-list">
{news}
      </ul>
    </section>{table}
  </main>

  <footer>
    <p>{counter} #<span id="change-number">{int(s['change_number'])}</span>
       &middot; Last updated <time id="last-updated">{e(s['last_updated'] or 'never')}</time>
       &middot; Theme: <span id="theme">{e(s['theme'])}</span></p>
  </footer>"""
    return layout(f"Sandbox {sandbox}" if sandbox else "Home", root, body, theme=s["theme"])


def page_products(s):
    body = f"""  <main>
    <h1>Products</h1>
{table_html(s["table"])}
  </main>"""
    return layout("Products", "../", body, theme=s["theme"])


def page_blog_index(s):
    items = "\n".join(
        f'      <li><a href="post-{i + 1}/">{e(p["title"])}</a></li>' for i, p in enumerate(s["blog_posts"])
    ) or "      <li><em>No posts yet.</em></li>"
    body = f"""  <main>
    <h1>Blog</h1>
    <ul id="post-list">
{items}
    </ul>
  </main>"""
    return layout("Blog", "../", body, theme=s["theme"])


def page_blog_post(s, i):
    p = s["blog_posts"][i]
    body = f"""  <main>
    <article id="post-{i + 1}">
      <h1>{e(p['title'])}</h1>
      <p id="post-body">{e(p['body'])}</p>
      <p><a href="../">Back to the blog</a></p>
    </article>
  </main>"""
    return layout(p["title"], "../../", body, theme=s["theme"])


def page_js():
    body = """  <main>
    <h1>JavaScript page</h1>
    <p class="note">Everything below is rendered by <code>app.js</code> from <code>data.json</code>. With JavaScript off, this page is nearly empty.
      Add <code>?autoplay=1</code> to make the carousel move by itself, <code>?popup=0</code> to skip the pop-up, or <code>?cookies=0</code> to skip the cookie banner.</p>

    <section class="card">
      <h2>Rendered message</h2>
      <p id="js-message">Loading&hellip;</p>
      <p id="delayed" hidden></p>
    </section>

    <section class="card">
      <h2>Carousel</h2>
      <div id="carousel" class="carousel">
        <div id="slides"></div>
        <button type="button" id="prev">&larr; Prev</button>
        <button type="button" id="next">Next &rarr;</button>
      </div>
    </section>

    <section class="card">
      <h2>Search and load more</h2>
      <label for="search">Filter items</label>
      <input id="search" type="search" autocomplete="off" placeholder="Type to filter">
      <ul id="item-list"></ul>
      <button type="button" id="load-more">Load more</button>
    </section>

    <section class="card">
      <h2>Fake login (for Actions tests)</h2>
      <p class="note">Nothing you type is stored or sent anywhere. Never enter a real password.</p>
      <form id="login-form" autocomplete="off">
        <label for="username">Username</label>
        <input id="username" name="username" autocomplete="off">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="off">
        <button type="submit">Log in</button>
      </form>
      <div id="members" hidden>
        <p id="welcome"></p>
        <p>Members-only content: the secret test word is <strong>pineapple</strong>.</p>
      </div>
    </section>
  </main>

  <div id="popup" class="popup" hidden role="dialog" aria-modal="true" aria-labelledby="popup-title">
    <div class="popup-box">
      <h2 id="popup-title">Join our newsletter!</h2>
      <p>This pop-up appears 2 seconds after load so you can test pop-up removal.</p>
      <button type="button" id="popup-close">Close</button>
    </div>
  </div>

  <div id="cookie-banner" class="cookie-banner" hidden>
    <p>We use cookies (not really). This banner shows on every load.</p>
    <button type="button" id="cookie-accept">Accept</button>
    <button type="button" id="cookie-reject">Reject</button>
  </div>"""
    return layout("JS page", "../", body, csp=JS_CSP, script="app.js")


def js_data(s):
    return json.dumps({
        "message": s["js_message"],
        "delayed": "This text appeared 5 seconds after load.",
        "slides": ["Slide 1: Spring collection", "Slide 2: Summer collection", "Slide 3: Autumn collection"],
        "items": [f"Item {n}" for n in range(1, 13)],
    }, indent=2) + "\n"


def page_long(s):
    sections = "\n".join(
        f'    <section class="card" id="section-{n}"><h2>Section {n}</h2>'
        f"<p>This is filler paragraph {n} on a deliberately long page, used to test full-page "
        f"screenshots and scrolling. Nothing in this section changes.</p></section>"
        for n in range(1, 61)
    )
    body = f"""  <main>
    <h1>Long page</h1>
    <p>Scroll to the bottom. Only the last line changes, using <code>long-note</code>.</p>
{sections}
    <section class="card"><h2>Bottom of the page</h2><p id="long-note">{e(s['long_note'])}</p></section>
  </main>"""
    return layout("Long page", "../", body, theme=s["theme"])


def page_redirect():
    # Pages has no server-side redirects, so this uses a meta refresh.
    body = """  <main>
    <h1>Redirecting&hellip;</h1>
    <p>This page sends you to <a href="../products/">Products</a> immediately (meta refresh).</p>
  </main>"""
    return layout("Redirect", "../", body,
                  extra_head='\n  <meta http-equiv="refresh" content="0; url=../products/">')


def page_404():
    body = f"""  <main>
    <h1 id="not-found">404: Page not found</h1>
    <p>This is the test site's custom 404 page. GitHub Pages returns it with a real 404 status.</p>
    <p><a href="{BASE_PATH}">Back to the home page</a></p>
  </main>"""
    # Served for any missing path at any depth, so links use the absolute site path.
    return layout("Not found", BASE_PATH, body)


def sitemap_paths(s):
    # Sandboxes are deliberately left out so creating one never changes what a crawl sees.
    paths = ["", "products/", "blog/", "js/", "long/", "files/report.pdf"]
    return paths + [f"blog/post-{i + 1}/" for i in range(len(s["blog_posts"]))]


def sitemap(s):
    urls = "\n".join(
        f"  <url><loc>{xml_escape(BASE_URL + p)}</loc><lastmod>{xml_escape(s['lastmod'][p])}</lastmod></url>"
        for p in sitemap_paths(s)
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n")


def pdf_escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(s):
    """A minimal one-page PDF written by hand (no dependencies)."""
    lines = [
        ("18", "Visualping QA Test Report"),
        ("12", f"PDF version {int(s['pdf_version'])}"),
        ("12", s["pdf_text"]),
    ]
    parts = ["BT", "72 720 Td"]
    for n, (size, text) in enumerate(lines):
        if n:
            parts.append("0 -28 Td")
        parts.append(f"/F1 {size} Tf ({pdf_escape(text)}) Tj")
    parts.append("ET")
    stream = "\n".join(parts)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode("latin-1")
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode("latin-1")
    return bytes(out)


SANDBOX_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def render_all(s):
    """Every generated file except sitemap.xml, as {path under docs/: bytes}."""
    files = {
        "index.html": page_home(s),
        "products/index.html": page_products(s),
        "blog/index.html": page_blog_index(s),
        "js/index.html": page_js(),
        "js/data.json": js_data(s),
        "long/index.html": page_long(s),
        "redirect/index.html": page_redirect(),
        "404.html": page_404(),
        "files/report.pdf": make_pdf(s),
    }
    for i in range(len(s["blog_posts"])):
        files[f"blog/post-{i + 1}/index.html"] = page_blog_post(s, i)
    for name, sb in s["sandboxes"].items():
        if SANDBOX_NAME.fullmatch(name):  # names are validated on creation; this is a second check
            files[f"t/{name}/index.html"] = page_home(sb, root="../../", sandbox=name)
    for name, svg in SVGS.items():
        files[f"images/widget-{name}.svg"] = svg + "\n"
    return {k: v if isinstance(v, bytes) else v.encode("utf-8") for k, v in files.items()}


def sitemap_path_for(rel):
    """Which sitemap entry a generated file belongs to, if any."""
    if rel == "js/data.json":
        return "js/"
    if rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("index.html")]
    return rel


def remove_stale_dirs(parent, pattern, keep):
    """Delete child folders of docs/<parent> whose names match pattern and aren't in keep."""
    folder = DOCS / parent
    if not folder.is_dir():
        return
    for child in folder.iterdir():
        if (child.is_dir() and not child.is_symlink() and re.fullmatch(pattern, child.name)
                and child.name not in keep):
            shutil.rmtree(child)


def build(s, now):
    """Write docs/. Updates s['lastmod'] for every sitemap page whose content changed."""
    files = render_all(s)
    lastmod = s.setdefault("lastmod", {})
    for rel, data in files.items():
        path = DOCS / rel
        if not path.exists() or path.read_bytes() != data:
            lastmod[sitemap_path_for(rel)] = now
    wanted = sitemap_paths(s)
    s["lastmod"] = {p: lastmod.get(p, now) for p in wanted}
    files["sitemap.xml"] = sitemap(s).encode("utf-8")

    for rel, data in files.items():
        path = DOCS / rel
        if path.exists() and path.read_bytes() == data:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    remove_stale_dirs("blog", r"post-\d+", {f"post-{i + 1}" for i in range(len(s["blog_posts"]))})
    remove_stale_dirs("t", SANDBOX_NAME.pattern, set(s["sandboxes"]))
