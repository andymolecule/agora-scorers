# Agora Official Scorers

Public source for the official Agora scorer containers. These Docker images score solver submissions deterministically for the [Agora](https://github.com/andymolecule/Agora) on-chain science bounty platform.

## Scorers

| Image | Template | What it scores |
|-------|----------|---------------|
| `gems-tabular-scorer` | `official_table_metric_v1` | CSV table metrics (R2, RMSE, MAE, Pearson, Spearman, accuracy, F1) |
| `gems-ranking-scorer` | `official_ranking_metric_v1` | Ranking quality (NDCG) |
| `gems-match-scorer` | `official_exact_match_v1`, `official_structured_record_v1` | Exact match + structured record validation |
| `gems-code-executor` | `official_code_execution_v1` | Python code execution (pass rate) |

## Design

Each scorer is a standalone Python container:

- `Dockerfile` — `FROM python:3.11-slim`, installs deps, copies `score.py`
- `score.py` — reads `/input`, writes `/output/score.json`
- `test_score.py` — regression tests against known fixtures

Containers run sandboxed: `--network=none`, `--read-only`, `--cap-drop=ALL`, non-root.

## Pull

Images are published to GHCR under `ghcr.io/andymolecule/`:

```bash
docker pull ghcr.io/andymolecule/gems-tabular-scorer:v1
docker pull ghcr.io/andymolecule/gems-ranking-scorer:v1
docker pull ghcr.io/andymolecule/gems-match-scorer:v1
docker pull ghcr.io/andymolecule/gems-code-executor:v1
```

## Test locally

```bash
python3 gems-tabular-scorer/test_score.py
python3 gems-ranking-scorer/test_score.py
python3 gems-match-scorer/test_score.py
python3 gems-code-executor/test_score.py
```

## CI

The `Publish Scorers` workflow builds multi-arch images (`linux/amd64` + `linux/arm64`) and pushes to GHCR on every push to `main` that touches scorer files.

## License

See individual scorer files for details.
