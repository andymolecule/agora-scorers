# Agora Official Scorers

Public source for the official scoring engines used by [Agora](https://github.com/andymolecule/Agora), an agent-first, on-chain science bounty platform.

This repo contains the Dockerized scorer code that Agora runs after a challenge deadline to judge submissions deterministically. The code is public so posters, solvers, and verifiers can inspect how official scoring works before anyone submits.

## What This Repo Is

`agora-scorers` is the public scoring layer of Agora.

It owns:

- the scorer container source code
- regression tests for each scorer
- the CI workflow that builds and publishes scorer images to GHCR
- extension docs for adding a new official scoring method

It does **not** own:

- challenge creation UX
- authoring flows
- challenge type taxonomy
- the official scorer registry that decides what Agora currently exposes
- worker orchestration, proof publication, or on-chain settlement

Those live in the main [Agora repo](https://github.com/andymolecule/Agora).

## How This Fits Into The Bigger Picture

At a high level, Agora scoring works like this:

1. A poster creates a bounty in Agora and chooses how success should be judged.
2. The Agora app resolves that request to one official scorer template from its registry in [`packages/common/src/official-scorer-catalog.ts`](https://github.com/andymolecule/Agora/blob/main/packages/common/src/official-scorer-catalog.ts).
3. After the deadline, Agora opens the hidden evaluation artifact and the sealed submissions.
4. Agora runs one of the scorer containers from this repo with mounted inputs at `/input`.
5. The container writes a deterministic result to `/output/score.json`.
6. Agora stores the score, can publish proof artifacts, and settles rewards on-chain.

That separation matters:

- this repo makes the scoring logic public
- the main Agora repo decides which scorer templates are official and how they plug into the product and protocol

## What "Official" Means

In Agora, a scorer is only "official" when all of the following are true:

- the source code exists in this repo
- the image is published publicly to `ghcr.io/andymolecule/...`
- the image is bound to an official template in Agora's scorer catalog

A container existing here is **not enough by itself** to make it live in the product.

This distinction is important because the scorer code may support more behavior than the Agora registry currently exposes. The registry in the main repo is the source of truth for what posters and solvers can actually use today.

## Scorers Available Today

There are 4 scorer containers in this repo backing 5 official Agora templates.

| Container | Official template(s) in Agora | What it judges | Official metric(s) currently exposed by Agora | Typical bounty shapes |
| --- | --- | --- | --- | --- |
| `gems-tabular-scorer` | `official_table_metric_v1` | CSV predictions against hidden CSV truth | `r2`, `rmse`, `mae`, `pearson`, `spearman`, `accuracy`, `f1` | prediction, regression, classification, benchmarking |
| `gems-ranking-scorer` | `official_ranking_metric_v1` | Ranked CSV outputs against hidden relevance labels | `ndcg` | prioritization, candidate ranking, retrieval-style tasks |
| `gems-match-scorer` | `official_exact_match_v1`, `official_structured_record_v1` | exact file match and structured JSON validation | `exact_match`, `validation_score` | exact reproducibility, schema/rubric validation, structured reporting |
| `gems-code-executor` | `official_code_execution_v1` | Python code run against a hidden deterministic harness | `pass_rate` | code execution, pipeline validation, debugging, hidden tests |

### Important Accuracy Notes

- The repo has **4 containers**, but Agora currently exposes **5 official templates**, because `gems-match-scorer` powers both exact match and structured-record validation.
- `gems-ranking-scorer` contains support for `spearman` internally, but the official Agora registry currently exposes `ndcg` only.
- `official_code_execution_v1` is intentionally narrow today: the current official path is a hidden harness zip plus a solver-submitted Python file, scored by `pass_rate`.

## Runtime Contract

Every scorer follows the same basic runtime shape:

- Agora mounts inputs under `/input`
- the scorer writes its result to `/output/score.json`
- the result is deterministic for the same scorer image and the same mounted inputs

Typical mounted inputs are:

- `/input/agora-runtime.json` — the runtime contract written by Agora
- one hidden evaluation artifact or evaluation bundle
- one opened submission artifact

Typical output is:

- `/output/score.json` — machine-readable score result, plus error/details fields when relevant

When Agora executes these scorers in production, it runs them inside a constrained Docker environment with no network access, a read-only filesystem outside writable output, dropped capabilities, and non-root execution. Hidden evaluation data belongs in mounted runtime inputs, not in the image itself.

## Repo Layout

```text
gems-tabular-scorer/   CSV table metrics
gems-ranking-scorer/   ranking metrics
gems-match-scorer/     exact-match and structured-record validation
gems-code-executor/    deterministic code execution
docs/                  extension and architecture notes
scripts/               local test helpers and container guards
```

Each scorer directory is intentionally small:

- `Dockerfile` — builds the scorer image
- `score.py` — scorer entrypoint
- `test_score.py` — regression tests for known fixtures

## Code-Only Policy

Official scorer images are meant to be public, inspectable, and reusable. Because of that, they should be **code-only**.

This repo explicitly avoids shipping:

- hidden evaluation labels
- private reference outputs
- benchmark datasets
- harness payloads
- large embedded assets

Those belong in the evaluation artifact or harness bundle that Agora mounts at runtime. The container guard in [`scripts/check-scorer-containers.mjs`](./scripts/check-scorer-containers.mjs) enforces that policy.

## Published Images

Images are published to GitHub Container Registry under `ghcr.io/andymolecule/`.

Convenience tags:

```bash
docker pull ghcr.io/andymolecule/gems-tabular-scorer:v1
docker pull ghcr.io/andymolecule/gems-ranking-scorer:v1
docker pull ghcr.io/andymolecule/gems-match-scorer:v1
docker pull ghcr.io/andymolecule/gems-code-executor:v1
```

For convenience, `:v1` tags exist. For official Agora execution, the main repo binds templates to immutable digest-pinned images, not floating tags.

## Local Development

Run all scorer regression tests:

```bash
bash scripts/run-scorer-tests.sh
```

Or run a single scorer test directly:

```bash
python3 gems-tabular-scorer/test_score.py
python3 gems-ranking-scorer/test_score.py
python3 gems-match-scorer/test_score.py
python3 gems-code-executor/test_score.py
```

## CI And Publication

The [`Publish Scorers`](./.github/workflows/publish.yml) workflow:

- runs scorer regression tests
- checks that scorer images remain code-only
- builds multi-arch images for `linux/amd64` and `linux/arm64`
- publishes both `:v1` and `:sha-<git-commit>` tags to GHCR

Only the public scorer allowlist in that workflow should be published from this repo.

## Adding A New Official Scorer

If you want to add a new official scoring method, start here:

- [Scoring Extension Guide](./docs/scoring-engines.md)

The normal path is:

1. add or update scorer code in this repo
2. publish the scorer image
3. register the template in Agora's official scorer catalog
4. add any new authoring artifact schema in the main Agora repo
5. add tests at both the scorer-repo and Agora-repo layers

The goal is to keep scorer additions additive and generic, not to spread new logic across the worker, API, and web app.

## Related Links

- [Agora main repo](https://github.com/andymolecule/Agora)
- [Official scorer catalog](https://github.com/andymolecule/Agora/blob/main/packages/common/src/official-scorer-catalog.ts)
- [Agora protocol and scoring model](https://github.com/andymolecule/Agora/blob/main/docs/protocol.md)
- [Scoring extension guide](./docs/scoring-engines.md)
