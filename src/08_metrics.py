"""Compute automated-pipeline metrics from generated artifacts.

Reads:
- data/reviews_clean.jsonl
- data/review_groups_auto.json
- personas/personas_auto.json
- spec/spec_auto.md
- tests/tests_auto.json

Writes:
- metrics/metrics_auto.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_REVIEWS = Path("data/reviews_clean.jsonl")
DEFAULT_GROUPS = Path("data/review_groups_auto.json")
DEFAULT_PERSONAS = Path("personas/personas_auto.json")
DEFAULT_SPEC = Path("spec/spec_auto.md")
DEFAULT_TESTS = Path("tests/tests_auto.json")
DEFAULT_OUTPUT = Path("metrics/metrics_auto.json")

AMBIGUOUS_TERMS = {
    "fast",
    "easy",
    "simple",
    "efficient",
    "user-friendly",
    "etc",
    "and/or",
    "appropriate",
    "robust",
    "intuitive",
    "seamless",
    "quickly",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute metrics for automated pipeline.")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_spec_markdown(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"\n(?=# Requirement ID:)", text) if b.strip()]

    reqs: list[dict[str, str]] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines or not lines[0].startswith("# Requirement ID:"):
            continue

        req_id = lines[0].split(":", 1)[1].strip()
        req = {"requirement_id": req_id, "description": "", "source_persona": "", "traceability": "", "acceptance_criteria": ""}

        for ln in lines[1:]:
            if ln.startswith("- Description:"):
                req["description"] = extract_bracket_value(ln)
            elif ln.startswith("- Source Persona:"):
                req["source_persona"] = extract_bracket_value(ln)
            elif ln.startswith("- Traceability:"):
                req["traceability"] = extract_bracket_value(ln)
            elif ln.startswith("- Acceptance Criteria:"):
                req["acceptance_criteria"] = extract_bracket_value(ln)

        reqs.append(req)

    return reqs


def extract_bracket_value(line: str) -> str:
    match = re.search(r"\[(.*)\]", line)
    return match.group(1).strip() if match else ""


def safe_div(numerator: float, denominator: float) -> float:
    return round((numerator / denominator), 4) if denominator else 0.0


def contains_ambiguous_text(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in AMBIGUOUS_TERMS)


def compute_metrics(
    reviews: list[dict[str, Any]],
    groups: dict[str, Any],
    personas_payload: dict[str, Any],
    requirements: list[dict[str, str]],
    tests_payload: dict[str, Any],
) -> dict[str, Any]:
    group_list = groups.get("groups", []) if isinstance(groups, dict) else []
    personas = personas_payload.get("personas", []) if isinstance(personas_payload, dict) else []
    tests = tests_payload.get("tests", []) if isinstance(tests_payload, dict) else []

    dataset_size = len(reviews)
    persona_count = len(personas)
    requirements_count = len(requirements)
    tests_count = len(tests)

    valid_group_ids = {str(g.get("group_id")) for g in group_list}
    valid_persona_names = {str(p.get("name")) for p in personas}
    valid_req_ids = {str(r.get("requirement_id")) for r in requirements}

    persona_links = sum(1 for p in personas if str(p.get("derived_from_group")) in valid_group_ids)
    req_links = sum(
        1
        for r in requirements
        if str(r.get("source_persona")) in valid_persona_names
        and any(gid in str(r.get("traceability", "")) for gid in valid_group_ids)
    )
    test_links = sum(1 for t in tests if str(t.get("requirement_id")) in valid_req_ids)

    traceability_links = persona_links + req_links + test_links
    traceability_possible = persona_count + requirements_count + tests_count
    traceability_ratio = safe_div(traceability_links, traceability_possible)

    covered_requirements = {str(t.get("requirement_id")) for t in tests if str(t.get("requirement_id")) in valid_req_ids}
    testability_rate = safe_div(len(covered_requirements), requirements_count)

    ambiguous_count = sum(1 for r in requirements if contains_ambiguous_text(str(r.get("description", ""))))
    ambiguity_ratio = safe_div(ambiguous_count, requirements_count)

    evidence_review_ids = set()
    for p in personas:
        for rid in p.get("evidence_reviews", []):
            evidence_review_ids.add(str(rid))
    review_coverage = safe_div(len(evidence_review_ids), dataset_size)

    return {
        "pipeline": "automated",
        "dataset_size": dataset_size,
        "persona_count": persona_count,
        "requirements_count": requirements_count,
        "tests_count": tests_count,
        "traceability_links": traceability_links,
        "review_coverage": review_coverage,
        "traceability_ratio": traceability_ratio,
        "testability_rate": testability_rate,
        "ambiguity_ratio": ambiguity_ratio,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()

    reviews = read_jsonl(args.reviews)
    groups = read_json(args.groups)
    personas = read_json(args.personas)
    requirements = parse_spec_markdown(args.spec)
    tests = read_json(args.tests)

    metrics = compute_metrics(reviews, groups, personas, requirements, tests)
    write_json(args.output, metrics)

    print(f"Computed automated metrics from {args.reviews}, {args.groups}, {args.personas}, {args.spec}, {args.tests}")
    print(f"Saved metrics to {args.output}")


if __name__ == "__main__":
    main()
