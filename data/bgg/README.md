# BoardGameGeek taxonomy reference

Curated lists pulled from BoardGameGeek, for the generator's idea step to pick real tags from instead of
inventing ad hoc ones (see `Prompts.taxonomy_text()` in `apps/generator/src/gd_generator/prompts.py`).

- `categories.json` — Board Game Categories (e.g. Card Game, Bluffing).
- `mechanics.json` — Board Game Mechanics (e.g. Trick-taking, Set Collection).
- `subdomains.json` — Board Game Subdomains (e.g. Strategy Games, Party Games).
- `families.json` / `families_by_prefix.json` — Board Game Families, grouped by their `Prefix:` (e.g.
  `Mechanism:`, `Category:`, `Theme:`); much larger and noisier, kept for reference rather than prompt use.

Each row: `{id, name, games, url, description}` (`games` = number of BGG items linked to it; sorted by that,
descending). Source and refresh tooling live in `apps/sourcing` (`gd-sourcing`); `data/bgg/raw/` is its
resumable, gitignored scan cache — safe to delete, `sourcing bgg <kind>` rebuilds it from scratch.

Refresh:

```
uv run sourcing bgg properties    # categories + mechanics + subdomains (~6k ids, few minutes)
uv run sourcing bgg families      # families (~120k ids, several hours at a polite rate)
uv run sourcing bgg build         # just re-derive the *.json from an existing raw/ cache
```

`boardgamegeek.com` itself sits behind a Cloudflare challenge; `api.geekdo.com` serves the same data per-id
without one but rate-limits aggressively (watch for sustained 429s — back off for a while, don't hammer it).
