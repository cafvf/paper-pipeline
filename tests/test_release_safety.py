"""Release gate tests: policy-only and deliberately free of connector I/O."""

import ast
from pathlib import Path

from paper_triage.release_safety import (
    ReleaseMode,
    ReleaseRequest,
    ValidationEvidence,
    authorize,
)


def _passing_evidence() -> ValidationEvidence:
    return ValidationEvidence(all_required_passed=True, evidence_reference="local-qa-2026-08-10")


def test_request_defaults_to_dry_run_without_live_authority() -> None:
    authorization = authorize(ReleaseRequest())

    assert authorization.allowed is False
    assert "dry-run" in authorization.reason.lower()


def test_live_mode_requires_explicit_human_approval() -> None:
    authorization = authorize(
        ReleaseRequest(mode=ReleaseMode.LIVE, validation_evidence=_passing_evidence())
    )

    assert authorization.allowed is False
    assert "approved preview" in authorization.reason.lower()


def test_live_mode_requires_validation_evidence() -> None:
    authorization = authorize(ReleaseRequest(mode=ReleaseMode.LIVE, human_approved=True))

    assert authorization.allowed is False
    assert "approved preview" in authorization.reason.lower()


def test_live_mode_rejects_failed_validation_evidence() -> None:
    authorization = authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=True,
            validation_evidence=ValidationEvidence(
                all_required_passed=False, evidence_reference="failing-local-check"
            ),
        )
    )

    assert authorization.allowed is False
    assert "approved preview" in authorization.reason.lower()


def test_live_mode_is_authorized_only_with_approval_and_passing_evidence() -> None:
    authorization = authorize(
        ReleaseRequest(
            mode=ReleaseMode.LIVE,
            human_approved=True,
            validation_evidence=_passing_evidence(),
        )
    )

    assert authorization.allowed is False
    assert "approved preview plan" in authorization.reason.lower()


def test_validation_evidence_is_hash_bound_not_a_passing_boolean() -> None:
    evidence = ValidationEvidence.create(plan_hash="a" * 64, checks=("pytest", "mypy"))

    assert evidence.verifies()
    assert ValidationEvidence.model_validate(
        {**evidence.model_dump(), "validation_digest": "b" * 64}
    ).verifies() is False


def test_release_gate_module_has_no_network_or_zotero_client_imports() -> None:
    module_path = Path("src/paper_triage/release_safety.py")
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(module_path.read_text()))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert imports.isdisjoint({"requests", "httpx", "urllib", "zotero", "pyzotero", "socket"})
