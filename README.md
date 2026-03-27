# EECS4312_W26_SpecChain

## Application Studied
- **Application:** Medito
- **Google Play URL:** https://play.google.com/store/apps/details?id=meditofoundation.medito
- **App ID:** `meditofoundation.medito`

## Data Collection Method
Raw reviews are collected from Google Play using `google-play-scraper` in:
- `src/01_collect_or_import.py`

The cleaner in `src/02_clean.py` processes the raw data and writes cleaned records used by the automated pipeline.

## Dataset Files
- **Raw dataset:** `data/reviews_raw.jsonl`
- **Cleaned dataset:** `data/reviews_clean.jsonl`

Current cleaned dataset size in this repository snapshot:
- **0 reviews** (environment did not allow live scraping/API credentials during generation run).

## Repository Structure
- `src/` – executable scripts for validation, collection, cleaning, generation, testing, and metrics
- `data/` – raw/clean review datasets and grouped review artifacts
- `personas/` – persona outputs (`manual`, `auto`, `hybrid`)
- `spec/` – generated requirement specifications
- `tests/` – generated validation tests
- `metrics/` – computed metrics per pipeline and summary
- `prompts/` – prompts/templates used for automated generation
- `reflection/` – final comparison/reflection write-up

## Automated Pipeline Artifacts (Task 4+)
The automated workflow produces/uses:
- `data/review_groups_auto.json`
- `personas/personas_auto.json`
- `spec/spec_auto.md`
- `tests/tests_auto.json`
- `metrics/metrics_auto.json`
- `prompts/prompt_auto.json`

## Activate Your GROQ API Key
```bash
$env:GROQ_API_KEY="YOUR_API_KEY"
```

## Exact Commands to Reproduce

From repository root:

1. Validate repository structure:
```bash
python src/00_validate_repo.py
```

2. Collect raw reviews:
```bash
python src/01_collect_or_import.py 
```

3. Clean reviews:
```bash
python src/02_clean.py
```

4. Generate groups + personas (requires Groq key):
```bash
python src/05_personas_auto.py
```

5. Generate requirements/specification (requires Groq key):
```bash
python src/06_spec_generate.py
```

6. Generate validation tests:
```bash
python src/07_tests_generate.py
```

7. Compute automated metrics:
```bash
python src/08_metrics.py
```

8. Run full automated pipeline orchestrator:
```bash
python src/run_all.py
```

## Notes
- `src/run_all.py` runs the automated flow in order and skips LLM-dependent stages if `GROQ_API_KEY` is not set.
- Groq model used in automated scripts: `meta-llama/llama-4-scout-17b-16e-instruct`.
