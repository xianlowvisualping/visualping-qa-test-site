# Visualping QA test site

A small static site that Visualping can monitor, plus commands that change it on demand so you can trigger an alert whenever a test needs one.

Live site: https://xianlowvisualping.github.io/visualping-qa-test-site/

## Pages

| Path | What it's for |
| --- | --- |
| `/` | Home page: headline, keyword slot, price, stock, quantity, percent, image, news list, change counter |
| `/products/` | A table, for table-diff and price-condition tests |
| `/blog/`, `/blog/post-1/`, `/blog/post-2/` | Linked subpages for Full Website Import. `blog-add` creates more posts |
| `/sitemap.xml` | Lists every shared page, including new blog posts, each with a `<lastmod>` that updates only when that page changes. Sandboxes aren't listed |
| `/js/` | JavaScript-rendered content: delayed text (5 s), carousel, Load more, search box, fake login, pop-up (2 s), cookie banner. Choose the noise with the query string: `?autoplay=1` makes the carousel move every 4 s (it's off by default), `?popup=0` turns the pop-up off, `?cookies=0` turns the banner off, and you can combine them |
| `/t/NAME/` | A **sandbox**: a private copy of the home page plus its own table, owned by one test (see below) |
| `/long/` | 60 sections. Only the last line changes, for full-page screenshot and scroll tests |
| `/redirect/` | Meta-refresh redirect to `/products/` |
| `/files/report.pdf` | A PDF that changes only with the `pdf` command |
| any missing path | Custom 404 page, served with a real 404 status |

Each page changes only when its own content changes. **The exception is the home page footer** ("Change #N · Last updated"), which updates on every change. To test that a monitor ignores unrelated changes, scope it to one element (for example `#price`), then run `touch`.

Pages also gives two real HTTP behaviours for free. A folder path without a trailing slash, such as `/products`, returns a **301** to `/products/`. A removed blog post returns a **404**. A 5xx error isn't possible on GitHub Pages.

Out of scope: a real login. The `/js/` page has a fake login form for Actions tests. It stores and sends nothing, so never type a real password into it.

## Sandboxes: keep tests from affecting each other

Every test shares the home page, `/products/` and the blog, and monitors from earlier weeks keep checking them. A `price` change for one test alerts every old monitor scoped to `#price`. Leftover blog posts and table rows also change what later tests see.

To keep tests independent, give each test its own sandbox:

1. **Setup:** run `sandbox-create price-test-1`, which creates `/t/price-test-1/`. Point the test's monitor at that URL.
2. **Changes:** run with **sandbox** set to `price-test-1` (or `--in price-test-1` locally). Only that page changes, and it has its own `Sandbox change #N` counter.
3. **Cleanup:** run `sandbox-delete price-test-1`. The page then returns 404.

Sandboxes support every home page command plus the `table-*` commands, which act on the sandbox's own table. The blog, PDF, `js-message` and `long-note` are shared by everyone, so they can't be sandboxed. For tests on those, run `reset` in Setup and write down the change number it reports. Names use lowercase letters, numbers and hyphens, and up to 50 sandboxes can exist at once.

## Making a change

### Option A: GitHub Actions (no credentials needed)

On GitHub, go to **Actions → Change test site → Run workflow**. Fill in:

- **commands**: one or more changes, separated by `;`, for example `price 24.99; stock out`. Quote text that has spaces: `headline "Big sale"`. A single run can make up to 20 changes, and they all share one change number and one wait.
- **sandbox**: optional. Fill it in to change only `/t/NAME/`.

You can also start a run from a terminal:

```bash
gh workflow run change-site.yml -R xianlowvisualping/visualping-qa-test-site -f commands="price 24.99; stock out"
```

If any command is invalid, nothing changes and the run fails.

When the run finishes:

- **Run summary:** the run page shows every change with its before and after values, the change number and the commit, for example `price: 19.99 → 24.99`. Copy it into your test notes and match it against the Visualping alert.
- **Waiting for the cache:** GitHub Pages caches every file for up to 10 minutes. That includes `data.json` and the PDF, not only HTML. By default the run **waits until every file it changed is live** at its normal URL, so a run often takes 1–12 minutes.
- **Which colour counts:** **only a green run counts.** Red means the change failed, the cache didn't clear in time, or the run wasn't started by `xianlowvisualping`. Treat red, grey (skipped) or still running as **Blocked**, and don't click Check now.

Pages is served from many cache servers. The run checks the one closest to GitHub's runners, which is usually, but not always, the one Visualping sees. If a check right after a green run still shows the old version, wait a few minutes and check again.

**Run inputs and logs are public.** Use only test values, and never a customer name, URL or email.

### Option B: from this folder

```bash
python3 change.py --publish run "price 24.99; stock out"
```

`--publish` runs `git pull --rebase` before and after the change, so it won't clash with workflow runs. This option doesn't wait for the cache. Either wait about 10 minutes, or run `python3 verify_live.py` after pushing.

## Commands

| Command | Values | What changes |
| --- | --- | --- |
| `touch` | | Only the change number and time (home page, or the sandbox with `--in`) |
| `random` | | One random change |
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
| `table-add` | NAME PRICE | Adds a row to `/products/`, or to the sandbox's table (20 rows at most) |
| `table-remove` | | Removes the last row |
| `table-price` | ROW PRICE | Changes one row's price |
| `blog-add` | TITLE | New page `/blog/post-N/`, plus a link and a sitemap entry (20 posts at most) |
| `blog-remove` | | Removes the last post, which then returns 404 |
| `blog-edit` | N TEXT | Changes a post's body |
| `pdf` | TEXT (plain ASCII) | Rewrites `/files/report.pdf` |
| `js-message` | TEXT | `#js-message` on `/js/` (rendered by JavaScript) |
| `long-note` | TEXT | `#long-note` at the bottom of `/long/` |
| `sandbox-create` | NAME | Creates `/t/NAME/`. Doesn't change any other page |
| `sandbox-delete` | NAME | Deletes `/t/NAME/`, which then returns 404 |

Text values are limited to 200 characters. To make several changes at once, use `run "CMD ARGS; CMD ARGS"`. Run `python3 change.py status` to see the current content, and `python3 change.py preview` to view the site at http://127.0.0.1:8000 (only this computer can reach it).

## Not included

`robots.txt`: search engines and crawlers only read `robots.txt` from the root of the domain (`xianlowvisualping.github.io/robots.txt`). This project site lives under `/visualping-qa-test-site/`, so it can't control that file. Testing it would need a separate repo named `xianlowvisualping.github.io`.

## What is public

Free GitHub Pages needs a public repository, so **everything committed here is public**: the pages, the scripts, the state file and the git history, including commit author names and emails. Your commits use your GitHub no-reply email, and workflow commits use `github-actions[bot]`. Never commit tokens, `.env` files or customer data; `.gitignore` blocks the common ones.

- The workflow uses only the built-in `GITHUB_TOKEN`, which is limited to writing this repo's contents. There's no personal access token anywhere.
- Only people with write access to the repo can run the workflow (today that's only `xianlowvisualping`). The workflow's first step also fails (red) for anyone else, even if collaborators are added later. Anyone can *see* the public run logs, but not start a run. Someone who forks the repo can only change their own copy, never this site.
- Static pages allow no scripts at all (`default-src 'none'`). The `/js/` page allows only its own `app.js`, which inserts text with `textContent` and never as HTML.
- Every page sets `noindex`, so search engines don't list it. Visualping still fetches pages normally.
