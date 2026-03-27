"""Collect raw Google Play reviews for Medito.

This script collects between 1,000 and 5,000 reviews for:
https://play.google.com/store/apps/details?id=meditofoundation.medito

Output:
- data/reviews_raw.jsonl

Usage:
    python src/01_collect_or_import.py
    python src/01_collect_or_import.py --count 1500 --output data/reviews_raw.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

APP_ID = "meditofoundation.medito"
MIN_COUNT = 1000
MAX_COUNT = 5000
DEFAULT_COUNT = 1200
DEFAULT_OUTPUT = Path("data/reviews_raw.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Medito reviews from Google Play using google-play-scraper.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Target number of reviews to collect ({MIN_COUNT}-{MAX_COUNT}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSONL output path.",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="ISO language code (default: en).",
    )
    parser.add_argument(
        "--country",
        default="us",
        help="ISO country code (default: us).",
    )
    return parser.parse_args()


def _load_scraper() -> tuple[Any, Any]:
    try:
        from google_play_scraper import Sort, reviews_all
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency 'google-play-scraper'. Install with: pip install google-play-scraper"
        ) from exc

    return Sort, reviews_all


def collect_reviews(count: int, lang: str, country: str) -> list[dict[str, Any]]:
    if not (MIN_COUNT <= count <= MAX_COUNT):
        raise ValueError(f"count must be between {MIN_COUNT} and {MAX_COUNT}.")

    Sort, reviews_all = _load_scraper()

    # reviews_all returns all pages. We slice to requested range.
    rows = reviews_all(
        APP_ID,
        sleep_milliseconds=0,
        lang=lang,
        country=country,
        sort=Sort.NEWEST,
    )

    if len(rows) < MIN_COUNT:
        raise RuntimeError(
            f"Collected only {len(rows)} reviews for {APP_ID}; need at least {MIN_COUNT}."
        )

    return rows[:count]


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)

    # Convert datetime objects to ISO8601 strings for JSONL serialization.
    for dt_key in ("at", "repliedAt"):
        value = normalized.get(dt_key)
        if value is not None and hasattr(value, "isoformat"):
            normalized[dt_key] = value.isoformat()

    normalized["app_id"] = APP_ID
    normalized["source"] = "google_play_scraper"
    return normalized


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(normalize_row(row), ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    rows = collect_reviews(args.count, args.lang, args.country)
    write_jsonl(args.output, rows)
    print(
        f"Collected {len(rows)} reviews for '{APP_ID}' and saved dataset to '{args.output}'."
    )


if __name__ == "__main__":
    main()