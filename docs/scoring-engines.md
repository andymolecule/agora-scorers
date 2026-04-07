# Scoring Extension Guide

## Purpose

How to extend the Agora scoring runtime without spreading logic across the
worker, API, and web app.

This repo targets one canonical scorer runtime contract only:

- `/input/runtime-manifest.json`
- `/input/evaluation/<role>/<filename>`
- `/input/submission/<role>/<filename>`
- `/output/score.json`

For official images in this repo, `runtime-manifest.json` must include:

- `scorer.kind=official`
- the official scorer `id`
- the pinned scorer `image`
- `relation_plan`

For external scorer images, `runtime-manifest.json` still mounts the same
artifacts and scoring metadata, but `relation_plan` is optional. External
scorers should use the generic runtime loader and implement their own
deterministic aggregation internally.

## Boundary

Agora scoring stays clean when these responsibilities remain separate:

1. `packages/common/src/official-scorer-registry.ts`
   - owns official scorer image identity and runtime limits
2. `packages/common/src/authoring-preset-registry.ts`
   - owns guided preset discovery for authoring
3. `packages/common/src/authoring-artifact-schemas.ts`
   - owns machine-readable uploaded artifact schemas
4. `packages/scorer/src/pipeline.ts`
   - stages files, writes `runtime-manifest.json`, runs Docker

This scorer repo should only implement the public scorer code, external scorer
examples, and local tests. It should not assume product routing or authoring
behavior beyond the runtime contract above.

## File Map

### `common/runtime_manifest.py`

Shared scorer-side runtime loader for both official and external scorers.

It owns:

- parsing `/input/runtime-manifest.json`
- resolving role-bound staged artifact paths
- validating scorer metadata, metric, artifact slots, and policies

If the mounted runtime contract changes, update this file first and port all
scorers in the same cut.

### `common/official_relation_plan.py`

Official-only relation-plan loader and aggregator.

It owns:

- validating `relation_plan`
- matching repeated relation declarations to official scorer templates
- resolving relation-level artifact sets
- aggregating repeated relation scores

External scorers should not import this module.

### `common/runtime_test_support.py`

Shared local fixture helpers.

It owns:

- staged artifact fixtures for both `official` and `external` scorers
- runtime manifest writers for local tests
- canonical score output readers for regression fixtures

### `agora-scorer-*/score.py`

Each official scorer entrypoint owns only scorer-specific logic:

- metric validation
- submission/evaluation contract validation
- deterministic comparison or execution
- writing `/output/score.json`

Do not re-parse runtime config differently in each scorer. Keep the shared
runtime loader as the one scorer-side protocol owner.

### `examples/external-*`

Executable external scorer templates.

These examples show the supported external scorer development path:

- reuse `common/runtime_manifest.py`
- stage local fixtures with `common/runtime_test_support.py`
- implement deterministic custom logic
- write one `/output/score.json`

### `agora-scorer-*/test_score.py`

Each official scorer test file should prove:

- canonical runtime manifest succeeds
- invalid runtime manifest kind fails loudly
- missing `relation_plan` fails loudly
- repeated relation execution aggregates correctly
- missing required scorer relation fails loudly

These are protocol regression tests, not dataset fixtures.

External example tests should prove:

- `scorer.kind=external` loads without `relation_plan`
- staged evaluation/submission artifacts resolve by role
- example score output is deterministic
- bad submission input is rejected without masquerading as runtime failure

## Adding A New Official Scorer

1. Add the scorer directory in this repo.
2. Reuse `common/runtime_manifest.py` and `common/official_relation_plan.py`.
3. Add `score.py` and `test_score.py`.
4. Add a Dockerfile that builds from the scorer repo root.
5. Publish the image.
6. Register the scorer and any preset in the main Agora repo.

## Building A Custom External Scorer

1. Start from `examples/external-minimal` or
   `examples/external-weighted-composite`.
2. Reuse `common/runtime_manifest.py`.
3. Stage local fixtures with `common/runtime_test_support.py`.
4. Keep all scoring deterministic and local to the container.
5. Write one `/output/score.json` with a single scalar `score` plus structured
   `details`.

## Design Rules

- Keep images code-only.
- Keep scorer logic deterministic.
- Keep runtime parsing centralized.
- Keep authoring concerns out of this repo.
- Prefer one explicit contract over compatibility shims.
- Keep relation aggregation owned by `relation_plan`, not ad hoc scorer code.
- Keep external scorer examples broad by runtime primitive, not by one
  challenge-specific domain.

## Release Rule

If the runtime contract changes, cut straight to the new contract and roll the
official scorer digests forward with the new scorer images. Do not keep
parallel runtime protocols unless there is an explicit migration requirement.
