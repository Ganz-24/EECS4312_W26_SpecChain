"""Generate structured system requirements from automated personas.

Input:
- personas/personas_auto.json

Output:
- spec/spec_auto.md

Each requirement includes:
- unique requirement ID
- description
- source persona
- traceability to review group
- acceptance criteria
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

DEFAULT_INPUT = Path("personas/personas_auto.json")
DEFAULT_OUTPUT = Path("spec/spec_auto.md")
DEFAULT_MIN_REQS_PER_PERSONA = 1

SYSTEM_PROMPT = (
    "You are a senior requirements engineer. "
    "Generate structured, testable functional requirements from personas. The requirements should be clear, avoid ambiguous wording, not be misinterpretable "
    "Output JSON only."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate automated spec from personas.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-reqs-per-persona", type=int, default=DEFAULT_MIN_REQS_PER_PERSONA)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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


def build_prompt(personas: list[dict[str, Any]], min_reqs_per_persona: int) -> str:
    compact_personas = []
    for persona in personas:
        compact_personas.append(
            {
                "id": persona.get("id"),
                "name": persona.get("name"),
                "description": persona.get("description"),
                "derived_from_group": persona.get("derived_from_group"),
                "goals": persona.get("goals", []),
                "pain_points": persona.get("pain_points", []),
                "context": persona.get("context", []),
                "constraints": persona.get("constraints", []),
                "evidence_reviews": persona.get("evidence_reviews", []),
            }
        )

    instructions = textwrap.dedent(
        f"""
        Generate functional requirements from the personas.

        Requirements:
        1) Generate at least {min_reqs_per_persona} requirement(s) per persona.
        2) Each requirement must include:
           - requirement_id (unique, format: FR_auto_1, FR_auto_2, ...)
           - description (clear system behavior)
           - source_persona (persona name)
           - traceability (must mention the persona's group id)
           - acceptance_criteria (Given/When/Then style)
        3) Keep requirements testable and implementation-agnostic.
        4) Requirements must be specific, contain no amibguity, no vague descriptor words and must be interpertable in only one way

        Return JSON only in this shape:
        {{
          "requirements": [
            {{
              "requirement_id": "FR_auto_1",
              "description": "...",
              "source_persona": "...",
              "traceability": "Derived from review group G1",
              "acceptance_criteria": "Given ... When ... Then ..."
            }}
          ]
        }}
        """
    ).strip()

    return f"{instructions}\n\nPersonas:\n{json.dumps(compact_personas, ensure_ascii=False)}"


def validate_requirements(requirements: list[dict[str, Any]], personas: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not requirements:
        raise RuntimeError("No requirements generated.")

    persona_names = {str(p.get("name")) for p in personas}
    group_ids = {str(p.get("derived_from_group")) for p in personas}

    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for i, req in enumerate(requirements, start=1):
        req_id = str(req.get("requirement_id") or f"FR_auto_{i}")
        if req_id in seen_ids:
            req_id = f"FR_auto_{i}"
        seen_ids.add(req_id)

        source_persona = str(req.get("source_persona") or "")
        if source_persona not in persona_names:
            source_persona = next(iter(persona_names))

        traceability = str(req.get("traceability") or "")
        if not any(gid in traceability for gid in group_ids):
            # Try to infer from matching persona.
            matched = next((p for p in personas if str(p.get("name")) == source_persona), None)
            gid = str(matched.get("derived_from_group")) if matched else "UNKNOWN"
            traceability = f"Derived from review group {gid}"

        normalized.append(
            {
                "requirement_id": req_id,
                "description": str(req.get("description") or "").strip(),
                "source_persona": source_persona,
                "traceability": traceability.strip(),
                "acceptance_criteria": str(req.get("acceptance_criteria") or "").strip(),
            }
        )

    return normalized


def render_markdown(requirements: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for req in requirements:
        blocks.append(
            "\n".join(
                [
                    f"# Requirement ID: {req['requirement_id']}",
                    f"- Description: [{req['description']}]",
                    f"- Source Persona: [{req['source_persona']}]",
                    f"- Traceability: [{req['traceability']}]",
                    f"- Acceptance Criteria: [{req['acceptance_criteria']}]",
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY environment variable.")

    payload = read_json(args.input)
    personas = payload.get("personas", [])
    if not isinstance(personas, list) or not personas:
        raise RuntimeError(f"No personas found in {args.input}")

    user_prompt = build_prompt(personas, args.min_reqs_per_persona)
    raw_output = call_groq(SYSTEM_PROMPT, user_prompt, api_key)

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned non-JSON output: {raw_output}") from exc

    requirements = validate_requirements(parsed.get("requirements", []), personas)
    markdown = render_markdown(requirements)
    write_text(args.output, markdown)

    print(f"Loaded {len(personas)} personas from {args.input}")
    print(f"Generated {len(requirements)} requirements")
    print(f"Saved specification to {args.output}")


if __name__ == "__main__":
    main()