"""Run the automated pipeline end-to-end.

Execution order (automated steps only):
1) Collect/import raw reviews -> data/reviews_raw.jsonl
2) Clean reviews -> data/reviews_clean.jsonl
3) Auto-group reviews + generate personas (LLM) ->
   data/review_groups_auto.json, personas/personas_auto.json, prompts/prompt_auto.json
4) Generate specifications (LLM) -> spec/spec_auto.md
5) Generate validation tests -> tests/tests_auto.json
6) Compute metrics -> metrics/metrics_auto.json

Notes:
- LLM-dependent steps (3, 4) require GROQ_API_KEY.
- If GROQ_API_KEY is missing, those steps are skipped with a warning.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

RAW_PATH = ROOT / "data" / "reviews_raw.jsonl"
CLEAN_PATH = ROOT / "data" / "reviews_clean.jsonl"
GROUPS_PATH = ROOT / "data" / "review_groups_auto.json"
PERSONAS_PATH = ROOT / "personas" / "personas_auto.json"
SPEC_PATH = ROOT / "spec" / "spec_auto.md"
TESTS_PATH = ROOT / "tests" / "tests_auto.json"
METRICS_PATH = ROOT / "metrics" / "metrics_auto.json"


def run_step(label: str, cmd: list[str], *, optional: bool = False) -> bool:
    print(f"\n=== {label} ===")
    print("$", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        if optional:
            print(f"[WARN] Step failed but marked optional: {label}")
            return False
        raise RuntimeError(f"Step failed: {label}")
    return True


def file_has_content(path: Path) -> bool:
    if not path.exists():
        return False
    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    return True
        return False
    return bool(path.read_text(encoding="utf-8").strip())


def ensure_placeholder_json(path: Path, payload: dict) -> None:
    if file_has_content(path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Wrote placeholder artifact: {path.relative_to(ROOT)}")


def main() -> None:
    print("Running automated pipeline from repository root:", ROOT)

    # Stage 1: Collect/import raw reviews.
    # If raw file already has data, we keep it; otherwise try collection (optional).
    if file_has_content(RAW_PATH):
        print(f"[INFO] Using existing raw dataset: {RAW_PATH.relative_to(ROOT)}")
    else:
        run_step(
            "Collect raw reviews",
            [PYTHON, "src/01_collect_or_import.py", "--count", "1000"],
            optional=True,
        )
        if not file_has_content(RAW_PATH):
            print("[WARN] Raw dataset is still empty. Continuing with current file content.")

    # Stage 2: Clean dataset.
    run_step("Clean reviews", [PYTHON, "src/02_clean.py"])

    # Stage 3 + 4: LLM-powered grouping/persona/spec.
    # Requires GROQ_API_KEY.
    if os.getenv("GROQ_API_KEY"):
        run_step("Generate groups + personas", [PYTHON, "src/05_personas_auto.py"])
        run_step("Generate specifications", [PYTHON, "src/06_spec_generate.py"])
    else:
        print("\n[WARN] GROQ_API_KEY is not set. Skipping LLM-dependent steps (05, 06).")
        ensure_placeholder_json(GROUPS_PATH, {"groups": []})
        ensure_placeholder_json(PERSONAS_PATH, {"personas": []})
        if not file_has_content(SPEC_PATH):
            SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
            SPEC_PATH.write_text("", encoding="utf-8")
            print(f"[INFO] Wrote placeholder artifact: {SPEC_PATH.relative_to(ROOT)}")

    # Stage 5: Generate tests from spec.
    run_step("Generate validation tests", [PYTHON, "src/07_tests_generate.py"], optional=True)
    ensure_placeholder_json(TESTS_PATH, {"tests": []})

    # Stage 6: Compute metrics from available artifacts.
    run_step("Compute metrics", [PYTHON, "src/08_metrics.py"])

    print("\nPipeline finished.")
    print("Produced/updated artifacts:")
    for p in [
        RAW_PATH,
        CLEAN_PATH,
        GROUPS_PATH,
        PERSONAS_PATH,
        SPEC_PATH,
        TESTS_PATH,
        METRICS_PATH,
    ]:
        print("-", p.relative_to(ROOT), "(exists:" , p.exists(), ")")


if __name__ == "__main__":
    main()