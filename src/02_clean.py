"""Clean raw Google Play reviews into a compact JSONL dataset.

Required cleaning steps implemented:
- remove duplicates
- remove empty entries
- remove extremely short reviews
- remove punctuation
- remove special characters and emojis
- convert numbers to text
- remove extra whitespace
- convert to lowercase
- remove stop words
- lemmatize

Input:  data/reviews_raw.jsonl
Output: data/reviews_clean.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/reviews_raw.jsonl")
DEFAULT_OUTPUT = Path("data/reviews_clean.jsonl")
DEFAULT_MIN_WORDS = 4

STOP_WORDS = {
    "the",
    "and",
    "is",
    "in",
    "it",
    "of",
    "to",
    "a",
    "for",
    "on",
    "this",
    "that",
    "was",
    "with",
    "as",
    "but",
    "are",
    "be",
    "have",
    "you",
    "i",
    "they",
    "my",
    "me",
    "we",
    "our",
    "your",
    "so",
    "if",
    "at",
    "by",
    "an",
    "or",
    "one",
    "from",
    "had",
    "more",
    "many",
    "those",
    "who",
}

NUM_TO_WORD = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

CONTRACTIONS = {
    "can't": "cannot",
    "won't": "will not",
    "don't": "do not",
    "didn't": "did not",
    "doesn't": "does not",
    "it's": "it is",
    "you're": "you are",
    "i'm": "i am",
    "i've": "i have",
    "i'll": "i will",
    "i'd": "i would",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean review dataset.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    return parser.parse_args()


def convert_numbers(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return " ".join(NUM_TO_WORD.get(char, char) for char in match.group(0))

    return re.sub(r"\d+", repl, text)


def expand_contractions(text: str) -> str:
    for short, expanded in CONTRACTIONS.items():
        text = re.sub(rf"\b{re.escape(short)}\b", expanded, text, flags=re.IGNORECASE)
    text = re.sub(r"(\w+)'re\b", r"\1 are", text)
    text = re.sub(r"(\w+)'ve\b", r"\1 have", text)
    text = re.sub(r"(\w+)'ll\b", r"\1 will", text)
    text = re.sub(r"(\w+)'d\b", r"\1 would", text)
    text = re.sub(r"(\w+)n't\b", r"\1 not", text)
    text = re.sub(r"(\w+)'m\b", r"\1 am", text)
    text = re.sub(r"(\w+)'s\b", r"\1 is", text)
    return text


def lemmatize_token(token: str) -> str:
    irregular = {
        "made": "make",
        "easing": "ease",
        "doing": "do",
    }
    if token in irregular:
        return irregular[token]

    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        base = token[:-3]
        # Handle doubled consonants: running -> run, suffering -> suffer.
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        elif base.endswith(("at", "it", "iz")):
            # donating -> donate, inviting -> invite
            base = base + "e"
        # Keep simple stems to avoid errors like "breaking" -> "breake".
        return base
    if token.endswith("ed") and len(token) > 4:
        base = token[:-2]
        if base.endswith("i"):
            base = base[:-1] + "y"
        elif base.endswith(("at", "it", "iz")):
            # donated -> donate, invited -> invite
            base = base + "e"
        return base
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token


def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"http\S+", " ", text)  # remove URLs
    text = expand_contractions(text)
    text = convert_numbers(text)
    text = re.sub(r"[^a-z\s]", " ", text)  # remove punctuation/symbols/emojis
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    tokens = [tok for tok in text.split() if tok not in STOP_WORDS]
    lemmas = [lemmatize_token(tok) for tok in tokens]
    lemmas = [tok for tok in lemmas if tok and tok not in STOP_WORDS]
    # Remove immediate repeated tokens (e.g., "lot lot").
    deduped: list[str] = []
    for tok in lemmas:
        if not deduped or deduped[-1] != tok:
            deduped.append(tok)
    return " ".join(deduped)


def select_text(row: dict[str, Any]) -> str:
    for key in ("content", "review", "text", "body"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def clean_rows(rows: list[dict[str, Any]], min_words: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    for row in rows:
        cleaned_text = clean_text(select_text(row))

        if not cleaned_text:
            continue
        if len(cleaned_text.split()) < min_words:
            continue
        if cleaned_text in seen:
            continue

        seen.add(cleaned_text)
        cleaned.append(
            {
                "reviewId": row.get("reviewId") or row.get("review_id"),
                "content": cleaned_text,
                "score": row.get("score", 0),
            }
        )

    return cleaned


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    raw_rows = read_jsonl(args.input)
    cleaned_rows = clean_rows(raw_rows, min_words=args.min_words)
    write_jsonl(args.output, cleaned_rows)
    print(f"Loaded {len(raw_rows)} raw rows from {args.input}")
    print(f"Saved {len(cleaned_rows)} cleaned rows to {args.output}")


if __name__ == "__main__":
    main()