"""
Weighted composite Agora external scorer example.

This example shows a broad custom scorer pattern:

- multiple evaluation artifacts
- multiple submission artifacts
- deterministic weighted aggregation
- structured score.json details suitable for scorer_result_schema
"""

import json
import math
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


def require_weight_mapping(
    payload: dict,
    *,
    field_name: str,
    runtime_error: bool,
) -> dict[str, float]:
    value = payload.get(field_name)
    if not isinstance(value, dict) or not value:
        message = f"Weight config must declare a non-empty {field_name} object."
        if runtime_error:
            fail_runtime(message)
        reject_submission(message)

    normalized: dict[str, float] = {}
    for key, weight in value.items():
        if not isinstance(key, str) or not key:
            message = f"Weight config {field_name} keys must be non-empty strings."
            if runtime_error:
                fail_runtime(message)
            reject_submission(message)
        if not isinstance(weight, (int, float)) or not math.isfinite(float(weight)):
            message = f"Weight config {field_name}.{key} must be numeric."
            if runtime_error:
                fail_runtime(message)
            reject_submission(message)
        normalized[key] = float(weight)
    return normalized


def require_numeric_metric(
    payload: dict,
    *,
    field_name: str,
    label: str,
) -> float:
    value = payload.get(field_name)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        reject_submission(f"{label} must declare numeric {field_name}.")
    return float(value)


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def main() -> None:
    runtime_manifest = load_runtime_manifest(
        input_dir=INPUT_DIR,
        fail_runtime=fail_runtime,
    )
    if runtime_manifest["runtime_profile"]["kind"] != "external":
        fail_runtime(
            "This example scorer requires runtime_profile.kind=external. Next step: use an external runtime manifest and retry."
        )

    weights_artifact = resolve_artifact_by_role(
        runtime_manifest,
        lane="evaluation",
        role="weights",
        fail_runtime=fail_runtime,
    )
    policy_artifact = resolve_artifact_by_role(
        runtime_manifest,
        lane="evaluation",
        role="policy",
        fail_runtime=fail_runtime,
    )
    metrics_artifact = resolve_artifact_by_role(
        runtime_manifest,
        lane="submission",
        role="metrics",
        fail_runtime=fail_runtime,
    )
    manifest_artifact = resolve_artifact_by_role(
        runtime_manifest,
        lane="submission",
        role="manifest",
        fail_runtime=fail_runtime,
    )
    if weights_artifact["path"] is None or policy_artifact["path"] is None:
        fail_runtime("Missing required evaluation artifacts for weighted composite scorer.")
    if metrics_artifact["path"] is None or manifest_artifact["path"] is None:
        reject_submission("Missing required submission artifacts for weighted composite scorer.")

    weights_config = read_json(
        weights_artifact["path"],
        label="Weights config",
        runtime_error=True,
    )
    policy_config = read_json(
        policy_artifact["path"],
        label="Policy config",
        runtime_error=True,
    )
    metrics = read_json(
        metrics_artifact["path"],
        label="Metrics submission",
        runtime_error=False,
    )
    manifest = read_json(
        manifest_artifact["path"],
        label="Manifest submission",
        runtime_error=False,
    )

    dimension_weights = require_weight_mapping(
        weights_config,
        field_name="dimensions",
        runtime_error=True,
    )
    bonus_weights = require_weight_mapping(
        weights_config,
        field_name="bonuses",
        runtime_error=True,
    )
    penalty_weights = require_weight_mapping(
        weights_config,
        field_name="penalties",
        runtime_error=True,
    )

    required_submission_roles = policy_config.get("required_submission_roles")
    if required_submission_roles != ["metrics", "manifest"]:
        fail_runtime(
            "Policy config must declare required_submission_roles=[\"metrics\",\"manifest\"]."
        )
    candidate_count_field = policy_config.get("candidate_count_field")
    if not isinstance(candidate_count_field, str) or not candidate_count_field:
        fail_runtime("Policy config must declare candidate_count_field.")

    weighted_total = 0.0
    details: dict[str, object] = {
        "aggregation": "weighted_composite",
        "weights": {
            **dimension_weights,
            **bonus_weights,
            **penalty_weights,
        },
    }

    for key, weight in dimension_weights.items():
        value = require_numeric_metric(metrics, field_name=key, label="Metrics submission")
        details[key] = value
        weighted_total += weight * value

    for key, weight in bonus_weights.items():
        value = require_numeric_metric(metrics, field_name=key, label="Metrics submission")
        details[key] = value
        weighted_total += weight * value

    for key, weight in penalty_weights.items():
        value = require_numeric_metric(metrics, field_name=key, label="Metrics submission")
        details[key] = value
        weighted_total -= weight * abs(value)

    candidates_scored = manifest.get(candidate_count_field)
    if not isinstance(candidates_scored, int) or candidates_scored < 0:
        reject_submission(
            f"Manifest submission must declare integer {candidate_count_field}."
        )
    passing_field = "candidates_passing_threshold"
    candidates_passing_threshold = manifest.get(passing_field)
    if (
        not isinstance(candidates_passing_threshold, int)
        or candidates_passing_threshold < 0
    ):
        reject_submission(f"Manifest submission must declare integer {passing_field}.")

    details[candidate_count_field] = candidates_scored
    details[passing_field] = candidates_passing_threshold

    final_score = clamp_score(weighted_total)
    write_result(
        {
            "ok": True,
            "score": final_score,
            "details": details,
        }
    )


if __name__ == "__main__":
    main()
