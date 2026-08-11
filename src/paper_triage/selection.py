"""Pure, deterministic selection of the first real paper lot."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from .eligibility import exclude_ineligible_candidates
from .errors import TriageError
from .models import ItemTypeClass, Paper, PaperKind

LOT_SIZE: Final = 10
TO_LOOK_COLLECTION: Final = ".ToLook"
TARGET_YEAR: Final = 2026


def select_first_real_lot(
    papers: Iterable[Paper], *, tolook_collection_key: str = TO_LOOK_COLLECTION
) -> tuple[Paper, ...]:
    """Return the first ten regular 2026 papers in a resolved ToLook collection.

    Selection is entirely local and does not mutate its input.  A partial lot is
    unsafe to process, so this function fails closed unless at least ten papers
    meet the eligibility criteria.
    """
    eligible = sorted(
        (
            paper
            for paper in exclude_ineligible_candidates(papers)
            if paper.item_type_class is ItemTypeClass.ORIGINAL_CANDIDATE
            and paper.paper_kind is PaperKind.ORIGINAL
            and paper.year == TARGET_YEAR
            and tolook_collection_key in paper.collections
        ),
        key=lambda paper: paper.item_key,
    )
    if len(eligible) < LOT_SIZE:
        raise TriageError(
            "LOT_INSUFFICIENT_ELIGIBLE_PAPERS",
            f"at least {LOT_SIZE} eligible papers are required",
        )
    return tuple(eligible[:LOT_SIZE])
