# Development Guidelines

This repository follows Test-Driven Development, Extreme Programming, Clean
Code, and Spec-Driven Development together. These are not optional style
preferences. They define when a change is ready to merge.

## Core Rule

No behavior change is complete without automated tests that control the
expected behavior.

If behavior changes, the same change must also add or update the tests that
prove the new behavior and prevent regression.

## Working Order

1. Start from the governing spec, contract, schema, roadmap item, or bug
   report.
2. Add or update the failing automated test that captures the intended
   behavior.
3. Implement the smallest change that makes the test pass.
4. Refactor while keeping the tests green.
5. Run the relevant validation commands before considering the work complete.

This is the default workflow for features, bug fixes, refactors that affect
behavior, safety-boundary changes, CLI changes, persistence changes, prompt
changes, and contract changes.

## TDD Expectations

- Prefer a red -> green -> refactor loop.
- Keep tests close to the behavior they protect.
- Make regressions explicit in tests before changing production behavior.
- If a missing seam makes testing hard, add the seam first rather than skipping
  tests.

## XP Expectations

- Prefer small, reversible increments.
- Keep feedback loops short through frequent test runs.
- Refactor continuously instead of accumulating design debt.
- Favor simple design over speculative abstraction.

## Clean Code Expectations

- Use clear names and small units with focused responsibilities.
- Remove duplication when it obscures intent or multiplies maintenance cost.
- Keep module boundaries explicit, especially around contracts, orchestration,
  and side effects.
- Treat unnecessary complexity as a defect, not a neutral tradeoff.

## Spec-Driven Expectations

- Specs, contracts, schemas, and documented policies are the source of truth
  for behavior.
- Update the governing spec or contract first when the intended behavior
  changes.
- Keep implementation, tests, and docs aligned with the same contract.
- If implementation and spec disagree, fix the disagreement explicitly instead
  of letting them drift.

## Test Policy

Automated tests are mandatory for:

- behavior changes;
- contract or schema changes;
- CLI changes;
- persistence or artifact-layout changes;
- integration-boundary changes;
- safety-policy changes;
- fixes for reported regressions.

Useful forms of coverage in this repository include:

- schema and contract validation tests;
- parser and CLI tests;
- unit tests around policy and planning logic;
- regression tests for migrations and path behavior;
- fixture-driven tests for Zotero, Obsidian, PDF, and review flows.

## Done Criteria

A change is ready only when:

- the governing spec or contract is updated when needed;
- the relevant automated tests were added or updated;
- the implementation satisfies the updated tests;
- the required local validation commands pass;
- the diff remains small, readable, and reversible.

Implementation alone is not considered completion.
