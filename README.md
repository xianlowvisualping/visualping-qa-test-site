# Visualping QA test site

A small static site that Visualping can monitor, plus commands that change it on demand so you can trigger an alert whenever a test needs one.

Live site: https://xianlowvisualping.github.io/visualping-qa-test-site/

## Pages

| Path | What it's for |
| --- | --- |
| `/` | Home page: headline, keyword slot, price, stock, quantity, percent, image, news list, change counter |
| `/products/` | A table, for table-diff and price-condition tests |
| `/blog/`, `/blog/post-1/`, `/blog/post-2/` | Linked subpages for Full Website Import. `blog-add` creates more posts |
| `/sitemap.xml` | Lists every page, including new blog posts |
| `/js/` | JavaScript-rendered content: delayed text (5 s), carousel, Load more, search box, fake login, pop-up (2 s), cookie banner |
| `/long/` | 60 sections. Only the last line changes, for full-page screenshot and scroll tests |
| `/redirect/` | Meta-refresh redirect to `/products/` |
| `/files/report.pdf` | A PDF that changes only with the `pdf` command |
| any missing path | Custom 404 page, served with a real 404 status |

Each page changes only when its own content changes. **The exception is the home page footer** ("Change #N · Last updated"), which updates on every change. To test that a monitor ignores unrelated changes, scope it to one element (for example `#price`), then run `touch`.

Pages also gives two real HTTP behaviours for free. A folder path without a trailing slash, such as `/products`, returns a **301** to `/products/`. A removed blog post returns a **404**. A 5xx error isn't possible on GitHub Pages.

Out of scope: a real login. The `/js/` page has a fake login form for Actions tests. It stores and sends nothing, so never type a real password into it.

## Making a change

### Option A: GitHub Actions (no credentials needed)

On GitHub, go to **Actions → Change test site → Run workflow**, pick a command and enter its value or values. You can also run it from a terminal:

```bash
gh workflow run change-site.yml -R xianlowvisualping/visualping-qa-test-site -f command=price -f value=24.99
```

The workflow commits with the built-in `GITHUB_TOKEN`. By default it then **waits until the live page shows the new change number**. GitHub Pages caches pages for up to 10 minutes, so the run often takes 5–12 minutes. Wait until the run shows green before you click **Check now** in Visualping.

### Option B: from this folder

```bash
python3 change.py price 24.99 --publish
```

`--publish` runs `git pull --rebase` before and after the change, so it won't clash with workflow runs. This option doesn't wait for the cache, so wait about 10 minutes before you click Check now.

## Commands

| Command | Values | What changes |
| --- | --- | --- |
| `touch` | | Only the home page change number and time |
| `random` | | One random home page change |
| `reset` | | All default content. The change number still goes up, so this alerts too |
| `headline` | TEXT | `#headline` |
| `announcement` | TEXT | `#announcement` |
| `keyword-add` | WORD | `#keyword` (one word: letters, numbers, hyphens) |
| `keyword-remove` | | Empties `#keyword` |
| `price` | AMOUNT | `#price` |
| `stock` | `in` / `out` | `#stock` text and colour |
| `quantity` | N (0–999999) | `#quantity` |
| `percent` | N (0–100) | `#percent` |
| `image` | `a` / `b` / `c` | `#product-image` (the image changes, the text doesn't) |
| `theme` | `blue` / `green` / `red` / `purple` | Colours only |
| `news-add` | TEXT | Adds a `#news-list` item. Only the newest 10 are kept |
| `news-remove` | | Removes the newest news item |
| `table-add` | NAME PRICE | Adds a row to `/products/` (20 rows at most) |
| `table-remove` | | Removes the last row |
| `table-price` | ROW PRICE | Changes one row's price |
| `blog-add` | TITLE | New page `/blog/post-N/`, plus a link and a sitemap entry (20 posts at most) |
| `blog-remove` | | Removes the last post, which then returns 404 |
| `blog-edit` | N TEXT | Changes a post's body |
| `pdf` | TEXT (plain ASCII) | Rewrites `/files/report.pdf` |
| `js-message` | TEXT | `#js-message` on `/js/` (rendered by JavaScript) |
| `long-note` | TEXT | `#long-note` at the bottom of `/long/` |

Text values are limited to 200 characters. Run `python3 change.py status` to see the current content, and `python3 change.py preview` to view the site at http://127.0.0.1:8000 (only this computer can reach it).

## What is public

Free GitHub Pages needs a public repository, so **everything committed here is public**: the pages, the scripts, the state file and the git history, including commit author names and emails. Your commits use your GitHub no-reply email, and workflow commits use `github-actions[bot]`. Never commit tokens, `.env` files or customer data; `.gitignore` blocks the common ones.

- The workflow uses only the built-in `GITHUB_TOKEN`, which is limited to writing this repo's contents. There's no personal access token anywhere.
- Only people with write access to the repo can run the workflow.
- Static pages allow no scripts at all (`default-src 'none'`). The `/js/` page allows only its own `app.js`, which inserts text with `textContent` and never as HTML.
- Every page sets `noindex`, so search engines don't list it. Visualping still fetches pages normally.
