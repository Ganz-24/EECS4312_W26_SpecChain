"""Generate validation tests from automated specification markdown.

Input:
- spec/spec_auto.md

Output:
- tests/tests_auto.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("spec/spec_auto.md")
DEFAULT_OUTPUT = Path("tests/tests_auto.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate validation tests from spec_auto.md")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    return path.read_text(encoding="utf-8")


def _extract_bracket_value(line: str) -> str:
    match = re.search(r"\[(.*)\]", line)
    return match.group(1).strip() if match else ""


def parse_requirements(markdown: str) -> list[dict[str, str]]:
    blocks = [b.strip() for b in re.split(r"\n(?=# Requirement ID:)", markdown) if b.strip()]
    requirements: list[dict[str, str]] = []

    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines or not lines[0].startswith("# Requirement ID:"):
            continue

        req_id = lines[0].split(":", 1)[1].strip()
        record = {
            "requirement_id": req_id,
            "description": "",
            "source_persona": "",
            "traceability": "",
            "acceptance_criteria": "",
        }

        for line in lines[1:]:
            if line.startswith("- Description:"):
                record["description"] = _extract_bracket_value(line)
            elif line.startswith("- Source Persona:"):
                record["source_persona"] = _extract_bracket_value(line)
            elif line.startswith("- Traceability:"):
                record["traceability"] = _extract_bracket_value(line)
            elif line.startswith("- Acceptance Criteria:"):
                record["acceptance_criteria"] = _extract_bracket_value(line)

        requirements.append(record)

    if not requirements:
        raise RuntimeError("No requirements found in spec markdown.")

    return requirements


def split_gwt(acceptance_criteria: str) -> tuple[str, str, str]:
    """Extract Given/When/Then clauses from free-text acceptance criteria."""

    given_match = re.search(r"given\s+(.*?)(?=\bwhen\b|$)", acceptance_criteria, flags=re.I)
    when_match = re.search(r"when\s+(.*?)(?=\bthen\b|$)", acceptance_criteria, flags=re.I)
    then_match = re.search(r"then\s+(.*)$", acceptance_criteria, flags=re.I)

    given = given_match.group(1).strip(" ,.") if given_match else "the user is in the relevant feature"
    when = when_match.group(1).strip(" ,.") if when_match else "the user performs the required action"
    then = then_match.group(1).strip(" ,.") if then_match else "the system satisfies the requirement"

    return given, when, then


def make_scenario_title(description: str, requirement_id: str) -> str:
    cleaned = description.replace("The system shall", "").strip(" .")
    if not cleaned:
        return f"Validate {requirement_id}"

    words = cleaned.split()
    short = " ".join(words[:10])
    return short[0].upper() + short[1:] if short else f"Validate {requirement_id}"


def build_tests(requirements: list[dict[str, str]]) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []

    for idx, req in enumerate(requirements, start=1):
        given, when, then = split_gwt(req.get("acceptance_criteria", ""))
        tests.append(
            {
                "test_id": f"T_auto_{idx}",
                "requirement_id": req["requirement_id"],
                "scenario": make_scenario_title(req.get("description", ""), req["requirement_id"]),
                "steps": [
                    f"Set up precondition: {given}.",
                    f"Execute action: {when}.",
                    "Observe system behavior and outputs.",
                ],
                "expected_result": then if then.endswith(".") else f"{then}.",
            }
        )

    return tests


def validate_tests(tests: list[dict[str, Any]], requirements: list[dict[str, str]]) -> None:
    if not tests:
        raise RuntimeError("No tests generated.")

    req_ids = {r["requirement_id"] for r in requirements}
    tested_req_ids = {t.get("requirement_id") for t in tests}

    missing = sorted(req_ids - tested_req_ids)
    if missing:
        raise RuntimeError(f"Missing test coverage for requirements: {missing}")

    test_ids = [str(t.get("test_id")) for t in tests]
    if len(set(test_ids)) != len(test_ids):
        raise RuntimeError("Duplicate test_id values detected.")

    for test in tests:
        if not isinstance(test.get("steps"), list) or not test["steps"]:
            raise RuntimeError(f"Invalid steps for test {test.get('test_id')}")
        if not str(test.get("expected_result", "")).strip():
            raise RuntimeError(f"Missing expected_result for test {test.get('test_id')}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    spec_text = read_text(args.input)
    requirements = parse_requirements(spec_text)
    tests = build_tests(requirements)
    validate_tests(tests, requirements)
    write_json(args.output, {"tests": tests})

    print(f"Loaded {len(requirements)} requirements from {args.input}")
    print(f"Generated {len(tests)} tests")
    print(f"Saved tests to {args.output}")


if __name__ == "__main__":
    main()
