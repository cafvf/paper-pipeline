"""Pure batch-level candidate eligibility checks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .models import Paper

_CHILD_ITEM_TYPES = frozenset({"attachment", "note", "annotation"})


def exclude_ineligible_candidates(papers: Iterable[Paper]) -> tuple[Paper, ...]:
    """Exclude child items and every paper in a duplicate non-null DOI group.

    Input order is retained so the caller can apply its own deterministic ordering
    policy.  Missing DOIs intentionally do not form a duplicate group.
    """
    candidates = tuple(paper for paper in papers if paper.raw_item_type not in _CHILD_ITEM_TYPES)
    doi_counts = Counter(paper.doi for paper in candidates if paper.doi is not None)
    return tuple(
        paper for paper in candidates if paper.doi is None or doi_counts[paper.doi] == 1
    )
