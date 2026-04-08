# Scoring Extension Guide

## Purpose

How to extend Agora scoring without spreading execution logic across the API,
worker, and web app.

This repo targets one canonical V2 scorer runtime contract:

- `/input/runtime-manifest.json`
- `/input/evaluation/<role>/<filename>`
- `/input/submission/<role>/<filename>`
- `/input/scoring_assets/<role>/<filename>`
- `/output/score.json`

The official image in this repo is the stable execution envelope. Challenge
variation belongs in staged scoring assets, not in new official image names.

## Boundary

Agora scoring stays clean when these responsibilities remain separate:

1. `packages/common/src/runtime-profile-registry.ts` in the main repo
   - owns official runtime image identity and runtime limits
2. `packages/common/src/authoring-preset-registry.ts` in the main repo
   - owns poster-facing archetype templates
3. `apps/api/src/lib/evaluation-materializer.ts` in the main repo
   - owns compilation from evaluation intent to staged scoring assets
4. `packages/scorer/src/pipeline.ts` in the main repo
   - stages files, writes `runtime-manifest.json`, runs Docker
5. This scorer repo
   - owns the public scorer code, helper SDK, external examples, and local tests

This repo should not assume product routing or poster authoring behavior beyond
the mounted runtime contract above.

## File Map

### `common/runtime_manifest.py`

Shared scorer-side runtime loader for both official and external scorers.

It owns:

- parsing `/input/runtime-manifest.json`
- resolving role-bound staged artifact paths
- resolving staged scoring-asset paths
- validating runtime profile metadata, final score key, and policies

If the mounted runtime contract changes, update this file first and port every
consumer in the same cut.

### `common/runtime_test_support.py`

Shared local fixture helpers.

It owns:

- staged artifact fixtures for official and external runtimes
- staged scoring-asset fixtures
- runtime manifest writers for local tests
- canonical score output readers for regression fixtures

### `agora-scorer-compiled/entrypoint.py`

The official runtime entrypoint.

It owns:

- validating `runtime_profile.kind=official`
- validating the official runtime profile id
- discovering the single staged program scoring asset
- exporting the python-v1 environment seam
- executing the staged compiled program

It must not re-implement challenge-specific scoring logic.

### `agora-scorer-compiled/sdk/agora_runtime.py`

The helper SDK for compiled programs.

It owns:

- stable input/output path helpers
- `load_runtime_context()`
- role-based evaluation/submission/scoring-asset resolution
- deterministic `write_score()`
- submission rejection vs runtime failure helpers

Compiled programs should prefer this helper SDK over re-parsing the runtime
manifest ad hoc.

### `examples/external-*`

Executable external scorer templates.

These examples show the supported external scorer development path:

- reuse `common/runtime_manifest.py`
- stage local fixtures with `common/runtime_test_support.py`
- implement deterministic custom logic
- write one `/output/score.json`

### `agora-scorer-compiled/test_score.py`

The official runtime regression test.

It should prove:

- canonical official runtime manifest succeeds
- missing staged program asset fails loudly
- external runtime manifests are rejected by the official image
- staged compiled programs can import the helper SDK
- compiled programs can reject a submission without masquerading as runtime failure

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
- Keep challenge semantics out of this repo.
- Keep one official image unless the dependency envelope changes materially.
- Keep the compiled-program ABI explicit and stable.
- Keep external examples broad by runtime primitive, not by one challenge domain.

## Release Rule

If the scorer runtime contract changes, cut straight to the new contract and
roll the official runtime digest forward with the new image. Do not keep
parallel official runtime protocols unless there is an explicit migration
requirement.
