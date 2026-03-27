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
DEFAULT_PIPELINE = "automated"

AMBIGUOUS_TERMS = {
    "fast",
    "easy",
    "simple",
    "efficient",
    "user-friendly",
    "user friendly",
    "etc",
    "and/or",
    "appropriate",
    "robust",
    "intuitive",
    "seamless",
    "quickly",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute metrics for manual, automated, or hybrid pipeline artifacts."
    )
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--groups", type=Path, default=DEFAULT_GROUPS)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--pipeline",
        type=str,
        default=None,
        choices=["manual", "automated", "hybrid"],
        help="Optional: run only one pipeline. If omitted, all pipelines are computed.",
    )
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


def normalize_text(text: str) -> str:
    text = str(text).strip().lower()
    text = re.sub(r"\([^)]*\)", "", text)  
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_spec_markdown(path: Path) -> list[dict[str, str]]:
    """
    Parse requirements from the markdown spec.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"\n(?=# Requirement ID:)", text) if b.strip()]

    requirements: list[dict[str, str]] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines or not lines[0].startswith("# Requirement ID:"):
            continue

        req_id = lines[0].split(":", 1)[1].strip()
        req = {
            "requirement_id": req_id,
            "description": "",
            "source_persona": "",
            "traceability": "",
            "acceptance_criteria": "",
            "notes": "",
        }

        for line in lines[1:]:
            key, value = parse_spec_line(line)
            if key == "description":
                req["description"] = value
            elif key == "source_persona":
                req["source_persona"] = value
            elif key == "traceability":
                req["traceability"] = value
            elif key == "acceptance_criteria":
                req["acceptance_criteria"] = value
            elif key == "notes":
                req["notes"] = value

        requirements.append(req)

    return requirements


def parse_spec_line(line: str) -> tuple[str, str]:
    mappings = {
        "- Description:": "description",
        "- Source Persona:": "source_persona",
        "- Traceability:": "traceability",
        "- Acceptance Criteria:": "acceptance_criteria",
        "- Notes:": "notes",
    }

    for prefix, field_name in mappings.items():
        if line.startswith(prefix):
            raw_value = line[len(prefix):].strip()
            return field_name, extract_value(raw_value)

    return "", ""


def extract_value(raw_value: str) -> str:
    raw_value = raw_value.strip()
    if raw_value.startswith("[") and raw_value.endswith("]"):
        return raw_value[1:-1].strip()
    return raw_value


def safe_div(numerator: float, denominator: float) -> float:
    return round((numerator / denominator), 4) if denominator else 0.0


def contains_ambiguous_text(text: str) -> bool:
    lower = str(text).lower()
    return any(term in lower for term in AMBIGUOUS_TERMS)


def extract_group_ids_from_traceability(traceability: str, valid_group_ids: set[str]) -> set[str]:
    traceability = str(traceability)
    found: set[str] = set()

    for group_id in valid_group_ids:
        if group_id in traceability:
            found.add(group_id)

    for match in re.findall(r"\bG[A-Za-z0-9]+\b", traceability):
        if match in valid_group_ids:
            found.add(match)

    return found


def compute_metrics(
    reviews: list[dict[str, Any]],
    groups_payload: dict[str, Any],
    personas_payload: dict[str, Any],
    requirements: list[dict[str, str]],
    tests_payload: dict[str, Any],
    pipeline_name: str,
) -> dict[str, Any]:
    group_list = groups_payload.get("groups", []) if isinstance(groups_payload, dict) else []
    personas = personas_payload.get("personas", []) if isinstance(personas_payload, dict) else []
    tests = tests_payload.get("tests", []) if isinstance(tests_payload, dict) else []

    dataset_size = len(reviews)
    persona_count = len(personas)
    requirements_count = len(requirements)
    tests_count = len(tests)

    valid_group_ids = {str(group.get("group_id", "")).strip() for group in group_list if group.get("group_id")}
    valid_req_ids = {str(req.get("requirement_id", "")).strip() for req in requirements if req.get("requirement_id")}

    persona_name_map: dict[str, str] = {}
    for persona in personas:
        name = str(persona.get("name", "")).strip()
        if name:
            persona_name_map[normalize_text(name)] = name

    persona_links = sum(
        1
        for persona in personas
        if str(persona.get("derived_from_group", "")).strip() in valid_group_ids
    )

    req_links = 0
    for req in requirements:
        normalized_source_persona = normalize_text(req.get("source_persona", ""))
        source_persona_valid = normalized_source_persona in persona_name_map
        group_links_found = extract_group_ids_from_traceability(req.get("traceability", ""), valid_group_ids)

        if source_persona_valid and group_links_found:
            req_links += 1

    test_links = sum(
        1
        for test in tests
        if str(test.get("requirement_id", "")).strip() in valid_req_ids
    )

    traceability_links = persona_links + req_links + test_links
    traceability_possible = persona_count + requirements_count + tests_count
    traceability_ratio = safe_div(traceability_links, traceability_possible)

    covered_requirements = {
        str(test.get("requirement_id", "")).strip()
        for test in tests
        if str(test.get("requirement_id", "")).strip() in valid_req_ids
    }
    testability_rate = safe_div(len(covered_requirements), requirements_count)

    ambiguous_count = sum(
        1
        for req in requirements
        if contains_ambiguous_text(req.get("description", ""))
    )
    ambiguity_ratio = safe_div(ambiguous_count, requirements_count)

    evidence_review_ids: set[str] = set()
    for persona in personas:
        for review_id in persona.get("evidence_reviews", []):
            evidence_review_ids.add(str(review_id).strip())

    review_coverage = safe_div(len(evidence_review_ids), dataset_size)

    return {
        "pipeline": pipeline_name,
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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_pipeline(pipeline_name, groups, personas, spec, tests, output):
    reviews = read_jsonl(Path("data/reviews_clean.jsonl"))

    metrics = compute_metrics(
        reviews=reviews,
        groups_payload=read_json(Path(groups)),
        personas_payload=read_json(Path(personas)),
        requirements=parse_spec_markdown(Path(spec)),
        tests_payload=read_json(Path(tests)),
        pipeline_name=pipeline_name,
    )

    write_json(Path(output), metrics)
    print(f"{pipeline_name} metrics saved to {output}")

def build_summary(manual_metrics: dict[str, Any],
                  automated_metrics: dict[str, Any],
                  hybrid_metrics: dict[str, Any]) -> dict[str, Any]:

    keys_to_keep = [
        "dataset_size",
        "persona_count",
        "requirements_count",
        "tests_count",
        "traceability_links",
        "review_coverage",
        "traceability_ratio",
        "testability_rate",
        "ambiguity_ratio",
    ]

    def strip_pipeline(metrics: dict[str, Any]) -> dict[str, Any]:
        return {key: metrics[key] for key in keys_to_keep}

    return {
        "manual": strip_pipeline(manual_metrics),
        "automated": strip_pipeline(automated_metrics),
        "hybrid": strip_pipeline(hybrid_metrics),
    }

def run_pipeline(pipeline_name, groups, personas, spec, tests, output):
    reviews = read_jsonl(Path("data/reviews_clean.jsonl"))

    metrics = compute_metrics(
        reviews=reviews,
        groups_payload=read_json(Path(groups)),
        personas_payload=read_json(Path(personas)),
        requirements=parse_spec_markdown(Path(spec)),
        tests_payload=read_json(Path(tests)),
        pipeline_name=pipeline_name,
    )

    write_json(Path(output), metrics)
    print(f"{pipeline_name} metrics saved to {output}")
    return metrics


def main():
    args = parse_args()

    if args.pipeline is not None:
        run_pipeline(
            args.pipeline,
            args.groups,
            args.personas,
            args.spec,
            args.tests,
            args.output,
        )
        return

    print("No pipeline specified. Running manual, automated, and hybrid pipelines...\n")

    manual_metrics = run_pipeline(
        "manual",
        "data/review_groups_manual.json",
        "personas/personas_manual.json",
        "spec/spec_manual.md",
        "tests/tests_manual.json",
        "metrics/metrics_manual.json",
    )

    automated_metrics = run_pipeline(
        "automated",
        "data/review_groups_auto.json",
        "personas/personas_auto.json",
        "spec/spec_auto.md",
        "tests/tests_auto.json",
        "metrics/metrics_auto.json",
    )

    hybrid_metrics = run_pipeline(
        "hybrid",
        "data/review_groups_hybrid.json",
        "personas/personas_hybrid.json",
        "spec/spec_hybrid.md",
        "tests/tests_hybrid.json",
        "metrics/metrics_hybrid.json",
    )

    summary = build_summary(
        manual_metrics=manual_metrics,
        automated_metrics=automated_metrics,
        hybrid_metrics=hybrid_metrics,
    )
    write_json(Path("metrics/metrics_summary.json"), summary)
    print("summary metrics saved to metrics/metrics_summary.json")

    print("\nAll metrics generated successfully.")


if __name__ == "__main__":
    main()