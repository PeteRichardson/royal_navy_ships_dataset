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

- `id` — a stable, dataset-internal identifier (a UUID). Derived from the ship's
  Wikidata QID, so it is the same in every release: you can join across dataset
  versions, and a ship that vanishes from Wikidata and later reappears keeps its
  original id. Renaming or re-rating a ship does not change it.
- `external_ids` — identifiers in other systems, e.g. `{"wikidata": "Q213958",
  "dbpedia": "HMS_Victory"}`.
- `names` — a time-qualified list of names, since ships were frequently renamed or
  rebuilt under a new name. Built only from naming events that carry a date: an
  undated one can't be placed in the sequence, so it is recorded in `notes` instead
  (see below) rather than dropped. A ship with no tagged naming events gets a single
  entry from its current Wikidata label, with no dates.
- `events` — a timeline of significant events (launched, renamed, wrecked, broken up,
  etc.), each optionally dated. Wikidata's coverage thins out sharply towards the end
  of a ship's life: of the 2,017 ships with any dated event, only 35 have a timeline
  that records how the vessel ended, and for 1,573 the last recorded event is simply
  the launch. Don't read the last event as a fate — use `end_reason`, which applies
  that gate for you and falls back to `fate` where the timeline says nothing.
- `rating` — the sailing-ship rating class (`First` .. `Sixth`, `Sloop`, `Gun-brig`).
  A ship reclassified during its career can carry several on Wikidata; the highest
  is recorded, so a vessel tagged both third-rate and gun-brig appears as `Third`.
  The rating is not yet time-qualified, so a reclassification is not visible here —
  check `events` for it.
- `guns` — gun count. Recorded only where a source states a total outright; the
  per-deck breakdown is not summed, because many descriptions span several eras or
  navies and would double-count. Absent for many ships.
- `armament` — the full armament description, usually a per-deck breakdown.
- `tonnage`, `length`, `beam`, `complement`, `sail_plan`, `builder`, `fate` —
  descriptive detail, largely from Wikipedia infoboxes via DBpedia. Present for most
  ships that have a Wikipedia article. `fate` stays the fullest statement of how a
  ship ended — *"Sold for breaking up in 1816"* says more than the bare `end_reason`
  label — and is the field to read when you want the sentence rather than a category.
- `start_year`, `end_year`, `end_reason`, `end_reason_source` — derived, not
  reported by any single source, and always present (`null` where unknown).
  `start_year` is the earliest dated event whatever it is. The other three answer
  *how did this ship end*:
  - `end_reason` is one of seven labels — `ship breaking`, `ship disposal`,
    `shipwrecking`, `sinking`, `destruction`, `scrapping`, `wreck` — so it can be
    grouped on. Present for 906 ships. It is deliberately silent rather than
    guessing: a ship that was captured, hulked, decommissioned or simply *"last
    listed in 1808"* has no `end_reason`, because none of those is an ending.
  - `end_reason_source` says where that answer came from, and the two are not
    equally confident. `"wikidata"` (35 ships) means a dated event from a
    controlled vocabulary. `"dbpedia"` (871 ships) means the leading verb of the
    `fate` sentence was recognised and matched to a label — a good parse of a
    free-text infobox fragment, but a parse. Wikidata wins where both exist.
  - `end_year` comes from the same source as `end_reason`, and is `null` for 21
    ships whose `fate` states an outcome with no date (*"Sold"*). It is not
    cross-checked against `start_year`: one ship, HMS *Camel*, reports an end the
    year before Wikidata says it launched, which is a real disagreement between the
    two sources rather than something to paper over.
- `notes` — a short free-text description. Where Wikidata records a former name with
  no date attached, it is appended here as *"Also recorded as X, with no date given
  for the change"* — the name is real, but its place in `names` would be a guess.
- `field_sources` — which sources concur on each field above, as a list in the order
  they were recorded, e.g. `{"rating": ["wikidata"], "builder": ["wikidata", "dbpedia"]}`.
  More than one entry means the sources agree, not that the value is contested.
- `conflicts` — values from other sources that disagree with the canonical answer.
  Kept rather than discarded, so you can judge for yourself. Each entry carries the
  source that supplied it; see *Which value wins* below for how to read one.

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
  "start_year": 1800,
  "end_year": 1949,
  "end_reason": "destruction",
  "end_reason_source": "dbpedia",
  "rating": "Third",
  "notes": "French Téméraire-class ship of the line, captured by the Royal Navy at Trafalgar.",
  "field_sources": {
    "rating": ["wikidata"],
    "tonnage": ["dbpedia"],
    "guns": ["wikidata", "dbpedia"]
  },
  "conflicts": {}
}
```

(Field values above are illustrative and abbreviated for readability; regenerate the
dataset to see the current, complete records.)

### Which value wins

When two sources supply different values for the same field, the canonical slot goes
to the higher-priority source — currently `wikidata` ahead of `dbpedia`, with
hand-curated entries ahead of both — and the displaced value moves into `conflicts`.
Priority is a declared policy, so the dataset does not depend on the order the
pipeline runs its adapters in.

`conflicts` covers two genuinely different situations, told apart by checking whether
the entry's `source` also appears in `field_sources` for that field:

- **source in `field_sources`** — that source agreed with the canonical value *and*
  offered an additional one. Not a disagreement. This is what a Wikipedia infobox
  listing two builders produces, and it accounts for every conflict entry in the
  current dataset.
- **source not in `field_sources`** — a real cross-source disagreement worth
  adjudicating.

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
data only. Where two sources disagree, the higher-priority one keeps the canonical
field and the other is preserved in `conflicts` — see [Which value wins](#which-value-wins).
