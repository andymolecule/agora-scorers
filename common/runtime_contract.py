import json
from pathlib import Path
from typing import Any, Callable

SCORER_RUNTIME_CONFIG_FILE_NAME = "agora-runtime.json"
SCORER_EVALUATION_BUNDLE_FILE_NAME = "evaluation"
SCORER_SUBMISSION_FILE_NAME = "submission"

_COVERAGE_POLICIES = {"reject", "ignore", "penalize"}
_DUPLICATE_ID_POLICIES = {"reject", "ignore"}
_INVALID_VALUE_POLICIES = {"reject", "ignore"}


def load_runtime_contract(
    *,
    input_dir: Path,
    fail_runtime: Callable[[str], None],
    require_evaluation_bundle: bool = True,
) -> dict[str, Any]:
    runtime_config_path = input_dir / SCORER_RUNTIME_CONFIG_FILE_NAME
    if not runtime_config_path.exists():
        fail_runtime(f"Missing required file: {runtime_config_path}")

    try:
        runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail_runtime(
            f"Invalid runtime config JSON at {runtime_config_path}: {error.msg}"
        )

    if runtime_config.get("version") != "v2":
        fail_runtime("Unsupported runtime config version. Expected version=v2.")

    mount = runtime_config.get("mount")
    if not isinstance(mount, dict):
        fail_runtime("Runtime config mount must be an object.")

    submission_file_name = mount.get("submission_file_name")
    if submission_file_name != SCORER_SUBMISSION_FILE_NAME:
        fail_runtime(
            f"Runtime config submission_file_name must be {SCORER_SUBMISSION_FILE_NAME}."
        )

    evaluation_bundle_name = mount.get("evaluation_bundle_name")
    if require_evaluation_bundle:
        if evaluation_bundle_name != SCORER_EVALUATION_BUNDLE_FILE_NAME:
            fail_runtime(
                f"Runtime config evaluation_bundle_name must be {SCORER_EVALUATION_BUNDLE_FILE_NAME}."
            )
    elif evaluation_bundle_name not in (None, SCORER_EVALUATION_BUNDLE_FILE_NAME):
        fail_runtime(
            f"Runtime config evaluation_bundle_name must be omitted or set to {SCORER_EVALUATION_BUNDLE_FILE_NAME}."
        )

    policies = runtime_config.get("policies", {})
    if not isinstance(policies, dict):
        fail_runtime("Runtime config policies must be an object.")

    coverage_policy = policies.get("coverage_policy", "ignore")
    duplicate_id_policy = policies.get("duplicate_id_policy", "ignore")
    invalid_value_policy = policies.get("invalid_value_policy", "ignore")
    if coverage_policy not in _COVERAGE_POLICIES:
        fail_runtime("Unsupported coverage_policy in runtime config.")
    if duplicate_id_policy not in _DUPLICATE_ID_POLICIES:
        fail_runtime("Unsupported duplicate_id_policy in runtime config.")
    if invalid_value_policy not in _INVALID_VALUE_POLICIES:
        fail_runtime("Unsupported invalid_value_policy in runtime config.")

    return {
        "metric": runtime_config.get("metric", "custom"),
        "submission_contract": runtime_config.get("submission_contract"),
        "evaluation_contract": runtime_config.get("evaluation_contract"),
        "policies": {
            "coverage_policy": coverage_policy,
            "duplicate_id_policy": duplicate_id_policy,
            "invalid_value_policy": invalid_value_policy,
        },
        "submission_path": input_dir / SCORER_SUBMISSION_FILE_NAME,
        "evaluation_path": input_dir / SCORER_EVALUATION_BUNDLE_FILE_NAME
        if require_evaluation_bundle
        else None,
    }
