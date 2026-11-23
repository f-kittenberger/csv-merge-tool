<!--
Sync Impact Report
- Version change: unratified template -> 1.0.0 (initial ratification)
- Modified principles:
  - Template Principle 1 -> I. Configuration-Driven Domain Logic (NON-NEGOTIABLE)
  - Template Principle 2 -> II. Strict Static Typing & Structured Models
  - Template Principle 3 -> III. Python 3.13 & Exclusive uv Toolchain
  - Template Principle 4 -> IV. Standardized Source & Test Layout
  - Template Principle 5 -> V. Mandatory Verification Gates (NON-NEGOTIABLE)
- Added sections:
  - Technical Stack & Project Structure (replaced Template Section 2)
  - Development Workflow & Quality Gates (replaced Template Section 3)
- Removed sections: None
- Dependent templates status:
  - .specify/templates/plan-template.md, spec-template.md, and tasks-template.md read this
    constitution dynamically at runtime; no template files were modified.
- Follow-up TODOs:
  - No constitution placeholders were deferred.
  - Out-of-scope repository alignment note: the current initial scaffold uses `src/csv_merge_tool/`
    (referenced by `pyproject.toml` script entry point) and does not yet have a `tests/` directory.
    Aligning the package path to `src/csv_merge/` and adding `tests/` must be performed in a
    separate repository setup/implementation step.
  - Remove this temporary Sync Impact Report HTML comment before committing the constitution.
-->

# CSV Merge Tool Constitution

## Core Principles

### I. Configuration-Driven Domain Logic (NON-NEGOTIABLE)

Application code MUST NOT hardcode domain-specific column names, field schemas, data types, or
merge precedence rules. Every input/output schema, column type definition, key mapping, and
conflict or precedence resolution rule MUST be defined in external configuration files and loaded
at runtime.

**Rationale**: Keeping domain rules strictly outside source code ensures the merge engine remains
reusable across datasets and business domains without code modifications when schemas or
precedence policies change.

### II. Strict Static Typing & Structured Models

All Python code across `src/csv_merge/` and `tests/` MUST use strict type hints for function
parameters, return types, class attributes, and module boundaries; untyped functions are
prohibited and `Any` MUST NOT be used unless strictly required at an external serialization
boundary with explicit validation. Configuration schemas, column specifications, precedence rules,
and domain data structures MUST be modeled with standard library `dataclasses` or Pydantic models
rather than unstructured dictionaries or tuples.

**Rationale**: Strong typing and explicit models surface contract mismatches early, make
configuration parsing and validation deterministic, and keep internal APIs self-documenting.

### III. Python 3.13 & Exclusive uv Toolchain

The project MUST target Python 3.13 (`requires-python = ">=3.13"`, `.python-version` set to
`3.13`) and manage all virtual environments, dependency resolution, lockfiles (`uv.lock`), builds,
and command execution exclusively via `uv`. Alternative Python environment or package managers
(such as `pip`, `poetry`, `pipenv`, or `conda`) MUST NOT be introduced or documented as supported
workflows.

**Rationale**: Standardizing on Python 3.13 and `uv` guarantees reproducible environments, fast
deterministic installs, and a single consistent workflow across local development and CI.

### IV. Standardized Source & Test Layout

All application source code MUST reside under `src/csv_merge/`, and all unit tests MUST reside
under `tests/`. Application modules MUST NOT be placed at the repository root or outside
`src/csv_merge/`. Test files under `tests/` MUST mirror the structure of `src/csv_merge/` and
remain isolated from runtime package distribution.

**Rationale**: Enforcing a clean `src/` package layout prevents accidental imports from the working
directory and establishes unambiguous boundaries between production code and test suites.

### V. Mandatory Verification Gates (NON-NEGOTIABLE)

Every change MUST pass static linting with `uv run ruff check .` and unit test execution with
`uv run pytest` with zero errors before being committed, merged, or declared complete. Every new
feature, configuration rule, or bug fix MUST be accompanied by unit tests under `tests/`.

**Rationale**: Automated lint and test gates prevent regressions, maintain uniform code quality,
and verify constitution compliance on every increment.

## Technical Stack & Project Structure

- **Language & Runtime**: Python 3.13 (`.python-version` pinned to `3.13`; `pyproject.toml`
  declares `requires-python = ">=3.13"`).
- **Package & Environment Management**: `uv` exclusively (`pyproject.toml`, `uv.lock`, and
  `uv_build` build backend). All project commands, linters, and test runners MUST execute via
  `uv run`.
- **Canonical Directory Layout**:
  - `src/csv_merge/`: All runtime application packages, CLI entry points, configuration loaders,
    typed models, and merge engine logic.
  - `tests/`: All unit and integration test suites using synthetic/fixture configurations rather
    than hardcoded domain schemas.
- **Data Modeling & Validation**: Strict Python 3.13 type annotations throughout; `dataclasses` or
  Pydantic models for all configuration definitions, schema metadata, precedence policies, and
  structured runtime records.
- **Configuration Boundary**: Configuration files are the sole source of truth for column names,
  data types, validation constraints, and merge precedence rules. Invalid configurations MUST fail
  fast with clear validation errors when parsed into typed models.

## Development Workflow & Quality Gates

- **Required Verification Commands**: Before any commit, pull request, or task sign-off,
  contributors MUST run and pass both gates with exit code `0`:
  1. `uv run ruff check .`
  2. `uv run pytest`
- **Test Coverage Expectations**: Changes to `src/csv_merge/` MUST include unit tests in `tests/`
  covering valid merge scenarios, precedence tie-breaking/override behavior, type handling, and
  invalid configuration failure modes.
- **Review Checklist**: Every specification, implementation plan, and code review MUST verify:
  - Zero hardcoded domain-specific column names, types, or precedence rules in `src/csv_merge/`.
  - Complete strict type annotations and `dataclasses`/Pydantic model usage.
  - Exclusive `uv` usage and adherence to `src/csv_merge/` and `tests/` boundaries.
  - Clean passes of `uv run ruff check .` and `uv run pytest`.

## Governance

- **Supremacy**: This constitution supersedes all other repository practices, ad-hoc scripts, or
  initial scaffolding defaults. Where existing repository scaffolding conflicts with this
  constitution, the scaffolding MUST be brought into compliance as part of project setup before
  feature work proceeds.
- **Amendment Procedure**: Proposed amendments MUST be documented as edits to
  `.specify/memory/constitution.md` with an explicit rationale, impact review against active
  specifications and plans, and maintainer approval prior to merge.
- **Versioning Policy**: Constitution versions follow Semantic Versioning (`MAJOR.MINOR.PATCH`):
  - `MAJOR`: Backward-incompatible removals or redefinitions of existing principles or
    non-negotiable rules.
  - `MINOR`: New principles or sections added, or materially expanded governance guidance.
  - `PATCH`: Clarifications, wording refinements, or typo fixes without semantic changes.
- **Compliance Review**: Every `/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, and pull
  request review MUST include a Constitution Check confirming adherence to Principles I through V.
  Any temporary exception MUST be documented with explicit justification and a tracked remediation
  task.

**Version**: 1.0.0 | **Ratified**: 2026-11-23 | **Last Amended**: 2026-11-23
