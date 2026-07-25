"""Raw source-result caching shared by all adapters.

Adapters never call `save` themselves: the pipeline commits caches only after
the dataset write succeeds, so a run that dies mid-write cannot leave a cache
falsely claiming the output is current.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("cache")


def load(cache_path: Path) -> Optional[dict]:
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("cache file %s is unreadable or corrupt; ignoring it", cache_path)
        return None


def save(cache_path: Path, raw: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, sort_keys=True)
    os.replace(tmp_path, cache_path)


def canonicalize(raw: dict) -> dict:
    """Sort each query's binding rows into a stable order so that comparing two
    raw results is insensitive to an endpoint's nondeterministic row order."""
    return {
        key: sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
        for key, rows in raw.items()
    }
