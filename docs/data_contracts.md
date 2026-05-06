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
  "project_state": "on",
  "state_source": "Efforts/On",
  "tags": [],
  "content_hash": "sha256:project-note-content"
}
```

Allowed `project_state` values:

- `on`;
- `ongoing`;
- `simmering`;
- `terminated`.

`projects.jsonl` is a single canonical file. It should include all categorized project states, while downstream commands decide which states to process.

Project state should map directly to the existing `Efforts` layout:

- `Efforts/On` -> `on`;
- `Efforts/Ongoing` -> `ongoing`;
- `Efforts/Simmering` -> `simmering`;
- `Efforts/Terminated` -> `terminated`.

`terminated` covers both completed and abandoned projects; that distinction is not needed for workflow management.

Do not duplicate the full note body in `projects.jsonl`. Store extracted fields useful to the code and a `content_hash`.

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
  "paper_hash": "sha256:title+abstract+tags+collections",
  "metadata_snapshot_path": "papers/robertson1990soilclassification/metadata_snapshot.json"
}
```

Zotero metadata should also be persisted per paper under `papers/{citekey}/metadata_snapshot.json`, because every extracted paper product belongs to the paper's own artifact history.

The metadata snapshot is current-state and complementable, not append-only history. Updating it must preserve previously useful fields unless a source value is explicitly superseded by better metadata.

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
  "current_zotero_stage": ".ToLook",
  "recommended_zotero_stage": ".To Revise",
  "stage_recommendation_reason": "approved project utility and Gate 2 score 4/6",
  "stage_gate_results": {
    "gate_1_triggers": [
      "active_keyword_in_title"
    ],
    "gate_2_score": 4,
    "gate_2_total": 6,
    "gate_2_passed": true,
    "gate_3_passed": false
  },
  "reading_protocol_evidence": [
    "matches To Revise methodological-review gate"
  ],
  "prompt_hash": "sha256:prompt-version",
  "input_layer": "metadata",
  "input_products": [
    "papers/robertson1990soilclassification/metadata_snapshot.json"
  ]
}
```

Allowed `input_layer` values:

- `metadata`;
- `overview`;
- `sections`;
- `technical`;
- `pdf_fallback`.

`pdf_fallback` must require explicit authorization and should not be used by the initial classifier.

`recommended_zotero_stage` is a reading-depth recommendation, not a project-utility decision. It may use the user's reading protocol/gates as secondary evidence. Human review must still decide project utility project by project.

Initial `.ToDig` recommendation threshold: max project-paper adherence score >= `0.80`, or ToDig protocol gate passed.

## PaperProduct

Paper products are per-paper artifacts used to keep local LLM inputs bounded.

```json
{
  "citekey": "robertson1990soilclassification",
  "product_type": "section_products",
  "product_layer": "sections",
  "source": {
    "kind": "pdf",
    "pdf_hash": "sha256:pdf-content"
  },
  "output_path": "papers/robertson1990soilclassification/section_products.json",
  "created_at": "2026-05-06T00:00:00",
  "content_hash": "sha256:product-content"
}
```

Allowed `product_layer` values:

- `metadata`;
- `overview`;
- `references`;
- `sections`;
- `technical`;
- `deep_analysis`.

Layer policy:

- `metadata`: generated for all discovered papers;
- `overview`: layer 1, generated for all papers with PDFs when feasible;
- `references`: generated for `.To Revise` and `.ToDig` papers when feasible;
- `sections`: layer 2, generated after human decision or explicit selection;
- `technical`: layer 3, generated after human decision or explicit selection;
- `deep_analysis`: generated only after approval and after lower-level products exist.

Expected layer contents:

- layer 1 `overview`: title page metadata cross-check, abstract, keywords, detected headings, first/last-page signals, conclusion snippets, figures/tables inventory, and coarse document type;
- layer 2 `sections`: structured extracts for introduction/background, methods, data/case study, results, discussion, limitations, conclusions, and cited reference section when available;
- layer 3 `technical`: equation candidates in Obsidian-readable block LaTeX, equation source locations, PDF crop/image paths for comparison evidence, `equation_verified: false` by default, variables/symbols, assumptions, algorithms/workflows, validation evidence, datasets, implementation hooks, reproducibility signals, and methodological caveats;
- `references`: parsed bibliography entries with raw reference text, author/institution, year, title, DOI when available, and document type.

Permanent Obsidian literature-note generation requires metadata plus layer 1, layer 2, and layer 3 products. A PDF alone is not enough.

Equations extracted from PDFs are candidates until manually verified. JSON should store only the LaTeX body without `$$` delimiters; Markdown renderers should add `$$` delimiters for Obsidian. Each equation should be paired with a PDF crop/image of the equation region for comparison, but the system must not treat it as an authoritative formula until human review confirms it. PNG is the default evidence-image format; JPG or another raster format may be used as fallback. The canonical crop lives under `papers/{citekey}/equations/`; equation-review export should also copy the image beside the Obsidian Markdown review file. Because the Obsidian inbox is flat, copied image filenames should be citekey-prefixed, for example `{citekey}-eq-001.png`.

Suggested equation candidate fields:

```json
{
  "equation_id": "eq_robertson1990_001",
  "latex_body": "Q_t = \\frac{q_t - \\sigma_{v0}}{\\sigma'_{v0}}",
  "source_location": {
    "page": 4,
    "bbox": [72, 220, 480, 280]
  },
  "evidence_image_path": "papers/robertson1990soilclassification/equations/eq_robertson1990_001.png",
  "obsidian_evidence_image_path": "robertson1990soilclassification-eq-001.png",
  "evidence_image_format": "png",
  "equation_verified": false,
  "verification_note": ""
}
```

PDF-derived products may be maintained as one current file per paper because the PDF itself is not expected to change. Refreshes should be explicit or triggered by missing fields/extractor version changes.

## ReferenceRecord

Reference records are extracted from paper bibliographies and aggregated independently from Zotero import. The per-paper extraction artifact `papers/{citekey}/references.json` should contain the references cited by that source paper. The global artifact `data/reference_index.jsonl` should aggregate each distinct referenced work across the whole analyzed collection and list which source papers cited it.

```json
{
  "reference_id": "normalized-title-year-or-doi",
  "title": "Referenced paper title",
  "reference_type": "article",
  "year": 2020,
  "authors": [
    "Author"
  ],
  "doi": "10.0000/example",
  "raw_references": [
    "Author (2020) Referenced paper title..."
  ],
  "cited_by": [
    {
      "source_citekey": "reviewpaper2024",
      "source_stage": ".To Revise"
    },
    {
      "source_citekey": "digpaper2023",
      "source_stage": ".ToDig"
    }
  ],
  "in_zotero": false,
  "matched_citekey": "",
  "citation_count_in_corpus": 2,
  "capture_recommendation_score": 3.0,
  "source_stage_counts": {
    ".To Revise": 1,
    ".ToDig": 1
  },
  "source_stages": [
    ".To Revise",
    ".ToDig"
  ],
  "normalized_title": "referenced paper title",
  "first_seen_in": "reviewpaper2024",
  "match_confidence": "none",
  "needs_match_review": false,
  "has_pdf_in_zotero": false,
  "capture_priority": "low",
  "recommended_for_capture": false,
  "recommended_followup_action": "",
  "capture_reason": "",
  "notes": ""
}
```

References from `.To Revise` and `.ToDig` papers should feed `data/reference_index.jsonl`. This supports citation graph construction, statistics, missing-reference detection, and later capture decisions. It must not automatically import items into Zotero.

`citation_count_in_corpus` is the simple count of distinct source papers that cite the reference. `capture_recommendation_score` is a separate weighted score for acquisition priority. The weighted score must not replace the simple citation count.

Initial capture score weights:

- citation from `.ToLook`: `1.0`;
- citation from `.To Revise`: `1.5`;
- citation from `.ToDig`: `2.0`;
- citation from `Expendable`: `1.0`.

Initial `capture_priority` behavior:

- `high`: absent from Zotero and `capture_recommendation_score >= 8`, or absent from Zotero and `citation_count_in_corpus >= 5`;
- `medium`: absent from Zotero and `capture_recommendation_score >= 4`;
- `low`: all other cases.

If a reference appears in at least 5 source papers and is not already present in Zotero, it should be recommended for acquisition in a capture plan/report even if the weighted score formula changes later. The simple threshold `5` is initial and can be tuned later.

If a reference has no known local PDF, the reference mining or match-review report should recommend `recommended_followup_action: "attach_or_find_pdf"`. If the reference is already present in Zotero, this is recommended instead of acquisition. If the reference is absent from Zotero, the acquisition recommendation can coexist with a follow-up to find or attach the PDF.

Deduplication rules:

- DOI wins when available;
- without DOI, use author + year + normalized title as the MVP fallback;
- `in_zotero: true` should be assigned automatically only for DOI matches or strong author + year + normalized-title matches;
- fuzzy matches should be recorded as `match_confidence: "fuzzy"` and routed to review instead of being treated as confirmed Zotero presence;
- `match_confidence` should record how reliable the match is, for example `doi`, `title_year_author`, `fuzzy`, or `none`.

Allowed initial `reference_type` values:

- `article`;
- `book`;
- `standard`;
- `report`;
- `monograph`;
- `dissertation`;
- `thesis`;
- `unknown`.

Many useful references do not have a DOI. Non-DOI references should remain first-class records instead of being treated as malformed articles.

Non-DOI or fuzzy matches that need human inspection should be emitted to a separate match-review report, for example `data/reference_match_review.jsonl` or a Markdown rendering of the same rows. This report is distinct from acquisition recommendations because the question is "is this already represented in Zotero?" rather than "should I acquire it?".

`data/reference_match_review.md` should render the same review queue in human language for understanding and decision-making. The Markdown should explain why the match is uncertain, show the author/institution + year + title comparison, list source papers, and expose the allowed decisions.

Acquisition recommendations are advisory only. The system should not create Zotero items from reference mining. The human is responsible for adding the work to Zotero, normally into the `.ToLook` inbox/stage collection. Until the work appears in Zotero inventory, it should remain in the acquisition recommendation plan. Once a later inventory confirms the reference in `.ToLook`, it should disappear immediately from acquisition recommendations and enter the standard scan, match, classify, and review flow.

## ApplyPlan

Write modules should generate immutable plans before any real Zotero or Obsidian mutation.

```json
{
  "plan_id": "zotero_apply_2026-05-06_001",
  "plan_path": "data/zotero_apply_plan.jsonl",
  "plan_hash": "sha256:plan-content",
  "created_at": "2026-05-06T00:00:00",
  "source_review_id": "review_2026-05-06_initial_triage",
  "source_review_hash": "sha256:review-content",
  "source_inventory_hash": "sha256:zotero-inventory-content",
  "source_config_hash": "sha256:policy-config-content",
  "dry_run": true,
  "target": "zotero"
}
```

`plan_hash` is the hash of the concrete mutation plan. The plan record must also register the source review hash, source inventory hash, and source config/policy hash used to build the plan. Real apply commands must receive the reviewed plan path and expected `plan_hash`. They should refuse to apply if the file content no longer matches the hash or if the command would recalculate a different plan at write time.

## HumanReview

Human review captures the user's decision and is the only authorization for write modules.

```json
{
  "review_id": "2026-05-06-initial-triage",
  "review_path": "data/review.md",
  "review_item_id": "robertson1990soilclassification",
  "citekey": "robertson1990soilclassification",
  "decision": "decided",
  "human_reason": "",
  "approved_actions": [
    "read_now",
    "link_to_project"
  ],
  "current_zotero_stage": ".ToLook",
  "recommended_zotero_stage": ".To Revise",
  "stage_recommendation_reason": "approved project utility and Gate 2 score 4/6",
  "zotero_stage_decision": "move_to_revise",
  "manual_credibility": "unknown",
  "project_decisions": [
    {
      "project_id": "cptu_bayesian_classification",
      "decision": "approved",
      "approved_actions": [
        "read_now",
        "link_to_project"
      ],
      "human_reason": ""
    }
  ],
  "apply_zotero_tags": false,
  "create_obsidian_note": false,
  "reviewed_at": "2026-05-06T00:00:00"
}
```

Allowed decisions:

- `pending`;
- `decided`.

Project-level decisions:

- `approved`;
- `rejected`;
- `deferred`;
- `pending`.

Zotero stage decisions:

- `pending`;
- `keep_current`;
- `move_to_revise`;
- `move_to_dig`;
- `move_to_expendable`;
- `manual_only`.

Manual credibility values:

- `unknown`;
- `credible`;
- `not_credible`;
- `seminal_or_classic`.

`manual_credibility` is a paper-level human field for h-index/author/venue credibility evidence. It is not project-specific.

Generated review YAML should include `manual_credibility: unknown` by default.

Allowed values should be documented in Markdown near the review block rather than embedded as `allowed_*` keys in YAML.

Paper-level `decision` is a completion marker. `pending` means the review item is incomplete. `decided` means all required project-level decisions and any required Zotero-stage decision are complete.

Paper-level reviews aggregate all project-paper classifications for the same citekey. A paper should not be discarded if any eligible project-level decision is approved.

If any `project_decisions[].decision` is `pending`, paper-level `decision` must remain `pending`.

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
