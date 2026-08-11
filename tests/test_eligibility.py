from datetime import date

from paper_triage.eligibility import exclude_ineligible_candidates
from paper_triage.models import Paper
from paper_triage.normalization import normalize_paper


def _paper(
    key: str,
    *,
    doi: str | None = "10.1000/unique",
    citekey: str = "same-citekey",
) -> Paper:
    return normalize_paper(
        {
            "library_id": "library",
            "item_key": key,
            "item_version": 1,
            "raw_item_type": "journalArticle",
            "citekey": citekey,
            "title": f"Paper {key}",
            "authors": [{"family": "Doe"}],
            "year": 2026,
            "doi": doi,
        },
        run_date=date(2026, 1, 1),
    )


def test_excludes_every_non_null_duplicate_doi_but_not_null_or_citekey_duplicates() -> None:
    first = _paper("ITEM001", doi="https://doi.org/10.1000/DUPLICATE")
    second = _paper("ITEM002", doi="doi: 10.1000/duplicate")
    no_doi_first = _paper("ITEM003", doi=None)
    no_doi_second = _paper("ITEM004", doi=None)
    same_citekey = _paper("ITEM005", doi="10.1000/distinct")

    selected = exclude_ineligible_candidates(
        (first, second, no_doi_first, no_doi_second, same_citekey)
    )

    assert tuple(paper.item_key for paper in selected) == ("ITEM003", "ITEM004", "ITEM005")


def test_defensively_excludes_child_items_and_preserves_remaining_order() -> None:
    first = _paper("ITEM001", doi="10.1000/first")
    child = _paper("ITEM002", doi="10.1000/child").model_copy(
        update={"raw_item_type": "attachment"}
    )
    last = _paper("ITEM003", doi="10.1000/last")

    selected = exclude_ineligible_candidates((last, child, first))

    assert tuple(paper.item_key for paper in selected) == ("ITEM003", "ITEM001")
