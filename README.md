# Royal Navy Ships Dataset

A dataset (and the pipeline that generates it) of Royal Navy sailing-era ships — the
rating classes first-rate through sixth-rate, plus sloops and gun-brigs — sourced live
from [Wikidata](https://www.wikidata.org/) and enriched from
[DBpedia](https://www.dbpedia.org/).

## Getting the data

- Grab `ships.json` from [GitHub Releases](https://github.com/PeteRichardson/royal_navy_ships_dataset/releases)
  (when published), or
- Regenerate it locally:

  ```
  python3 -m royal_navy_ships.pipeline
  ```

  Requires Python 3 and a network connection (queries the public Wikidata and
  DBpedia SPARQL endpoints). No third-party dependencies.

`ships.json` is gitignored -- it isn't tracked in git history, only published as a
release artifact.

Run the tests with:

```
python3 -m unittest discover
```

They use the standard library's `unittest` and hit no network, so they need no
setup beyond a Python 3 checkout.

## Data shape

`ships.json` is a JSON array with one object per ship:

- `id` — a stable, dataset-internal identifier (a UUID), independent of any source.
- `external_ids` — identifiers in other systems, e.g. `{"wikidata": "Q213958",
  "dbpedia": "HMS_Victory"}`.
- `names` — a time-qualified list of names, since ships were frequently renamed or
  rebuilt under a new name.
- `events` — a timeline of significant events (launched, renamed, wrecked, broken up,
  etc.), each optionally dated.
- `rating` — the sailing-ship rating class (`First` .. `Sixth`, `Sloop`, `Gun-brig`).
- `guns` — gun count. Recorded only where a source states a total outright; the
  per-deck breakdown is not summed, because many descriptions span several eras or
  navies and would double-count. Absent for many ships.
- `armament` — the full armament description, usually a per-deck breakdown.
- `tonnage`, `length`, `beam`, `complement`, `sail_plan`, `builder`, `fate` —
  descriptive detail, largely from Wikipedia infoboxes via DBpedia. Present for most
  ships that have a Wikipedia article.
- `notes` — a short free-text description.
- `field_sources` — which source supplied each field above, e.g.
  `{"rating": "wikidata", "tonnage": "dbpedia"}`.
- `conflicts` — values from other sources that disagree with the canonical answer.
  Kept rather than discarded, so you can judge for yourself.

An abbreviated example, HMS *Implacable* (originally the French *Duguay-Trouin*,
captured in 1805, later renamed *Foudroyant*):

```json
{
  "id": "f3b1c9a2-6e4d-4a1b-9c2e-7d5f8a0b1c2d",
  "external_ids": { "wikidata": "Q63218", "dbpedia": "HMS_Implacable_(1805)" },
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
  "armament": "Gun deck: 28 × 32-pounder guns; Upper gun deck: 30 × 18-pounder guns",
  "tonnage": "1885",
  "length": "52.4",
  "complement": "640",
  "sail_plan": "Full-rigged ship",
  "builder": "Rochefort",
  "fate": "Scuttled off Portsmouth, 2 December 1949",
  "rating": "Third",
  "notes": "French Téméraire-class ship of the line, captured by the Royal Navy at Trafalgar.",
  "field_sources": { "rating": "wikidata", "tonnage": "dbpedia", "guns": "dbpedia" },
  "conflicts": {}
}
```

(Field values above are illustrative and abbreviated for readability; regenerate the
dataset to see the current, complete records.)

## Background

The dataset holds roughly 2,100 ships as of writing. It was formerly a hand-scraped
CSV built from a single Wikipedia list; that approach was replaced in 2026 by the
live Wikidata pipeline in this repo (see
[issue #3](https://github.com/PeteRichardson/royal_navy_ships_dataset/issues/3)).

Ships are selected by rating class rather than by a date range, because the rating
system is itself an era boundary. Two classes are exceptions: Wikidata's
`sloop-of-war` and `gun-brig` are not era-bounded, and the same classes cover
20th-century convoy escorts. Those two — and only those two — are additionally
constrained to vessels dated before 1860.

## Sources

| Source | Contributes |
| --- | --- |
| [Wikidata](https://query.wikidata.org) | The ship list itself (rating classes + Royal Navy operator), name histories, and the event timeline |
| [DBpedia](https://dbpedia.org) | Wikipedia infobox detail — armament, tonnage, dimensions, complement, sail plan, builder, fate — joined on the Wikidata QID |

Roughly three quarters of the fleet has an English Wikipedia article and therefore a
DBpedia record; the remainder — mostly small sloops and gun-brigs — carries Wikidata
data only. Where two sources disagree, the canonical field keeps one answer and the
other is preserved in `conflicts`.
