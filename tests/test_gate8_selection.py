from paper_pipeline.contracts import Stage
from paper_pipeline.selection import CandidatePaper, score_candidate, select_batch


INDEX = {
    "notes": [
        {"title": "CPT Bayesian", "text": "probabilistic soil characterization", "weight": 35, "aliases": [], "tags": [], "headings": []}
    ]
}


def paper(citekey, stage, **kwargs):
    defaults = {
        "title": "Bayesian CPT paper",
        "abstract": "soil characterization and uncertainty",
        "has_pdf": True,
        "publication_year": 2025,
    }
    defaults.update(kwargs)
    return CandidatePaper(citekey=citekey, stage=stage, **defaults)


def test_score_rewards_doi_and_review():
    candidate = paper("a", Stage.TO_LOOK, doi="10.1000/test", source_type="review-paper")
    assert score_candidate(candidate, INDEX) >= 25


def test_select_batch_respects_base_quotas_reallocates_and_skips_same_layer_tag():
    candidates = [paper(f"l{i}", Stage.TO_LOOK) for i in range(6)]
    candidates += [paper(f"r{i}", Stage.TO_REVISE) for i in range(5)]
    candidates += [paper("d0", Stage.TO_DIG, tags=["@dug_by_llm"])]
    result = select_batch(candidates, INDEX)
    selected = result["selected"]
    assert len([entry for entry in selected if entry["candidate"].stage == Stage.TO_LOOK]) == 5
    assert len([entry for entry in selected if entry["candidate"].stage == Stage.TO_REVISE]) == 5
    assert all(entry["candidate"].citekey != "d0" for entry in selected)


def test_reallocates_slots_to_advanced_layers():
    candidates = [paper(f"r{i}", Stage.TO_REVISE) for i in range(8)]
    result = select_batch(candidates, INDEX, max_total=10)
    assert len(result["selected"]) == 8


def test_missing_pdf_is_blocked_not_selected_when_pdf_candidates_exist():
    candidates = [paper("missing", Stage.TO_LOOK, has_pdf=False), paper("ok", Stage.TO_LOOK, has_pdf=True)]
    result = select_batch(candidates, INDEX, quotas={Stage.TO_LOOK: 2, Stage.TO_REVISE: 0, Stage.TO_DIG: 0})
    assert [entry["candidate"].citekey for entry in result["selected"]] == ["ok"]
    assert result["blocked_missing_pdf"][0]["candidate"].citekey == "missing"
