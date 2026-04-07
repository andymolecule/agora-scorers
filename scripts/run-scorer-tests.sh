#!/usr/bin/env bash
set -Eeuo pipefail

current_step=""

trap 'status=$?; if [[ $status -ne 0 && -n "${current_step:-}" ]]; then echo "[scorer:test] FAIL ${current_step}" >&2; fi' ERR

run_step() {
  current_step="$1"
  shift
  echo "[scorer:test] START ${current_step}"
  "$@"
  echo "[scorer:test] PASS ${current_step}"
  current_step=""
}

run_step "Tabular scorer regression fixture" \
  python3 agora-scorer-table-metric/test_score.py

run_step "Exact-match scorer regression fixture" \
  python3 agora-scorer-artifact-compare/test_score.py

run_step "Ranking scorer regression fixture" \
  python3 agora-scorer-ranking-metric/test_score.py

run_step "Code executor regression fixture" \
  python3 agora-scorer-python-execution/test_score.py

run_step "Runtime manifest split fixture" \
  python3 common/test_runtime_manifest.py

run_step "External minimal scorer fixture" \
  python3 examples/external-minimal/test_score.py

run_step "External weighted composite scorer fixture" \
  python3 examples/external-weighted-composite/test_score.py
