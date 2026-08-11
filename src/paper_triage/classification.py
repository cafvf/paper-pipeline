"""Deterministic, side-effect-free subject, method, and stage classification."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .config import CONFIDENCE_THRESHOLD, TriageConfig
from .errors import Issue, IssueCode
from .models import (
    Classification,
    ConfidenceComponents,
    CriterionResult,
    CriterionStatus,
    EvidenceRef,
    Outcome,
    Paper,
    PaperKind,
    Stage,
)

_Q = Decimal("0.0001")
_TOKEN = re.compile(r"[^\w]+")
_SUBJECT_ALIASES = {
    "rock mechanics": "#rock-mechanics",
    "bayesian inference": "#bayesian",
    "bayesian methods": "#bayesian",
    "pinn": "#pinn",
    "pinns": "#pinn",
    "physics informed neural network": "#pinn",
    "physics informed neural networks": "#pinn",
    "soil classification": "#soil-classification",
    "structural reliability": "#structural-reliability",
    "wellbore stability": "#wellbore-stability",
    "borehole stability": "#wellbore-stability",
    "sand production": "#sand-production",
    "sanding": "#sand-production",
    "structural analysis": "#structural-analysis",
}
_METHOD_ALIASES = {
    "finite element method": "%finite-element",
    "finite element analysis": "%finite-element",
    "fem": "%finite-element",
    "finite difference method": "%finite-difference",
    "fdm": "%finite-difference",
    "discrete element method": "%discrete-element",
    "dem": "%discrete-element",
    "boundary element method": "%boundary-element",
    "bem": "%boundary-element",
    "experimental": "%experimental",
    "experiment": "%experimental",
    "laboratory test": "%experimental",
    "field data": "%field-data",
    "field measurement": "%field-data",
    "machine learning": "%machine-learning",
    "ml": "%machine-learning",
    "narrative review": "%narrative-review",
    "systematic review": "%systematic-review",
    "prisma": "%systematic-review",
    "python": "%python",
    "scipy": "%python",
}
_GAPS = ("research gap", "open problem", "remains unclear", "future work")


def _norm(value: str) -> str:
    return " ".join(part for part in _TOKEN.sub(" ", value.casefold()).split() if part)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _find_aliases(
    paper: Paper, aliases: dict[str, str]
) -> tuple[tuple[str, ...], list[EvidenceRef]]:
    exact = {tag for tag in paper.tags if tag in set(aliases.values())}
    text = _norm(" ".join(v for v in (paper.title, paper.abstract, paper.venue) if v))
    selected = set(exact)
    evidence = [
        EvidenceRef(
            evidence_id=f"tag:{tag}",
            source_field="tag",
            match_kind="existing_canonical_tag",
            normalized_excerpt=tag,
            value_hash=_hash(tag),
        )
        for tag in sorted(exact)
    ]
    words = text.split()
    for phrase, canonical in sorted(aliases.items(), key=lambda item: (-len(item[0]), item[0])):
        phrase_words = phrase.split()
        for index in range(len(words) - len(phrase_words) + 1):
            if words[index : index + len(phrase_words)] != phrase_words:
                continue
            if any(word in {"no", "not", "without"} for word in words[max(0, index - 3) : index]):
                continue
            selected.add(canonical)
            evidence.append(
                EvidenceRef(
                    evidence_id=f"alias:{canonical}:{phrase}",
                    source_field="title",
                    match_kind="frozen_alias",
                    normalized_excerpt=phrase,
                    value_hash=_hash(phrase),
                )
            )
            break
    return tuple(sorted(selected)), evidence


def _criterion(
    identifier: str, passed: bool | None, reason: str, refs: tuple[str, ...] = ()
) -> CriterionResult:
    return CriterionResult(
        criterion_id=identifier,
        status=CriterionStatus.PASS
        if passed
        else CriterionStatus.UNKNOWN
        if passed is None
        else CriterionStatus.FAIL,
        reason_code=reason,
        evidence_refs=refs,
    )


def _q(value: Decimal) -> Decimal:
    return value.quantize(_Q, rounding=ROUND_HALF_UP)


def classify(paper: Paper, config: TriageConfig, *, run_date: date) -> Classification:
    """Classify a normalized Paper with no I/O and no mutation capability."""
    subjects, subject_evidence = _find_aliases(paper, _SUBJECT_ALIASES)
    methods, method_evidence = _find_aliases(paper, _METHOD_ALIASES)
    advisory_project = tuple(sorted(tag for tag in paper.tags if tag.startswith("$")))
    advisory_quality = tuple(sorted(tag for tag in paper.tags if tag.startswith("!")))
    abstract = _norm(paper.abstract or "")
    gap = any(phrase in abstract for phrase in _GAPS) or "$gap-signal" in paper.tags
    look = (
        _criterion("look.subject", bool(subjects), "SUBJECT_MATCH"),
        _criterion("look.method", bool(methods), "METHOD_MATCH"),
        _criterion("look.project", bool(advisory_project), "PROJECT_SIGNAL"),
        _criterion("look.gap", gap, "GAP_SIGNAL"),
        _criterion("look.seminal", "!seminal" in paper.tags, "SEMINAL_SIGNAL"),
    )
    relevance = bool(subjects or advisory_project)
    method_good = bool(methods) and "!weak-methods" not in paper.tags
    recency = paper.year is not None and paper.year >= run_date.year - 10
    credibility = (
        (paper.venue or "").casefold() in {v.casefold() for v in config.credible_venues}
        or "!seminal" in paper.tags
        or "!high-impact" in paper.tags
    )
    citable = any(
        cue in abstract
        for cue in (
            "we show",
            "we find",
            "results indicate",
            "this study demonstrates",
            "we conclude",
            "our results",
        )
    )
    review = (
        _criterion("review.relevance", relevance, "RELEVANCE"),
        _criterion("review.method", method_good, "METHOD"),
        _criterion(
            "review.recency_or_seminal", recency or "!seminal" in paper.tags, "RECENCY_OR_SEMINAL"
        ),
        _criterion("review.author_venue_credibility", credibility, "CREDIBILITY"),
        _criterion("review.gap", gap, "GAP"),
        _criterion("review.citable_claim", citable, "CITABLE_CLAIM"),
    )
    look_pass = any(item.status is CriterionStatus.PASS for item in look)
    review_count = sum(item.status is CriterionStatus.PASS for item in review)
    dig: tuple[CriterionResult, ...] = ()
    stage: Stage | None = Stage.LOOK if look_pass else None
    if look_pass and review_count >= 3:
        stage = Stage.REVIEW
        if paper.paper_kind is PaperKind.ORIGINAL:
            dig = (
                _criterion("dig.question_gap", gap, "GAP"),
                _criterion(
                    "dig.reproducible_method",
                    method_good
                    and any(
                        x in abstract
                        for x in ("method", "model", "experiment", "algorithm", "procedure")
                    ),
                    "REPRODUCIBLE_METHOD",
                ),
                _criterion(
                    "dig.accessible_results",
                    "!data-available" in paper.tags or citable,
                    "ACCESSIBLE_RESULTS",
                ),
                _criterion("dig.direct_relevance", relevance, "RELEVANCE"),
                _criterion(
                    "dig.limitation",
                    any(
                        x in abstract
                        for x in (
                            "limitation",
                            "boundary condition",
                            "valid for",
                            "restricted to",
                            "future work",
                        )
                    ),
                    "LIMITATION",
                ),
            )
        elif paper.paper_kind is PaperKind.REVIEW:
            dig = (
                _criterion("dig.scope", "scope" in abstract or gap, "SCOPE"),
                _criterion(
                    "dig.selection",
                    any(
                        x in abstract
                        for x in (
                            "search strategy",
                            "selection criteria",
                            "inclusion criteria",
                            "database search",
                        )
                    )
                    or "%systematic-review" in methods,
                    "SELECTION",
                ),
                _criterion(
                    "dig.synthesis",
                    any(
                        x in abstract
                        for x in (
                            "synthesis",
                            "meta analysis",
                            "taxonomy",
                            "framework",
                            "consensus",
                        )
                    ),
                    "SYNTHESIS",
                ),
                _criterion(
                    "dig.gap_map",
                    any(x in abstract for x in ("gap", "consensus", "conflict", "contradiction")),
                    "GAP_MAP",
                ),
                _criterion("dig.direct_utility", relevance and citable, "UTILITY"),
            )
        if len(dig) == 5 and all(item.status is CriterionStatus.PASS for item in dig):
            stage = Stage.DIG
    availability = (
        paper.title is not None,
        paper.abstract is not None,
        paper.year is not None,
        bool(paper.authors),
        paper.venue is not None,
        paper.doi is not None,
    )
    coverage = _q(Decimal(sum(availability)) / Decimal(6))
    refs = subject_evidence + method_evidence
    weights = {"existing_canonical_tag": Decimal("1.0000"), "frozen_alias": Decimal("0.8500")}
    specificity = (
        _q(sum((weights[e.match_kind] for e in refs), Decimal(0)) / len(refs))
        if refs
        else Decimal(0)
    )
    evaluated = look + review + dig
    completeness = _q(
        Decimal(
            sum(item.status in {CriterionStatus.PASS, CriterionStatus.FAIL} for item in evaluated)
        )
        / Decimal(len(evaluated))
    )
    agreement = Decimal("1.0000")
    confidence = _q(
        Decimal("0.3000") * coverage
        + Decimal("0.3000") * specificity
        + Decimal("0.2500") * agreement
        + Decimal("0.1500") * completeness
    )
    outcome = (
        Outcome.HIGH_CONFIDENCE
        if confidence >= CONFIDENCE_THRESHOLD
        else Outcome.NEEDS_REREAD
        if look_pass
        else Outcome.UNCLASSIFIABLE
    )
    warnings = list(paper.normalization_warnings)
    if confidence < CONFIDENCE_THRESHOLD:
        warnings.append(
            Issue(code=IssueCode.CONFIDENCE_BELOW_THRESHOLD, message="confidence is below 0.8500")
        )
    if paper.paper_kind is PaperKind.AMBIGUOUS:
        warnings.append(
            Issue(code=IssueCode.PAPER_KIND_AMBIGUOUS, message="ambiguous paper kind blocks Dig")
        )
    return Classification(
        paper_key=paper.item_key,
        ruleset_version=config.ruleset_version,
        taxonomy_version=config.taxonomy_version,
        run_date=run_date,
        subjects=subjects,
        methods=methods,
        project_uses=advisory_project,
        quality_flags=advisory_quality,
        proposed_stage=stage,
        look_triggers=look,
        review_criteria=review,
        dig_criteria=dig,
        confidence=confidence,
        confidence_components=ConfidenceComponents(
            coverage=coverage,
            specificity=specificity,
            agreement=agreement,
            completeness=completeness,
        ),
        evidence=tuple(refs),
        warnings=tuple(warnings),
        outcome=outcome,
    )
