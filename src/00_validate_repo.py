"""Validate required repository structure for the project submission."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = [
    "src",
    "data",
    "personas",
    "spec",
    "tests",
    "metrics",
    "prompts",
    "reflection",
]

REQUIRED_FILES = [
    "data/reviews_raw.jsonl",
    "data/reviews_clean.jsonl",
    "data/dataset_metadata.json",
    "data/review_groups_manual.json",
    "data/review_groups_auto.json",
    "data/review_groups_hybrid.json",
    "personas/personas_manual.json",
    "personas/personas_auto.json",
    "personas/personas_hybrid.json",
    "spec/spec_manual.md",
    "spec/spec_auto.md",
    "spec/spec_hybrid.md",
    "tests/tests_manual.json",
    "tests/tests_auto.json",
    "tests/tests_hybrid.json",
    "metrics/metrics_manual.json",
    "metrics/metrics_auto.json",
    "metrics/metrics_hybrid.json",
    "metrics/metrics_summary.json",
    "prompts/prompt_auto.json",
    "reflection/reflection.md",
    "README.md",
    "src/run_all.py",
    "src/00_validate_repo.py",
    "src/01_collect_or_import.py",
    "src/02_clean.py",
    "src/03_manual_coding_template.py",
    "src/04_personas_manual.py",
    "src/05_personas_auto.py",
    "src/06_spec_generate.py",
    "src/07_tests_generate.py",
    "src/08_metrics.py",
]

def main() -> None:
    missing_dirs = [d for d in REQUIRED_DIRS if not (ROOT / d).is_dir()]
    missing_files = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]

    print("Repository validation report")
    print("-" * 40)

    if missing_dirs:
        print("Missing directories:")
        for d in missing_dirs:
            print(f"  - {d}")
    else:
        print("All required directories exist.")

    if missing_files:
        print("Missing files:")
        for f in missing_files:
            print(f"  - {f}")
    else:
        print("All required files exist.")

    if not missing_dirs and not missing_files:
        print("\nRepository structure is complete.")
    else:
        print("\nRepository structure is incomplete.")


if __name__ == "__main__":
    main()