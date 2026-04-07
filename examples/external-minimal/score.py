"""
Minimal Agora external scorer example.

This example shows the smallest useful external scorer shape:

- load the canonical runtime manifest
- resolve evaluation/submission artifacts by role
- apply deterministic custom logic
- write /output/score.json
"""

import json
import sys
from pathlib import Path

SCORER_REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_DIR = SCORER_REPO_ROOT / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from runtime_manifest import load_runtime_manifest, resolve_artifact_by_role

INPUT_DIR = Path("/input")
OUTPUT_DIR = Path("/output")
OUTPUT_PATH = OUTPUT_DIR / "score.json"


def write_result(payload: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    OUTPUT_PATH.write_text(serialized, encoding="utf-8")


def fail_runtime(message: str) -> None:
    write_result({"ok": False, "score": 0.0, "error": message, "details": {}})
    raise SystemExit(1)


def reject_submission(message: str, details: dict | None = None) -> None:
    write_result(
        {
            "ok": False,
            "score": 0.0,
            "error": message,
            "details": details or {},
        }
    )
    raise SystemExit(0)


def read_json(path: Path, *, label: str, runtime_error: bool) -> dict:
    if not path.exists():
        message = f"Missing required {label}: {path}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        message = f"{label} is not valid JSON: {error.msg}"
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    if not isinstance(payload, dict):
        message = f"{label} must be a JSON object."
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    return payload


def main() -> None:
    runtime_manifest = load_runtime_manifest(
        input_dir=INPUT_DIR,
        fail_runtime=fail_runtime,
    )
    if runtime_manifest["scorer"]["kind"] != "external":
        fail_runtime(
            "This example scorer requires scorer.kind=external. Next step: use an external runtime manifest and retry."
        )

    rubric_artifact = resolve_artifact_by_role(
        runtime_manifest,
        lane="evaluation",
        role="rubric",
        fail_runtime=fail_runtime,
    )
    submission_artifact = resolve_artifact_by_role(
        runtime_manifest,
        lane="submission",
        role="candidate",
        fail_runtime=fail_runtime,
    )
    if rubric_artifact["path"] is None:
        fail_runtime("Missing required evaluation artifact role rubric.")
    if submission_artifact["path"] is None:
        reject_submission("Missing required submission artifact role candidate.")

    rubric = read_json(rubric_artifact["path"], label="Rubric", runtime_error=True)
    candidate = read_json(
        submission_artifact["path"],
        label="Candidate submission",
        runtime_error=False,
    )

    expected_fields = rubric.get("expected_fields")
    if not isinstance(expected_fields, dict) or not expected_fields:
        fail_runtime("Rubric must declare a non-empty expected_fields object.")

    matched_fields = 0
    missing_fields: list[str] = []
    mismatched_fields: list[str] = []
    for key, expected_value in expected_fields.items():
        if key not in candidate:
            missing_fields.append(key)
            continue
        if candidate[key] != expected_value:
            mismatched_fields.append(key)
            continue
        matched_fields += 1

    evaluated_fields = len(expected_fields)
    correctness_score = (
        matched_fields / evaluated_fields if evaluated_fields > 0 else 1.0
    )
    write_result(
        {
            "ok": True,
            "score": correctness_score,
            "details": {
                "correctness_score": correctness_score,
                "matched_fields": matched_fields,
                "evaluated_fields": evaluated_fields,
                "missing_fields": missing_fields,
                "mismatched_fields": mismatched_fields,
            },
        }
    )


if __name__ == "__main__":
    main()
