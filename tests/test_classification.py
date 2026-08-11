from datetime import date

from paper_triage.classification import classify
from paper_triage.config import StageCollections, TriageConfig
from paper_triage.models import Stage
from paper_triage.normalization import normalize_paper


def _config() -> TriageConfig:
    return TriageConfig(
        stage_collections=StageCollections(look="look-key", review="review-key", dig="dig-key"),
        credible_venues=("Trusted Journal",),
    )


def _paper(*, abstract: str, tags: list[str], year: int = 2026, title: str = "Rock mechanics study"):
    return normalize_paper(
        {
            "library_id": "library",
            "item_key": "ITEM001",
            "item_version": 1,
            "raw_item_type": "journalArticle",
            "title": title,
            "authors": [{"family": "Doe"}],
            "year": year,
            "doi": "10.1000/test",
            "venue": "Trusted Journal",
            "abstract": abstract,
            "tags": tags,
        },
        run_date=date(2026, 1, 1),
    )


def test_dig_requires_look_and_three_review_passes() -> None:
    paper = _paper(
        tags=["#rock-mechanics", "%finite-element", "!data-available"],
        abstract="We show a research gap. This method gives results with a limitation.",
    )
    result = classify(paper, _config(), run_date=date(2026, 1, 1))
    assert result.proposed_stage is Stage.DIG

    no_look = _paper(
        tags=["!data-available"],
        title="A generic study",
        abstract="We show a method results with a limitation.",
    )
    assert classify(no_look, _config(), run_date=date(2026, 1, 1)).proposed_stage is None


def test_advisory_signals_remain_classification_only() -> None:
    paper = _paper(
        tags=["$methods-cite", "!seminal"],
        abstract="Metadata only.",
    )
    result = classify(paper, _config(), run_date=date(2026, 1, 1))
    assert result.project_uses == ("$methods-cite",)
    assert result.quality_flags == ("!seminal",)
    assert all(not tag.startswith(("$", "!")) for tag in (*result.subjects, *result.methods))
