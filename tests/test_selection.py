from datetime import date

import pytest

from paper_triage.errors import TriageError
from paper_triage.models import Paper
from paper_triage.normalization import normalize_paper
from paper_triage.selection import LOT_SIZE, select_first_real_lot


def _paper(
    key: str,
    *,
    year: int = 2026,
    collections: list[str] | None = None,
    raw_item_type: str = "journalArticle",
    tags: list[str] | None = None,
    doi: str | None = None,
) -> Paper:
    return normalize_paper(
        {
            "library_id": "library",
            "item_key": key,
            "item_version": 1,
            "raw_item_type": raw_item_type,
            "title": f"Paper {key}",
            "authors": [{"family": "Doe"}],
            "year": year,
            "doi": doi,
            "collections": collections if collections is not None else [".ToLook"],
            "tags": tags or [],
        },
        run_date=date(2026, 8, 9),
    )


def test_selects_exactly_ten_eligible_papers_in_stable_item_key_order() -> None:
    papers = [_paper(f"ITEM{index:03}") for index in range(12, 0, -1)]

    selected = select_first_real_lot(papers)

    assert len(selected) == LOT_SIZE
    assert [paper.item_key for paper in selected] == [f"ITEM{index:03}" for index in range(1, 11)]


@pytest.mark.parametrize(
    "paper",
    (
        _paper("OLD0001", year=2025),
        _paper("OTHER001", collections=[".ToRevise"]),
        _paper("REVIEW01", tags=["%systematic-review"]),
        _paper("BOOK0001", raw_item_type="book"),
    ),
)
def test_ignores_papers_outside_the_regular_2026_tolook_criteria(paper: Paper) -> None:
    eligible = [_paper(f"ITEM{index:03}") for index in range(1, 11)]

    assert select_first_real_lot([paper, *eligible]) == tuple(eligible)


def test_fails_closed_when_fewer_than_ten_papers_are_eligible() -> None:
    papers = [_paper(f"ITEM{index:03}") for index in range(1, LOT_SIZE)]

    with pytest.raises(TriageError, match="LOT_INSUFFICIENT_ELIGIBLE_PAPERS"):
        select_first_real_lot(papers)


def test_duplicate_non_null_dois_are_excluded_before_selecting_the_lot() -> None:
    unique = [_paper(f"ITEM{index:03}") for index in range(1, 11)]
    duplicates = [
        _paper("DUP0001", doi="10.1000/shared"),
        _paper("DUP0002", doi="10.1000/shared"),
    ]

    assert select_first_real_lot([*duplicates, *reversed(unique)]) == tuple(unique)


def test_duplicate_non_null_dois_can_make_a_lot_fail_closed() -> None:
    papers = [
        *[_paper(f"ITEM{index:03}") for index in range(1, 10)],
        _paper("DUP0001", doi="10.1000/shared"),
        _paper("DUP0002", doi="10.1000/shared"),
    ]

    with pytest.raises(TriageError, match="LOT_INSUFFICIENT_ELIGIBLE_PAPERS"):
        select_first_real_lot(papers)
