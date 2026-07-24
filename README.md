# Royal Navy Ships Dataset

A dataset (and the pipeline that generates it) of Royal Navy sailing-era ships — the
rating classes first-rate through sixth-rate, plus sloops and gun-brigs — sourced live
from [Wikidata](https://www.wikidata.org/).

## Getting the data

- Grab `ships.json` from [GitHub Releases](https://github.com/PeteRichardson/royal_navy_ships_dataset/releases)
  (when published), or
- Regenerate it locally:

  ```
  python3 -m royal_navy_ships.pipeline
  ```

  Requires Python 3 and a network connection (queries Wikidata's public SPARQL
  endpoint). No third-party dependencies.

`ships.json` is gitignored -- it isn't tracked in git history, only published as a
release artifact.

## Data shape

`ships.json` is a JSON array with one object per ship:

- `id` — a stable, dataset-internal identifier (a UUID), independent of any source.
- `external_ids` — identifiers in other systems, e.g. the Wikidata QID.
- `names` — a time-qualified list of names, since ships were frequently renamed or
  rebuilt under a new name.
- `events` — a timeline of significant events (launched, renamed, wrecked, broken up,
  etc.), each optionally dated.
- `guns` — gun count, where Wikidata records it. Sparse and best-effort, not
  authoritative -- absent for many ships and known to undercount even well-documented
  ones (e.g. HMS Victory).
- `rating` — the sailing-ship rating class (`First` .. `Sixth`, `Sloop`, `Gun-brig`).
- `notes` — a short free-text description.

An abbreviated example, HMS *Implacable* (originally the French *Duguay-Trouin*,
captured in 1805, later renamed *Foudroyant*):

```json
{
  "id": "f3b1c9a2-6e4d-4a1b-9c2e-7d5f8a0b1c2d",
  "external_ids": { "wikidata": "Q63218" },
  "names": [
    { "name": "Duguay-Trouin", "start_date": "1800-01-01", "end_date": "1805-11-04" },
    { "name": "HMS Implacable", "start_date": "1805-11-04", "end_date": "1855-01-01" },
    { "name": "HMS Foudroyant", "start_date": "1855-01-01", "end_date": null }
  ],
  "events": [
    { "description": "built", "date": "1800-01-01", "named_as": "Duguay-Trouin" },
    { "description": "captured", "date": "1805-11-04", "named_as": "HMS Implacable" },
    { "description": "renamed", "date": "1855-01-01", "named_as": "HMS Foudroyant" },
    { "description": "scuttled", "date": "1949-12-02", "named_as": null }
  ],
  "guns": "74",
  "rating": "Third",
  "notes": "French Téméraire-class ship of the line, captured by the Royal Navy at Trafalgar."
}
```

(Field values above are illustrative and abbreviated for readability; regenerate the
dataset to see the current, complete records.)

## Background

The dataset holds roughly 2,270 ships as of writing. It was formerly a hand-scraped
CSV built from a single Wikipedia list; that approach was replaced in 2026 by the
live Wikidata pipeline in this repo (see
[issue #3](https://github.com/PeteRichardson/royal_navy_ships_dataset/issues/3)).
