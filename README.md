# Agora Scorers

Public source for the official scorer images used by
[Agora](https://github.com/andymolecule/Agora), plus the reference kit for
building deterministic external scorers against the same runtime contract.

This repo owns:

- scorer container source code
- regression tests for each scorer
- the GHCR publication workflow
- scorer-repo documentation
- shared scorer-side runtime helpers
- external scorer reference examples

It does not own:

- authoring flows
- challenge taxonomy
- official scorer selection in Agora
- preset discovery
- worker orchestration
- proof publication
- on-chain settlement

Those live in the main Agora repo.

## Runtime Contract

Every scorer in this repo now speaks the same canonical Agora runtime contract:

- `/input/runtime-manifest.json`
- `/input/evaluation/<role>/<filename>`
- `/input/submission/<role>/<filename>`
- `/output/score.json`

Official scorers require `runtime-manifest.json` to declare:

- `scorer.kind=official`
- the concrete official scorer `id` and pinned `image`
- the scorer-owned `relation_plan`

They score one or more concrete artifact relations, then aggregate
relation-level scores through the aggregation mode declared by that plan.

Scorers do not support retired runtime layouts or compatibility shims.

External scorers use the same mounted layout and score output shape, but do not
require `relation_plan`. They should reuse the shared runtime loader in
`common/runtime_manifest.py` instead of re-parsing mounted files ad hoc.

## Scorers

There are four scorer images:

| Container | Official scorer(s) in Agora | What it judges | Current metric(s) |
| --- | --- | --- | --- |
| `agora-scorer-table-metric` | `official_table_metric` | CSV predictions against hidden CSV truth | `r2`, `rmse`, `mae`, `pearson`, `spearman`, `accuracy`, `f1` |
| `agora-scorer-ranking-metric` | `official_ranking_metric` | ranked CSV outputs against hidden relevance labels | `ndcg`, `spearman` |
| `agora-scorer-artifact-compare` | `official_exact_match`, `official_structured_validation` | exact file match and structured JSON validation | `exact_match`, `validation_score` |
| `agora-scorer-python-execution` | `official_python_execution` | Python code run against a hidden deterministic harness | `pass_rate` |

## Repo Layout

```text
common/                        shared scorer runtime helpers
agora-scorer-table-metric/   CSV table metrics
agora-scorer-ranking-metric/   ranking metrics
agora-scorer-artifact-compare/     exact-match and structured-record validation
agora-scorer-python-execution/    deterministic code execution
examples/                      external scorer templates
docs/                          extension notes
scripts/                       local test helpers and container guards
```

Each scorer directory stays intentionally small:

- `Dockerfile`
- `score.py`
- `test_score.py`

Shared runtime helpers:

- `common/runtime_manifest.py`
  - generic manifest parsing for both `official` and `external` scorer kinds
  - role-bound artifact resolution from `/input/evaluation/*` and `/input/submission/*`
- `common/official_relation_plan.py`
  - official-only relation template matching and aggregation
- `common/runtime_test_support.py`
  - fixture helpers for official and external scorer tests

## Code-Only Policy

Official scorer images must stay public and code-only. This repo must not ship:

- hidden evaluation labels
- private reference outputs
- benchmark datasets
- harness payloads
- large embedded assets

Those belong in the mounted evaluation artifact, not in the image. The guard in [`scripts/check-scorer-containers.mjs`](./scripts/check-scorer-containers.mjs) enforces that policy.

## Published Images

Images publish to `ghcr.io/andymolecule/`.

Convenience tags:

```bash
docker pull ghcr.io/andymolecule/agora-scorer-table-metric:latest
docker pull ghcr.io/andymolecule/agora-scorer-ranking-metric:latest
docker pull ghcr.io/andymolecule/agora-scorer-artifact-compare:latest
docker pull ghcr.io/andymolecule/agora-scorer-python-execution:latest
```

Agora itself binds official scorers to immutable digests, not floating tags.

## Local Development

Run all scorer regression tests:

```bash
bash scripts/run-scorer-tests.sh
```

Run one scorer directly:

```bash
python3 agora-scorer-table-metric/test_score.py
python3 agora-scorer-ranking-metric/test_score.py
python3 agora-scorer-artifact-compare/test_score.py
python3 agora-scorer-python-execution/test_score.py
python3 common/test_runtime_manifest.py
python3 examples/external-minimal/test_score.py
python3 examples/external-weighted-composite/test_score.py
```

## External Scorer Reference Kit

If you are building a custom scorer image for Agora, start here:

1. Use `common/runtime_manifest.py` for the canonical mounted runtime contract.
2. Use `common/runtime_test_support.py` to build valid local fixtures.
3. Copy one of the external examples under `examples/`.
4. Keep your scorer deterministic and write one `/output/score.json`.

Reference examples:

- `examples/external-minimal`
  - smallest useful external scorer skeleton
  - one evaluation role, one submission role
- `examples/external-weighted-composite`
  - multi-artifact external scorer
  - weighted composite scoring with structured `details`

## CI And Publication

The publish workflow:

- runs scorer regression tests
- checks that scorer images remain code-only
- builds multi-arch images for `linux/amd64` and `linux/arm64`
- publishes `:latest` and `:sha-<git-commit>` tags to GHCR

The Docker build context is the scorer repo root so the shared runtime loader in `common/` is available to every scorer image.

## Adding A New Official Scorer

Normal path:

1. Add or update scorer code in this repo.
2. Publish the scorer image.
3. Register the scorer and any authoring preset in the main Agora repo.
4. Add any new shared artifact schema in the main Agora repo if needed.
5. Add tests in both repos.

## Related Links

- [Agora main repo](https://github.com/andymolecule/Agora)
- [Official scorer registry](https://github.com/andymolecule/Agora/blob/main/packages/common/src/official-scorer-registry.ts)
- [Authoring preset registry](https://github.com/andymolecule/Agora/blob/main/packages/common/src/authoring-preset-registry.ts)
- [Agora protocol](https://github.com/andymolecule/Agora/blob/main/docs/protocol.md)
- [Scoring extension guide](./docs/scoring-engines.md)
