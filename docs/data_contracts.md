# Data Contracts

This file documents the target project-paper contracts. They are not all implemented yet. Existing implemented contracts are mostly reading-stage contracts in `paper_pipeline/contracts.py` and `paper_pipeline/llm_schema.py`.

## ProjectProfile

Minimum fields for an Obsidian project or objective.

```json
{
  "project_id": "cptu_bayesian_classification",
  "title": "CPTu Bayesian Soil Classification",
  "source_path": "Projects/CPTu Bayesian Soil Classification.md",
  "objectives": [
    "Develop a hybrid probabilistic model for CPTu soil classification"
  ],
  "methods": [
    "CPTu",
    "Robertson chart",
    "Bayesian changepoint",
    "probabilistic classification"
  ],
  "knowledge_gaps": [
    "distance to nonlinear chart regions",
    "validation using geological reports"
  ],
  "expected_outputs": [
    "paper",
    "python implementation"
  ],
  "priority": "high",
  "tags": [
    "projeto"
  ],
  "status": "active",
  "content_hash": "sha256:project-note-content"
}
```

## PaperProfile

Minimum fields for Zotero metadata inventory. MVP 0.1 should not require PDF text.

```json
{
  "citekey": "robertson1990soilclassification",
  "zotero_key": "ABC123",
  "title": "Soil classification using the cone penetration test",
  "year": 1990,
  "authors": [
    "Robertson"
  ],
  "abstract": "Abstract text when available.",
  "collections": [
    "CPTu",
    "Soil Classification"
  ],
  "tags": [
    "cpt",
    "classification"
  ],
  "doi": "10.0000/example",
  "has_pdf": true,
  "pdf_paths": [],
  "paper_hash": "sha256:title+abstract+tags+collections"
}
```

## ProjectPaperCandidate

Candidate rows are generated before LLM classification.

```json
{
  "project_id": "cptu_bayesian_classification",
  "citekey": "robertson1990soilclassification",
  "candidate_score": 0.87,
  "rank": 1,
  "evidence": [
    "CPTu appears in project profile",
    "soil classification appears in title",
    "Robertson chart appears in abstract"
  ],
  "method": "lexical_v1",
  "created_at": "2026-05-06T00:00:00"
}
```

## LLMClassification

Allowed utility classes:

```yaml
utility_classes:
  - essential
  - methodological
  - formulational
  - case_study
  - review
  - counterpoint
  - implementable
  - peripheral
  - irrelevant_now
```

Allowed actions:

```yaml
actions:
  - read_now
  - read_later
  - extract_equations
  - reproduce_code
  - summarize_only
  - link_to_project
  - ignore_for_now
```

Example:

```json
{
  "project_id": "cptu_bayesian_classification",
  "citekey": "robertson1990soilclassification",
  "utility_class": "essential",
  "scores": {
    "topic_fit": 5,
    "method_fit": 5,
    "formulation_value": 4,
    "implementation_value": 3,
    "empirical_value": 3,
    "gap_value": 5,
    "reading_effort": 3
  },
  "recommended_action": "read_now",
  "reason": "The paper defines the deterministic CPT classification framework that the project intends to extend probabilistically.",
  "possible_uses": [
    "literature review",
    "baseline method",
    "problem formulation"
  ],
  "limitations": [
    "Classification is empirical and deterministic",
    "Uncertainty treatment is limited"
  ],
  "confidence": "high",
  "requires_human_review": true,
  "prompt_hash": "sha256:prompt-version"
}
```

## HumanReview

Human review captures the user's decision and is the only authorization for write modules.

```json
{
  "review_id": "2026-05-06-initial-triage",
  "project_id": "cptu_bayesian_classification",
  "citekey": "robertson1990soilclassification",
  "decision": "approved",
  "human_reason": "",
  "approved_actions": [
    "read_now",
    "link_to_project"
  ],
  "apply_zotero_tags": false,
  "create_obsidian_note": false,
  "reviewed_at": "2026-05-06T00:00:00"
}
```

Allowed decisions:

- `pending`;
- `approved`;
- `rejected`;
- `deferred`;
- `manual_only`.

## ProcessingRun

```json
{
  "run_id": "20260506_000000",
  "command": "classify",
  "config_hash": "sha256:config-without-secrets",
  "prompt_hash": "sha256:prompt-version",
  "model": "qwen/qwen3.5-9b",
  "started_at": "2026-05-06T00:00:00",
  "finished_at": "2026-05-06T00:03:00",
  "status": "complete",
  "counts": {
    "projects": 5,
    "papers": 250,
    "candidates": 100,
    "classifications": 50
  }
}
```

## Future Schema Files

Suggested files:

- `schemas/project_profile.schema.json`;
- `schemas/paper_profile.schema.json`;
- `schemas/project_paper_match.schema.json`;
- `schemas/llm_classification.schema.json`.

Acceptance: the system rejects malformed LLM output before it is stored, rendered, or applied.

