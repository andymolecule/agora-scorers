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
  python3 gems-tabular-scorer/test_score.py

run_step "Exact-match scorer regression fixture" \
  python3 gems-match-scorer/test_score.py

run_step "Ranking scorer regression fixture" \
  python3 gems-ranking-scorer/test_score.py

run_step "Code executor regression fixture" \
  python3 gems-code-executor/test_score.py
