"""Automatically group reviews and generate personas using Groq + Llama 4 Scout.

Inputs:
- data/reviews_clean.jsonl

Outputs:
- data/review_groups_auto.json
- personas/personas_auto.json
- prompts/prompt_auto.json
"""

from __future__ import annotations

import argparse
import json
import os
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_INPUT = Path("data/reviews_clean.jsonl")
DEFAULT_GROUPS_OUTPUT = Path("data/review_groups_auto.json")
DEFAULT_PERSONAS_OUTPUT = Path("personas/personas_auto.json")
DEFAULT_PROMPT_OUTPUT = Path("prompts/prompt_auto.json")
DEFAULT_MAX_REVIEWS = 75
DEFAULT_GROUP_COUNT = 10

GROUP_SYSTEM_PROMPT = (
    "You are a requirements engineering analyst. "
    "Group similar mobile app user reviews into coherent themes. "
    "Output JSON only."
)

PERSONA_SYSTEM_PROMPT = (
    "You are a requirements engineering analyst. "
    "Create structured personas from grouped app reviews. "
    "Output JSON only."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-group reviews and generate personas.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--groups-output", type=Path, default=DEFAULT_GROUPS_OUTPUT)
    parser.add_argument("--personas-output", type=Path, default=DEFAULT_PERSONAS_OUTPUT)
    parser.add_argument("--prompt-output", type=Path, default=DEFAULT_PROMPT_OUTPUT)
    parser.add_argument("--max-reviews", type=int, default=DEFAULT_MAX_REVIEWS)
    parser.add_argument("--target-groups", type=int, default=DEFAULT_GROUP_COUNT)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def call_groq(system_prompt: str, user_prompt: str, api_key: str) -> str:
    body = {
        "model": MODEL_NAME,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    req = urllib.request.Request(
        GROQ_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Python/urllib EECS4312 SpecChain",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq API error ({exc.code}): {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to reach Groq API: {exc}") from exc

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Groq response: {payload}") from exc


def normalize_review_id(row: dict[str, Any]) -> str:
    return str(row.get("reviewId") or row.get("review_id") or "")


def build_group_prompt(reviews: list[dict[str, Any]], target_groups: int) -> str:
    rows = [
        {
            "reviewId": normalize_review_id(r),
            "content": r.get("content", ""),
            "score": r.get("score"),
        }
        for r in reviews
    ]

    instructions = textwrap.dedent(
        f"""
        Group these cleaned app reviews into around {target_groups} meaningful themes.

        Rules:
        1) Use every reviewId exactly once.
        2) Prefer groups with at least 3 related reviews.
        3) Keep theme names concise and requirements-relevant.
        4) Include 2 representative example_reviews for each group.

        Return valid JSON only:
        {{
          "groups": [
            {{
              "group_id": "G1",
              "theme": "short theme",
              "review_ids": ["..."],
              "example_reviews": ["...", "..."]
            }}
          ]
        }}
        """
    ).strip()

    return f"{instructions}\n\nReviews:\n{json.dumps(rows, ensure_ascii=False)}"


def repair_and_validate_groups(groups: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected_ids = {normalize_review_id(r) for r in reviews if normalize_review_id(r)}

    cleaned_groups: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, group in enumerate(groups, start=1):
        group_id = str(group.get("group_id") or f"G{i}")
        theme = str(group.get("theme") or "miscellaneous feedback").strip()
        examples = group.get("example_reviews") if isinstance(group.get("example_reviews"), list) else []

        review_ids: list[str] = []
        for rid in group.get("review_ids", []):
            sid = str(rid)
            if sid in expected_ids and sid not in seen:
                review_ids.append(sid)
                seen.add(sid)

        if review_ids:
            cleaned_groups.append(
                {
                    "group_id": group_id,
                    "theme": theme,
                    "review_ids": review_ids,
                    "example_reviews": [str(x) for x in examples[:2]],
                }
            )

    missing_ids = sorted(expected_ids - seen)
    if missing_ids:
        if len(missing_ids) >= 3:
            cleaned_groups.append(
                {
                    "group_id": f"G{len(cleaned_groups) + 1}",
                    "theme": "uncategorized residual reviews",
                    "review_ids": missing_ids,
                    "example_reviews": [],
                }
            )
        elif cleaned_groups:
            cleaned_groups[-1]["review_ids"].extend(missing_ids)
        else:
            cleaned_groups.append(
                {
                    "group_id": "G1",
                    "theme": "general feedback",
                    "review_ids": missing_ids,
                    "example_reviews": [],
                }
            )

    if not cleaned_groups:
        raise RuntimeError("No valid groups could be produced.")

    return cleaned_groups


def build_persona_prompt(groups: list[dict[str, Any]], reviews_by_id: dict[str, dict[str, Any]]) -> str:
    compact_groups = []
    for group in groups:
        sample_texts = []
        for rid in group.get("review_ids", [])[:4]:
            review = reviews_by_id.get(str(rid))
            if review:
                sample_texts.append(review.get("content", ""))
        compact_groups.append(
            {
                "group_id": group.get("group_id"),
                "theme": group.get("theme"),
                "review_ids": group.get("review_ids", []),
                "sample_reviews": sample_texts,
            }
        )

    instructions = textwrap.dedent(
        """
        Create one persona per group using this template:
        {
          "id": "P1",
          "name": "...",
          "description": "...",
          "derived_from_group": "G1",
          "goals": ["...", "..."],
          "pain_points": ["...", "..."],
          "context": ["...", "..."],
          "constraints": ["...", "..."],
          "evidence_reviews": ["reviewId1", "reviewId2"]
        }

        Rules:
        - Output valid JSON only as: {"personas": [...]}.
        - Every persona must reference one existing group_id.
        - evidence_reviews must be valid review IDs from that group.
        - Keep statements grounded in the provided reviews.
        """
    ).strip()

    return f"{instructions}\n\nGroups:\n{json.dumps(compact_groups, ensure_ascii=False)}"


def validate_personas(personas: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    group_ids = {str(g.get("group_id")) for g in groups}
    group_to_reviews = {str(g.get("group_id")): {str(x) for x in g.get("review_ids", [])} for g in groups}

    if not personas:
        raise RuntimeError("No personas generated.")

    normalized: list[dict[str, Any]] = []
    for idx, persona in enumerate(personas, start=1):
        derived = str(persona.get("derived_from_group") or "")
        if derived not in group_ids:
            raise RuntimeError(f"Persona references unknown group: {derived}")

        evidence = [str(x) for x in persona.get("evidence_reviews", [])]
        valid_evidence = [rid for rid in evidence if rid in group_to_reviews[derived]]
        if len(valid_evidence) < 1:
            valid_evidence = list(group_to_reviews[derived])[:2]

        normalized.append(
            {
                "id": str(persona.get("id") or f"P{idx}"),
                "name": str(persona.get("name") or f"Persona {idx}"),
                "description": str(persona.get("description") or ""),
                "derived_from_group": derived,
                "goals": [str(x) for x in persona.get("goals", [])][:5],
                "pain_points": [str(x) for x in persona.get("pain_points", [])][:5],
                "context": [str(x) for x in persona.get("context", [])][:5],
                "constraints": [str(x) for x in persona.get("constraints", [])][:5],
                "evidence_reviews": valid_evidence[:2],
            }
        )

    return normalized


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY environment variable.")

    raw_reviews = read_jsonl(args.input)
    if not raw_reviews:
        raise RuntimeError(f"No reviews found in {args.input}")

    reviews = raw_reviews[: args.max_reviews]
    review_by_id = {normalize_review_id(r): r for r in reviews if normalize_review_id(r)}

    # Step 4.1: Review grouping
    grouping_prompt = build_group_prompt(reviews, args.target_groups)
    groups_raw_text = call_groq(GROUP_SYSTEM_PROMPT, grouping_prompt, api_key)
    groups_payload = json.loads(groups_raw_text)
    groups = repair_and_validate_groups(groups_payload.get("groups", []), reviews)

    # Step 4.2: Persona generation
    persona_prompt = build_persona_prompt(groups, review_by_id)
    personas_raw_text = call_groq(PERSONA_SYSTEM_PROMPT, persona_prompt, api_key)
    personas_payload = json.loads(personas_raw_text)
    personas = validate_personas(personas_payload.get("personas", []), groups)

    write_json(args.groups_output, {"groups": groups})
    write_json(args.personas_output, {"personas": personas})
    write_json(
        args.prompt_output,
        {
            "model": MODEL_NAME,
            "grouping": {
                "system_prompt": GROUP_SYSTEM_PROMPT,
                "user_prompt": grouping_prompt,
            },
            "persona_generation": {
                "system_prompt": PERSONA_SYSTEM_PROMPT,
                "user_prompt": persona_prompt,
            },
            "max_reviews": args.max_reviews,
            "target_groups": args.target_groups,
        },
    )

    print(f"Loaded {len(raw_reviews)} cleaned reviews from {args.input}")
    print(f"Grouped {len(reviews)} reviews into {len(groups)} themes -> {args.groups_output}")
    print(f"Generated {len(personas)} personas -> {args.personas_output}")
    print(f"Saved prompts -> {args.prompt_output}")


if __name__ == "__main__":
    main()