# Visualping QA test site

A tiny static page that Visualping can monitor, plus a script that changes it on demand so you can trigger alerts whenever you need one.

- `docs/` is the website (plain HTML + CSS, no JavaScript, no forms, no server code). GitHub Pages serves this folder for free.
- `site-state.json` holds the current content. `change.py` edits it and rebuilds `docs/index.html`.

## Make a change

```bash
python3 change.py price 24.99 --publish
```

| Command | What changes on the page |
| --- | --- |
| `headline "text"` | Main heading (`#headline`) |
| `announcement "text"` | Line under the heading (`#announcement`) |
| `price 24.99` | Product price (`#price`) |
| `stock in` / `stock out` | Stock badge text and colour (`#stock`) |
| `news-add "text"` | Adds a list item at the top (`#news-list`) |
| `news-remove` | Removes the top list item |
| `theme blue/green/red/purple` | Colours only, no text change (good for visual-compare tests) |
| `random` | One random change from the list above |
| `reset` | Back to the default content |
| `status` | Prints the current content, changes nothing |
| `preview` | Serves the page at http://127.0.0.1:8000 (only this computer can reach it) |

Every change also bumps the footer's change number and "Last updated" time. If you want to test that Visualping ignores a region, monitor just one element (for example `#price`) so the footer doesn't trigger alerts.

Leave off `--publish` to change the page locally without pushing.

## What is public

Free GitHub Pages needs a public repository, so **everything committed here is public**: the page, the script, the state file and the git history (including the commit author name and email). The repo is set to use your GitHub no-reply email so your work email isn't in commit history. Never commit tokens, `.env` files or customer data here; `.gitignore` blocks the common ones.

The page sets `noindex` so search engines don't list it; Visualping still fetches it normally.
