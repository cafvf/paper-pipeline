from datetime import date

import pytest

from paper_triage.errors import IssueCode, TriageError
from paper_triage.models import ItemTypeClass, PaperKind
from paper_triage.normalization import normalize_doi, normalize_paper, normalize_text


def _raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "library_id": "library",
        "item_key": "ITEM001",
        "item_version": 1,
        "raw_item_type": "journalArticle",
        "citekey": "cite-001",
        "title": "  <b>Roc\u006b\u0301</b> &amp;   soil  ",
        "authors": [{"family": "Doe", "given": "Jane"}],
        "year": 2025,
        "doi": "https://doi.org/10.1000/ABC.Def).",
        "venue": "  Journal   Name ",
        "abstract": "<p>We show results.</p>",
        "collections": ["b", "a", "a"],
        "tags": [" #rock ", "%fem", "#rock"],
    }
    raw.update(overrides)
    return raw


def test_text_and_doi_normalization_are_deterministic() -> None:
    assert normalize_text("  A\u0301  &amp;  B ") == "Á & B"
    assert normalize_text("<p>A</p>   <em>B</em>", strip_markup=True) == "A B"
    assert normalize_doi("doi: 10.1000/ABC.Def).") == "10.1000/abc.def"
    assert normalize_doi("not-a-doi") is None


def test_normalizes_metadata_and_records_invalid_optional_values() -> None:
    paper = normalize_paper(_raw(year=999, doi="not-a-doi"), run_date=date(2026, 1, 1))
    assert paper.title == "Rocḱ & soil"
    assert paper.doi is None
    assert paper.year is None
    assert paper.collections == frozenset({"a", "b"})
    assert paper.tags == frozenset({"#rock", "%fem"})
    assert {warning.code for warning in paper.normalization_warnings} == {IssueCode.YEAR_INVALID, IssueCode.DOI_INVALID}


@pytest.mark.parametrize(
    ("raw_type", "tags", "expected_class", "expected_kind"),
    [
        ("journalArticle", (), ItemTypeClass.ORIGINAL_CANDIDATE, PaperKind.ORIGINAL),
        ("journalArticle", ("%systematic-review",), ItemTypeClass.ORIGINAL_CANDIDATE, PaperKind.REVIEW),
        ("book", ("%systematic-review",), ItemTypeClass.SUPPORT_OR_NONPAPER, PaperKind.AMBIGUOUS),
        ("futureType", (), ItemTypeClass.UNKNOWN, PaperKind.AMBIGUOUS),
    ],
)
def test_item_type_matrix(raw_type: str, tags: tuple[str, ...], expected_class: ItemTypeClass, expected_kind: PaperKind) -> None:
    paper = normalize_paper(_raw(raw_item_type=raw_type, tags=tags), run_date=date(2026, 1, 1))
    assert (paper.item_type_class, paper.paper_kind) == (expected_class, expected_kind)


@pytest.mark.parametrize("child_type", ["attachment", "note", "annotation"])
def test_child_items_are_rejected_before_paper(child_type: str) -> None:
    with pytest.raises(TriageError) as exc:
        normalize_paper(_raw(raw_item_type=child_type), run_date=date(2026, 1, 1))
    assert exc.value.code == IssueCode.PAPER_KIND_AMBIGUOUS


def test_blank_title_fails_with_stable_issue() -> None:
    with pytest.raises(TriageError) as exc:
        normalize_paper(_raw(title="  <b> </b>  "), run_date=date(2026, 1, 1))
    assert exc.value.code == IssueCode.PAPER_TITLE_REQUIRED
