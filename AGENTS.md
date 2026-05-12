# AGENTS

## Purpose

Standalone pipeline for Zotero-driven paper triage, local LLM assessment, Obsidian note handoff, and auditable runtime artifacts.

Use this file for persistent Codex/agent instructions. Human-facing setup and usage remain in `README.md`; executable policy lives in `.pre-commit-config.yaml`, `.gitleaks.toml`, `pytest.ini`, `run_audit.sh`, and `.github/workflows/ci.yml`.

## Shared Codex Rules

- Prefer `uv` for every repository command; do not rely on global Python for checks.
- Keep `.venv/`, caches, local configs, scanner reports, runtime data, PDFs, and generated artifacts out of Git unless a workflow explicitly promotes them.
- Treat `uv.lock` as the project lockfile and keep it versioned.
- Before commit or push, run the local equivalent of affected CI jobs and remove ignored temporary artifacts.
- Never use `--no-verify` unless hooks are environmentally broken and equivalent checks were already run and reported.
- Preserve user changes. Do not revert unrelated dirty work.
- Keep diffs small, reversible, and aligned with existing local patterns.
- Security defaults are conservative: no real tokens, IDs, cookies, local DBs, request payload dumps, or personal config in Git.

## Development Paradigms

- All software development in this repository must follow Test-Driven Development, Extreme Programming, Clean Code, and Spec-Driven Development together.
- Specs, contracts, schemas, and executable tests are the source of truth for behavior. Update the spec/contract first, then add or update tests, then implement.
- No behavior change is complete without automated tests that control the expected behavior. If behavior changes, the relevant tests must be added or updated in the same change.
- Prefer small, reversible increments with continuous refactoring, simple design, clear naming, and removal of duplication.
- When a change affects CLI behavior, contracts, schemas, prompts, planning logic, persistence, or safety boundaries, add or update tests before considering the work done.

## Canonical References

- `README.md`: onboarding and standalone-vs-vault layout.
- `docs/architecture.md`: current architecture, target module boundaries, and write/read-only surfaces.
- `docs/roadmap.md`: Obsidian + Zotero modular roadmap and current repository adherence.
- `docs/development_guidelines.md`: engineering paradigms, TDD/XP/Clean Code/Spec-Driven workflow, and mandatory test policy.
- `docs/data_contracts.md`: target project-paper contracts and examples.
- `docs/zotero_policy.md` and `docs/obsidian_policy.md`: external-system safety policy.
- `config.example.yaml`: safe configuration template.
- `.pre-commit-config.yaml`: local hook contract.
- `.gitleaks.toml`: secret-scanning contract.
- `.github/workflows/ci.yml`: CI contract.
- `tests/`: behavioral and migration contracts.

## Work Areas

- Core package: `paper_pipeline/`.
- CLI entrypoints: `paper_pipeline/cli.py` and compatibility `cli.py`.
- Tests: `tests/`.
- Tooling and scanners: `tools/`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `.github/workflows/`.
- Runtime artifacts should default to `papers/` and `index/`; Obsidian content is addressed through `vault_root`.

## Commands

- Bootstrap: `uv sync --locked`
- Lint: `uv run ruff check`
- Tests: `uv run pytest -q -o addopts=`
- Hooks: `uv run pre-commit install`
- Hooks audit: `uv run pre-commit run --all-files`
- Secret scan: `python3 tools/run_gitleaks.py`
- Static security: `uv run bandit -r paper_pipeline`
- Dependency audit: `uvx pip-audit`
- Full local audit: `./run_audit.sh`
- CLI smoke: `uv run paper-pipeline run --vault-root . --dry-run`

## Change Rules

- Keep the project standalone. Do not reintroduce required `x/LLM` paths.
- Resolve runtime paths relative to the config file unless the contract explicitly says they belong to `vault_root`.
- Keep `config.example.yaml` placeholder-only; real `config.yaml` stays ignored.
- Start behavior work from the governing spec, contract, or roadmap entry, and keep implementation aligned with that source.
- Do not merge behavior changes without tests that lock the intended behavior and prevent regression.
- If `save_payloads=True` behavior changes, document and test the privacy impact.
- Avoid writing secrets into logs, exception messages, artifact links, test fixtures, or reports.
- For migration/layout changes, update tests that encode the standalone contract.
- For CLI behavior, add parser or subprocess coverage where practical.

## Validation

- Python/tooling change: run `uv run ruff check` and `uv run pytest -q -o addopts=`.
- Security/tooling change: also run `uv run pre-commit run --all-files`, `python3 tools/run_gitleaks.py`, and `uv run bandit -r paper_pipeline`.
- Dependency or CI change: run `uvx pip-audit` when network is available.
- A change that modifies behavior, contracts, or safety policy is not validated until the relevant automated tests are added or updated and passing.
- Before commit/push: run `./run_audit.sh` or explicitly report any CI-equivalent check that could not run.

## Review Guidelines

- Review proposed changes through TDD/XP/Clean Code/Spec-Driven lenses: missing tests, drift from spec, unnecessary complexity, duplication, unclear naming, and weak refactoring boundaries are first-class issues.
- Prioritize regressions in path contracts, secret handling, external-service failure modes, and stale migration assumptions.
- Check that docs, tests, CI, pre-commit, and scripts name the same commands.
- Treat warnings hidden by `|| true` as CI smell unless the step is deliberately advisory and documented.
- When reviewing security, verify both tracked history scanning and working-tree/pre-commit scanning behavior.
